pipeline {
    agent any

    stages {

        stage('Checkout Backend') {
            steps {
                git branch: 'main', url: 'https://github.com/ish666/Smart-Lost-and-Found.git'
            }
        }

        stage('Setup Backend') {
            steps {
                sh 'pip3 install flask'
            }
        }

        stage('Run Backend (Test Mode)') {
            steps {
                sh '''
                python3 server.py &
                sleep 5
                pkill -f server.py || true
                '''
            }
        }

        stage('Checkout Frontend') {
            steps {
                dir('frontend') {
                    git branch: 'frontend', url: 'https://github.com/ish666/Smart-Lost-and-Found.git'
                }
            }
        }

        stage('Validate Frontend') {
            steps {
                dir('frontend') {
                    sh 'ls'
                }
            }
        }

        stage('Completion') {
            steps {
                echo 'Frontend + Backend pipeline executed successfully!'
            }
        }
    }
}
