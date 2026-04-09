# 入党文档管理系统 - 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Dispatch subagents for development, testing, and QA. Keep main agent context clean.

**Goal:** 重建入党文档管理系统，支持5阶段26步骤的入党流程管理和文档管理。

**Architecture:** Flask + SQLite + Jinja2，三层审批流程（申请人→书记→管理员），红色主题前端。

**Tech Stack:** Flask, SQLAlchemy, Flask-Login, Jinja2, SQLite, pytest

---

## Phase 1: 核心系统开发

**执行模式:** Subagent-Driven Development
- 主 Agent 负责任务调度和 Code Review
- 开发 Subagent 负责实现
- 测试 Subagent 负责编写测试
- QA Subagent 负责质量检查

### 1.1 项目基础结构

**Task 1: 初始化项目结构**

**Files:**
- Create: `config.py`
- Create: `run.py`
- Create: `requirements.txt`
- Create: `app/__init__.py`

**Step 1: 创建 requirements.txt**

```txt
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Werkzeug==3.0.1
python-dotenv==1.0.0
pytest==7.4.3
pytest-flask==1.3.0
reportlab==4.0.7  # PDF导出
```

**Step 2: 创建 config.py**

```python
import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'SQLite_DB', 'cpc.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    TEMPLATE_FOLDER = os.path.join(basedir, 'templates')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
```

**Step 3: 创建 app/__init__.py (Flask Factory)**

```python
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

    # 注册蓝图
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.secretary import secretary_bp
    from app.routes.applicant import applicant_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(secretary_bp, url_prefix='/secretary')
    app.register_blueprint(applicant_bp, url_prefix='/applicant')

    # 首页路由
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
```

**Step 4: 创建 run.py**

```python
from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5001)
```

**Step 5: 创建目录结构**

```bash
mkdir -p app/routes app/templates/auth app/templates/admin app/templates/secretary app/templates/applicant app/static/css app/static/images uploads templates tests
```

**Step 6: Commit**

```bash
git add .
git commit -m "chore: initialize project structure with Flask factory pattern"
```

---

**Task 2: 数据模型**

**Files:**
- Create: `app/models.py`
- Create: `tests/test_models.py`

**Step 1: 写测试 - User 模型**

```python
# tests/test_models.py
import pytest
from app import create_app, db
from app.models import User, Branch

@pytest.fixture
def app():
    app = create_app()
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

def test_create_user(app):
    with app.app_context():
        user = User(username='test', name='测试用户', role='applicant')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        
        assert user.id is not None
        assert user.check_password('password123') is True
        assert user.check_password('wrong') is False

def test_user_roles(app):
    with app.app_context():
        admin = User(username='admin', name='管理员', role='admin')
        secretary = User(username='sec', name='书记', role='secretary')
        applicant = User(username='app', name='申请人', role='applicant')
        
        assert admin.is_admin() is True
        assert secretary.is_secretary() is True
        assert applicant.is_applicant() is True
```

**Step 2: 运行测试确认失败**

```bash
pytest tests/test_models.py -v
# Expected: FAIL - module not found
```

**Step 3: 实现 User 模型**

```python
# app/models.py
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


class User(db.Model, UserMixin):
    """用户表"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    name = db.Column(db.String(50), nullable=False)
    employee_id = db.Column(db.String(20), unique=True)
    role = db.Column(db.String(20), nullable=False, default='applicant')
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    branch = db.relationship('Branch', backref='users')
    application = db.relationship('Application', backref='user', uselist=False, lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'

    def is_secretary(self):
        return self.role == 'secretary'

    def is_contact(self):
        return self.role == 'contact'

    def is_applicant(self):
        return self.role == 'applicant'


class Branch(db.Model):
    """支部表"""
    __tablename__ = 'branches'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    applications = db.relationship('Application', backref='branch', lazy=True)


class StepDefinition(db.Model):
    """步骤定义表 - 26个入党步骤"""
    __tablename__ = 'step_definitions'

    id = db.Column(db.Integer, primary_key=True)
    step_code = db.Column(db.String(10), unique=True, nullable=False)
    stage = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    order_num = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'<StepDefinition {self.step_code}: {self.name}>'


class Application(db.Model):
    """入党申请表"""
    __tablename__ = 'applications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    current_step = db.Column(db.String(10), default='L1')
    current_stage = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='in_progress')
    apply_date = db.Column(db.Date, default=datetime.utcnow().date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    step_records = db.relationship('StepRecord', backref='application', lazy=True, cascade='all, delete-orphan')
    documents = db.relationship('Document', backref='application', lazy=True, cascade='all, delete-orphan')


class StepRecord(db.Model):
    """步骤记录表"""
    __tablename__ = 'step_records'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    step_code = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(30), default='pending')
    result = db.Column(db.Text)
    completed_at = db.Column(db.DateTime)
    completed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Document(db.Model):
    """文档表"""
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    step_code = db.Column(db.String(10))
    doc_type = db.Column(db.String(50))
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255))
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class Template(db.Model):
    """模版表"""
    __tablename__ = 'templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    stage = db.Column(db.Integer)
    step_code = db.Column(db.String(10))
    description = db.Column(db.Text)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255))
    file_path = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ContactAssignment(db.Model):
    """联系人分配表"""
    __tablename__ = 'contact_assignments'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    contact_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    application = db.relationship('Application', backref='contact_assignments')
    contact_user = db.relationship('User', backref='contact_assignments')


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


class QuarterlyReview(db.Model):
    """季度考察表"""
    __tablename__ = 'quarterly_reviews'

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)
    quarter = db.Column(db.String(20))
    review_type = db.Column(db.String(20))
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

**Step 4: 运行测试确认通过**

```bash
pytest tests/test_models.py -v
# Expected: PASS
```

**Step 5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat: add data models with tests"
```

