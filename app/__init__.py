from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config
from datetime import timezone, timedelta

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录'

# China Standard Time timezone (UTC+8)
CHINA_TZ = timezone(timedelta(hours=8))

def format_cn_time(value, fmt='%Y-%m-%d %H:%M'):
    """Convert a UTC datetime to China Standard Time (UTC+8) and format it.

    This Jinja2 filter is used in templates to display timestamps
    in the user's local timezone (China). The database stores times
    in UTC (via datetime.utcnow), so we add 8 hours for display.

    Args:
        value: A datetime object (assumed to be in UTC), or None
        fmt: strftime format string, default '%Y-%m-%d %H:%M'

    Returns:
        Formatted string in China time, or '-' if value is None
    """
    if value is None:
        return '-'
    # If the datetime is naive (no timezone info), assume UTC
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    # Convert to China Standard Time
    china_time = value.astimezone(CHINA_TZ)
    return china_time.strftime(fmt)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    # Register Jinja2 template filters
    app.jinja_env.filters['cn_time'] = format_cn_time

    # 注册蓝图 - 先创建空的蓝图
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.secretary import secretary_bp
    from app.routes.applicant import applicant_bp
    from app.routes.contact import contact_bp
    from app.routes.notifications import notifications_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(secretary_bp, url_prefix='/secretary')
    app.register_blueprint(applicant_bp, url_prefix='/applicant')
    app.register_blueprint(contact_bp, url_prefix='/contact')
    # 通知中心蓝图（不使用前缀，因为路由已包含完整路径）
    app.register_blueprint(notifications_bp)

    @app.route('/')
    def index():
        from flask_login import current_user
        if current_user.is_authenticated:
            from flask import redirect, url_for
            if current_user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif current_user.role == 'secretary':
                return redirect(url_for('secretary.dashboard'))
            elif current_user.role == 'contact_person':
                return redirect(url_for('contact.dashboard'))
            else:
                return redirect(url_for('applicant.dashboard'))
        from flask import render_template
        return render_template('index.html')

    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))
