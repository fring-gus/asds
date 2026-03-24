from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

main = Blueprint('main', __name__)


@main.route('/')
def index():
    """Home page — redirects logged-in users to their dashboard."""
    if current_user.is_authenticated:
        if current_user.role == 'faculty':
            return redirect(url_for('faculty.dashboard'))
        elif current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('student.dashboard'))
    return render_template('index.html')


@main.route('/home')
def home():
    """Generic home for students (until student dashboard is built)."""
    return render_template('index.html')
