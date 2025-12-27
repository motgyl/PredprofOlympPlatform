from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid
from enum import Enum

db = SQLAlchemy()

class Difficulty(Enum):
    EASY = 'Easy'
    MEDIUM = 'Medium'
    HARD = 'Hard'
    INSANE = 'Insane'


# ===========================
# Database Models
# ===========================

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(50), unique=True, nullable=False)
    telegram = db.Column(db.String(100))
    password_hash = db.Column(db.Text, nullable=False)
    elo_rating = db.Column(db.Integer, default=1200)
    bio = db.Column(db.Text)
    avatar_url = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    challenges = db.relationship("Challenge", backref="author", lazy=True)
    solves = db.relationship("Solve", backref="user", lazy=True)

class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    challenges = db.relationship("Challenge", backref="category", lazy=True)

class Challenge(db.Model):
    __tablename__ = "challenges"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    hint = db.Column(db.Text)
    public_files_path = db.Column(db.Text)
    flag = db.Column(db.String(128), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    difficulty = db.Column(db.Enum(Difficulty), nullable=False)
    author_id = db.Column(db.String(36), db.ForeignKey("users.id"))
    is_active = db.Column(db.Boolean, default=True)

    solves = db.relationship("Solve", backref="challenge", lazy=True)

class Solve(db.Model):
    __tablename__ = "solves"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    challenge_id = db.Column(db.String(36), db.ForeignKey("challenges.id"), nullable=False)
    solved_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_first_blood = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "challenge_id", name="unique_user_challenge"),
    )

class MatchmakingQueue(db.Model):
    __tablename__ = "matchmaking_queue"

    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), primary_key=True)
    entered_at = db.Column(db.DateTime, default=datetime.utcnow)
    current_elo = db.Column(db.Integer, nullable=False)

