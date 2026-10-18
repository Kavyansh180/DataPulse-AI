# DataPulse AI — Direct AWS Production Deployment Guide (Docker + AWS CLI)

This guide documents the direct, production-grade deployment of the **DataPulse AI** backend using **Docker**, **AWS CLI**, **Amazon ECR**, **AWS Lambda** (container image), **Amazon API Gateway** (HTTP API v2), **Amazon S3**, and **AWS Systems Manager (SSM) Parameter Store** / **AWS Secrets Manager**, connecting to **Neon PostgreSQL** in the **Mumbai region (`ap-south-1`)**.

> **Architecture Notice**: This deployment uses Docker and the AWS CLI directly. **AWS SAM and SAM CLI are not used.**

---

## 1. Architectural Overview & Guardrails

```
                               ┌────────────────────────────────┐
                               │ Streamlit Dashboard (External) │
                               └───────────────┬────────────────┘
                                               │ HTTPS / REST (CORS terminated at API Gateway)
                                               ▼
                               ┌────────────────────────────────┐
                               │ Amazon API Gateway (HTTP API)  │
                               │  - Region: ap-south-1 (Mumbai) │
                               │  - Protocol: HTTP API v2       │
                               │  - Payload Format: 2.0         │
                               │  - Max Payload: 10 MB          │
                               │  - CORS: Single Source of Truth│
                               │  - Throttling: 10 rps / 20 burst│
                               └───────────────┬────────────────┘
                                               │ Proxy Request (v2.0)
                                               ▼
                               ┌────────────────────────────────┐
                               │ AWS Lambda (Container Image)   │
                               │  - Name: datapulse-backend     │
                               │  - Arch: x86_64 (1024 MB RAM)  │
                               │  - Timeout: 30 seconds         │
                               │  - Mangum ASGI Adapter         │
                               │  - ENABLE_CORS_MIDDLEWARE=False│
                               └───────┬──────────────┬─────────┘
                                       │              │
                       ┌───────────────┘              └───────────────┐
                       ▼                                              ▼
        ┌───────────────────────────┐                  ┌───────────────────────────┐
        │ Amazon S3 Storage Bucket  │                  │ Neon PostgreSQL Database  │
        │  - Region: ap-south-1     │                  │  - Pooled connection URI  │
        │  - Private & SSE-256      │                  │  - DB_POOL_SIZE=1         │
        │  - Block all public ACLs  │                  │  - DB_MAX_OVERFLOW=0      │
        └───────────────────────────┘                  └───────────────────────────┘
                       ▲                                              ▲
                       │                                              │
                       └───────────────┐              ┌───────────────┘
                                       │              │
                               ┌───────┴──────────────┴─────────┐
                               │ AWS SSM Parameter Store / SM   │
                               │  - /datapulse/production/*     │
                               │  - Encrypted (SecureString)    │
                               │  - Least-privilege IAM Read    │
                               └────────────────────────────────┘
```

---

## 2. Security Boundaries, Protections & Demo Exposure

### A. CORS Does NOT Provide Authentication
> **CRITICAL SECURITY NOTE**: CORS (Cross-Origin Resource Sharing) is strictly a browser-enforced security mechanism that controls which web origins can read API responses from JavaScript. **CORS does not authenticate requests, does not authorize users, and provides zero server-side security.** Any automated tool, curl command, Python script, or non-browser client can invoke public HTTP endpoints directly, ignoring CORS completely.

### B. Sensible Protections for the Public Demo API
1. **API Gateway Default Route Stage Throttling (Rate Limiting & Quotas)**:
   - Configured at the API Gateway `$default` stage:
     - **Steady Rate Limit**: 10 requests per second.
     - **Burst Limit**: 20 concurrent requests.
   - Protects against accidental denial-of-wallet, infinite retry loops, and request floods. When exceeded, API Gateway returns `429 Too Many Requests` directly at the network edge without invoking Lambda or incurring compute costs.
2. **Payload & Row Count Bounds**:
   - HTTP API v2 enforces an unchangeable **10 MB hard payload limit** (`MAX_UPLOAD_SIZE_BYTES=10485760`).
   - Profiling and remediation enforce a **1,000,000 row ceiling** (`MAX_ROW_COUNT_LIMIT=1000000`).
   - Path-traversal sequences and malicious filenames are sanitized (`datasets/{id}/{uuid}_{file}.csv`).
