# DataPulse AI — Intelligent Data Quality Monitoring Platform

DataPulse AI is a production-minded data quality monitoring and root-cause analysis platform. It provides automated CSV dataset ingestion, statistical profiling, anomaly detection, explainable 0–100 quality scoring, historical run comparisons, AI-powered root-cause analysis, an interactive Streamlit analytics dashboard, Amazon S3 artifact storage, and audit logging for enterprise data pipelines.

---

## What DataPulse AI Does

1. **Robust Ingestion**: Ingests CSV datasets via multipart/form-data with content validation, mime-type checking, encoding fallback (UTF-8, Latin-1), duplicate header detection, and path-traversal prevention.
2. **Comprehensive Profiling**: Computes dataset-level and column-level summary statistics including row/col counts, missing rates, duplicate rates, numeric quartiles & IQR outliers, string length distributions, date-validity parsing, and candidate primary key detection.
3. **Automated Issue Detection**: Detects and aggregates data quality issues into standard severities (`low`, `medium`, `high`, `critical`) across missing values, duplicates, numeric outliers, invalid dates, empty/constant columns, and Pandera schema mismatches.
4. **Deterministic & Explainable Quality Scoring**: Calculates a transparent 0–100 score with component dimensions (`completeness`, `uniqueness`, `validity`, `consistency`) and human-readable deduction reasons.
5. **Historical Run Comparison**: Evaluates schema changes (added/removed columns), metric deltas (missing/duplicate percentages), score differences, and newly introduced vs. resolved quality issues between profiling runs.
6. **AI Root-Cause Diagnostics**: Explains profiling results, anomalies, and historical shifts using an LLM to generate grounded findings, hypothesized root causes, and prioritized remediation actions.
7. **Interactive Streamlit Dashboard**: Provides an enterprise-grade analytics UI with Plotly gauges, column defect charts, issue severity breakdowns, comparison deltas, and on-demand AI diagnostics.
8. **Cloud-Native Storage & Serverless Database**: Backed by Neon PostgreSQL (with connection pooling and automatic pre-pinging) and Amazon S3 with IAM credential chaining and local offline test mocking.
9. **Safe Data Remediation & Revalidation**: User-controlled, deterministic data cleaning workflow that previews corrections, preserves the original CSV, creates a new dataset version with a separate S3 key, and re-validates data quality using the existing profiler to compute before/after scores and resolved issues.

---

## Architecture & Data Flow

```
[ CSV File Upload (FastAPI / Streamlit UI) ] 
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ CSV Ingestion & Validation Service (csv_service.py)    │
│  - Filename sanitization & path-traversal prevention   │
│  - Size limit & row limit checks                       │
│  - Encoding detection (UTF-8 / Latin-1)                │
│  - Duplicate header & malformed CSV detection          │
└────────────────────────────────────────────────────────┘
       │
       ├──► [ Amazon S3 Storage Service (s3_service.py) ]
       │     - Generates safe UUID object key: datasets/{id}/{uuid}_{file}.csv
       │     - Uploads raw CSV without local disk leakage
       ▼
┌────────────────────────────────────────────────────────┐
│ Profiling & Anomaly Engine (profiler_service.py)       │
│  - General statistics (rows, cols, memory, nulls)      │
│  - Column statistics (types, quantiles, distincts)     │
│  - IQR outlier detection: [Q1 - 1.5*IQR, Q3 + 1.5*IQR] │
│  - Date parsing heuristics & invalid format detection  │
│  - Optional Pandera schema validation                  │
│  - Deterministic 0-100 Quality Scoring                 │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Persistence Coordinator (profiling_service.py)         │
│  - Atomic Neon PostgreSQL transactions                 │
│  - Persists DatasetVersion, ProfilingRun,              │
│    QualityMetrics, QualityIssues, and AuditLogs        │
└────────────────────────────────────────────────────────┘
       │
       ├──► [ Historical Comparison Engine (comparison_service.py) ]
       │     - Compares baseline vs. target profiling runs
       │     - Identifies schema shifts, metric deltas, & issues
       ├──► [ Remediation & Revalidation Engine (remediation_service.py) ]
       │     - Non-destructive simulation on DataFrame deep copy
       │     - Cryptographic preview_id signature binding approval
       │     - Safe copy upload to S3 (never overwrites original CSV)
       │     - Automated re-profiling & comparison calculation
       ▼
┌────────────────────────────────────────────────────────┐
│ AI Root-Cause Diagnostics Engine (ai_analysis_service) │
│  - Gathers empirical metrics, anomalies, & diffs       │
│  - Enforces strict factual grounding in system prompt  │
│  - Calls LLM via Provider interface (llm_provider.py)  │
│  - Returns validated Pydantic structured output        │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Streamlit Analytics Dashboard (dashboard/app.py)       │
│  - Decoupled HTTP client consuming FastAPI endpoints   │
│  - Plotly quality gauges, defect charts, & KPIs        │
│  - Run comparisons with delta progression              │
│  - Interactive Remediation Preview & Revalidation UI   │
│  - Executive AI diagnostics formatting                 │
└────────────────────────────────────────────────────────┘
```

