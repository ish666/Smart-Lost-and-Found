from flask import Flask

from db import db

from routes import routes
 
app = Flask(__name__)
 
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///lostfound.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
 
db.init_app(app)

app.register_blueprint(routes)
 
@app.route("/")

def home():

    return "Smart Lost & Found is running!"
 
if __name__ == "__main__":

    with app.app_context():

        db.create_all()

    app.run(debug=True, port=8000)

 