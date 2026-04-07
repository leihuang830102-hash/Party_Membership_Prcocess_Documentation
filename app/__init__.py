from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录'

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    # 注册蓝图 - 先创建空的蓝图
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.secretary import secretary_bp
    from app.routes.applicant import applicant_bp
    from app.routes.notifications import notifications_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(secretary_bp, url_prefix='/secretary')
    app.register_blueprint(applicant_bp, url_prefix='/applicant')
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
            else:
                return redirect(url_for('applicant.dashboard'))
        from flask import render_template
        return render_template('index.html')

    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))