### Modular Repository Layout

```
DataPulse-AI/
├── .env.example              # Environment variables template (placeholders only)
├── .gitignore                # Git ignore rules for Python, virtual environments, and secrets
├── README.md                 # Complete setup, PowerShell instructions, and documentation
├── requirements.txt          # Application dependencies (FastAPI, Streamlit, Plotly, etc.)
├── alembic.ini               # Alembic database migration configuration
├── alembic/
│   ├── env.py                # Migration runner binding to application Base & DATABASE_URL
│   ├── script.py.mako        # Migration revision template
│   └── versions/
│       ├── 0001_initial_schema.py             # Phase 1: 6 core tables
│       └── 0002_add_quality_score_and_summary.py # Phase 2: Score & summary columns
├── app/
│   ├── __init__.py           # Application package root
│   ├── main.py               # FastAPI factory, lifespan handler, route registration
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py         # Settings with secure Neon URL normalization, S3, & LLM config
│   │   └── database.py       # SQLAlchemy 2.0 engine, pooling, get_db, and readiness probe
│   ├── models/               # SQLAlchemy Declarative Models
│   │   ├── __init__.py       # Model exports for clean imports and Alembic discovery
│   │   ├── dataset.py        # Dataset & DatasetVersion models
│   │   ├── profiling.py      # ProfilingRun & QualityMetric models
│   │   ├── quality_issue.py  # QualityIssue anomaly tracking model
│   │   └── audit_log.py      # Immutable AuditLog model
│   ├── schemas/              # Pydantic Request & Response Schemas
│   │   ├── __init__.py
│   │   ├── health.py         # HealthResponse & ReadyResponse schemas
│   │   ├── dataset.py        # Dataset & version schemas
│   │   ├── profiling.py      # ProfilingRun, QualityMetric, & Comparison schemas
│   │   ├── quality_issue.py  # QualityIssue schemas
│   │   ├── audit_log.py      # AuditLog schemas
│   │   ├── ai_analysis.py    # AI Root-Cause Analysis request & response schemas
│   │   └── remediation.py    # Remediation preview, apply, and history schemas
│   ├── services/             # Decoupled Business Logic & Profiling Engines
│   │   ├── __init__.py
│   │   ├── s3_service.py     # Boto3 S3 upload/download with safe key generation
│   │   ├── csv_service.py    # Multipart CSV validation, sanitization, & encoding handling
│   │   ├── profiler_service.py # Pure Pandas/Pandera statistical profiler & quality scorer
│   │   ├── profiling_service.py# Persistence coordinator with atomic DB transactions
│   │   ├── comparison_service.py # Historical run comparison & schema diff engine
│   │   ├── remediation_service.py # Deterministic data remediation, preview hash, & safe apply
│   │   ├── llm_provider.py   # LLM provider abstraction & OpenAI-compatible client
│   │   ├── ai_analysis_service.py # AI root-cause diagnostics & evidence preparation
│   │   ├── dataset_service.py# Dataset CRUD service
│   │   └── audit_service.py  # Audit event logger service
│   └── api/
│       ├── __init__.py
│       ├── errors.py         # Centralized API error handlers & structured error responses
│       └── v1/
│           ├── __init__.py
│           ├── router.py     # Aggregated v1 router (/health, /datasets, /profiling)
│           ├── health.py     # /health (liveness) and /ready (database probe)
│           ├── datasets.py   # Dataset catalog, CSV upload, & remediation history endpoints
│           └── profiling.py  # Profiling, metrics, comparison, AI analysis, & remediation preview/apply
├── dashboard/                # Streamlit Analytics Dashboard (Phase 3.2 & 3.3)
│   ├── __init__.py
│   ├── api_client.py         # HTTP client consuming FastAPI endpoints (upload, profiling, AI, remediation)
│   ├── theme.py              # Modern dark SaaS design system, CSS injection, & header components
│   ├── components.py         # Reusable dark Plotly gauge charts, defect bars, and severity pies
│   └── app.py                # Main Streamlit analytics application with persistent sidebar navigation
└── tests/                    # Automated Test Suite (95 tests passing)
    ├── __init__.py
    ├── conftest.py           # Shared test fixtures (isolated DB engine, rollback session, TestClient)
    ├── test_health.py        # Tests for /health and /ready (healthy & 503 failure paths)
    ├── test_config.py        # Tests for Pydantic Settings, Neon URL normalization, and pooling
    ├── test_models.py        # Tests for SQLAlchemy models, foreign keys, cascades, & constraints
    ├── test_datasets_api.py  # Tests for REST catalog endpoints and validation error formatting
    ├── test_csv_service.py   # Tests for CSV validation, empty/malformed files, & duplicate headers
    ├── test_profiler_service.py # Tests for IQR outliers, date checks, scoring, and edge cases
    ├── test_s3_service.py    # Tests for S3 storage service, safe keys, and mocked boto3
    ├── test_comparison_service.py # Tests for run comparisons, schema shifts, & metric deltas
    ├── test_profiling_service.py  # Tests for atomic persistence and failed run handling
    ├── test_phase2_api.py    # Tests for multipart upload, runs, and comparison API endpoints
    ├── test_ai_analysis.py   # Tests for AI root-cause analysis, prompts, error handling, & mocking
    ├── test_remediation.py   # Tests for remediation preview, safe apply, revalidation, and tampering prevention
    └── test_dashboard.py     # Tests for dashboard api_client, remediation client, & Plotly components
```

