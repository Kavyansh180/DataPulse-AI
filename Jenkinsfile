
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
                    py -3 -m venv .venv
                    call .venv\\Scripts\\activate.bat
                    python -m pip install --upgrade pip
                    pip install -r requirements.txt
                    python -m pytest -v
                '''
            }
        }

        stage('Build Docker Container') {
            steps {
                bat '''
                    docker build --provenance=false --platform linux/amd64 -t datapulse-ai:test .
                '''
            }
        }
    }

    post {
        success {
            echo 'DataPulse AI tests and Docker build completed successfully. No AWS deployment was performed.'
        }
        failure {
            echo 'Build failed. No AWS deployment was performed.'
        }
    }
}
