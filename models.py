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
from database import db
import math
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property

class User(UserMixin, db.Model):
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
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
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
    last_active = db.Column(db.DateTime, default=func.now())

    # Relationships for friend suggestions
    sent_matches = db.relationship(
        'UserMatch',
        foreign_keys='UserMatch.user_id',
        backref='sender',
        lazy='dynamic'
    )
    received_matches = db.relationship(
        'UserMatch',
        foreign_keys='UserMatch.matched_user_id',
        backref='receiver',
        lazy='dynamic'
    )

    def get_match_score(self, other_user):
        """Calculate match score with another user based on various factors"""
        score = 0

        # Location proximity score (if both users have location data)
        if self.latitude and self.longitude and other_user.latitude and other_user.longitude:
            distance = self._calculate_distance(
                self.latitude, self.longitude,
                other_user.latitude, other_user.longitude
            )
            # Convert distance to a 0-1 score (closer = higher score)
            location_score = max(0, 1 - (distance / 100))  # 100km as max distance
            score += location_score * 0.3  # 30% weight for location

        # Interest matching score
        if self.interests and other_user.interests:
            my_interests = set(self.interests.lower().split(','))
            their_interests = set(other_user.interests.lower().split(','))
            common_interests = len(my_interests.intersection(their_interests))
            total_interests = len(my_interests.union(their_interests))
            interest_score = common_interests / total_interests if total_interests > 0 else 0
            score += interest_score * 0.3  # 30% weight for interests

        # Activity preference matching
        if self.activities and other_user.activities:
            my_activities = set(self.activities.lower().split(','))
            their_activities = set(other_user.activities.lower().split(','))
            common_activities = len(my_activities.intersection(their_activities))
            total_activities = len(my_activities.union(their_activities))
            activity_score = common_activities / total_activities if total_activities > 0 else 0
            score += activity_score * 0.2  # 20% weight for activities

        # Availability matching
        if self.availability and other_user.availability:
            availability_score = 1.0 if self.availability == other_user.availability else 0.5
            score += availability_score * 0.2  # 20% weight for availability

        return round(score, 2)

    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points using Haversine formula"""
        R = 6371  # Earth's radius in kilometers

        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return R * c

    def get_friend_suggestions(self, limit=10):
        """Get friend suggestions sorted by match score"""
        potential_friends = User.query.filter(
            User.id != self.id,
            User.looking_for == self.looking_for
        ).all()

        # Calculate scores for all potential matches
        scored_matches = [
            (user, self.get_match_score(user))
            for user in potential_friends
        ]

        # Sort by score and return top matches
        scored_matches.sort(key=lambda x: x[1], reverse=True)
        return scored_matches[:limit]

class UserMatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    matched_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    match_score = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=func.now())
    updated_at = db.Column(db.DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f'<UserMatch {self.user_id} -> {self.matched_user_id} ({self.match_score})>'