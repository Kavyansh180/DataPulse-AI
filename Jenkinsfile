pipeline {
    agent any

    environment {
        AWS_DEFAULT_REGION = 'ap-south-1'
        ECR_REPOSITORY_NAME = 'datapulse-ai'
        LAMBDA_FUNCTION_NAME = 'datapulse-backend'
        ROLE_NAME = 'datapulse-lambda-execution-role'
        SSM_PARAMETER_PATH = '/datapulse/production'
        IMAGE_TAG = "${BUILD_NUMBER}"
        // AWS credentials managed safely in Jenkins Credential Manager (never hardcoded or logged)
        AWS_CREDS = credentials('aws-deploy-credentials')
    }

    options {
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Python Dependencies & Tests') {
            steps {
                sh '''
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements.txt
                    pytest -v
                '''
            }
        }

        stage('Build Docker Container') {
            steps {
                sh '''
                    docker build --provenance=false --platform linux/amd64 -t ${ECR_REPOSITORY_NAME}:${IMAGE_TAG} .
                    docker tag ${ECR_REPOSITORY_NAME}:${IMAGE_TAG} ${ECR_REPOSITORY_NAME}:latest
                '''
            }
        }

        stage('Production Deployment Gate') {
            // Guardrail: Manual interactive approval required; only main branch can trigger deploy
            when {
                branch 'main'
            }
            steps {
                input(
                    message: "Approve deployment of build #${BUILD_NUMBER} to AWS Lambda (${AWS_DEFAULT_REGION}) via AWS CLI?",
                    ok: 'Deploy to AWS',
                    submitterParameter: 'APPROVER'
                )
                echo "Deployment approved by ${APPROVER}"
            }
        }

        stage('Push to Amazon ECR') {
            when {
                branch 'main'
            }
            steps {
                sh '''
                    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
                    ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com"
                    aws ecr get-login-password --region ${AWS_DEFAULT_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY}
                    docker tag ${ECR_REPOSITORY_NAME}:${IMAGE_TAG} ${ECR_REGISTRY}/${ECR_REPOSITORY_NAME}:${IMAGE_TAG}
                    docker tag ${ECR_REPOSITORY_NAME}:latest ${ECR_REGISTRY}/${ECR_REPOSITORY_NAME}:latest
                    docker push ${ECR_REGISTRY}/${ECR_REPOSITORY_NAME}:${IMAGE_TAG}
                    docker push ${ECR_REGISTRY}/${ECR_REPOSITORY_NAME}:latest
                '''
            }
        }

        stage('Deploy to AWS Lambda via AWS CLI') {
            when {
                branch 'main'
            }
            steps {
                sh '''
                    set -e
                    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
                    IMAGE_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}:${IMAGE_TAG}"
                    ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
                    S3_BUCKET_NAME="datapulse-storage-${ACCOUNT_ID}-${AWS_DEFAULT_REGION}"

                    echo "Starting Lambda deployment for image: ${IMAGE_URI}"
                    echo "Target region: ${AWS_DEFAULT_REGION}, function: ${LAMBDA_FUNCTION_NAME}"

                    # Query Lambda function state with robust error classification
                    set +e
                    FUNCTION_INFO=$(aws lambda get-function --function-name "${LAMBDA_FUNCTION_NAME}" --region "${AWS_DEFAULT_REGION}" 2>&1)
                    EXIT_CODE=$?
                    set -e

                    LAMBDA_ENV="Variables={ENVIRONMENT=production,DEBUG=False,APP_NAME='DataPulse AI',API_V1_PREFIX=/api/v1,ALLOWED_ORIGINS='*',ENABLE_CORS_MIDDLEWARE=False,S3_BUCKET_NAME=${S3_BUCKET_NAME},SSM_PARAMETER_PATH=${SSM_PARAMETER_PATH},DB_POOL_SIZE=1,DB_MAX_OVERFLOW=0,DB_POOL_TIMEOUT=15,DB_POOL_RECYCLE=600,MAX_UPLOAD_SIZE_BYTES=10485760,MAX_ROW_COUNT_LIMIT=1000000,LLM_PROVIDER=openai,LLM_MODEL=gpt-4o-mini}"

                    if [ $EXIT_CODE -eq 0 ]; then
                        echo "Lambda function '${LAMBDA_FUNCTION_NAME}' exists. Initiating code update..."
                        aws lambda update-function-code \
                            --function-name "${LAMBDA_FUNCTION_NAME}" \
                            --image-uri "${IMAGE_URI}" \
                            --region "${AWS_DEFAULT_REGION}"

                        echo "Waiting for function code update to complete..."
                        aws lambda wait function-updated \
                            --function-name "${LAMBDA_FUNCTION_NAME}" \
                            --region "${AWS_DEFAULT_REGION}"

                        echo "Updating Lambda runtime configuration and environment settings..."
                        aws lambda update-function-configuration \
                            --function-name "${LAMBDA_FUNCTION_NAME}" \
                            --memory-size 1024 \
                            --timeout 30 \
                            --environment "${LAMBDA_ENV}" \
                            --region "${AWS_DEFAULT_REGION}"

                        echo "Waiting for function configuration update to complete..."
                        aws lambda wait function-updated \
                            --function-name "${LAMBDA_FUNCTION_NAME}" \
                            --region "${AWS_DEFAULT_REGION}"

                    elif echo "$FUNCTION_INFO" | grep -q "ResourceNotFoundException"; then
                        echo "Lambda function '${LAMBDA_FUNCTION_NAME}' does not exist. Creating new container function..."
                        aws lambda create-function \
                            --function-name "${LAMBDA_FUNCTION_NAME}" \
                            --package-type Image \
                            --code ImageUri="${IMAGE_URI}" \
                            --role "${ROLE_ARN}" \
                            --memory-size 1024 \
                            --timeout 30 \
                            --environment "${LAMBDA_ENV}" \
                            --region "${AWS_DEFAULT_REGION}"

                        echo "Waiting for newly created Lambda container function to become Active..."
                        aws lambda wait function-active-v2 \
                            --function-name "${LAMBDA_FUNCTION_NAME}" \
                            --region "${AWS_DEFAULT_REGION}"

                    elif echo "$FUNCTION_INFO" | grep -E -q "AccessDenied|UnrecognizedClientException|InvalidClientTokenId"; then
                        echo "FATAL: AWS permission denied or invalid credentials when querying Lambda function: ${FUNCTION_INFO}" >&2
                        exit 1
                    else
                        echo "FATAL: Unexpected AWS CLI error when checking Lambda function: ${FUNCTION_INFO}" >&2
                        exit 1
                    fi

                    # Post-Deployment Health Check & Waiter Verification
                    echo "Verifying final Lambda function operational state..."
                    aws lambda wait function-active-v2 \
                        --function-name "${LAMBDA_FUNCTION_NAME}" \
                        --region "${AWS_DEFAULT_REGION}"

                    CURRENT_STATE=$(aws lambda get-function-configuration \
                        --function-name "${LAMBDA_FUNCTION_NAME}" \
                        --region "${AWS_DEFAULT_REGION}" \
                        --query "State" \
                        --output text)

                    UPDATE_STATUS=$(aws lambda get-function-configuration \
                        --function-name "${LAMBDA_FUNCTION_NAME}" \
                        --region "${AWS_DEFAULT_REGION}" \
                        --query "LastUpdateStatus" \
                        --output text)

                    echo "Lambda Function State: ${CURRENT_STATE}, LastUpdateStatus: ${UPDATE_STATUS}"

                    if [ "$CURRENT_STATE" != "Active" ] || [ "$UPDATE_STATUS" = "Failed" ]; then
                        REASON=$(aws lambda get-function-configuration \
                            --function-name "${LAMBDA_FUNCTION_NAME}" \
                            --region "${AWS_DEFAULT_REGION}" \
                            --query "LastUpdateStatusReason" \
                            --output text)
                        echo "FATAL: Lambda function failed stabilization. Reason: ${REASON}" >&2
                        exit 1
                    fi

                    echo "SUCCESS: Lambda deployment verified active and ready for traffic."
                '''
            }
        }
    }

    post {
        always {
            cleanWs(deleteDirs: true, notFailBuild: true)
        }
        success {
            echo "DataPulse AI pipeline completed successfully!"
        }
        failure {
            echo "DataPulse AI pipeline failed. Cloud resources were not modified."
        }
    }
}