3. **LLM Cost Controls & Quotas**:
   - The AI root-cause analysis endpoint (`POST /api/v1/profiling/{run_id}/ai-analysis`) does **not** send raw tabular dataset rows to the LLM. Instead, it extracts compact statistical summaries (column anomaly counts, rule violations, null percentages), bounding each prompt to <2,000 tokens.
   - LLM requests enforce a strict 30-second timeout (`LLM_TIMEOUT_SECONDS=30.0`).
   - AWS Budgets should be configured with a **$5.00/month threshold** to alert the team before unexpected cloud charges accumulate.
4. **CloudWatch Alarms & Observability**:
   - CloudWatch 7-day log retention prevents log sprawl costs.
   - Monitor `5XXError`, `4XXError`, `Invocations`, `Duration`, and `Throttles`.

---

## 3. Safe Runtime Secret Management (AWS SSM Parameter Store / Secrets Manager)

**Plaintext secret injection via local files (`.deploy-env.json`) or commit history is strictly prohibited.**

Instead, sensitive production credentials (`DATABASE_URL`, `LLM_API_KEY`) are stored encrypted in **AWS Systems Manager (SSM) Parameter Store** (or AWS Secrets Manager). The Lambda execution role is granted least-privilege read access to decrypt them in-process upon container cold start.

### A. Provision Secrets into SSM Parameter Store (One-Time Setup)

Run these commands from your secure administrator terminal before deploying Lambda. Secret values are never printed or echoed to logs:

```powershell
$REGION = "ap-south-1"

# 1. Store Neon PostgreSQL Pooled Connection URL (SecureString)
aws ssm put-parameter `
  --name "/datapulse/production/DATABASE_URL" `
  --type "SecureString" `
  --value "$env:DATABASE_URL" `
  --description "Neon Postgres pooled connection URL with sslmode=require" `
  --overwrite `
  --region $REGION

# 2. Store Gemini API Key (SecureString)
aws ssm put-parameter `
  --name "/datapulse/production/GEMINI_API_KEY" `
  --type "SecureString" `
  --value "$env:GEMINI_API_KEY" `
  --description "Google Gemini API key for AI diagnostics and remediation recommendations" `
  --overwrite `
  --region $REGION

# 3. Store Optional Legacy LLM API Key (if using OpenAI / Groq fallback)
aws ssm put-parameter `
  --name "/datapulse/production/LLM_API_KEY" `
  --type "SecureString" `
  --value "$env:LLM_API_KEY" `
  --description "API key for fallback LLM root cause analysis provider" `
  --overwrite `
  --region $REGION
```

*(Alternative: If using AWS Secrets Manager, create secret `datapulse/production/secrets` with JSON payload `{"DATABASE_URL":"...","GEMINI_API_KEY":"...","LLM_API_KEY":"..."}` and set `SECRETS_MANAGER_SECRET_ID=datapulse/production/secrets`).*

### B. Neon Connection Pooler & Lambda Concurrency Settings
Neon serverless Postgres requires using the **pooled connection endpoint** (`-pooler.`) for Lambda:
- **Pooled Host Format**: `ep-xyz-pooler.ap-south-1.aws.neon.tech` (**Required**)
- **Connection Parameter**: `?sslmode=require`
- **Conservative SQLAlchemy Pool Settings for Lambda**:
  ```ini
  DB_POOL_SIZE=1
  DB_MAX_OVERFLOW=0
  DB_POOL_TIMEOUT=15
  DB_POOL_RECYCLE=600
  ```

---

## 4. Alembic Database Migrations Protocol (Separate Approved Step)

> **CRITICAL RULE**: Never execute Alembic migrations inside the Lambda runtime or during cold starts. Migrations must be run as an explicitly approved, one-off CLI operation from a trusted management environment before routing traffic to new code.

### Step 4.1: Target Verification (Pre-Flight Check)
Verify the database target and confirm connectivity without altering data:
```powershell
# Set temporary local environment variable
$env:DATABASE_URL = "postgresql://user:password@ep-sample-pooler.ap-south-1.aws.neon.tech/neondb?sslmode=require"

# Verify connection and target database identity
python -c "from sqlalchemy import create_engine, text; import os; engine = create_engine(os.environ['DATABASE_URL']); conn = engine.connect(); row = conn.execute(text('SELECT current_database(), current_user, version()')).fetchone(); print('Target Verified:', row); conn.close()"
```

