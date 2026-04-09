# 入党文档管理系统 - 架构文档

## 目录
1. [系统概述](#1-系统概述)
2. [技术栈](#2-技术栈)
3. [系统架构](#3-系统架构)
4. [数据库设计](#4-数据库设计)
5. [API设计](#5-api设计)
6. [开发过程中的问题与解决方案](#6-开发过程中的问题与解决方案)
7. [部署说明](#7-部署说明)

---

## 1. 系统概述

入党文档管理系统是一个基于Flask的Web应用，用于管理党员发展全流程。系统支持多角色用户（管理员、书记、申请人），实现入党申请、文档上传、审批流程等核心功能。

### 核心功能
- 用户管理与认证
- 支部组织管理
- 文档模板管理
- 入党申请流程管理（5阶段26步骤）
- 文档上传与审核
- 进度追踪与看板

---

## 2. 技术栈

### 2.1 后端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.8+ | 编程语言 |
| Flask | 3.0.0 | Web框架 |
| SQLAlchemy | 3.1.1 | ORM数据库框架 |
| Flask-Login | 0.6.3 | 用户认证管理 |
| Werkzeug | 3.0.1 | 密码加密、文件处理 |
| python-dotenv | 1.0.0 | 环境变量管理 |
| reportlab | 4.0.7 | PDF文档生成 |

### 2.2 前端技术

| 技术 | 用途 |
|------|------|
| Jinja2 | 模板引擎 |
| 原生CSS3 | 样式（CSS变量、Flexbox、Grid） |
| 原生JavaScript | 交互逻辑（无框架） |
| SVG | 图标 |

### 2.3 数据库

| 技术 | 用途 |
|------|------|
| SQLite | 开发/小规模部署数据库 |

### 2.4 测试框架

| 技术 | 版本 | 用途 |
|------|------|------|
| pytest | 7.4.3 | 测试框架 |
| pytest-flask | 1.3.0 | Flask测试插件 |
| playwright | 1.58.0 | 端到端测试 |
| pytest-playwright | 0.7.2 | Playwright pytest集成 |

### 2.5 开发工具

| 工具 | 用途 |
|------|------|
| Git | 版本控制 |
| VS Code | IDE |
| Playwright | 浏览器自动化测试 |

---

## 3. 系统架构

### 3.1 项目结构

```
CPCWebIII/
├── app/
│   ├── __init__.py          # 应用工厂
│   ├── models.py             # 数据模型
│   ├── routes/               # 路由蓝图
│   │   ├── auth.py           # 认证路由
│   │   ├── admin.py          # 管理员路由
│   │   ├── secretary.py      # 书记路由
│   │   ├── applicant.py      # 申请人路由
│   │   └── notifications.py  # 通知路由
│   ├── templates/            # Jinja2模板
│   │   ├── base.html         # 基础布局
│   │   ├── auth/             # 认证页面
│   │   ├── admin/            # 管理员页面
│   │   ├── secretary/        # 书记页面
│   │   └── applicant/        # 申请人页面
│   └── static/
│       ├── css/style.css     # 主样式
│       └── uploads/          # 上传文件存储
├── backend/
│   └── data/cpc.db           # SQLite数据库
├── tests/
│   ├── unit/                 # 单元测试
│   └── integration/          # 集成测试
├── docs/                     # 文档
├── run.py                    # 启动脚本
├── requirements.txt          # 依赖列表
└── pytest.ini               # 测试配置
```

### 3.2 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         客户端（浏览器）                          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Flask Web 应用                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    路由层 (Blueprints)                    │   │
│  │  auth │ admin │ secretary │ applicant │ notifications   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                │                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    业务逻辑层                             │   │
│  │  用户管理 │ 审批流程 │ 文档处理 │ 通知系统                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                │                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   SQLAlchemy ORM 层                       │   │
│  │  User │ Branch │ Application │ Document │ Template       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SQLite 数据库                               │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 请求流程

```
用户请求 → Nginx(可选) → Flask路由 → Blueprint处理器 → 业务逻辑 → SQLAlchemy → SQLite
                ↓
            Jinja2模板 → HTML响应 → 浏览器渲染
```

---

## 4. 数据库设计

### 4.1 核心表结构

#### users 表
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    name VARCHAR(50) NOT NULL,
    employee_id VARCHAR(20),
    role VARCHAR(20) NOT NULL,  -- admin, secretary, applicant
    branch_id INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);
```

#### branches 表
```sql
CREATE TABLE branches (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME
);
```

#### applications 表
```sql
CREATE TABLE applications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    branch_id INTEGER NOT NULL,
    current_stage INTEGER DEFAULT 1,  -- 1-5阶段
    current_step VARCHAR(10) DEFAULT 'L1',  -- 步骤代码
    status VARCHAR(20) DEFAULT 'in_progress',  -- in_progress, completed, cancelled
    apply_date DATE,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (branch_id) REFERENCES branches(id)
);
```

#### documents 表
```sql
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL,
    step_code VARCHAR(10),
    doc_type VARCHAR(50),
    filename VARCHAR(200) NOT NULL,
    original_filename VARCHAR(200),
    file_path VARCHAR(500) NOT NULL,
    file_size INTEGER,
    uploaded_by INTEGER,
    uploaded_at DATETIME,
    FOREIGN KEY (application_id) REFERENCES applications(id),
    FOREIGN KEY (uploaded_by) REFERENCES users(id)
);
```

#### templates 表
```sql
CREATE TABLE templates (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    stage INTEGER,
    step_code VARCHAR(10),
    filename VARCHAR(200) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME
);
```

### 4.2 实体关系图

```
┌─────────┐       ┌───────────┐       ┌──────────────┐
│  User   │───┬───│  Branch   │       │   Template   │
└─────────┘   │   └───────────┘       └──────────────┘
    │         │         │
    │         │         │
    │         │    ┌────┴─────┐
    ▼         │    │          │
┌─────────────┴────┴──┐    │
│   Application       │    │
└─────────────────────┘    │
    │                      │
    ▼                      │
┌─────────────────────────┴┐
│      Document            │
└──────────────────────────┘
```

---

## 5. API设计

### 5.1 RESTful API 端点

#### 认证 API
| 方法 | 端点 | 描述 |
|------|------|------|
| GET | /auth/login | 登录页面 |
| POST | /auth/login | 登录处理 |
| GET | /auth/logout | 登出 |

#### 管理员 API
| 方法 | 端点 | 描述 |
|------|------|------|
| GET | /admin/api/users | 获取用户列表 |
| POST | /admin/api/users | 创建用户 |
| PUT | /admin/api/users/{id} | 更新用户 |
| DELETE | /admin/api/users/{id} | 删除用户 |
| GET | /admin/api/branches | 获取支部列表 |
| POST | /admin/api/branches | 创建支部 |
| PUT | /admin/api/branches/{id} | 更新支部 |
| DELETE | /admin/api/branches/{id} | 删除支部 |
| GET | /admin/api/templates | 获取模板列表 |
| POST | /admin/api/templates | 上传模板 |
| DELETE | /admin/api/templates/{id} | 删除模板 |
| GET | /admin/api/templates/{id}/download | 下载模板 |

#### 书记 API
| 方法 | 端点 | 描述 |
|------|------|------|
| GET | /secretary/api/applicants | 获取本支部申请人 |
| GET | /secretary/api/applicants/{id} | 获取申请人详情 |
| POST | /secretary/api/applicants/{id}/approve-step | 审批步骤 |
| GET | /secretary/api/documents | 获取待审核文档 |
| POST | /secretary/api/documents/{id}/review | 审核文档 |

#### 申请人 API
| 方法 | 端点 | 描述 |
|------|------|------|
| GET | /applicant/api/progress | 获取进度信息 |
| GET | /applicant/api/documents | 获取文档列表 |
| POST | /applicant/api/documents | 上传文档 |

---

## 6. 开发过程中的问题与解决方案

### 问题1: 端口冲突
**描述：** 初始使用端口5001，与其他应用冲突导致服务无法启动。

**解决方案：**
- 修改 `run.py` 中的端口为 `5003`
- 更新所有测试中的URL为 `http://127.0.0.1:5003`

```python
# run.py
app.run(debug=True, port=5003, host='0.0.0.0')
```

### 问题2: 模板变量缺失
**描述：** 页面路由未向模板传递必要的变量，导致 `UndefinedError` 或空列表。

**解决方案：**
- 更新路由函数，添加必要的变量传递

```python
# 修复前
@admin_bp.route('/users')
def users():
    return render_template('admin/users.html')

# 修复后
@admin_bp.route('/users')
def users():
    users = User.query.order_by(User.created_at.desc()).all()
    branches = Branch.query.filter_by(is_active=True).order_by(Branch.name).all()
    return render_template('admin/users.html', users=users, branches=branches)
```

### 问题3: Playwright严格模式违规
**描述：** 测试中选择器匹配到多个元素，导致测试失败。

**错误示例：**
```
Error: strict mode violation: locator("h1") resolved to 2 elements
```

**解决方案：**
- 使用更具体的选择器
- 使用 `.first()` 或 `.nth()`
- 使用ID选择器替代通用选择器

```python
# 错误方式
expect(page.locator("h1")).to_contain_text("标题")

# 正确方式
expect(page.locator(".page-title")).to_contain_text("标题")
expect(page.locator("#mainHeading")).to_contain_text("标题")
```

### 问题4: Python正则表达式语法
**描述：** Playwright的 `expect().not_to_have_url()` 需要使用 `re.compile()`，不能直接使用 `/regex/` 语法。

**错误示例：**
```python
expect(page).not_to_have_url(/.*error.*/)  # 语法错误
```

**解决方案：**
```python
import re
expect(page).not_to_have_url(re.compile(r".*error.*"))
```

### 问题5: 路由蓝图注册顺序
**描述：** 蓝图注册时 `url_prefix` 设置错误导致路由404。

**解决方案：**
- 确保蓝图注册时正确设置前缀

```python
# app/__init__.py
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(secretary_bp, url_prefix='/secretary')
app.register_blueprint(applicant_bp, url_prefix='/applicant')
```

### 问题6: 文件上传路径
**描述：** Windows环境下路径分隔符问题导致文件上传失败。

**解决方案：**
- 使用 `os.path.join()` 构建路径
- 使用 `secure_filename()` 处理文件名

```python
import os
from werkzeug.utils import secure_filename

upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'templates')
os.makedirs(upload_dir, exist_ok=True)
filename = secure_filename(original_filename)
```

### 问题7: 中文编码问题
**描述：** Python文件包含中文时需要正确设置编码声明。

**解决方案：**
- 在文件头部添加编码声明

```python
# -*- coding: utf-8 -*-
```

### 问题8: 缺失模板文件
**描述：** 部分路由引用了不存在的模板文件。

**解决方案：**
- 创建缺失的模板文件
- 主要添加了：
  - `secretary/applicants.html`
  - `secretary/documents.html`

---

## 7. 部署说明

### 7.1 生产环境配置

**环境变量 (.env):**
```env
FLASK_ENV=production
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///path/to/database.db
```

**Gunicorn启动:**
```bash
gunicorn -w 4 -b 0.0.0.0:5003 "app:create_app()"
```

### 7.2 Nginx配置示例

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5003;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /static {
        alias /path/to/CPCWebIII/app/static;
        expires 30d;
    }
}
```

### 7.3 数据库迁移

```bash
# 初始化迁移
flask db init

# 创建迁移脚本
flask db migrate -m "Initial migration"

# 应用迁移
flask db upgrade
```

---

## 附录

### A. 依赖版本锁定 (requirements.txt)

```
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Werkzeug==3.0.1
python-dotenv==1.0.0
pytest==7.4.3
pytest-flask==1.3.0
playwright==1.58.0
pytest-playwright==0.7.2
reportlab==4.0.7
```

### B. 有用的命令

```bash
# 启动开发服务器
python run.py

# 运行所有测试
pytest tests/ -v

# 运行集成测试（带浏览器）
pytest tests/integration/ -v --headed

# 运行特定测试
pytest tests/integration/test_login.py -v

# 生成测试覆盖率报告
pytest --cov=app tests/

# 初始化数据库
flask init-db
```

---

*文档版本：1.0*
*更新日期：2026年4月7日*
*作者：CPCWebIII开发团队*