---

### 1.2 认证系统

**Task 3: 登录/登出功能**

**Files:**
- Create: `app/routes/auth.py`
- Create: `tests/test_auth.py`

**Step 1: 写测试 - 登录**

```python
# tests/test_auth.py
import pytest
from app import create_app, db
from app.models import User

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            # 创建测试用户
            user = User(username='test', name='测试用户', role='applicant')
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()
        yield client

def test_login_success(client):
    response = client.post('/auth/login', data={
        'username': 'test',
        'password': 'password123'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'测试用户' in response.data

def test_login_wrong_password(client):
    response = client.post('/auth/login', data={
        'username': 'test',
        'password': 'wrongpassword'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'用户名或密码错误' in response.data

def test_logout(client):
    client.post('/auth/login', data={'username': 'test', 'password': 'password123'})
    response = client.get('/auth/logout', follow_redirects=True)
    assert response.status_code == 200
```

**Step 2: 运行测试确认失败**

```bash
pytest tests/test_auth.py -v
# Expected: FAIL
```

**Step 3: 实现登录路由**

```python
# app/routes/auth.py
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('账号已被禁用，请联系管理员', 'error')
                return redirect(url_for('auth.login'))
            
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        
        flash('用户名或密码错误', 'error')
    
    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已成功退出登录', 'success')
    return redirect(url_for('auth.login'))
```

**Step 4: 运行测试确认通过**

```bash
pytest tests/test_auth.py -v
# Expected: PASS
```

**Step 5: Commit**

```bash
git add app/routes/auth.py tests/test_auth.py
git commit -m "feat: add authentication routes with tests"
```

---

### 1.3 前端界面 (优先 - 使用 frontend-design skill)

> **IMPORTANT:** 使用 `superpowers:frontend-design` skill 开发前端界面。完成后发用户确认，确认后继续其他开发。

**Task 4: 基础布局和登录页面**

**Files:**
- Create: `app/templates/base.html`
- Create: `app/templates/index.html`
- Create: `app/templates/auth/login.html`
- Create: `app/static/css/style.css`
- Create: `app/static/images/` (党徽图片)

**使用 frontend-design skill 要求:**
- 红色主题: 主色 `#C41E3A`，深红 `#8B0000`，金色 `#D4AF37`
- 党徽元素
- 现代、简洁风格
- 响应式布局（PC优先）

**Step 1: 调用 frontend-design skill**

由开发 Subagent 调用 frontend-design skill 生成：
1. `base.html` - 包含头部（党徽+系统名）、导航、页脚
2. `login.html` - 登录表单页面
3. `style.css` - 红色主题样式

**Step 2: 视觉检查**

启动开发服务器，检查登录页面：
```bash
python run.py
# 访问 http://localhost:5001
```

**Step 3: 用户确认**

截图发送用户确认样式。

**Step 4: Commit（确认后）**

```bash
git add app/templates/ app/static/
git commit -m "feat: add base layout and login page with red theme"
```

---

**Task 5: 管理员仪表盘页面**

**Files:**
- Create: `app/templates/admin/dashboard.html`
- Create: `app/routes/admin.py` (基础结构)

**使用 frontend-design skill 生成:**
1. 统计卡片（总申请人、进行中、已完成、待审核）
2. 各支部人数图表
3. 各阶段分布图表
4. 最近申请列表

**Step 1: 调用 frontend-design skill**

生成管理员仪表盘页面。

**Step 2: 视觉检查**

```bash
python run.py
# 登录管理员账号访问 http://localhost:5001/admin/dashboard
```

**Step 3: 用户确认**

截图发送用户确认。

**Step 4: Commit（确认后）**

```bash
git add .
git commit -m "feat: add admin dashboard page with statistics"
```

---

**Task 6: 申请人时间线页面**

**Files:**
- Create: `app/templates/applicant/dashboard.html`
- Create: `app/templates/applicant/timeline.html`