### Step 4.2: Current State Inspection
Inspect current database revision against available repository migrations:
```powershell
# Inspect the current revision recorded in the Neon database
.\.venv\Scripts\alembic.exe current

# Inspect the latest migration revision defined in code
.\.venv\Scripts\alembic.exe heads

# View full migration history
.\.venv\Scripts\alembic.exe history --verbose
```
*If `current` matches `heads`, your database schema is already up-to-date and no migration is required.*

### Step 4.3: Neon Backup & Recovery Plan
Before applying any migration to production:
1. **Neon Instant Branching (Zero-Cost Snapshot)**:
   In the Neon Console or via Neon CLI, create a branch from `main`:
   ```bash
   # Create a instant point-in-time recovery branch
   neon branches create --name pre-migration-backup-$(date +%Y%m%d)
   ```
2. **Schema & Data Backup Dump**:
   ```bash
   pg_dump --format=custom --no-owner --no-privileges "$DATABASE_URL" > neon_backup_pre_migration.dump
   ```
3. **Rollback Procedure**:
   If a migration fails or causes issues:
   ```powershell
   # Roll back the single last applied migration revision
   .\.venv\Scripts\alembic.exe downgrade -1
   ```
   Or restore the Neon branch to the pre-migration snapshot in the Neon Console.

### Step 4.4: Apply Migrations (With Human Approval)
```powershell
# Apply pending migrations to head
.\.venv\Scripts\alembic.exe upgrade head
```

---

## 5. Direct AWS CLI Deployment Step-by-Step (Region: ap-south-1)

### Prerequisites Check
```powershell
aws sts get-caller-identity
docker --version
```

Set deployment shell variables:
```powershell
$REGION = "ap-south-1"
$ACCOUNT_ID = (aws sts get-caller-identity --query "Account" --output text)
$ECR_REPO = "datapulse-ai"
$LAMBDA_NAME = "datapulse-backend"
$S3_BUCKET = "datapulse-storage-$ACCOUNT_ID-$REGION"
$ROLE_NAME = "datapulse-lambda-execution-role"
```

---

### Step 1: Create Private Amazon S3 Storage Bucket
Robust check: Distinguishes between bucket existing (0), not found (404), and access denied / owned by another account (403):
```powershell
$BucketCheck = aws s3api head-bucket --bucket $S3_BUCKET 2>&1
$BucketExit = $LASTEXITCODE

if ($BucketExit -eq 0) {
    Write-Host "[OK] S3 Bucket '$S3_BUCKET' already exists and is accessible."
} elseif ($BucketCheck -match "404|NoSuchBucket|Not Found") {
    Write-Host "[INFO] Creating S3 bucket '$S3_BUCKET' in $REGION..."
    aws s3api create-bucket `
        --bucket $S3_BUCKET `
        --region $REGION `
        --create-bucket-configuration LocationConstraint=$REGION
} elseif ($BucketCheck -match "403|Forbidden|AccessDenied") {
    Write-Error "CRITICAL: Bucket '$S3_BUCKET' returned 403 Forbidden. Either this bucket name is owned by another AWS account or your credentials lack permission."
    return
} else {
    Write-Error "CRITICAL: Unexpected error checking S3 bucket: $BucketCheck"
    return
}

# 2. Block all public access
aws s3api put-public-access-block `
    --bucket $S3_BUCKET `
    --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# 3. Enable default AES-256 server-side encryption
$EncryptionConfig = '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-encryption `
    --bucket $S3_BUCKET `
    --server-side-encryption-configuration $EncryptionConfig
```

---

### Step 2: Create CloudWatch Log Group with 7-Day Retention
```powershell
$LogCheck = aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/$LAMBDA_NAME" --region $REGION 2>&1
if ($LASTEXITCODE -ne 0) {
    if ($LogCheck -match "AccessDenied") {
        Write-Error "CRITICAL: Access denied to CloudWatch logs: $LogCheck"
        return
    }
    Write-Error "CRITICAL: Error checking CloudWatch logs: $LogCheck"
    return
}

$LogObj = $LogCheck | ConvertFrom-Json
$ExistingLog = $LogObj.logGroups | Where-Object { $_.logGroupName -eq "/aws/lambda/$LAMBDA_NAME" }

if (-not $ExistingLog) {
    Write-Host "[INFO] Creating CloudWatch log group '/aws/lambda/$LAMBDA_NAME'..."
    aws logs create-log-group `
        --log-group-name "/aws/lambda/$LAMBDA_NAME" `
        --region $REGION
} else {
    Write-Host "[OK] CloudWatch log group already exists."
}

aws logs put-retention-policy `
    --log-group-name "/aws/lambda/$LAMBDA_NAME" `
    --retention-in-days 7 `
    --region $REGION
