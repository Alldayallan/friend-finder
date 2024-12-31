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
from models import User, UserMatch, FriendRequest, Message, ChatGroup, GroupMessage, Notification # Added FriendRequest and chat models
from forms import LoginForm, RegistrationForm, RequestPasswordResetForm, ResetPasswordForm, ProfileForm
import json
from flask_socketio import SocketIO, emit, join_room, leave_room

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

# Add to the existing app configuration
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

def send_otp_email(user_email, otp):
    try:
        subject = 'Your Login OTP'
        body = f'''Your OTP for login is: {otp}

This code will expire in 10 minutes.
If you did not request this code, please ignore this email.'''

        msg = Message(
            subject=subject,
            recipients=[user_email],
            body=body,
            sender=app.config['MAIL_DEFAULT_SENDER']
        )
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

    # Get filter parameters from request
    filters = {
        'search': request.args.get('search', ''),
        'min_age': request.args.get('min_age', type=int),
        'max_age': request.args.get('max_age', type=int),
        'activity': request.args.get('activity', ''),
        'interest': request.args.get('interest', ''),
        'max_distance': request.args.get('max_distance', type=float)
    }

    # Remove empty filters
    filters = {k: v for k, v in filters.items() if v}

    # Get friend suggestions with filters
    suggestions = current_user.get_friend_suggestions(limit=10, filters=filters)

    # Update last active timestamp
    current_user.last_active = datetime.now(timezone.utc)
    db.session.commit()

    return render_template('friend_suggestions.html', 
                         suggestions=suggestions,
                         current_filters=filters)

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

#NEW ROUTES ADDED HERE
@app.route('/send-friend-request/<int:user_id>', methods=['POST'])
@login_required
def send_friend_request(user_id):
    if user_id == current_user.id:
        flash('You cannot send a friend request to yourself.', 'error')
        return redirect(url_for('friend_suggestions'))

    # Check if request already exists
    existing_request = FriendRequest.query.filter_by(
        sender_id=current_user.id,
        receiver_id=user_id
    ).first()

    if existing_request:
        flash('Friend request already sent.', 'info')
        return redirect(url_for('friend_suggestions'))

    # Create new friend request
    friend_request = FriendRequest(sender_id=current_user.id, receiver_id=user_id)
    db.session.add(friend_request)
    db.session.commit()

    flash('Friend request sent successfully!', 'success')
    return redirect(url_for('friend_suggestions'))

@app.route('/friend-requests')
@login_required
def friend_requests():
    received_requests = FriendRequest.query.filter_by(
        receiver_id=current_user.id,
        status='pending'
    ).all()
    return render_template('friend_requests.html', requests=received_requests)

@app.route('/handle-friend-request/<int:request_id>/<string:action>')
@login_required
def handle_friend_request(request_id, action):
    friend_request = FriendRequest.query.get_or_404(request_id)

    if friend_request.receiver_id != current_user.id:
        flash('Unauthorized action', 'danger')
        return redirect(url_for('friend_requests'))

    if action == 'accept':
        # Add to friends list
        current_user.friends.append(friend_request.sender)
        friend_request.status = 'accepted'
        flash('Friend request accepted!', 'success')
    elif action == 'decline':
        friend_request.status = 'declined'
        flash('Friend request declined.', 'info')
    else:
        flash('Invalid action', 'danger')
        return redirect(url_for('friend_requests'))

    db.session.commit()
    return redirect(url_for('friend_requests'))

@app.route('/my-friends')
@login_required
def my_friends():
    return render_template('friends.html', friends=current_user.friends)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload-activity-image', methods=['POST'])