**使用 frontend-design skill 生成:**
1. 垂直时间线展示26步
2. 5个阶段分组
3. 状态图标：●已完成 ◉进行中 ○未开始
4. 当前步骤高亮

**Step 1: 调用 frontend-design skill**

生成时间线页面。

**Step 2: 视觉检查**

**Step 3: 用户确认**

**Step 4: Commit（确认后）**

```bash
git add .
git commit -m "feat: add applicant timeline page"
```

---

**Task 7: 书记待处理列表页面**

**Files:**
- Create: `app/templates/secretary/dashboard.html`
- Create: `app/templates/secretary/applications.html`

**使用 frontend-design skill 生成:**
1. 待处理步骤列表
2. 通过/驳回/补充上传按钮
3. 文档预览区域

**Step 1-4: 同上流程**

---

**Task 8: 管理员审批页面**

**Files:**
- Create: `app/templates/admin/applications.html`
- Create: `app/templates/admin/review.html`

**使用 frontend-design skill 生成:**
1. 待审批申请列表
2. 审批详情页（文档预览+操作按钮）

**Step 1-4: 同上流程**

---

**Task 9: 通知中心页面**

**Files:**
- Create: `app/templates/shared/notifications.html`

**使用 frontend-design skill 生成:**
1. 通知列表
2. 已读/未读状态
3. 点击跳转功能

**Step 1-4: 同上流程**

---

**Task 10: 用户管理页面**

**Files:**
- Create: `app/templates/admin/users.html`
- Create: `app/templates/admin/user_form.html`

**使用 frontend-design skill 生成:**
1. 用户列表表格
2. 添加/编辑用户表单
3. 重置密码功能

**Step 1-4: 同上流程**

---

**Task 11: 支部管理页面**

**Files:**
- Create: `app/templates/admin/branches.html`

**Step 1-4: 同上流程**

---

**Task 12: 模板管理页面**

**Files:**
- Create: `app/templates/admin/templates.html`

**Step 1-4: 同上流程**

---

### 1.4 前端确认检查点

> **在此暂停，等待用户确认所有前端页面**

**确认清单：**
- [ ] 登录页面
- [ ] 管理员仪表盘
- [ ] 申请人时间线
- [ ] 书记待处理列表
- [ ] 管理员审批页面
- [ ] 通知中心
- [ ] 用户管理
- [ ] 支部管理
- [ ] 模板管理

**用户确认后继续后续开发。**

---

### 1.5 后端路由实现

**Task 13-20: 各模块路由实现**

每个任务按 TDD 流程：
1. 写测试
2. 运行确认失败
3. 实现代码
4. 运行确认通过
5. Commit

模块列表：
- Task 13: 管理员路由 (admin.py)
- Task 14: 书记路由 (secretary.py)
- Task 15: 申请人路由 (applicant.py)
- Task 16: 文档上传 API
- Task 17: 步骤审批 API
- Task 18: 通知 API
- Task 19: 统计 API
- Task 20: 导出 API

---

### 1.6 集成测试

**Task 21: 完整流程测试**

测试三层审批流程：
1. 申请人上传 → 书记审批 → 管理员确认
2. 驳回流程
3. 状态流转

---

## Phase 1 完成标准

- [ ] 所有测试通过
- [ ] 前端页面用户确认
- [ ] 核心流程可用
- [ ] 代码 Review 完成

**打第一个基线:**
```bash
git tag -a v1.0.0 -m "Phase 1 baseline - core system complete"
git push origin v1.0.0
```

---

## Phase 2: 集成测试

> **独立 Subagent 执行** - 参考 CPCWebII 集成测试文件

**Task 22: Playwright 集成测试设计**

单独派发 Subagent：
1. 研究 CPCWebII/tests/integration/ 结构
2. 设计测试场景
3. 编写 Playwright 测试

**测试场景：**
1. 用户登录流程
2. 申请人上传文档
3. 书记审批流程
4. 管理员确认流程
5. 完整26步流程
6. 导出功能

**Files:**
- Create: `tests/integration/test_login.py`
- Create: `tests/integration/test_application_flow.py`
- Create: `tests/integration/test_approval_flow.py`
- Create: `tests/integration/conftest.py`

---

## 执行策略

### Subagent 调度

| 阶段 | Subagent | 职责 |
|------|----------|------|
| 开发 | general-purpose | 实现代码，调用 frontend-design |
| 测试 | general-purpose | 编写/运行 pytest 测试 |
| QA | superpowers:code-reviewer | Code Review |
| 集成测试 | general-purpose | Playwright 测试开发 |

### 提交频率

- 每个任务完成后 Commit
- 每个功能模块完成后 Push
- Phase 1 完成后打 Tag

---

## 参考资源

- 数据库: `SQLite_DB/cpc.db` (现有)
- 模型参考: `../CPCWebII/app/models.py`
- 集成测试参考: `../CPCWeb/tests/integration/`
- 设计文档: `docs/plans/2026-04-07-party-membership-system-design.md`
