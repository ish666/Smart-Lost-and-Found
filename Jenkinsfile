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
                sh '''
                python3 server.py &
                sleep 10
                pkill -f server.py || true
                '''
            }
        }

        stage('Completion') {
            steps {
                echo 'Pipeline executed successfully!'
            }
        }
    }
}
