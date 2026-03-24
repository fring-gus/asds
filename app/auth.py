from functools import wraps
from urllib.parse import urlparse
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models import db, User

auth = Blueprint('auth', __name__)


def role_required(role):
    """Decorator to restrict access by role."""
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role != role:
                flash('Access denied.', 'error')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return wrapped
    return decorator


@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'student')

        # Basic validation
        if not username or not name or not email or not password:
            flash('All fields are required.', 'error')
            return render_template('auth/register.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('auth/register.html')

        if role not in ('faculty', 'student'):
            flash('Invalid role.', 'error')
            return render_template('auth/register.html')

        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            return render_template('auth/register.html')

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('auth/register.html')

        user = User(username=username, name=name, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'student')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if user.role != role:
                flash('Invalid username or password.', 'error')
                return render_template('auth/login.html')
            login_user(user)
            flash(f'Welcome, {user.name}!', 'success')
            next_page = request.args.get('next')
            if next_page:
                parsed = urlparse(next_page)
                # Only allow safe, relative redirects (no external URLs)
                if not parsed.netloc and not parsed.scheme and next_page.startswith('/'):
                    return redirect(next_page)
            # Role-based redirect
            if user.role == 'faculty':
                return redirect(url_for('faculty.dashboard'))
            elif user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('student.dashboard'))

        flash('Invalid username or password.', 'error')

    return render_template('auth/login.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'success')
    return redirect(url_for('auth.login'))
