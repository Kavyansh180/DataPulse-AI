# ==============================================================================
# DataPulse AI — Production AWS Lambda Container Image
# Base: AWS Lambda Python 3.11
# ==============================================================================
FROM public.ecr.aws/lambda/python:3.11

# Set task root directory (defaults to /var/task in Lambda base image)
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy backend requirements first to optimize Docker layer caching
COPY requirements-backend.txt .

# Install dependencies directly into LAMBDA_TASK_ROOT
RUN pip install --no-cache-dir -r requirements-backend.txt --target "${LAMBDA_TASK_ROOT}"

# Copy application package
COPY app/ ${LAMBDA_TASK_ROOT}/app/

# Copy Alembic database migration scripts
COPY alembic/ ${LAMBDA_TASK_ROOT}/alembic/
COPY alembic.ini ${LAMBDA_TASK_ROOT}/alembic.ini

# Set entrypoint handler for AWS Lambda
CMD ["app.lambda_handler.handler"]
