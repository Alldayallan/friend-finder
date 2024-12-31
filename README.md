# Geo Friender

A sophisticated location-based social networking platform that revolutionizes friend discovery through intelligent geospatial matching and secure communication technologies.

## Features

### Authentication & Security
- Email/password authentication with secure signup/signin
- Password reset functionality with email verification
- OTP-based two-factor authentication
- Profile privacy controls

### Profile Management
- Customizable user profiles with profile pictures
- Bio and interest management
- Location sharing preferences
- Activity preferences and availability settings

### Friend Discovery & Management
- Advanced friend search with multiple filters:
  - Location-based search
  - Age range filtering
  - Interest matching
  - Activity preferences
  - Distance-based filtering
- Smart match scoring system
- Animated friend request system
- Friend request notifications

### Interactive Map Features
- Real-time friend location tracking
- Multiple map views (satellite, terrain)
- Nearby friends list with distance calculation
- Interactive friend markers with profile previews

### Real-time Communication
- Direct messaging system
- Real-time message notifications
- Unread message counters
- Chat history management

## Technology Stack

- Backend: Python with Flask
- Database: PostgreSQL with SQLAlchemy ORM
- Frontend: 
  - HTML5/CSS3 with Bootstrap
  - JavaScript for interactivity
  - Leaflet.js for map integration
- Real-time Features:
  - Flask-SocketIO for WebSocket communication
  - Real-time location updates
- Security:
  - Flask-Login for authentication
  - Secure password hashing
  - Email verification system

## Project Structure

```
├── app.py              # Main application file
├── models.py           # Database models
├── forms.py           # Form definitions
├── templates/         # HTML templates
│   ├── base.html
│   ├── map.html
│   ├── messages.html
│   ├── friend_requests.html
│   └── friend_suggestions.html
└── static/           # Static assets
```

## Setup Instructions

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up environment variables:
   - `DATABASE_URL`: PostgreSQL database URL
   - `MAIL_USERNAME`: Email service username
   - `MAIL_PASSWORD`: Email service password
   - `MAIL_DEFAULT_SENDER`: Default email sender

4. Initialize the database:
   ```bash
   flask db upgrade
   ```

5. Run the application:
   ```bash
   python main.py
   ```

The application will be available at `http://localhost:5000`

## Environment Variables

Required environment variables:
- `DATABASE_URL`: PostgreSQL database connection string
- `FLASK_SECRET_KEY`: Secret key for session management
- `MAIL_USERNAME`: SMTP email username
- `MAIL_PASSWORD`: SMTP email password
- `MAIL_DEFAULT_SENDER`: Default email sender address
