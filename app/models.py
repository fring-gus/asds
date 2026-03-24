from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ── Association table: Students ↔ Classes (many-to-many) ──
class_students = db.Table(
    'class_students',
    db.Column('student_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('class_id', db.Integer, db.ForeignKey('class.id'), primary_key=True),
    db.Column('joined_at', db.DateTime, default=datetime.utcnow)
)


class User(UserMixin, db.Model):
    """User model — supports both Faculty and Student roles."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False, default='')
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'faculty' or 'student'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    classes_created = db.relationship('Class', backref='faculty', lazy=True)
    submissions = db.relationship('Submission', backref='student', lazy=True)
    joined_classes = db.relationship(
        'Class', secondary=class_students,
        backref=db.backref('students', lazy=True)
    )

    def set_password(self, password):
        """Hash and store the password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify a password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class Class(db.Model):
    """A class/section created by a faculty member."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_open = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    submissions = db.relationship('Submission', backref='class_', lazy=True)
    results = db.relationship('Result', backref='class_', lazy=True)

    def __repr__(self):
        return f'<Class {self.name} ({self.code})>'


class Submission(db.Model):
    """A project abstract submitted by a student."""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    project_title = db.Column(db.String(200), nullable=False)
    abstract_text = db.Column(db.Text, nullable=False)
    file_path = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending / accepted / rejected
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Submission "{self.project_title}" by User {self.student_id}>'


class Result(db.Model):
    """Pairwise similarity comparison result between two submissions."""
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    submission_1_id = db.Column(db.Integer, db.ForeignKey('submission.id'), nullable=False)
    submission_2_id = db.Column(db.Integer, db.ForeignKey('submission.id'), nullable=False)
    similarity_score = db.Column(db.Float, nullable=False)
    is_similar = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships to access the two submissions
    submission_1 = db.relationship('Submission', foreign_keys=[submission_1_id], backref='results_as_first')
    submission_2 = db.relationship('Submission', foreign_keys=[submission_2_id], backref='results_as_second')

    def __repr__(self):
        return f'<Result Sub{self.submission_1_id} vs Sub{self.submission_2_id}: {self.similarity_score:.2f}>'
