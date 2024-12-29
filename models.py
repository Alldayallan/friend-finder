from app import db
from flask_login import UserMixin
from time import time
import jwt
from app import app

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    reset_token = db.Column(db.String(120), unique=True)
    reset_token_expiry = db.Column(db.DateTime)
    # New profile fields
    profile_picture = db.Column(db.String(200))  # URL to profile picture
    bio = db.Column(db.Text)
    interests = db.Column(db.Text)
    location = db.Column(db.String(120))
    privacy_settings = db.Column(db.JSON, default={
        'location_visible': True,
        'interests_visible': True,
        'bio_visible': True
    })

    def __repr__(self):
        return f'<User {self.username}>'

    def get_reset_token(self, expires_in=600):
        """Generate a password reset token that expires in 10 minutes"""
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )

    @staticmethod
    def verify_reset_token(token):
        """Verify the reset token"""
        try:
            id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['reset_password']
        except:
            return None
        return User.query.get(id)

    def update_profile(self, data):
        """Update user profile with the provided data"""
        for field in ['bio', 'interests', 'location', 'profile_picture']:
            if field in data:
                setattr(self, field, data[field])

        if 'privacy_settings' in data:
            self.privacy_settings.update(data['privacy_settings'])