---

## Streamlit Analytics Dashboard (Phase 3.2)

The Streamlit dashboard (`dashboard/app.py`) provides an interactive interface for data quality monitoring, profiling inspection, historical run tracking, and on-demand AI diagnostics.

### Dashboard Views
1. **Overview & Ingestion**:
   - Upload any CSV dataset with optional dataset naming, version tags, and expected Pandera schema JSON.
   - Shows instant profiling results, quality score KPI, radial gauge, and dimension breakdown.
   - If S3 is unconfigured, displays a helpful, informative warning rather than crashing.
   - Displays a live table of existing registered datasets.
2. **Quality Deep-Dive**:
   - Select any monitored dataset and profiling run.
   - Executive KPIs: Overall Score, Profiled Rows, Anomalous Metrics, and Total Issues.
   - Interactive Plotly score gauge and dimension breakdown (`completeness`, `uniqueness`, `validity`, `consistency`).
   - Granular column defects bar chart highlighting missing rates and numeric IQR outliers.
   - Searchable table of detected quality issues color-coded by severity (`critical`, `high`, `medium`, `low`).
3. **Historical Run Comparison**:
   - Select any two profiling runs for the same dataset.
   - Evaluates score progression with $\Delta$ score delta cards.
   - Displays row count shifts, schema compatibility notes (added/removed columns), and metric diffs.
   - Side-by-side lists of newly emerged issues vs. resolved issues.
4. **AI Root-Cause Diagnostics**:
   - Trigger AI root-cause analysis on any completed profiling run.
   - Optional diagnostic focus areas (e.g. `email, salary`) and ingestion domain context.
   - Renders executive assessment, key empirical findings, hypothesized root causes with evidence, prioritized remediation actions, and diagnostic limitations.