```

---

### Step 3: Create IAM Lambda Execution Role with Least-Privilege Policies
```powershell
$TrustPolicy = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

$RoleCheck = aws iam get-role --role-name $ROLE_NAME 2>&1
$RoleExit = $LASTEXITCODE

if ($RoleExit -eq 0) {
    Write-Host "[OK] IAM role '$ROLE_NAME' already exists."
} elseif ($RoleCheck -match "NoSuchEntity") {
    Write-Host "[INFO] Creating IAM role '$ROLE_NAME'..."
    aws iam create-role `
        --role-name $ROLE_NAME `
        --assume-role-policy-document $TrustPolicy
} elseif ($RoleCheck -match "AccessDenied") {
    Write-Error "CRITICAL: Access denied checking IAM role '$ROLE_NAME': $RoleCheck"
    return
} else {
    Write-Error "CRITICAL: Error querying IAM role: $RoleCheck"
    return
}

# Attach standard CloudWatch logging execution policy
aws iam attach-role-policy `
    --role-name $ROLE_NAME `
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

# Attach least-privilege policy for S3 CRUD
$S3Policy = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:AbortMultipartUpload"
      ],
      "Resource": [
        "arn:aws:s3:::$S3_BUCKET",
        "arn:aws:s3:::$S3_BUCKET/*"
      ]
    }
  ]
}
"@
aws iam put-role-policy `
    --role-name $ROLE_NAME `
    --policy-name "DataPulseS3CrudPolicy" `
    --policy-document $S3Policy

# Attach least-privilege policy for reading SSM Parameter Store credentials
$SSMPolicy = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParametersByPath",
        "ssm:GetParameters",
        "ssm:GetParameter"
      ],
      "Resource": [
        "arn:aws:ssm:${REGION}:${ACCOUNT_ID}:parameter/datapulse/production",
        "arn:aws:ssm:${REGION}:${ACCOUNT_ID}:parameter/datapulse/production/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt"
      ],
      "Resource": "*"
    }
  ]
}
"@
aws iam put-role-policy `
    --role-name $ROLE_NAME `
    --policy-name "DataPulseSSMReadPolicy" `
    --policy-document $SSMPolicy

# Fetch Role ARN and pause 10 seconds for IAM propagation
$ROLE_ARN = (aws iam get-role --role-name $ROLE_NAME --query "Role.Arn" --output text)
Start-Sleep -Seconds 10
```

---

### Step 4: Create Amazon ECR Repository & Push Container Image
```powershell
$RepoCheck = aws ecr describe-repositories --repository-names $ECR_REPO --region $REGION 2>&1
$RepoExit = $LASTEXITCODE

