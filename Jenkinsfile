
pipeline {
    agent any

    options {
        timeout(time: 60, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
        disableConcurrentBuilds()
        timestamps()
    }

    environment {
        AWS_DEFAULT_REGION = 'ap-south-1'
        AWS_ACCOUNT_ID = '091336586352'
        ECR_REPOSITORY = 'datapulse-ai'
        LAMBDA_FUNCTION = 'datapulse-backend'
        AWS_CREDS_ID = 'aws-deploy-credentials'
        IMAGE_TAG = "build-${BUILD_NUMBER}"
        ECR_REGISTRY = '091336586352.dkr.ecr.ap-south-1.amazonaws.com'
        PYTHON_EXE = 'C:\\Users\\hp\\AppData\\Local\\Programs\\Python\\Python310\\python.exe'
    }

    stages {
        stage('1. Checkout') {
            steps {
                checkout scm
                bat 'git rev-parse --short HEAD'
            }
        }

        stage('2. Setup Python and Run Tests') {
            steps {
                bat '''
                    @echo off
                    "%PYTHON_EXE%" --version
                    if errorlevel 1 exit /b 1

                    if not exist .venv\\Scripts\\python.exe (
                        "%PYTHON_EXE%" -m venv .venv
                        if errorlevel 1 exit /b 1
                    )

                    call .venv\\Scripts\\activate.bat
                    python -m pip install --upgrade pip
                    if errorlevel 1 exit /b 1

                    pip install -r requirements.txt
                    if errorlevel 1 exit /b 1

                    python -m pytest -v
                    if errorlevel 1 exit /b 1
                '''
            }
        }

        stage('3. Build Docker Image') {
            steps {
                bat '''
                    @echo off
                    docker --version
                    if errorlevel 1 exit /b 1

                    docker build --provenance=false --platform linux/amd64 -t datapulse-ai:%IMAGE_TAG% .
                    if errorlevel 1 exit /b 1

                    docker image inspect datapulse-ai:%IMAGE_TAG%
                    if errorlevel 1 exit /b 1
                '''
            }
        }

        stage('4. Validate AWS Access') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'aws-deploy-credentials',
                    usernameVariable: 'AWS_ACCESS_KEY_ID',
                    passwordVariable: 'AWS_SECRET_ACCESS_KEY'
                )]) {
                    bat '''
                        @echo off
                        set AWS_PAGER=
                        set AWS_DEFAULT_REGION=ap-south-1

                        aws sts get-caller-identity --query Account --output text
                        if errorlevel 1 exit /b 1

                        aws ecr describe-repositories --repository-names datapulse-ai --region ap-south-1
                        if errorlevel 1 exit /b 1

                        aws lambda get-function --function-name datapulse-backend --region ap-south-1 --query "Configuration.[FunctionName,PackageType,State]" --output table
                        if errorlevel 1 exit /b 1
                    '''
                }
            }
        }

        stage('5. Push Image to ECR') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'aws-deploy-credentials',
                    usernameVariable: 'AWS_ACCESS_KEY_ID',
                    passwordVariable: 'AWS_SECRET_ACCESS_KEY'
                )]) {
                    bat '''
                        @echo off
                        set AWS_PAGER=
                        set AWS_DEFAULT_REGION=ap-south-1

                        aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin %ECR_REGISTRY%
                        if errorlevel 1 exit /b 1

                        docker tag datapulse-ai:%IMAGE_TAG% %ECR_REGISTRY%/%ECR_REPOSITORY%:%IMAGE_TAG%
                        if errorlevel 1 exit /b 1

                        docker push %ECR_REGISTRY%/%ECR_REPOSITORY%:%IMAGE_TAG%
                        if errorlevel 1 exit /b 1

                        aws ecr describe-images --repository-name datapulse-ai --image-ids imageTag=%IMAGE_TAG% --region ap-south-1 --query "imageDetails[0].imageDigest" --output text
                        if errorlevel 1 exit /b 1
                    '''
                }
            }
        }

        stage('6. Deploy Image to Lambda') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'aws-deploy-credentials',
                    usernameVariable: 'AWS_ACCESS_KEY_ID',
                    passwordVariable: 'AWS_SECRET_ACCESS_KEY'
                )]) {
                    bat '''
                        @echo off
                        set AWS_PAGER=
                        set AWS_DEFAULT_REGION=ap-south-1

                        aws lambda update-function-code --function-name datapulse-backend --image-uri %ECR_REGISTRY%/%ECR_REPOSITORY%:%IMAGE_TAG% --region ap-south-1
                        if errorlevel 1 exit /b 1

                        aws lambda wait function-updated --function-name datapulse-backend --region ap-south-1
                        if errorlevel 1 exit /b 1

                        aws lambda get-function --function-name datapulse-backend --region ap-south-1 --query "Configuration.[FunctionName,LastUpdateStatus,State,PackageType,LastModified]" --output table
                        if errorlevel 1 exit /b 1
                    '''
                }
            }
        }

        stage('7. Verify API Health') {
            steps {
                bat '''
                    @echo off
                    "%PYTHON_EXE%" -c "import urllib.request; u='https://e3bllh77q4.execute-api.ap-south-1.amazonaws.com/health'; r=urllib.request.urlopen(u, timeout=20); print('Health endpoint HTTP status:', r.status); print(r.read().decode()[:1000]); assert r.status == 200"
                    if errorlevel 1 exit /b 1
                '''
            }
        }
    }

    post {
        success {
            echo 'CI/CD SUCCESS: Tests passed, Docker image built, image pushed to ECR, Lambda updated, and API health check passed.'
            echo 'This does not by itself confirm that live Gemini AI analysis succeeds.'
        }

        failure {
            echo 'CI/CD FAILED. Inspect the first failing stage. An image may have been pushed or Lambda may have been updated before a later stage failed.'
        }

        always {
            echo 'DataPulse AI CI/CD pipeline finished.'
        }
    }
}
