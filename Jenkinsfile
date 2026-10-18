
pipeline {
    agent any

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
                bat '''
                    @echo off
                    "C:\\Users\\hp\\AppData\\Local\\Programs\\Python\\Python310\\python.exe" --version
                    "C:\\Users\\hp\\AppData\\Local\\Programs\\Python\\Python310\\python.exe" -m venv .venv

                    call .venv\\Scripts\\activate.bat

                    python -m pip install --upgrade pip
                    pip install -r requirements.txt
                    python -m pytest -v

                    if errorlevel 1 exit /b 1
                '''
            }
        }

        stage('Build Docker Container') {
            steps {
                bat '''
                    docker --version
                    docker build --provenance=false --platform linux/amd64 -t datapulse-ai:test .
                    if errorlevel 1 exit /b 1
                '''
            }
        }
    }

    post {
        success {
            echo 'SUCCESS: DataPulse AI tests and Docker build completed. No AWS deployment was performed.'
        }

        failure {
            echo 'FAILURE: The build or tests failed. No AWS deployment was performed.'
        }

        always {
            echo 'Pipeline execution finished.'
        }
    }
}