5. **Data Remediation & Revalidation (Phase 3.3)**:
   - Select any monitored dataset and completed profiling run.
   - Configure deterministic operations via interactive expanders: missing value strategies, duplicate removal, whitespace/empty-string normalization, type casting, and outlier capping.
   - Preview proposed changes: view predicted row counts, affected cells per operation, warnings, and tabular before/after sample diffs.
   - User approval gating: requires explicit confirmation checkbox before applying.
   - Safe apply: creates a new dataset version with a unique S3 object key (never modifies original CSV or run), executes re-profiling, and computes score delta and issue resolution.
   - Inspects remediation history and audit log entries for the dataset.


---

## AI Root-Cause Analysis (Phase 3.1)

The AI Root-Cause Analysis engine interprets statistical profiling metrics, anomalies, and schema shifts into human-understandable diagnostics and prioritized remediation steps.

### Diagnostic Design Principles
1. **Strict Factual Grounding**: The LLM prompt is constructed strictly from empirical profiling facts (null ratios, duplicate counts, IQR outliers, invalid dates, and schema diffs). The system prompt prohibits hallucinating unobserved columns or metrics.
2. **Hypothesis vs. Fact Distinction**: Potential root causes are explicitly designated with `is_hypothesis: true` to prevent presenting unverified assumptions as absolute ground truth.
3. **Actionable Remediation**: Every recommendation includes a priority (`high`, `medium`, or `low`) and cites the specific profiling metric justifying the action.
4. **Isolated Provider Interface**: The `LLMProvider` interface abstracts LLM communication, allowing easy substitution between OpenAI, Groq, OpenRouter, or local models (Ollama, vLLM) via `httpx`.
5. **No Database Modification**: The analysis runs stateless and returns validated Pydantic output without requiring schema changes or database migrations.

### Calling the Analysis Endpoint

```http
POST /api/v1/profiling/{run_id}/analyze HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{
  "focus_areas": ["email", "salary"],
  "custom_context": "Daily employee roster ingestion from HR portal"
}
```

---

## Safe Data Remediation & Revalidation (Phase 3.3)

Phase 3.3 implements a user-controlled, deterministic remediation workflow that previews corrections to data quality issues, applies approved corrections to a separate copy of the CSV, and re-runs the existing data quality profiler to measure empirical improvement.

### 1. Supported Deterministic Corrections

All operations are executed deterministically in Python/Pandas without executing arbitrary code, SQL expressions, or shell commands:

| Category | Operation Type | Options / Strategies | Safe Guardrails |
| :--- | :--- | :--- | :--- |
| **Missing Values** | `fill_missing` | `constant`, `median`, `mean` (numeric); `constant`, `mode` (categorical) | Validates numeric-only strategies against column dtype; forbids mean/median on string columns. |
| **Duplicates** | `remove_duplicates` | Drops exact duplicate rows | Preserves first occurrence (`keep='first'`); reports exact rows to be removed. |
| **Whitespace** | `trim_whitespace` | Trims leading/trailing whitespace | Restricts to string/object columns; preserves inner spaces and capitalization. |
| **Empty Strings** | `normalize_empty_strings` | Converts `""` or whitespace-only cells to `NaN` | Restricts to string/object columns; transparently increases missing counts for explicit handling. |
| **Data Types** | `convert_type` | Target types: `integer`, `float`, `string`, `date` | Never silently discards data. Handles failures via explicit user choice: `reject` (halts preview/apply) or `preserve_as_null` (coerces invalid cells to missing with warnings). |
| **Outliers** | `cap_outliers` | Caps values outside numeric `lower_bound` and/or `upper_bound` | Requires numeric column, explicit bounds, and previews affected cell counts. |

### 2. Preview Before Applying (Non-Destructive)

1. The client requests a preview via `POST /api/v1/profiling/{run_id}/remediation/preview`.
2. The server loads the source CSV from S3 and performs simulation exclusively on a **deep copy** of the DataFrame (`df.copy(deep=True)`).
3. The response returns:
   - `preview_id`: A 24-character SHA-256 cryptographic signature binding the `run_id` and the canonical operations list.
   - `original_row_count` and `predicted_row_count`.
   - `operations`: Per-operation affected row/cell counts and sample before/after diffs (`row_index`, `before_value`, `after_value`).
   - `warnings`: Actionable warnings regarding potential information loss (e.g., dropped duplicates or coerced type conversions).
4. **Tamper-Proof Binding**: The subsequent `apply` request MUST provide the identical `preview_id` and operations. If operations or parameters are altered after preview, the server rejects the request with `400 Bad Request`.

