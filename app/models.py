from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class Employee(db.Model):
    __tablename__ = 'employees'
    id = db.Column(db.Integer, primary_key=True)
    personal_number = db.Column(db.String(50), unique=True, nullable=True)
    full_name = db.Column(db.String(255), nullable=False)
    hire_date = db.Column(db.Date)
    fire_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'full_name': self.full_name,
            'hire_date': self.hire_date.isoformat() if self.hire_date else None,
            'fire_date': self.fire_date.isoformat() if self.fire_date else None,
            'is_active': self.is_active
        }

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class JobStatus(db.Model):
    __tablename__ = 'job_status'
    id = db.Column(db.Integer, primary_key=True)
    current_step = db.Column(db.String(50), default='idle')  # idle, downloading, processing, finalizing, done, error
    step_name = db.Column(db.String(100), default='Ожидание')
    progress = db.Column(db.Integer, default=0)  # 0-100
    message = db.Column(db.String(500), default='Готов к работе')
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)