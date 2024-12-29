import os
import logging
from flask import Flask, render_template, flash, redirect, url_for, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from sqlalchemy.orm import DeclarativeBase
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
mail = Mail()  # Initialize mail first
app = Flask(__name__)

# Configuration
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "dev_key_only_for_development"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Mail configuration with better error handling
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

# Additional check for required email configuration
if not all([
    app.config['MAIL_USERNAME'],
    app.config['MAIL_PASSWORD'],
    app.config['MAIL_DEFAULT_SENDER']
]):
    app.logger.warning(
        "Email configuration incomplete. Password reset functionality may not work properly. "
        "Please ensure MAIL_USERNAME, MAIL_PASSWORD, and MAIL_DEFAULT_SENDER are set."
    )


# Initialize extensions
db.init_app(app)
mail.init_app(app)  # Initialize mail with app
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

def send_reset_email(user):
    try:
        token = user.get_reset_token()
        msg = Message(
            'Password Reset Request',
            sender=app.config['MAIL_DEFAULT_SENDER'],
            recipients=[user.email]
        )
        msg.body = f'''To reset your password, visit the following link:
{url_for('reset_password', token=token, _external=True)}

If you did not make this request then simply ignore this email and no changes will be made.
'''
        mail.send(msg)
        app.logger.info(f"Password reset email sent to {user.email}")
    except Exception as e:
        app.logger.error(f"Failed to send password reset email: {str(e)}")
        raise

# Import after app initialization to avoid circular imports
from models import User
from forms import LoginForm, RegistrationForm, RequestPasswordResetForm, ResetPasswordForm, ProfileForm

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/home')
@login_required
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            # Generate and send OTP
            otp = user.generate_otp()
            try:
                msg = Message('Your Login OTP',
                            sender=app.config['MAIL_DEFAULT_SENDER'],
                            recipients=[user.email])
                msg.body = f'Your OTP for login is: {otp}\nThis code will expire in 5 minutes.'
                mail.send(msg)
                flash('An OTP has been sent to your email.', 'info')
                return jsonify({'success': True, 'message': 'OTP sent successfully'})
            except Exception as e:
                app.logger.error(f"Failed to send OTP email: {str(e)}")
                flash('Error sending OTP. Please try again.', 'danger')
                return jsonify({'success': False, 'message': 'Failed to send OTP'})
        flash('Invalid email or password', 'danger')
    return render_template('login.html', form=form)

@app.route('/verify-otp', methods=['POST'])
def verify_otp():
    otp = request.form.get('otp')
    email = request.form.get('email')

    if not otp or not email:
        return jsonify({'success': False, 'message': 'Missing OTP or email'})

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'})

    if user.verify_otp(otp):
        login_user(user)
        return jsonify({'success': True, 'redirect': url_for('home')})
    else:
        return jsonify({'success': False, 'message': 'Invalid or expired OTP'})

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            email=form.email.data,
            username=form.username.data,
            password_hash=generate_password_hash(form.password.data)
        )
        db.session.add(user)
        try:
            db.session.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Registration failed. Please try again.', 'danger')
            app.logger.error(f"Registration error: {str(e)}")
    return render_template('register.html', form=form)

@app.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RequestPasswordResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            try:
                send_reset_email(user)
                flash('Check your email for the instructions to reset your password', 'info')
                return redirect(url_for('login'))
            except Exception as e:
                app.logger.error(f"Password reset error: {str(e)}")
                flash('An error occurred sending the password reset email. Please try again.', 'danger')
        else:
            # Don't reveal if email exists or not for security
            flash('Check your email for the instructions to reset your password', 'info')
            return redirect(url_for('login'))
    return render_template('reset_password_request.html', form=form)

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    user = User.verify_reset_token(token)
    if not user:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('reset_password_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password_hash = generate_password_hash(form.password.data)
        db.session.commit()
        flash('Your password has been updated! You can now log in', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm()
    if form.validate_on_submit():
        current_user.update_profile({
            'profile_picture': form.profile_picture.data,
            'bio': form.bio.data,
            'interests': form.interests.data,
            'location': form.location.data,
            'privacy_settings': {
                'location_visible': form.location_visible.data,
                'interests_visible': form.interests_visible.data,
                'bio_visible': form.bio_visible.data
            }
        })
        db.session.commit()
        flash('Your profile has been updated!', 'success')
        return redirect(url_for('profile'))
    elif request.method == 'GET':
        form.profile_picture.data = current_user.profile_picture
        form.bio.data = current_user.bio
        form.interests.data = current_user.interests
        form.location.data = current_user.location
        form.location_visible.data = current_user.privacy_settings.get('location_visible', True)
        form.interests_visible.data = current_user.privacy_settings.get('interests_visible', True)
        form.bio_visible.data = current_user.privacy_settings.get('bio_visible', True)
    return render_template('profile.html', form=form)


# Create tables
with app.app_context():
    db.create_all()