### 3. Protection of the Original Dataset (Strict Invariant)

- **Source Immutability**: The original CSV object in S3, original `ProfilingRun`, `QualityMetric`, and `QualityIssue` records are NEVER overwritten or mutated.
- **Dedicated S3 Artifact**: Corrected data is uploaded to a unique object key: `datasets/{dataset_id}/{uuid}_{filename}_remediated.csv`.
- **New Dataset Version**: A new `DatasetVersion` record (e.g. `v{N}_remediated`) is created and linked to the dataset.
- **Traceable Audit Log**: An immutable `AuditLog` entry (`action='remediation_applied'`) logs `source_run_id`, `new_run_id`, score improvement, and operation parameters without storing credentials.
- **No Silent Fallback**: If AWS S3 is unconfigured, the application returns a clean `503 Service Unavailable` with `SERVICE_UNAVAILABLE` error code, preventing local disk file leaks.

### 4. Automated Revalidation

Upon applying corrections:
1. The new CSV artifact is profiled using `ProfilingService.execute_and_persist_profiling`.
2. The previous and new runs are compared using `ComparisonService.compare_runs`.
3. The response provides:
   - `previous_score`, `current_score`, and `score_change`.
   - `resolved_issues`: Quality issues present in the baseline run that are absent in the remediated run.
   - `remaining_issues`: Unresolved issues still present.
   - `new_issues`: Any issues inadvertently introduced by remediation.

### 5. Remediation API Endpoints & Payloads

#### Preview Request:
```http
POST /api/v1/profiling/1/remediation/preview HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{
  "operations": [
    {
      "operation_type": "fill_missing",
      "column_name": "salary",
      "strategy": "median"
    },
    {
      "operation_type": "remove_duplicates"
    },
    {
      "operation_type": "trim_whitespace",
      "column_name": "email"
    }
  ]
}
```

#### Preview Response:
```json
{
  "preview_id": "8a3cf5b12d90ef014a6b2311",
  "source_run_id": 1,
  "dataset_id": 10,
  "original_row_count": 100,
  "predicted_row_count": 98,
  "operations": [
    {
      "operation_type": "fill_missing",
      "column_name": "salary",
      "affected_count": 4,
      "sample_diffs": [
        {"row_index": 5, "column_name": "salary", "before_value": null, "after_value": "75000.0"}
      ]
    },
    {
      "operation_type": "remove_duplicates",
      "column_name": null,
      "affected_count": 2,
      "sample_diffs": []
    }
  ],
  "warnings": [
    "Duplicate removal will discard 2 identical rows (preserving the first occurrence)."
  ]
}
```

#### Apply Request:
```http
POST /api/v1/profiling/1/remediation/apply HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{
  "preview_id": "8a3cf5b12d90ef014a6b2311",
  "operations": [
    {
      "operation_type": "fill_missing",
      "column_name": "salary",
      "strategy": "median"
    },
    {
      "operation_type": "remove_duplicates"
    },
    {
      "operation_type": "trim_whitespace",
      "column_name": "email"
    }
  ],
  "new_version_tag": "v2_remediated"
}
```

---

## Explainable Quality Score Calculation

The DataPulse AI quality engine uses a **transparent, deterministic, bounded (0–100) scoring formula**.

### Penalty Weights

Starting from **100.0**:

| Quality Dimension | Metric / Criterion | Penalty Weight | Cap |
| :--- | :--- | :--- | :--- |
| **Completeness** | Missing cell ratio (`null_cells / total_cells`) | `missing_ratio * 40.0` | 40.0 pts |
| **Uniqueness** | Duplicate row ratio (`duplicate_rows / total_rows`) | `duplicate_ratio * 20.0` | 20.0 pts |
| **Validity** | Invalid date format ratio (`invalid_dates / total_dates`) | `invalid_ratio * 15.0` | 15.0 pts |
| **Validity** | Empty columns (`null_count == row_count`) | `10.0` per empty column | 20.0 pts |
| **Validity** | Constant-value columns (`distinct_count == 1`) | `5.0` per constant column | 15.0 pts |
| **Consistency** | Numeric IQR outliers (`outliers / total_numeric_cells`) | `outlier_ratio * 15.0` | 15.0 pts |
| **Consistency** | Pandera expected schema validation errors | `15.0` flat penalty if invalid | 15.0 pts |

