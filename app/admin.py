from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user, login_user
from app.models import db, User
from werkzeug.security import generate_password_hash

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """Decorator to restrict access to admin users only."""
    @wraps(f)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != 'admin':
            flash('Access denied. Admin only.', 'error')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return wrapped


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Admin-only login page."""
    if current_user.is_authenticated and current_user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username, role='admin').first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('admin.dashboard'))
        flash('Invalid admin credentials.', 'error')
    return render_template('admin/login.html')


@admin_bp.route('/')
@admin_required
def dashboard():
    """Admin panel — list all users."""
    users = User.query.order_by(User.role, User.username).all()
    faculty_count = User.query.filter_by(role='faculty').count()
    student_count = User.query.filter_by(role='student').count()
    admin_count = User.query.filter_by(role='admin').count()
    return render_template(
        'admin/dashboard.html',
        users=users,
        faculty_count=faculty_count,
        student_count=student_count,
        admin_count=admin_count,
    )


@admin_bp.route('/change-password', methods=['GET', 'POST'])
@admin_required
def change_password():
    """Admin — change own password."""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not current_user.check_password(current_password):
            flash('Incorrect current password.', 'error')
            return redirect(url_for('admin.change_password'))

        if len(new_password) < 8:
            flash('New password must be at least 8 characters.', 'error')
            return redirect(url_for('admin.change_password'))

        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return redirect(url_for('admin.change_password'))

        current_user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash('Password changed successfully.', 'success')
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/change_password.html')


@admin_bp.route('/add-user', methods=['GET', 'POST'])
@admin_required
def add_user():
    """Admin — add a new user."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'student')

        if not username or not name or not email or not password:
            flash('All fields are required.', 'error')
            return render_template('admin/add_user.html')

        if role not in ('faculty', 'student', 'admin'):
            flash('Invalid role.', 'error')
            return render_template('admin/add_user.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('admin/add_user.html')

        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            return render_template('admin/add_user.html')

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('admin/add_user.html')

        user = User(username=username, name=name, email=email, role=role)
        user.password_hash = generate_password_hash(password)
        db.session.add(user)
        db.session.commit()
        flash(f'User "{username}" ({role}) created successfully.', 'success')
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/add_user.html')


@admin_bp.route('/reset-password/<int:user_id>', methods=['POST'])
@admin_required
def reset_password(user_id):
    """Admin — reset a user's password to a temporary one."""
    import secrets
    import string
    
    user = User.query.get_or_404(user_id)
    
    # Prevent admin from resetting their own password here
    if user.id == current_user.id:
        flash('You cannot reset your own password here.', 'error')
        return redirect(url_for('admin.dashboard'))
        
    # Generate an 8-character random password
    alphabet = string.ascii_letters + string.digits
    temp_password = ''.join(secrets.choice(alphabet) for i in range(8))
    
    user.password_hash = generate_password_hash(temp_password)
    db.session.commit()
    
    flash(f'Password for {user.username} reset successfully. New temporary password: {temp_password}', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/delete-user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Admin — delete a user and all their data."""
    from app.models import Submission, Result, class_students
    import os, shutil
    from flask import current_app

    user = User.query.get_or_404(user_id)

    # Prevent admin from deleting themselves
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.dashboard'))

    # If faculty — delete their classes, submissions, and files
    if user.role == 'faculty':
        for cls in user.classes_created:
            # Delete files from disk
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], cls.code)
            if os.path.exists(upload_dir):
                shutil.rmtree(upload_dir)
            # Delete results and submissions for those classes
            Result.query.filter_by(class_id=cls.id).delete()
            Submission.query.filter_by(class_id=cls.id).delete()
            db.session.execute(class_students.delete().where(class_students.c.class_id == cls.id))
            db.session.delete(cls)

    # If student — delete their submissions and files
    if user.role == 'student':
        for sub in user.submissions:
            if sub.file_path and os.path.exists(sub.file_path):
                os.remove(sub.file_path)
            Result.query.filter(
                (Result.submission_1_id == sub.id) | (Result.submission_2_id == sub.id)
            ).delete(synchronize_session='fetch')
        Submission.query.filter_by(student_id=user.id).delete()
        # Remove from class associations
        db.session.execute(class_students.delete().where(class_students.c.student_id == user.id))

    db.session.delete(user)
    db.session.commit()
    flash(f'User "{user.username}" deleted.', 'success')
    return redirect(url_for('admin.dashboard'))