if ($RepoExit -eq 0) {
    Write-Host "[OK] ECR repository '$ECR_REPO' already exists."
} elseif ($RepoCheck -match "RepositoryNotFoundException") {
    Write-Host "[INFO] Creating ECR repository '$ECR_REPO'..."
    aws ecr create-repository `
        --repository-name $ECR_REPO `
        --region $REGION `
        --image-scanning-configuration scanOnPush=true
} elseif ($RepoCheck -match "AccessDeniedException") {
    Write-Error "CRITICAL: Access denied to Amazon ECR: $RepoCheck"
    return
} else {
    Write-Error "CRITICAL: Error checking ECR repository: $RepoCheck"
    return
}

# Authenticate Docker with Amazon ECR
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# Build and push production image
docker build -t "$ECR_REPO:latest" .
docker tag "$ECR_REPO:latest" "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO:latest"
docker push "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO:latest"
```

---

### Step 5: Create or Update AWS Lambda Function (Zero Plaintext Secrets)

Notice: **Zero secret credentials are passed in Lambda environment variables.** Only non-sensitive parameters and the `SSM_PARAMETER_PATH` are supplied. In addition, `ENABLE_CORS_MIDDLEWARE=False` is set so API Gateway terminates CORS without duplicate headers:

```powershell
$IMAGE_URI = "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO:latest"

# Build non-sensitive environment variables file cleanly
$EnvConfig = @{
  Variables = @{
    ENVIRONMENT = "production"
    DEBUG = "False"
    APP_NAME = "DataPulse AI"
    API_V1_PREFIX = "/api/v1"
    ALLOWED_ORIGINS = "*"
    ENABLE_CORS_MIDDLEWARE = "False"
    AWS_REGION = $REGION
    S3_BUCKET_NAME = $S3_BUCKET
    SSM_PARAMETER_PATH = "/datapulse/production"
    DB_POOL_SIZE = "1"
    DB_MAX_OVERFLOW = "0"
    DB_POOL_TIMEOUT = "15"
    DB_POOL_RECYCLE = "600"
    MAX_UPLOAD_SIZE_BYTES = "10485760"
    MAX_ROW_COUNT_LIMIT = "1000000"
    LLM_PROVIDER = "gemini"
    LLM_MODEL = "gemini-2.5-flash"
  }
}

$EnvConfig | ConvertTo-Json -Depth 5 | Out-File -FilePath ".\.lambda-env.json" -Encoding utf8

$LambdaCheck = aws lambda get-function --function-name $LAMBDA_NAME --region $REGION 2>&1
$LambdaExit = $LASTEXITCODE

if ($LambdaExit -eq 0) {
    Write-Host "[OK] Lambda function '$LAMBDA_NAME' exists. Updating code and configuration..."
    aws lambda update-function-code `
        --function-name $LAMBDA_NAME `
        --image-uri $IMAGE_URI `
        --region $REGION

    aws lambda wait function-updated --function-name $LAMBDA_NAME --region $REGION

    aws lambda update-function-configuration `
        --function-name $LAMBDA_NAME `
        --memory-size 1024 `
        --timeout 30 `
        --environment file://.lambda-env.json `
        --region $REGION

    aws lambda wait function-updated --function-name $LAMBDA_NAME --region $REGION
} elseif ($LambdaCheck -match "ResourceNotFoundException") {
    Write-Host "[INFO] Creating Lambda container function '$LAMBDA_NAME'..."
    aws lambda create-function `
        --function-name $LAMBDA_NAME `
        --package-type Image `
        --code ImageUri=$IMAGE_URI `
        --role $ROLE_ARN `
        --memory-size 1024 `
        --timeout 30 `
        --environment file://.lambda-env.json `
        --region $REGION

    aws lambda wait function-active-v2 --function-name $LAMBDA_NAME --region $REGION
} elseif ($LambdaCheck -match "AccessDeniedException") {
    Write-Error "CRITICAL: Access denied querying Lambda function '$LAMBDA_NAME': $LambdaCheck"
    return
} else {
    Write-Error "CRITICAL: Unexpected error checking Lambda function: $LambdaCheck"
    return
}

# Clean up local temporary configuration file
Remove-Item -Path ".\.lambda-env.json" -Force

# Verify active status
aws lambda wait function-active-v2 --function-name $LAMBDA_NAME --region $REGION
Write-Host "[SUCCESS] Lambda function is Active and operational!"
```

---

### Step 6: Create API Gateway (HTTP API v2) with CORS, Throttling & Integration

#### Resolving the API Gateway CORS vs FastAPI CORS Conflict:
When API Gateway is configured with CORS, it handles preflight `OPTIONS` requests automatically and injects `Access-Control-Allow-Origin: *` into response headers. If FastAPI also appends CORS headers, API Gateway merges them into a comma-separated list (`Access-Control-Allow-Origin: *, *`), which browsers reject with a CORS error.
**Our Solution**: By setting `ENABLE_CORS_MIDDLEWARE=False` in the Lambda configuration, FastAPI omits its CORS middleware, and API Gateway acts as the single source of truth.

```powershell
# 1. Check or Create HTTP API v2 with CORS
$ApiCheck = aws apigatewayv2 get-apis --region $REGION 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "CRITICAL: Access denied or error querying API Gateway: $ApiCheck"
    return
}

$ApiObj = $ApiCheck | ConvertFrom-Json
$ExistingApi = $ApiObj.Items | Where-Object { $_.Name -eq "datapulse-http-api" }