### Score Normalization & Edge Cases
- **Clamped Range**: Final score is clamped between `0.0` and `100.0`.
- **Zero-Row / Zero-Column Edge Case**: An empty dataset or DataFrame with 0 columns immediately receives a score of `0.0` with explicit explanatory notes.
- **Explainability**: Every profiling response includes overall score, component scores (`completeness`, `uniqueness`, `validity`, `consistency`), and human-readable deductions.

---

## Environment Variables Configuration

Copy `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

Configure your local `.env` variables:

```env
# Application Settings
APP_NAME=DataPulse AI
API_V1_PREFIX=/api/v1
ENVIRONMENT=development
LOG_LEVEL=INFO

# Neon PostgreSQL Database
DATABASE_URL=postgresql://neondb_owner:YOUR_PASSWORD@ep-sample-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800

# Amazon S3 Storage Integration
S3_BUCKET_NAME=your-s3-bucket-name
AWS_REGION=us-east-1
# S3_ENDPOINT_URL=http://localhost:4566  # Optional: For LocalStack / MinIO

# AI Root-Cause Analysis (LLM Integration)
LLM_PROVIDER=openai
LLM_API_KEY=sk-your-openai-or-groq-api-key
LLM_MODEL=gpt-4o-mini
# LLM_API_BASE=https://api.openai.com/v1  # Optional: Custom endpoint (Groq, OpenRouter, Ollama)
LLM_TIMEOUT_SECONDS=30.0

# Streamlit Dashboard Configuration
DATAPULSE_API_URL=http://127.0.0.1:8000

# Dataset Limits
MAX_UPLOAD_SIZE_MB=50
MAX_ROW_COUNT=1000000
```

---

## Windows PowerShell Setup & Running Instructions

### 1. Open Windows PowerShell and Navigate to the Repository

```powershell
cd d:\DataPulse-AI
```

### 2. Configure PowerShell Execution Policy (If Needed)

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 3. Create and Activate Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 4. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 5. Run Database Migrations

Apply Alembic migrations to update your Neon database schema to the latest version:

```powershell
alembic upgrade head
```

---

### 6. Running Backend and Dashboard in Separate Terminals

#### Terminal 1 — Start FastAPI Backend Server
```powershell
cd d:\DataPulse-AI
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- **API Server**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

