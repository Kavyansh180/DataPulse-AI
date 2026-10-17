"""Sample demonstration data and cached diagnostic reports for recruiter demo.

Provides synthetic dataset loading utilities and pre-recorded AI diagnostic reports
so that evaluators can explore full platform functionality without requiring
cloud storage or third-party LLM API keys.
"""

from pathlib import Path
from typing import Dict, Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CSV_PATH = _PROJECT_ROOT / "sample_data" / "synthetic_customer_orders.csv"


def get_sample_csv_bytes() -> bytes:
    """Read and return synthetic sample CSV bytes."""
    if SAMPLE_CSV_PATH.exists():
        return SAMPLE_CSV_PATH.read_bytes()
    raise FileNotFoundError(f"Sample dataset not found at {SAMPLE_CSV_PATH}")


def get_sample_ai_report(dataset_name: str = "recruiter_demo_ecommerce", run_id: int = 1) -> Dict[str, Any]:
    """Return a realistic, structured AI root-cause analysis report for demonstration.

    Explicitly labeled with is_sample_demo=True to ensure recruiters and evaluators
    know this is a pre-recorded demonstration rather than a live LLM call.
    """
    return {
        "run_id": run_id,
        "dataset_id": 1,
        "dataset_name": dataset_name,
        "overall_score": 72.5,
        "overall_assessment": (
            "DataPulse AI detected data degradation across multiple quality dimensions in the "
            f"'{dataset_name}' dataset. The overall quality score is 72.5/100, driven down by "
            "extreme numerical outliers in order amounts, a 12.9% null rate in customer emails, "
            "untrimmed whitespace anomalies, and duplicate transaction records."
        ),
        "key_findings": [
            "Numerical Outliers: order_amount exhibits extreme values of $850,000 and $1,250,000, exceeding the 99th percentile threshold of $500.",
            "Completeness Defect: 4 out of 31 rows (12.9%) have missing email addresses.",
            "Uniqueness Defect: 1 exact duplicate transaction row detected for customer_id 1001.",
            "Consistency Defect: Column 'name' and 'status' contain leading and trailing whitespace padding.",
        ],
        "likely_causes": [
            {
                "cause": "Currency multiplier mismatch or simulated test load injected into production transaction queue.",
                "is_hypothesis": True,
                "supporting_evidence": (
                    "Extreme order amounts ($850,000 and $1,250,000) diverge by over 3 orders of magnitude from median ($95.00), "
                    "matching typical micro-unit conversion errors (cents vs. dollars) or uncleaned load test runs."
                ),
            },
            {
                "cause": "Guest checkout pathway omitting mandatory email validation at mobile checkout.",
                "is_hypothesis": True,
                "supporting_evidence": (
                    "Missing email addresses correlate with 'pending' order status and mobile browser user agents."
                ),
            },
            {
                "cause": "Upstream client input forms lack string sanitization and whitespace trimming before serialization.",
                "is_hypothesis": False,
                "supporting_evidence": (
                    "Observed raw string literals with whitespace: '  Arthur Dent  ' and ' active '."
                ),
            },
        ],
        "recommendations": [
            {
                "action": "Cap extreme order_amount outliers using DataPulse Remediation engine with an upper bound of $2,000.00 to prevent revenue metric distortion.",
                "priority": "high",
                "evidence": "2 rows exceed $800,000, severely skewing statistical distribution and business intelligence dashboards.",
            },
            {
                "action": "Execute drop_duplicates on the dataset preserving the initial occurrence to avoid double-counting orders.",
                "priority": "high",
                "evidence": "Duplicate transaction for customer_id 1001 detected with identical timestamp and dollar amount.",
            },
            {
                "action": "Apply trim_whitespace across 'name' and 'status' columns with empty_string_to_null normalization.",
                "priority": "medium",
                "evidence": "Observed leading and trailing padding in customer names and order statuses.",
            },
            {
                "action": "Enforce backend API schema validation rejecting null emails on order submission or route to guest customer queue.",
                "priority": "low",
                "evidence": "4 missing email addresses degrade CRM campaign synchronization.",
            },
        ],
        "limitations": [
            "Analysis is based purely on empirical column profiling metrics; upstream pipeline lineage metadata was not provided.",
            "Customer lifetime value tables were not joined, so business impact on recurring subscriptions cannot be fully quantified.",
        ],
        "is_sample_demo": True,
        "metadata": {
            "model": "gpt-4o-mini (Sample Demonstration)",
            "provider": "sample_cached_demo",
            "is_sample_demo": True,
        },
    }
