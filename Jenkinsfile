pipeline {
    agent any

    stages {
        stage('Install Dependencies') {
            steps {
                sh 'pip3 install flask'
            }
        }

        stage('Run Server (Test Mode)') {
            steps {
                sh 'timeout 10 python3 server.py || true'
            }
        }

        stage('Completion') {
            steps {
                echo 'Pipeline executed successfully!'
            }
        }
    }
}
