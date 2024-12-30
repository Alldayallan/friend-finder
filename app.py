from flask import Flask, render_template, flash, redirect, url_for, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
import os
import logging
from datetime import datetime, timezone, timedelta
from oauthlib.oauth2 import WebApplicationClient
import random
import string
import io
from database import db
from models import User, UserMatch # Assuming UserMatch model exists
from forms import LoginForm, RegistrationForm, RequestPasswordResetForm, ResetPasswordForm, ProfileForm

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-12345')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Mail configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

# Initialize Flask-Mail
mail = Mail(app)

# Ensure upload directory exists
upload_dir = os.path.join('static', 'uploads')
os.makedirs(upload_dir, exist_ok=True)

def send_otp_email(user_email, otp):
    try:
        msg = Message('Your Login OTP',
                     sender=app.config['MAIL_DEFAULT_SENDER'],
                     recipients=[user_email])
        msg.body = f'''Your OTP for login is: {otp}

This code will expire in 10 minutes.
If you did not request this code, please ignore this email.'''
        mail.send(msg)
        logger.info(f"OTP email sent successfully to {user_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email: {str(e)}")
        return False

@login_manager.user_loader
def load_user(user_id):
    logger.debug(f"Loading user with ID: {user_id}")
    return User.query.get(int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    logger.info("Accessing login route")
    if current_user.is_authenticated:
        return redirect(url_for('profile'))

    form = LoginForm()
    if form.validate_on_submit():
        logger.debug(f"Attempting login for email: {form.email.data}")
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            logger.debug("User found, checking password")
            password_matches = check_password_hash(user.password_hash, form.password.data)
            logger.debug(f"Password check result: {password_matches}")
            if password_matches:
                # Generate and store OTP
                otp = ''.join(random.choices(string.digits, k=6))
                user.otp_code = otp
                user.otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)

                # Send OTP via email
                if send_otp_email(user.email, otp):
                    db.session.commit()
                    return jsonify({"success": True, "message": "OTP sent successfully"})
                else:
                    return jsonify({"success": False, "message": "Failed to send OTP. Please try again."})
            else:
                logger.debug("Password verification failed")
        else:
            logger.debug("User not found")
        return jsonify({"success": False, "message": "Invalid email or password"})

    return render_template('login.html', form=form)

@app.route('/verify-otp', methods=['POST'])
def verify_otp():
    logger.info("Verifying OTP")
    email = request.form.get('email')
    otp = request.form.get('otp')

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"success": False, "message": "User not found"})

    if not user.otp_code or not user.otp_expiry:
        return jsonify({"success": False, "message": "No OTP request found"})

    # Convert otp_expiry to UTC if it's naive
    user_otp_expiry = user.otp_expiry
    if user_otp_expiry.tzinfo is None:
        user_otp_expiry = user_otp_expiry.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > user_otp_expiry:
        return jsonify({"success": False, "message": "OTP has expired"})

    if user.otp_code != otp:
        return jsonify({"success": False, "message": "Invalid OTP"})

    login_user(user)
    user.otp_code = None
    user.otp_expiry = None
    db.session.commit()

    return jsonify({"success": True, "redirect": url_for('profile')})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/home')
@login_required
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    logger.info("Accessing register route")
    if current_user.is_authenticated:
        return redirect(url_for('profile'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data
        )
        user.password_hash = generate_password_hash(form.password.data)

        try:
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            db.session.rollback()
            flash('An error occurred during registration.', 'danger')

    return render_template('register.html', form=form)

@app.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RequestPasswordResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            # Generate reset token
            token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
            user.reset_token = token
            user.reset_token_expiry = datetime.now(timezone.utc) + timedelta(hours=24)
            db.session.commit()
            # TODO: Send password reset email
            flash('Check your email for instructions to reset your password', 'info')
            return redirect(url_for('login'))
        flash('If an account exists with that email, password reset instructions will be sent.', 'info')
        return redirect(url_for('login'))
    return render_template('reset_password_request.html', form=form)

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_expiry or datetime.now(timezone.utc) > user.reset_token_expiry:
        flash('Invalid or expired reset token', 'error')
        return redirect(url_for('login'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password_hash = generate_password_hash(form.password.data)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()
        flash('Your password has been reset.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form)

@app.route('/')
def index():
    logger.info("Accessing index route")
    return redirect(url_for('login'))

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


@app.route('/friend-suggestions')
@login_required
def friend_suggestions():
    logger.info(f"Getting friend suggestions for user {current_user.id}")

    # Get friend suggestions
    suggestions = current_user.get_friend_suggestions(limit=10)

    # Update last active timestamp
    current_user.last_active = datetime.now(timezone.utc)
    db.session.commit()

    return render_template('friend_suggestions.html', suggestions=suggestions)

@app.route('/match-response/<int:match_id>/<string:response>')
@login_required
def match_response(match_id, response):
    match = UserMatch.query.get_or_404(match_id)

    # Verify the current user is the receiver of this match
    if match.matched_user_id != current_user.id:
        flash('Unauthorized action', 'danger')
        return redirect(url_for('friend_suggestions'))

    if response not in ['accept', 'reject']:
        flash('Invalid response', 'danger')
        return redirect(url_for('friend_suggestions'))

    match.status = 'accepted' if response == 'accept' else 'rejected'
    match.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    flash(f'Successfully {response}ed the friend suggestion', 'success')
    return redirect(url_for('friend_suggestions'))


if __name__ == "__main__":
    app.run(debug=True)