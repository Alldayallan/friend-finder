
from flask_login import UserMixin
from time import time
from datetime import datetime, timezone
import jwt
import random
import string
import os
from werkzeug.utils import secure_filename
from PIL import Image
import io
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(UserMixin, db.Model):
    # Rest of the User model code remains the same
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    reset_token = db.Column(db.String(500), unique=True)
    reset_token_expiry = db.Column(db.DateTime)
    profile_picture = db.Column(db.String(200))
    bio = db.Column(db.Text)
    interests = db.Column(db.Text)
    location = db.Column(db.String(120))
    age = db.Column(db.Integer)
    looking_for = db.Column(db.String(50))
    activities = db.Column(db.Text)
    availability = db.Column(db.String(50))
    privacy_settings = db.Column(db.JSON, default={
        'location_visible': True,
        'interests_visible': True,
        'bio_visible': True,
        'age_visible': True,
        'activities_visible': True,
        'availability_visible': True
    })
    uploaded_files = db.Column(db.JSON, default=[])
    otp_code = db.Column(db.String(6))
    otp_expiry = db.Column(db.DateTime)