@login_required
def upload_activity_image():
    try:
        if 'activity_image' not in request.files:
            return jsonify({'success': False, 'message': 'No file provided'})

        file = request.files['activity_image']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'})

        if file and allowed_file(file.filename):
            # Process image
            image = Image.open(file)

            # Resize image maintaining aspect ratio
            max_size = (800, 800)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)

            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"activity_{current_user.id}_{timestamp}_{secure_filename(file.filename)}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            # Save processed image
            image.save(filepath, format='JPEG', quality=85)

            # Update user's activity images
            image_url = url_for('static', filename=f'uploads/{filename}')
            if not current_user.activity_images:
                current_user.activity_images = []
            current_user.activity_images.append(image_url)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Image uploaded successfully',
                'image_url': image_url
            })

    except Exception as e:
        app.logger.error(f"Image upload error: {str(e)}")
        return jsonify({'success': False, 'message': 'Error uploading image'})

    return jsonify({'success': False, 'message': 'Invalid file type'})

# SocketIO initialization
socketio = SocketIO(app, cors_allowed_origins="*")

#New Routes for Chat

@app.route('/chat/<int:user_id>')
@login_required
def chat(user_id):
    other_user = User.query.get_or_404(user_id)
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.recipient_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.recipient_id == current_user.id))
    ).order_by(Message.created_at.asc()).all()

    # Mark messages as read
    unread_messages = Message.query.filter_by(
        recipient_id=current_user.id,
        sender_id=user_id,
        is_read=False
    ).all()

    for message in unread_messages:
        message.is_read = True
    db.session.commit()

    return render_template('chat.html', other_user=other_user, messages=messages)

@app.route('/messages')
@login_required
def messages():
    # Get list of users current user has chatted with using subqueries
    sent_messages = Message.query.filter_by(sender_id=current_user.id).with_entities(Message.recipient_id).distinct()
    received_messages = Message.query.filter_by(recipient_id=current_user.id).with_entities(Message.sender_id).distinct()

    # Combine both subqueries to get all unique user IDs
    user_ids = [id[0] for id in sent_messages.union(received_messages).all()]

    # Get user objects for these IDs and all friends
    chat_partners = User.query.filter(User.id.in_(user_ids)).all()
    friends = current_user.friends.all()  # Get all friends using the relationship

    return render_template('messages.html', chat_partners=chat_partners, friends=friends)


@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(f'user_{current_user.id}')
        current_user.last_active = datetime.now(timezone.utc)
        db.session.commit()

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        leave_room(f'user_{current_user.id}')

@socketio.on('send_message')
def handle_message(data):
    if not current_user.is_authenticated:
        return

    recipient_id = data.get('recipient_id')
    content = data.get('content')
    media_url = data.get('media_url')
    media_type = data.get('media_type')

    message = Message(
        sender_id=current_user.id,
        recipient_id=recipient_id,
        content=content,
        media_url=media_url,
        media_type=media_type
    )
    db.session.add(message)

    # Create notification for recipient
    notification = Notification(
        user_id=recipient_id,
        type='message',
        content=f'New message from {current_user.username}',
        related_id=message.id
    )
    db.session.add(notification)
    db.session.commit()

    # Emit the message to both sender and recipient
    message_data = {
        'id': message.id,
        'sender_id': message.sender_id,
        'content': message.content,
        'media_url': message.media_url,
        'media_type': message.media_type,
        'created_at': message.created_at.isoformat(),
        'sender_username': current_user.username
    }

    emit('new_message', message_data, room=f'user_{recipient_id}')
    emit('new_message', message_data, room=f'user_{current_user.id}')

@app.route('/test-message/<int:recipient_id>')
@login_required
def test_message(recipient_id):
    # Create a test message
    message = Message(
        sender_id=current_user.id,
        recipient_id=recipient_id,
        content="Test message"
    )
    db.session.add(message)
    db.session.commit()

    flash('Test message sent successfully!', 'success')
    return redirect(url_for('messages'))

# Add these new routes after the existing chat routes

@app.route('/groups')
@login_required
def groups():
    return render_template('group_chat.html', active_group=None)

