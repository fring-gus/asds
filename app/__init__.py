from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import config
from app.models import db, User


login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'error'

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def create_app(config_name='default'):
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    with app.app_context():
        db.create_all()

    # Register blueprints
    from app.routes import main
    from app.auth import auth
    from app.faculty import faculty
    from app.student import student
    from app.admin import admin_bp
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(faculty)
    app.register_blueprint(student)
    app.register_blueprint(admin_bp)

    # Rate limit auth endpoints (5 requests/minute per IP)
    auth_limit = limiter.shared_limit("5 per minute", scope="auth")
    app.view_functions['auth.login'] = auth_limit(app.view_functions['auth.login'])
    app.view_functions['auth.register'] = auth_limit(app.view_functions['auth.register'])
    app.view_functions['admin.login'] = auth_limit(app.view_functions['admin.login'])

    return app