#### Terminal 2 — Start Streamlit Analytics Dashboard
```powershell
cd d:\DataPulse-AI
.\.venv\Scripts\Activate.ps1
streamlit run dashboard/app.py
```
- **Streamlit Dashboard**: [http://localhost:8501](http://localhost:8501)

---

## Summary of API Endpoints & Security Classification

| Category | Method | Endpoint | Exposure & Classification | Description |
| :--- | :---: | :--- | :--- | :--- |
| **System** | `GET` | `/health` | **Read-Only** | Application liveness probe (reports `DataPulse AI`) |
| **System** | `GET` | `/ready` | **Read-Only** | Database readiness probe (`SELECT 1`) |
| **Datasets** | `GET` | `/api/v1/datasets` | **Read-Only** | List registered datasets (paginated) |
| **Datasets** | `POST` | `/api/v1/datasets` | **Write (Demo Scope)** | Register a new dataset entry |
| **Datasets** | `GET` | `/api/v1/datasets/{id}` | **Read-Only** | Get dataset metadata by ID |
| **Datasets** | `POST` | `/api/v1/datasets/{id}/versions` | **Write (Demo Scope)** | Register a dataset version snapshot |
| **Datasets** | `POST` | `/api/v1/datasets/upload` | **Write / Intensive (10MB Cap)** | Multipart CSV upload, S3 storage, & auto-profiling |
| **Datasets** | `GET` | `/api/v1/datasets/{id}/runs` | **Read-Only** | List historical profiling runs for a dataset |
| **Datasets** | `GET` | `/api/v1/datasets/{id}/compare-runs` | **Read-Only** | Compare two profiling runs for a dataset |
| **Profiling** | `POST` | `/api/v1/profiling/runs` | **Intensive (Demo Scope)** | Trigger profiling on an existing dataset version |
| **Profiling** | `GET` | `/api/v1/profiling/{id}` | **Read-Only** | Get profiling run status and quality score |
| **Profiling** | `GET` | `/api/v1/profiling/{id}/summary` | **Read-Only** | Get high-level quality score, component scores, & stats |
| **Profiling** | `GET` | `/api/v1/profiling/{id}/metrics` | **Read-Only** | Get detailed column-level metrics |
| **Profiling** | `GET` | `/api/v1/profiling/{id}/issues` | **Read-Only** | Get aggregated quality issues |
| **Profiling** | `GET` | `/api/v1/profiling/compare` | **Read-Only** | Compare any two profiling runs |
| **Diagnostics** | `POST` | `/api/v1/profiling/{id}/analyze` | **Intensive / Outbound LLM** | AI-powered root-cause analysis and remediation steps |
| **Remediation** | `POST` | `/api/v1/profiling/{id}/remediation/preview` | **Simulation (Read-Only)** | Simulate corrections & preview before/after diffs |
| **Remediation** | `POST` | `/api/v1/profiling/{id}/remediation/apply` | **Remediation (Immutable Copy)** | Apply approved corrections, store new S3 copy, & revalidate |
| **Remediation** | `GET` | `/api/v1/datasets/{id}/remediation-history` | **Read-Only** | Get remediation audit trail and score improvements |

> **Security & Public Demo Notice**: Authentication and per-user authorization are explicitly deferred to future scope. Write endpoints are unauthenticated to allow seamless portfolio and recruiter exploration. They are guarded by strict 10 MB payload limits, path-traversal sanitization, and bounded processing, but are **not suitable for unrestricted public production use without authentication**.

---

## Recruiter & Evaluation Demo Experience

Evaluators can test DataPulse AI immediately without signing in or configuring cloud credentials:
1. **1-Click Synthetic Dataset**: On the **Overview & Ingestion** tab, click **⚡ Ingest & Profile Synthetic Demo Dataset** to load our bundled synthetic customer transaction data (`synthetic_customer_orders.csv`).
2. **Quality Deep-Dive**: Explore automated completeness, uniqueness, consistency, and validity scoring alongside IQR numeric outliers.
3. **Historical Run Comparison**: Compare run snapshots to evaluate data drift, schema evolution, and resolved defects.
4. **Sample AI Root-Cause Diagnostics**: In **AI Root-Cause Diagnostics**, click **📖 View Sample AI Diagnostic Report** to inspect pre-recorded grounded LLM diagnostics without requiring an OpenAI or Groq API key.
5. **Safe Remediation Preview & Apply**: Test deterministic missing value imputation, duplicate removal, whitespace trimming, and outlier capping with cryptographic approval tokens.

---

## Running Automated Tests

All automated tests use an isolated in-memory SQLite database and test doubles so **all 105 tests run offline without live database or external API credentials**:

```powershell
pytest -v
```

Expected output:
```
105 passed, 1 warning in ~4.5s
```

---

## AWS Cloud Deployment (Target: ap-south-1 Mumbai)

DataPulse AI is packaged as a serverless container image for AWS Lambda with Amazon API Gateway HTTP API v2:
- **Direct Deployment**: Deployed using Docker + AWS CLI directly to Amazon ECR, AWS Lambda, and API Gateway (without SAM CLI).
- **Target Region**: `ap-south-1` (Mumbai).
- **Deployment Documentation**: Complete step-by-step CLI commands, IAM role setup, and cost breakdowns in [docs/DEPLOYMENT_AWS.md](docs/DEPLOYMENT_AWS.md).
- **CI/CD Automation**: Production pipeline declared in `Jenkinsfile` with automated testing, container builds, and gated direct AWS CLI deployments.

---

## Future Scope (Post-Demo Production Hardening)

1. **User Authentication & Authorization**: JSON Web Tokens (JWT), AWS Cognito User Pool integration, or OAuth2 social login.
2. **Tenant & Dataset Ownership**: Per-user dataset isolation, organization-level RBAC, and granular access permissions.
3. **Direct-to-S3 Presigned Uploads**: Asynchronous processing pipeline allowing dataset uploads >10 MB bypassing API Gateway payload constraints.