@app.route('/group/<int:group_id>')
@login_required
def group_chat(group_id):
    group = ChatGroup.query.get_or_404(group_id)
    messages = GroupMessage.query.filter_by(group_id=group_id).order_by(GroupMessage.created_at.asc()).all()
    return render_template('group_chat.html', active_group=group, messages=messages)

@app.route('/create-group', methods=['POST'])
@login_required
def create_group():
    name = request.form.get('name')
    member_ids = request.form.getlist('members[]')

    if not name:
        flash('Group name is required', 'error')
        return redirect(url_for('groups'))

    try:
        # Create new group
        group = ChatGroup(name=name, created_by=current_user.id)
        db.session.add(group)

        # Add creator as member
        group.members.append(current_user)

        # Add selected members
        for member_id in member_ids:
            member = User.query.get(int(member_id))
            if member and member != current_user:
                group.members.append(member)

        db.session.commit()
        flash('Group created successfully!', 'success')
        return redirect(url_for('group_chat', group_id=group.id))
    except Exception as e:
        app.logger.error(f"Group creation error: {str(e)}")
        flash('Error creating group', 'error')
        db.session.rollback()
        return redirect(url_for('groups'))

# Add these new socket event handlers after the existing ones

@socketio.on('join_group')
def handle_join_group(data):
    if not current_user.is_authenticated:
        return

    group_id = data.get('group_id')
    if group_id:
        join_room(f'group_{group_id}')
        current_user.last_active = datetime.now(timezone.utc)
        db.session.commit()

@socketio.on('group_message')
def handle_group_message(data):
    if not current_user.is_authenticated:
        return

    group_id = data.get('group_id')
    content = data.get('content')
    media_url = data.get('media_url')
    media_type = data.get('media_type')

    group = ChatGroup.query.get(group_id)
    if not group or current_user not in group.members:
        return

    message = GroupMessage(
        group_id=group_id,
        sender_id=current_user.id,
        content=content,
        media_url=media_url,
        media_type=media_type
    )
    db.session.add(message)

    # Create notifications for group members
    for member in group.members:
        if member.id != current_user.id:
            notification = Notification(
                user_id=member.id,
                type='group_message',
                content=f'New message in {group.name} from {current_user.username}',
                related_id=message.id
            )
            db.session.add(notification)

    db.session.commit()

    # Emit the message to all group members
    message_data = {
        'id': message.id,
        'sender_id': message.sender_id,
        'sender_username': current_user.username,
        'content': message.content,
        'media_url': message.media_url,
        'media_type': message.media_type,
        'created_at': message.created_at.isoformat()
    }

    emit('group_message', message_data, room=f'group_{group_id}')


@app.route('/map')
@login_required
def friend_map():
    return render_template('map.html')

@app.route('/api/friend-locations')
@login_required
def friend_locations():
    friends = current_user.friends.all()
    friend_data = []

    for friend in friends:
        if friend.latitude and friend.longitude:
            friend_data.append({
                'id': friend.id,
                'username': friend.username,
                'latitude': friend.latitude,
                'longitude': friend.longitude,
                'profile_picture': friend.profile_picture,
                'last_active': friend.last_active.isoformat() if friend.last_active else None
            })

    return jsonify(friend_data)

@app.route('/api/update-location', methods=['POST'])
@login_required
def update_location():
    data = request.get_json()

    try:
        current_user.latitude = float(data.get('latitude'))
        current_user.longitude = float(data.get('longitude'))
        current_user.last_active = datetime.now(timezone.utc)
        db.session.commit()

        # Notify friends about location update
        friend_ids = [friend.id for friend in current_user.friends]
        location_data = {
            'id': current_user.id,
            'username': current_user.username,
            'latitude': current_user.latitude,
            'longitude': current_user.longitude,
            'profile_picture': current_user.profile_picture,
            'last_active': current_user.last_active.isoformat()
        }

        for friend_id in friend_ids:
            socketio.emit('friend_location_update', location_data, room=f'user_{friend_id}')

        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Location update error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 400

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)