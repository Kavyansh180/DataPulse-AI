import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.dataset import DatasetVersion
from app.models.profiling import ProfilingRun, QualityMetric
from app.models.quality_issue import QualityIssue
from app.schemas.ai_analysis import (
    AnalysisRequest,
    LikelyCause,
    Recommendation,
    RootCauseAnalysisResponse,
)
from app.services.profiling_service import ProfilingService
from app.services.comparison_service import ComparisonService
from app.services.llm_provider import (
    LLMProvider,
    get_llm_provider,
    LLMConfigurationError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMProviderError,
    LLMResponseFormatError,
)
from app.api.errors import APIError

logger = logging.getLogger("datapulse.ai_analysis")


class AIAnalysisService:
    """Service orchestrating AI-driven root-cause analysis on completed profiling runs."""

    SYSTEM_PROMPT = (
        "You are DataPulse AI's Lead Data Quality Diagnostics Engine. "
        "Your task is to analyze empirical data quality profiling metrics, anomalies, and issues "
        "and generate an objective, explainable root-cause analysis with actionable remediation recommendations.\n\n"
        "STRICT DIAGNOSTIC RULES:\n"
        "1. GROUNDING: Every finding and recommendation must be grounded strictly in the provided profiling evidence. "
        "Never invent columns, sample values, or metrics that are not in the evidence.\n"
        "2. HYPOTHESES: Clearly distinguish observed empirical facts from possible explanations. "
        "Label all root causes as hypotheses unless definitive evidence is present.\n"
        "3. ACTIONABILITY: Recommend practical, prioritized corrective actions (priority: 'high', 'medium', or 'low') "
        "and cite the exact profiling evidence (e.g., column names, null percentages, outlier counts) justifying each.\n"
        "4. UNCERTAINTIES & LIMITATIONS: Acknowledge diagnostic limitations (e.g., lack of upstream ETL logs, unknown business domain rules).\n"
        "5. OUTPUT FORMAT: Respond ONLY with a valid JSON object matching the requested schema. Do not include markdown code fences or conversational text."
    )

    @classmethod
    def prepare_evidence(cls, run: ProfilingRun, db: Session) -> Dict[str, Any]:
        """Aggregate all empirical profiling evidence, metrics, issues, and historical shifts."""
        dataset_version = run.dataset_version
        dataset = dataset_version.dataset if dataset_version else None

        # 1. Summary stats & component scores
        summary_dict = {}
        if run.summary_stats:
            try:
                summary_dict = json.loads(run.summary_stats)
            except Exception:
                pass

        # 2. Granular metrics & anomalies
        table_metrics = {}
        column_metrics: Dict[str, Dict[str, Any]] = {}
        anomalies = []

        for m in run.metrics:
            if m.column_name is None:
                table_metrics[m.metric_name] = m.metric_value
            else:
                col = m.column_name
                if col not in column_metrics:
                    column_metrics[col] = {}
                column_metrics[col][m.metric_name] = m.metric_value

            if m.is_anomalous:
                anomalies.append({
                    "column": m.column_name or "table_level",
                    "metric": m.metric_name,
                    "value": m.metric_value,
                    "threshold": m.threshold_value,
                    "details": m.details,
                })

        # 3. Quality issues
        issues_list = []
        if dataset_version and dataset_version.quality_issues:
            for issue in dataset_version.quality_issues:
                issues_list.append({
                    "rule_name": issue.rule_name,
                    "severity": issue.severity,
                    "issue_type": issue.issue_type,
                    "description": issue.description,
                    "status": issue.status,
                })

        # 4. Historical comparison (if prior run exists)
        historical_comparison = None
        if dataset:
            prior_run = db.scalar(
                select(ProfilingRun)
                .join(DatasetVersion)
                .where(
                    DatasetVersion.dataset_id == dataset.id,
                    ProfilingRun.id != run.id,
                    ProfilingRun.status == "completed",
                    ProfilingRun.created_at < run.created_at,
                )
                .order_by(ProfilingRun.created_at.desc())
            )
            if prior_run:
                try:
                    comp = ComparisonService.compare_runs(prior_run, run)
                    historical_comparison = {
                        "baseline_run_id": prior_run.id,
                        "previous_quality_score": comp.previous_score,
                        "current_quality_score": comp.current_score,
                        "score_delta": comp.score_change,
                        "schema_compatible": comp.schema_compatible,
                        "added_columns": comp.added_columns,
                        "removed_columns": comp.removed_columns,
                        "metric_changes": comp.metric_changes,
                        "new_issues": comp.new_issues,
                        "resolved_issues": comp.resolved_issues,
                    }
                except Exception as comp_err:
                    logger.warning(f"Could not compute historical run comparison: {comp_err}")

        evidence = {
            "run_id": run.id,
            "dataset_id": dataset.id if dataset else None,
            "dataset_name": dataset.name if dataset else "Unknown",
            "version_tag": dataset_version.version_tag if dataset_version else None,
            "total_rows_profiled": run.total_rows_profiled,
            "quality_score": run.quality_score,
            "component_scores": summary_dict.get("component_scores", {}),
            "penalties": summary_dict.get("penalties", []),
            "score_explanation": summary_dict.get("explanation"),
            "table_metrics": table_metrics,
            "column_metrics": column_metrics,
            "anomalies_detected": anomalies,
            "quality_issues": issues_list,
            "historical_comparison": historical_comparison or "Baseline run (no prior completed profiling run available)",
        }
        return evidence

    @classmethod
    def build_user_prompt(
        cls,
        evidence: Dict[str, Any],
        request_data: Optional[AnalysisRequest] = None,
    ) -> str:
        """Format empirical evidence and schema requirements into the LLM user prompt."""
        evidence_json = json.dumps(evidence, indent=2, default=str)
        context_notes = []

        if request_data:
            if request_data.focus_areas:
                context_notes.append(f"Focus areas requested: {', '.join(request_data.focus_areas)}")
            if request_data.custom_context:
                context_notes.append(f"Additional domain context: {request_data.custom_context}")

        joined_notes = "\n".join(context_notes)
        context_str = f"\nUser Context:\n{joined_notes}\n" if context_notes else ""

        schema_instructions = (
            "You MUST respond with a JSON object conforming to the following structure:\n"
            "{\n"
            '  "overall_assessment": "Concise summary of dataset health and major quality risks.",\n'
            '  "key_findings": ["Observed finding 1 with metric numbers", "Observed finding 2"],\n'
            '  "likely_causes": [\n'
            "    {\n"
            '      "cause": "Hypothesized origin or ETL bug leading to the issue.",\n'
            '      "is_hypothesis": true,\n'
            '      "supporting_evidence": "Profiling evidence backing this hypothesis."\n'
            "    }\n"
            "  ],\n"
            '  "recommendations": [\n'
            "    {\n"
            '      "action": "Specific remediation step for engineering or data owners.",\n'
            '      "priority": "high",\n'
            '      "evidence": "Metric or issue triggering this priority."\n'
            "    }\n"
            "  ],\n"
            '  "limitations": ["Limitation or uncertainty 1", "Limitation 2"]\n'
            "}"
        )

        return (
            f"Please perform a data quality root-cause analysis based on the following empirical evidence:\n\n"
            f"--- PROFILING EVIDENCE ---\n{evidence_json}\n--- END EVIDENCE ---\n"
            f"{context_str}\n"
            f"{schema_instructions}"
        )

    @classmethod
    def analyze_run(
        cls,
        db: Session,
        run_id: int,
        request_data: Optional[AnalysisRequest] = None,
        provider: Optional[LLMProvider] = None,
    ) -> RootCauseAnalysisResponse:
        """Execute end-to-end AI root-cause analysis for a completed profiling run."""
        # 1. Validate profiling run
        run = ProfilingService.get_run_by_id(db, run_id)
        if not run:
            raise APIError(
                status_code=404,
                message=f"Profiling run {run_id} not found.",
                code="NOT_FOUND",
            )

        if run.status != "completed":
            raise APIError(
                status_code=400,
                message=f"Profiling run {run_id} has status '{run.status}'. Only completed runs can be analyzed.",
                code="RUN_NOT_COMPLETED",
            )

        # 2. Gather empirical evidence
        evidence = cls.prepare_evidence(run, db)
        user_prompt = cls.build_user_prompt(evidence, request_data)

        # 3. Retrieve LLM provider
        llm = provider or get_llm_provider()

        # 4. Invoke LLM provider with robust error translation
        try:
            raw_response = llm.generate(prompt=user_prompt, system_prompt=cls.SYSTEM_PROMPT)
        except LLMConfigurationError as err:
            logger.warning(f"AI Root-Cause Analysis called without API key: {err}")
            raise APIError(
                status_code=503,
                message="LLM API key is not configured. Please set LLM_API_KEY in your environment.",
                code="LLM_NOT_CONFIGURED",
            )
        except LLMTimeoutError as err:
            logger.error(f"AI Root-Cause Analysis timed out: {err}")
            raise APIError(
                status_code=504,
                message="LLM provider request timed out.",
                code="LLM_TIMEOUT",
            )
        except LLMRateLimitError as err:
            logger.warning(f"AI Root-Cause Analysis rate-limited: {err}")
            raise APIError(
                status_code=429,
                message="LLM provider rate limit exceeded. Please try again later.",
                code="LLM_RATE_LIMIT",
            )
        except LLMProviderError as err:
            logger.error(f"AI Root-Cause Analysis provider error: {err}")
            raise APIError(
                status_code=502,
                message="LLM provider communication failed.",
                code="LLM_PROVIDER_ERROR",
            )
        except Exception as err:
            logger.exception(f"Unexpected error during AI analysis: {err}")
            raise APIError(
                status_code=500,
                message="An unexpected error occurred during root-cause analysis.",
                code="INTERNAL_SERVER_ERROR",
            )

        # 5. Clean and parse JSON response
        cleaned_json = raw_response.strip()
        if cleaned_json.startswith("```json"):
            cleaned_json = cleaned_json[7:]
        elif cleaned_json.startswith("```"):
            cleaned_json = cleaned_json[3:]
        if cleaned_json.endswith("```"):
            cleaned_json = cleaned_json[:-3]
        cleaned_json = cleaned_json.strip()

        try:
            parsed_data = json.loads(cleaned_json)
            if not isinstance(parsed_data, dict):
                raise ValueError("Parsed JSON is not an object.")
        except Exception as exc:
            logger.error(f"Failed to parse LLM JSON response: {exc}")
            raise APIError(
                status_code=502,
                message="LLM provider returned a malformed or non-JSON response.",
                code="LLM_MALFORMED_RESPONSE",
            )

        # 6. Validate structured response against Pydantic model
        try:
            dataset_version = run.dataset_version
            dataset = dataset_version.dataset if dataset_version else None

            if "overall_assessment" not in parsed_data or not parsed_data["overall_assessment"]:
                raise ValueError("LLM response is missing required field 'overall_assessment'.")

            response_payload = {
                "run_id": run.id,
                "dataset_id": dataset.id if dataset else 0,
                "dataset_name": dataset.name if dataset else None,
                "overall_score": run.quality_score,
                "overall_assessment": parsed_data["overall_assessment"],
                "key_findings": parsed_data.get("key_findings", []),
                "likely_causes": parsed_data.get("likely_causes", []),
                "recommendations": parsed_data.get("recommendations", []),
                "limitations": parsed_data.get("limitations", []),
                "generated_at": datetime.utcnow(),
            }
            return RootCauseAnalysisResponse.model_validate(response_payload)
        except Exception as val_exc:
            logger.error(f"Validation error against RootCauseAnalysisResponse: {val_exc}")
            raise APIError(
                status_code=502,
                message="LLM provider response failed structural schema validation.",
                code="LLM_INVALID_SCHEMA",
            )
