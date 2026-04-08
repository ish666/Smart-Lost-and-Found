pipeline {
    agent any

    stages {
        stage('Install Dependencies') {
            steps {
                sh 'pip3 install flask'
            }
        }

        stage('Run Server') {
            steps {
                sh 'python3 server.py'
            }
        }
    }
}
