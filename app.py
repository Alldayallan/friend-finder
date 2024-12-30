from flask import Flask, render_template, flash, redirect, url_for, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import os
import logging
from datetime import datetime
from oauthlib.oauth2 import WebApplicationClient
from database import db
from models import User
from forms import LoginForm, RegistrationForm, RequestPasswordResetForm, ResetPasswordForm, ProfileForm
import os
from werkzeug.utils import secure_filename
from PIL import Image
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-12345')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'

db.init_app(app)

with app.app_context():
    db.create_all()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm()
    if form.validate_on_submit():
        try:
            # Handle profile picture upload
            if 'profile_picture' in request.files:
                file = request.files['profile_picture']
                if file and file.filename:
                    # Process image
                    image = Image.open(file)
                    # Resize image to 512x512
                    image = image.resize((512, 512))
                    # Convert to RGB if necessary
                    if image.mode != 'RGB':
                        image = image.convert('RGB')
                    # Save to bytes
                    img_byte_arr = io.BytesIO()
                    image.save(img_byte_arr, format='JPEG')
                    img_byte_arr = img_byte_arr.getvalue()

                    # Generate unique filename
                    filename = secure_filename(file.filename)
                    filepath = os.path.join('static', 'uploads', filename)

                    # Save processed image
                    with open(filepath, 'wb') as f:
                        f.write(img_byte_arr)

                    current_user.profile_picture = url_for('static', filename=f'uploads/{filename}')

            # Update user profile information
            current_user.bio = form.bio.data
            current_user.interests = form.interests.data
            current_user.location = form.location.data
            current_user.age = form.age.data
            current_user.looking_for = form.looking_for.data
            current_user.activities = form.activities.data
            current_user.availability = form.availability.data

            # Update privacy settings
            current_user.privacy_settings = {
                'location_visible': form.location_visible.data,
                'interests_visible': form.interests_visible.data,
                'bio_visible': form.bio_visible.data,
                'age_visible': form.age_visible.data,
                'activities_visible': form.activities_visible.data,
                'availability_visible': form.availability_visible.data
            }

            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('profile'))

        except Exception as e:
            app.logger.error(f"Profile update error: {str(e)}")
            flash('An error occurred while updating your profile.', 'danger')
            db.session.rollback()

    # Pre-populate form with current user data
    elif request.method == 'GET':
        form.bio.data = current_user.bio
        form.interests.data = current_user.interests
        form.location.data = current_user.location
        form.age.data = current_user.age
        form.looking_for.data = current_user.looking_for
        form.activities.data = current_user.activities
        form.availability.data = current_user.availability

        # Set privacy settings
        if current_user.privacy_settings:
            form.location_visible.data = current_user.privacy_settings.get('location_visible', True)
            form.interests_visible.data = current_user.privacy_settings.get('interests_visible', True)
            form.bio_visible.data = current_user.privacy_settings.get('bio_visible', True)
            form.age_visible.data = current_user.privacy_settings.get('age_visible', True)
            form.activities_visible.data = current_user.privacy_settings.get('activities_visible', True)
            form.availability_visible.data = current_user.privacy_settings.get('availability_visible', True)

    return render_template('profile.html', form=form)

if __name__ == "__main__":
    app.run(debug=True)