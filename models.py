from flask_login import UserMixin
from time import time
import jwt
from app import db, app
from datetime import datetime
import random
import string
import os
from werkzeug.utils import secure_filename
from PIL import Image
import io

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
    # File storage field
    uploaded_files = db.Column(db.JSON, default=[])
    # OTP fields
    otp_code = db.Column(db.String(6))
    otp_expiry = db.Column(db.DateTime)

    def __repr__(self):
        return f'<User {self.username}>'

    def save_profile_picture(self, file):
        """Save and resize profile picture"""
        if file:
            # Create upload directory if it doesn't exist
            upload_dir = os.path.join(app.static_folder, 'uploads', 'profile_pics')
            os.makedirs(upload_dir, exist_ok=True)

            # Secure filename and generate unique name
            filename = secure_filename(file.filename)
            unique_filename = f"{self.id}_{int(time())}_{filename}"
            file_path = os.path.join(upload_dir, unique_filename)

            # Open and resize image
            image = Image.open(file)
            image = image.convert('RGB')

            # Resize image maintaining aspect ratio
            max_size = (512, 512)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)

            # Save image
            image.save(file_path, format='JPEG', quality=85)

            # Update database with relative path
            self.profile_picture = f'/static/uploads/profile_pics/{unique_filename}'
            db.session.commit()

            return True
        return False

    def update_profile(self, data):
        """Update user profile with the provided data"""
        profile_fields = [
            'bio', 'interests', 'location', 'age', 
            'looking_for', 'activities', 'availability'
        ]

        for field in profile_fields:
            if field in data:
                setattr(self, field, data[field])

        if 'privacy_settings' in data:
            if not self.privacy_settings:
                self.privacy_settings = {}
            self.privacy_settings.update(data['privacy_settings'])

        db.session.commit()

    def get_public_profile(self):
        """Get public profile based on privacy settings"""
        profile = {
            'username': self.username,
            'profile_picture': self.profile_picture
        }

        fields = {
            'bio': 'bio_visible',
            'interests': 'interests_visible',
            'location': 'location_visible',
            'age': 'age_visible',
            'activities': 'activities_visible',
            'availability': 'availability_visible'
        }

        for field, setting in fields.items():
            if self.privacy_settings.get(setting, True):
                profile[field] = getattr(self, field)

        return profile

    def save_file(self, file):
        """Save uploaded file with metadata"""
        if file:
            # Create upload directory if it doesn't exist
            upload_dir = os.path.join(app.static_folder, 'uploads', 'user_files')
            os.makedirs(upload_dir, exist_ok=True)

            # Secure filename and generate unique name
            filename = secure_filename(file.filename)
            unique_filename = f"{self.id}_{int(time())}_{filename}"
            file_path = os.path.join(upload_dir, unique_filename)

            # Save file
            file.save(file_path)

            # Add file metadata to uploaded_files
            file_metadata = {
                'original_name': filename,
                'stored_name': unique_filename,
                'path': f'/static/uploads/user_files/{unique_filename}',
                'upload_date': datetime.utcnow().isoformat(),
                'size': os.path.getsize(file_path)
            }

            if not self.uploaded_files:
                self.uploaded_files = []

            self.uploaded_files.append(file_metadata)
            db.session.commit()

            return file_metadata
        return None

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