
from flask import Flask, render_template, flash, redirect, url_for, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from sqlalchemy.orm import DeclarativeBase
from werkzeug.security import generate_password_hash, check_password_hash
import os
import logging
from datetime import datetime
from oauthlib.oauth2 import WebApplicationClient
from models import db, User
from forms import LoginForm, RegistrationForm, RequestPasswordResetForm, ResetPasswordForm, ProfileForm

# Rest of app.py remains the same
