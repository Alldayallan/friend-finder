from flask_login import UserMixin
from time import time
import jwt
from app import db, app
from datetime import datetime
import random
import string

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    reset_token = db.Column(db.String(500), unique=True)
    reset_token_expiry = db.Column(db.DateTime)
    # Profile fields
    profile_picture = db.Column(db.String(200))
    bio = db.Column(db.Text)
    interests = db.Column(db.Text)
    location = db.Column(db.String(120))
    privacy_settings = db.Column(db.JSON, default={
        'location_visible': True,
        'interests_visible': True,
        'bio_visible': True
    })
    # OTP fields
    otp_code = db.Column(db.String(6))
    otp_expiry = db.Column(db.DateTime)

    def __repr__(self):
        return f'<User {self.username}>'

    def get_reset_token(self, expires_in=600):
        """Generate a password reset token that expires in 10 minutes"""
        try:
            token = jwt.encode(
                {'reset_password': self.id, 'exp': time() + expires_in},
                app.config['SECRET_KEY'],
                algorithm='HS256'
            )
            self.reset_token = token
            self.reset_token_expiry = datetime.fromtimestamp(time() + expires_in)
            db.session.commit()
            return token
        except Exception as e:
            app.logger.error(f"Error generating reset token: {str(e)}")
            raise

    @staticmethod
    def verify_reset_token(token):
        """Verify the reset token"""
        try:
            id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['reset_password']
            return User.query.get(id)
        except Exception as e:
            app.logger.error(f"Error verifying reset token: {str(e)}")
            return None

    def generate_otp(self, expires_in=300):
        """Generate a 6-digit OTP that expires in 5 minutes"""
        otp = ''.join(random.choices(string.digits, k=6))
        self.otp_code = otp
        self.otp_expiry = datetime.fromtimestamp(time() + expires_in)
        db.session.commit()
        return otp

    def verify_otp(self, otp):
        """Verify the OTP code"""
        if not self.otp_code or not self.otp_expiry:
            return False
        if datetime.utcnow() > self.otp_expiry:
            return False
        return self.otp_code == otp

    def update_profile(self, data):
        """Update user profile with the provided data"""
        for field in ['bio', 'interests', 'location', 'profile_picture']:
            if field in data:
                setattr(self, field, data[field])

        if 'privacy_settings' in data:
            self.privacy_settings.update(data['privacy_settings'])