if ($ExistingApi) {
    $API_ID = $ExistingApi.ApiId
    Write-Host "[OK] API Gateway 'datapulse-http-api' already exists: $API_ID"
} else {
    Write-Host "[INFO] Creating API Gateway 'datapulse-http-api'..."
    $API_ID = (aws apigatewayv2 create-api `
        --name "datapulse-http-api" `
        --protocol-type HTTP `
        --cors-configuration "AllowOrigins=*,AllowMethods=GET,POST,PUT,DELETE,OPTIONS,AllowHeaders=*,MaxAge=300" `
        --region $REGION `
        --query "ApiId" --output text)
}

$LAMBDA_ARN = (aws lambda get-function --function-name $LAMBDA_NAME --region $REGION --query "Configuration.FunctionArn" --output text)

# 2. Check or Create Integration
$IntCheck = (aws apigatewayv2 get-integrations --api-id $API_ID --region $REGION | ConvertFrom-Json).Items | Where-Object { $_.IntegrationUri -eq $LAMBDA_ARN }

if ($IntCheck) {
    $INTEGRATION_ID = $IntCheck.IntegrationId
    Write-Host "[OK] Integration already exists: $INTEGRATION_ID"
} else {
    Write-Host "[INFO] Creating AWS_PROXY Integration with Payload Format 2.0..."
    $INTEGRATION_ID = (aws apigatewayv2 create-integration `
        --api-id $API_ID `
        --integration-type AWS_PROXY `
        --integration-uri $LAMBDA_ARN `
        --payload-format-version "2.0" `
        --region $REGION `
        --query "IntegrationId" --output text)
}

# 3. Check or Create Catch-All Route ($default)
$RouteCheck = (aws apigatewayv2 get-routes --api-id $API_ID --region $REGION | ConvertFrom-Json).Items | Where-Object { $_.RouteKey -eq '$default' }
if (-not $RouteCheck) {
    Write-Host "[INFO] Creating `$default route..."
    aws apigatewayv2 create-route `
        --api-id $API_ID `
        --route-key '$default' `
        --target "integrations/$INTEGRATION_ID" `
        --region $REGION
} else {
    Write-Host "[OK] Route `$default already exists."
}

# 4. Check or Create Auto-Deploying Default Stage with Rate Limiting (10 rps / 20 burst)
$StageCheck = (aws apigatewayv2 get-stages --api-id $API_ID --region $REGION | ConvertFrom-Json).Items | Where-Object { $_.StageName -eq '$default' }
if (-not $StageCheck) {
    Write-Host "[INFO] Creating `$default stage with throttling protections..."
    aws apigatewayv2 create-stage `
        --api-id $API_ID `
        --stage-name '$default' `
        --auto-deploy `
        --default-route-settings "ThrottlingBurstLimit=20,ThrottlingRateLimit=10" `
        --region $REGION
} else {
    Write-Host "[INFO] Updating `$default stage rate limiting settings..."
    aws apigatewayv2 update-stage `
        --api-id $API_ID `
        --stage-name '$default' `
        --default-route-settings "ThrottlingBurstLimit=20,ThrottlingRateLimit=10" `
        --region $REGION
}

# 5. Grant API Gateway permission to invoke Lambda
$PermCheck = aws lambda get-policy --function-name $LAMBDA_NAME --region $REGION 2>&1
if ($PermCheck -notmatch "apigateway-invoke-permission") {
    Write-Host "[INFO] Granting API Gateway invocation permission on Lambda..."
    aws lambda add-permission `
        --function-name $LAMBDA_NAME `
        --statement-id "apigateway-invoke-permission" `
        --action "lambda:InvokeFunction" `
        --principal "apigateway.amazonaws.com" `
        --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT_ID:$API_ID/*" `
        --region $REGION
} else {
    Write-Host "[OK] API Gateway invocation permission already present."
}

# 6. Display public HTTPS endpoint
$ENDPOINT = "https://$API_ID.execute-api.$REGION.amazonaws.com"
Write-Host "=================================================="
Write-Host "Public API Gateway Endpoint: $ENDPOINT"
Write-Host "Test Health: curl $ENDPOINT/health"
Write-Host "=================================================="
```

---

## 6. Jenkins CI/CD Automated Deployment Reference

The repository's [`Jenkinsfile`](file:///d:/DataPulse-AI/Jenkinsfile) implements automated continuous integration and deployment with the following built-in safeguards:

1. **Test Gate**: Executes `pytest -v` in a local virtual environment before container packaging.
2. **Interactive Production Gate**: Halts execution and requires explicit human approval before touching AWS ECR or Lambda.
3. **Safe Runtime Secrets**: Uses `SSM_PARAMETER_PATH=/datapulse/production` and `ENABLE_CORS_MIDDLEWARE=False`. Secrets are never passed through Jenkins build arguments or shell scripts.
4. **Idempotent Deployment Logic**:
   - Inspects `aws lambda get-function` to distinguish `ResourceNotFoundException` from credential/access-denied errors.
   - If missing, calls `create-function` and waits on `function-active-v2`.
   - If existing, calls `update-function-code` followed by `update-function-configuration` and waits on `function-updated`.
   - Validates final operational state: verifies `State == Active` and `LastUpdateStatus != Failed`.

---

## 7. Rollback Procedure

To roll back Lambda to a previously stable container tag:
```powershell
aws lambda update-function-code `
    --function-name $LAMBDA_NAME `
    --image-uri "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO:<previous-tag>" `
    --region $REGION

aws lambda wait function-updated --function-name $LAMBDA_NAME --region $REGION
Write-Host "[ROLLBACK] Reverted successfully to <previous-tag>"
```

---

## 8. Safe Resource Deletion / Complete Teardown

To delete all provisioned AWS cloud resources cleanly and prevent ongoing costs:
```powershell
# SAFETY BACKUP: Sync any uploaded datasets locally before bucket deletion
Write-Host "Backing up uploaded S3 datasets locally before teardown..."
aws s3 sync "s3://$S3_BUCKET" "./backup-s3-datasets/" --region $REGION

# 1. Delete API Gateway
aws apigatewayv2 delete-api --api-id $API_ID --region $REGION

# 2. Delete Lambda function
aws lambda delete-function --function-name $LAMBDA_NAME --region $REGION

# 3. Delete IAM Role and attached policies
aws iam delete-role-policy --role-name $ROLE_NAME --policy-name "DataPulseS3CrudPolicy"
aws iam delete-role-policy --role-name $ROLE_NAME --policy-name "DataPulseSSMReadPolicy"
aws iam detach-role-policy --role-name $ROLE_NAME --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
aws iam delete-role --role-name $ROLE_NAME

# 4. Delete CloudWatch Log Group
aws logs delete-log-group --log-group-name "/aws/lambda/$LAMBDA_NAME" --region $REGION

# 5. Empty and delete S3 Bucket
aws s3 rm "s3://$S3_BUCKET" --recursive --region $REGION
aws s3api delete-bucket --bucket $S3_BUCKET --region $REGION

# 6. Delete ECR Repository and images
aws ecr delete-repository --repository-name $ECR_REPO --force --region $REGION

# 7. Delete SSM Parameters (if desired)
aws ssm delete-parameter --name "/datapulse/production/DATABASE_URL" --region $REGION
aws ssm delete-parameter --name "/datapulse/production/LLM_API_KEY" --region $REGION
```

---

## 9. Connecting the Streamlit Dashboard

Set the environment variable `DATAPULSE_API_URL` on your Streamlit host:
```powershell
$env:DATAPULSE_API_URL = "https://$API_ID.execute-api.ap-south-1.amazonaws.com"
streamlit run dashboard/app.py
```

---

## 10. Estimated Ongoing Costs (Mumbai `ap-south-1`)

| Component | Pricing in `ap-south-1` | Scenario A (Portfolio / Recruiter) | Scenario B (Active Demo / 100k req) |
| :--- | :--- | :--- | :--- |
| **AWS Lambda** | $0.20/1M req + $0.0000166667/GB-s | $0.00 (Always Free Tier) | $0.00 (Within 400k GB-s Always Free) |
| **API Gateway HTTP API** | $1.00/1M requests | $0.00 (12-mo Free Tier) or $0.001 | $0.10 |
| **Amazon S3 Storage** | $0.025/GB-month | $0.00 (<50 MB) | $0.25 (10 GB data) |
| **Amazon ECR Storage** | $0.10/GB-month (>500 MB) | $0.00 (Single image <500 MB) | $0.07 (1.2 GB stored) |
| **SSM Parameter Store** | Standard parameters are free | $0.00 | $0.00 |
| **CloudWatch Logs** | $0.57/GB ingestion (7-day retention) | $0.00 (Always Free 5 GB) | $0.00 (Within 5 GB Always Free) |
| **Total Estimated Cost** | — | **$0.00 - $0.05 / month** | **$0.45 - $1.20 / month** |

*Note: Billing alerts notify of accrued charges; they do not place hard spending caps.*
