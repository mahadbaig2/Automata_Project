from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    tasks = db.relationship('Task', backref='owner', lazy=True)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    remind_time = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='Pending')
    repeat = db.Column(db.String(20), default='once')
    alert_type = db.Column(db.String(20), default='both')  # email, browser, both
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
