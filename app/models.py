"""
Data models for the Party Membership Application Management System.
These models are compatible with the existing SQLite database schema.
"""

from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db


class User(UserMixin, db.Model):
    """User model for all system users (admin, secretary, applicant)."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    employee_id = db.Column(db.String(20))
    role = db.Column(db.String(20), nullable=False)  # admin, secretary, applicant
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    branch = db.relationship('Branch', backref='users')
    applications = db.relationship('Application', backref='user', lazy='dynamic')
    uploaded_documents = db.relationship('Document', backref='uploader', lazy='dynamic')

    def set_password(self, password):
        """Set password hash from plain text password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if provided password matches stored hash."""
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        """Check if user has admin role."""
        return self.role == 'admin'

    def is_secretary(self):
        """Check if user has secretary role."""
        return self.role == 'secretary'

    def is_applicant(self):
        """Check if user has applicant role."""
        return self.role == 'applicant'

    def __repr__(self):
        return f'<User {self.username}>'


class Branch(db.Model):
    """Party branch model."""
    __tablename__ = 'branches'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    applications = db.relationship('Application', backref='branch', lazy='dynamic')

    def __repr__(self):
        return f'<Branch {self.name}>'


class StepDefinition(db.Model):
    """Step definition for the party membership application process."""
    __tablename__ = 'step_definitions'

    id = db.Column(db.Integer, primary_key=True)
    step_code = db.Column(db.String(10), unique=True, nullable=False)  # e.g., L1, L2, A1, etc.
    stage = db.Column(db.Integer, nullable=False)  # 1-5 for different stages
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    order_num = db.Column(db.Integer, nullable=False)
    required_templates = db.Column(db.Text)  # JSON string of template IDs

    def __repr__(self):
        return f'<StepDefinition {self.step_code}: {self.name}>'


class Application(db.Model):
    """Party membership application model."""
    __tablename__ = 'applications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    current_stage = db.Column(db.Integer, default=1)
    current_step = db.Column(db.String(10), default='L1')
    status = db.Column(db.String(20), default='in_progress')  # in_progress, completed, cancelled
    apply_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    step_records = db.relationship('StepRecord', backref='application', lazy='dynamic')
    documents = db.relationship('Document', backref='application', lazy='dynamic')
    contact_assignments = db.relationship('ContactAssignment', backref='application', lazy='dynamic')
    quarterly_reviews = db.relationship('QuarterlyReview', backref='application', lazy='dynamic')

    def __init__(self, **kwargs):
        super(Application, self).__init__(**kwargs)
        if self.apply_date is None:
            self.apply_date = date.today()

    def __repr__(self):
        return f'<Application {self.id} by User {self.user_id}>'


class StepRecord(db.Model):
    """Record of each step in the application process."""
    __tablename__ = 'step_records'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    step_code = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, completed, failed
    result = db.Column(db.Text)
    completed_at = db.Column(db.DateTime)
    completed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    completer = db.relationship('User', backref='completed_steps')

    def __repr__(self):
        return f'<StepRecord App:{self.application_id} Step:{self.step_code}>'


class Document(db.Model):
    """Document model for uploaded files."""
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    step_code = db.Column(db.String(10))
    doc_type = db.Column(db.String(50))  # e.g., application_letter, thought_report
    filename = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200))
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Document {self.filename}>'


class Template(db.Model):
    """Document template model."""
    __tablename__ = 'templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    stage = db.Column(db.Integer)
    step_code = db.Column(db.String(10))
    filename = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Template {self.name}>'


class ContactAssignment(db.Model):
    """Contact person assignment for applicants."""
    __tablename__ = 'contact_assignments'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    contact_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    contact_user = db.relationship('User', backref='contact_assignments')

    def __repr__(self):
        return f'<ContactAssignment App:{self.application_id} Contact:{self.contact_user_id}>'


class QuarterlyReview(db.Model):
    """Quarterly review for activist and probationary members."""
    __tablename__ = 'quarterly_reviews'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    quarter = db.Column(db.String(20), nullable=False)  # e.g., "2024-Q1"
    review_type = db.Column(db.String(20))  # regular, special
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    reviewer = db.relationship('User', backref='quarterly_reviews')

    def __repr__(self):
        return f'<QuarterlyReview App:{self.application_id} {self.quarter}>'


class Notification(db.Model):
    """通知表"""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text)
    link = db.Column(db.String(200))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='notifications')

    def __repr__(self):
        return f'<Notification User:{self.user_id} {self.title}>'
