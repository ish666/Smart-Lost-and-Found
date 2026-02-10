from db import db

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    description = db.Column(db.String(200))
    location = db.Column(db.String(100))
    status = db.Column(db.String(20), default="lost")

    def __repr__(self):
        return f"<Item {self.name}>"
