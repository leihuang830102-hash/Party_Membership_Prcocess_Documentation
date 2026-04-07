"""
Admin routes for the Party Membership Application Management System.
Handles admin dashboard, user management, branch management, template management, and approvals.
"""

import os
from datetime import datetime, date
from functools import wraps
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from app import db
from app.models import User, Branch, Template, Application, StepRecord, StepDefinition, Document

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin():
            return jsonify({'error': '无权访问'}), 403
        return f(*args, **kwargs)
    return decorated_function


# ==================== Page Routes ====================

@admin_bp.route('/dashboard')
@login_required
def dashboard():
    """Admin dashboard page with statistics and recent applications."""
    # Get statistics
    pending_count = Application.query.filter_by(status='in_progress').count()
    in_progress_count = Application.query.filter_by(status='in_progress').count()

    # Count applications created this month
    today = date.today()
    month_start = date(today.year, today.month, 1)
    monthly_new_count = Application.query.filter(
        Application.created_at >= month_start
    ).count()

    # Total users count
    total_users = User.query.count()

    # Recent applications (last 10)
    recent_applications = Application.query.order_by(
        Application.created_at.desc()
    ).limit(10).all()

    # Build recent applications data
    recent_apps_data = []
    for app in recent_applications:
        recent_apps_data.append({
            'id': app.id,
            'user_name': app.user.name if app.user else 'N/A',
            'branch_name': app.branch.name if app.branch else 'N/A',
            'status': app.status,
            'current_step': app.current_step,
            'created_at': app.created_at.strftime('%Y-%m-%d %H:%M') if app.created_at else ''
        })

    return render_template('admin/dashboard.html',
        pending_count=pending_count,
        in_progress_count=in_progress_count,
        monthly_new_count=monthly_new_count,
        total_users=total_users,
        recent_applications=recent_apps_data
    )


@admin_bp.route('/users')
@login_required
def users():
    """User management page."""
    # Get filter query parameters
    search = request.args.get('search', '').strip()
    role = request.args.get('role', '').strip()
    branch_id = request.args.get('branch', type=int)

    # Build query
    query = User.query

    if search:
        # Search by name, username, or employee_id
        query = query.filter(
            db.or_(
                User.name.contains(search),
                User.username.contains(search),
                User.employee_id.contains(search)
            )
        )

    if role:
        query = query.filter_by(role=role)

    if branch_id:
        query = query.filter_by(branch_id=branch_id)

    users = query.order_by(User.created_at.desc()).all()
    branches = Branch.query.filter_by(is_active=True).order_by(Branch.name).all()
    return render_template('admin/users.html', users=users, branches=branches)


@admin_bp.route('/branches')
@login_required
def branches():
    """Branch management page."""
    # Get search query parameter
    search = request.args.get('search', '').strip()

    # Build query
    query = Branch.query

    if search:
        # Search by name (case-insensitive, contains the keyword)
        query = query.filter(Branch.name.contains(search))

    branches = query.order_by(Branch.name).all()
    # Add applicant count to each branch (only users with role='applicant')
    for branch in branches:
        branch.applicant_count = User.query.filter_by(
            branch_id=branch.id, role='applicant'
        ).count()
    return render_template('admin/branches.html', branches=branches)


@admin_bp.route('/templates')
@login_required
def templates():
    """Template management page."""
    templates = Template.query.order_by(Template.stage, Template.step_code).all()
    return render_template('admin/templates.html', templates=templates)


@admin_bp.route('/approvals')
@login_required
def approvals():
    """Approval list page."""
    # Get filter query parameters
    status = request.args.get('status', '').strip()
    branch_id = request.args.get('branch', type=int)
    search = request.args.get('search', '').strip()

    # Build query
    query = Application.query

    if status:
        # Map status to application status
        if status == 'pending':
            query = query.filter_by(status='in_progress')
        elif status == 'approved':
            query = query.filter_by(status='completed')
        elif status == 'rejected':
            query = query.filter_by(status='cancelled')

    if branch_id:
        query = query.filter_by(branch_id=branch_id)

    if search:
        # Search by applicant name
        query = query.join(User).filter(
            db.or_(
                User.name.contains(search),
                User.username.contains(search)
            )
        )

    applications = query.order_by(Application.created_at.desc()).all()
    branches = Branch.query.filter_by(is_active=True).order_by(Branch.name).all()
    return render_template('admin/approvals.html', applications=applications, branches=branches)


@admin_bp.route('/approvals/<int:approval_id>')
@login_required
def approval_detail(approval_id):
    """Approval detail page."""
    application = Application.query.get_or_404(approval_id)

    # Get step records
    step_records = StepRecord.query.filter_by(application_id=application.id).all()
    step_record_map = {sr.step_code: sr for sr in step_records}

    # Get all step definitions
    step_definitions = StepDefinition.query.order_by(
        StepDefinition.stage, StepDefinition.order_num
    ).all()

    # Build timeline data
    timeline = []
    for step_def in step_definitions:
        record = step_record_map.get(step_def.step_code)
        timeline.append({
            'step_code': step_def.step_code,
            'name': step_def.name,
            'stage': step_def.stage,
            'status': record.status if record else 'pending',
            'result': record.result if record else None,
            'completed_at': record.completed_at if record else None
        })

    # Get documents
    documents = Document.query.filter_by(application_id=application.id).all()

    return render_template('admin/approval_detail.html',
                         application=application,
                         timeline=timeline,
                         documents=documents)


@admin_bp.route('/approvals/<int:approval_id>/review', methods=['GET', 'POST'])
@login_required
def approval_review(approval_id):
    """Approval review page."""
    application = Application.query.get_or_404(approval_id)

    if request.method == 'POST':
        action = request.form.get('action') or request.json.get('action') if request.is_json else None
        step_code = request.form.get('step_code') or request.json.get('step_code') if request.is_json else None
        result = request.form.get('result') or request.json.get('result', '') if request.is_json else ''

        if not step_code:
            if request.is_json:
                return jsonify({'success': False, 'error': '缺少步骤代码'}), 400
            flash('缺少步骤代码', 'error')
            return redirect(request.url)

        # Find step record
        step_record = StepRecord.query.filter_by(
            application_id=application.id,
            step_code=step_code
        ).first()

        if not step_record:
            step_record = StepRecord(
                application_id=application.id,
                step_code=step_code,
                status='pending'
            )
            db.session.add(step_record)

        if action == 'approve':
            step_record.status = 'completed'
            step_record.result = result
            step_record.completed_at = datetime.utcnow()
            step_record.completed_by = current_user.id

            # Move to next step
            current_step_def = StepDefinition.query.filter_by(step_code=step_code).first()
            if current_step_def:
                next_step = StepDefinition.query.filter(
                    StepDefinition.order_num > current_step_def.order_num
                ).order_by(StepDefinition.order_num).first()

                if next_step:
                    application.current_step = next_step.step_code
                    application.current_stage = next_step.stage
                else:
                    # All steps completed
                    application.status = 'completed'

        elif action == 'reject':
            step_record.status = 'failed'
            step_record.result = result

        db.session.commit()

        if request.is_json:
            return jsonify({'success': True, 'message': '审批完成'})
        flash('审批完成', 'success')
        return redirect(url_for('admin.approvals'))

    # GET request - show review form
    step_code = request.args.get('step_code', application.current_step)
    step_def = StepDefinition.query.filter_by(step_code=step_code).first()
    step_record = StepRecord.query.filter_by(
        application_id=application.id,
        step_code=step_code
    ).first()

    # Get documents for this step
    documents = Document.query.filter_by(
        application_id=application.id,
        step_code=step_code
    ).all()

    return render_template('admin/approval_review.html',
                         application=application,
                         step_def=step_def,
                         step_record=step_record,
                         documents=documents)


# ==================== User API Routes ====================

@admin_bp.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    """Get list of users with optional filters."""
    # Get query parameters
    search = request.args.get('search', '').strip()
    role = request.args.get('role', '').strip()
    branch_id = request.args.get('branch_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # Build query
    query = User.query

    if search:
        query = query.filter(
            db.or_(
                User.name.contains(search),
                User.username.contains(search),
                User.employee_id.contains(search)
            )
        )

    if role:
        query = query.filter_by(role=role)

    if branch_id:
        query = query.filter_by(branch_id=branch_id)

    # Order by creation date
    query = query.order_by(User.created_at.desc())

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    users_data = []
    for user in pagination.items:
        users_data.append({
            'id': user.id,
            'username': user.username,
            'name': user.name,
            'employee_id': user.employee_id,
            'role': user.role,
            'branch_id': user.branch_id,
            'branch_name': user.branch.name if user.branch else None,
            'is_active': user.is_active,
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None
        })

    return jsonify({
        'users': users_data,
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    })


@admin_bp.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    """Create a new user."""
    data = request.get_json()

    if not data:
        return jsonify({'error': '无效的请求数据'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')
    name = data.get('name', '').strip()
    employee_id = data.get('employee_id', '').strip()
    role = data.get('role', 'applicant')
    # Handle branch_id - convert to int if provided as string
    branch_id = data.get('branch_id')
    if branch_id is not None and isinstance(branch_id, str):
        try:
            branch_id = int(branch_id)
        except (ValueError, TypeError):
            branch_id = None

    # Validate required fields
    if not username or not password or not name:
        return jsonify({'error': '用户名、密码和姓名为必填项'}), 400

    # Check if username already exists
    if User.query.filter_by(username=username).first():
        return jsonify({'error': '用户名已存在'}), 400

    # Validate role
    valid_roles = ['admin', 'secretary', 'applicant']
    if role not in valid_roles:
        return jsonify({'error': '无效的角色类型'}), 400

    # Create user
    user = User(
        username=username,
        name=name,
        employee_id=employee_id if employee_id else None,
        role=role,
        branch_id=branch_id if branch_id else None,
        is_active=True
    )
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    return jsonify({
        'message': '用户创建成功',
        'user': {
            'id': user.id,
            'username': user.username,
            'name': user.name,
            'employee_id': user.employee_id,
            'role': user.role,
            'branch_id': user.branch_id,
            'branch_name': user.branch.name if user.branch else None,
            'is_active': user.is_active
        }
    }), 201


@admin_bp.route('/api/users/<int:id>', methods=['PUT'])
@admin_required
def update_user(id):
    """Update an existing user."""
    user = User.query.get(id)
    if not user:
        return jsonify({'error': '用户不存在'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': '无效的请求数据'}), 400

    # Update fields
    if 'name' in data:
        user.name = data['name'].strip()

    if 'employee_id' in data:
        user.employee_id = data['employee_id'].strip() if data['employee_id'] else None

    if 'role' in data:
        valid_roles = ['admin', 'secretary', 'applicant']
        if data['role'] not in valid_roles:
            return jsonify({'error': '无效的角色类型'}), 400
        user.role = data['role']

    if 'branch_id' in data:
        user.branch_id = data['branch_id'] if data['branch_id'] else None

    if 'is_active' in data:
        user.is_active = bool(data['is_active'])

    db.session.commit()

    return jsonify({
        'message': '用户更新成功',
        'user': {
            'id': user.id,
            'username': user.username,
            'name': user.name,
            'employee_id': user.employee_id,
            'role': user.role,
            'branch_id': user.branch_id,
            'branch_name': user.branch.name if user.branch else None,
            'is_active': user.is_active
        }
    })


@admin_bp.route('/api/users/<int:id>', methods=['DELETE'])
@admin_required
def delete_user(id):
    """Delete a user."""
    user = User.query.get(id)
    if not user:
        return jsonify({'error': '用户不存在'}), 404

    # Prevent deleting yourself
    if user.id == current_user.id:
        return jsonify({'error': '不能删除当前登录的用户'}), 400

    # Prevent deleting the last admin
    if user.role == 'admin':
        admin_count = User.query.filter_by(role='admin').count()
        if admin_count <= 1:
            return jsonify({'error': '不能删除最后一个管理员'}), 400

    db.session.delete(user)
    db.session.commit()

    return jsonify({'message': '用户删除成功'})


@admin_bp.route('/api/users/<int:id>/reset-password', methods=['POST'])
@admin_required
def reset_user_password(id):
    """Reset a user's password."""
    user = User.query.get(id)
    if not user:
        return jsonify({'error': '用户不存在'}), 404

    data = request.get_json()
    if not data or not data.get('new_password'):
        return jsonify({'error': '请提供新密码'}), 400

    new_password = data.get('new_password')

    # Validate password length
    if len(new_password) < 6:
        return jsonify({'error': '密码长度至少为6位'}), 400

    user.set_password(new_password)
    db.session.commit()

    return jsonify({'message': '密码重置成功'})


# ==================== Branch API Routes ====================

@admin_bp.route('/api/branches', methods=['GET'])
@admin_required
def get_branches():
    """Get list of all branches."""
    branches = Branch.query.order_by(Branch.name).all()

    branches_data = []
    for branch in branches:
        # Count members in each branch
        member_count = User.query.filter_by(branch_id=branch.id).count()
        branches_data.append({
            'id': branch.id,
            'name': branch.name,
            'description': branch.description,
            'is_active': branch.is_active,
            'member_count': member_count,
            'created_at': branch.created_at.strftime('%Y-%m-%d %H:%M:%S') if branch.created_at else None
        })

    return jsonify({'branches': branches_data})


@admin_bp.route('/api/branches', methods=['POST'])
@admin_required
def create_branch():
    """Create a new branch."""
    data = request.get_json()

    if not data:
        return jsonify({'error': '无效的请求数据'}), 400

    name = data.get('name', '').strip()
    description = data.get('description', '').strip()

    if not name:
        return jsonify({'error': '支部名称为必填项'}), 400

    # Check if branch name already exists
    if Branch.query.filter_by(name=name).first():
        return jsonify({'error': '支部名称已存在'}), 400

    branch = Branch(
        name=name,
        description=description if description else None,
        is_active=True
    )

    db.session.add(branch)
    db.session.commit()

    return jsonify({
        'message': '支部创建成功',
        'branch': {
            'id': branch.id,
            'name': branch.name,
            'description': branch.description,
            'is_active': branch.is_active
        }
    }), 201


@admin_bp.route('/api/branches/<int:id>', methods=['PUT'])
@admin_required
def update_branch(id):
    """Update an existing branch."""
    branch = Branch.query.get(id)
    if not branch:
        return jsonify({'error': '支部不存在'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': '无效的请求数据'}), 400

    if 'name' in data:
        name = data['name'].strip()
        if not name:
            return jsonify({'error': '支部名称不能为空'}), 400

        # Check if new name already exists (excluding current branch)
        existing = Branch.query.filter(Branch.name == name, Branch.id != id).first()
        if existing:
            return jsonify({'error': '支部名称已存在'}), 400

        branch.name = name

    if 'description' in data:
        branch.description = data['description'].strip() if data['description'] else None

    if 'is_active' in data:
        branch.is_active = bool(data['is_active'])

    db.session.commit()

    return jsonify({
        'message': '支部更新成功',
        'branch': {
            'id': branch.id,
            'name': branch.name,
            'description': branch.description,
            'is_active': branch.is_active
        }
    })


@admin_bp.route('/api/branches/<int:id>', methods=['DELETE'])
@admin_required
def delete_branch(id):
    """Delete a branch."""
    branch = Branch.query.get(id)
    if not branch:
        return jsonify({'error': '支部不存在'}), 404

    # Check if branch has members
    member_count = User.query.filter_by(branch_id=id).count()
    if member_count > 0:
        return jsonify({'error': f'该支部下有{member_count}名成员，无法删除'}), 400

    # Check if branch has applications
    app_count = Application.query.filter_by(branch_id=id).count()
    if app_count > 0:
        return jsonify({'error': f'该支部下有{app_count}条申请记录，无法删除'}), 400

    db.session.delete(branch)
    db.session.commit()

    return jsonify({'message': '支部删除成功'})


# ==================== Template API Routes ====================

ALLOWED_EXTENSIONS = {'doc', 'docx', 'dotx', 'pdf'}


def allowed_file(filename):
    """Check if file has allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@admin_bp.route('/api/templates', methods=['GET'])
@admin_required
def get_templates():
    """Get list of all templates."""
    templates = Template.query.order_by(Template.stage, Template.step_code).all()

    templates_data = []
    for template in templates:
        templates_data.append({
            'id': template.id,
            'name': template.name,
            'stage': template.stage,
            'step_code': template.step_code,
            'filename': template.filename,
            'description': template.description,
            'is_active': template.is_active,
            'created_at': template.created_at.strftime('%Y-%m-%d %H:%M:%S') if template.created_at else None
        })

    return jsonify({'templates': templates_data})


@admin_bp.route('/api/templates', methods=['POST'])
@admin_required
def upload_template():
    """Upload a new template."""
    # Check if file was uploaded
    if 'file' not in request.files:
        return jsonify({'error': '未上传文件'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': '不支持的文件类型，仅支持 .doc, .docx, .dotx, .pdf'}), 400

    # Get form data
    name = request.form.get('name', '').strip()
    stage = request.form.get('stage', type=int)
    step_code = request.form.get('step_code', '').strip()
    description = request.form.get('description', '').strip()

    if not name:
        return jsonify({'error': '模板名称为必填项'}), 400

    # Secure filename and save
    original_filename = file.filename
    filename = secure_filename(original_filename)

    # Add timestamp to avoid filename conflicts
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    name_part, ext = os.path.splitext(filename)
    filename = f"{name_part}_{timestamp}{ext}"

    # Ensure upload directory exists
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'templates')
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)

    # Get file size
    file_size = os.path.getsize(file_path)

    # Create template record
    template = Template(
        name=name,
        stage=stage,
        step_code=step_code if step_code else None,
        filename=filename,
        file_path=file_path,
        description=description if description else None,
        is_active=True
    )

    db.session.add(template)
    db.session.commit()

    return jsonify({
        'message': '模板上传成功',
        'template': {
            'id': template.id,
            'name': template.name,
            'stage': template.stage,
            'step_code': template.step_code,
            'filename': template.filename,
            'description': template.description,
            'is_active': template.is_active
        }
    }), 201


@admin_bp.route('/api/templates/<int:id>/download', methods=['GET'])
@admin_required
def download_template(id):
    """Download a template file."""
    from flask import send_file

    template = Template.query.get(id)
    if not template:
        return jsonify({'error': '模板不存在'}), 404

    if not os.path.exists(template.file_path):
        return jsonify({'error': '文件不存在'}), 404

    return send_file(
        template.file_path,
        as_attachment=True,
        download_name=template.filename
    )


@admin_bp.route('/api/templates/<int:id>', methods=['DELETE'])
@admin_required
def delete_template(id):
    """Delete a template."""
    template = Template.query.get(id)
    if not template:
        return jsonify({'error': '模板不存在'}), 404

    # Delete file from disk
    if template.file_path and os.path.exists(template.file_path):
        try:
            os.remove(template.file_path)
        except Exception as e:
            current_app.logger.warning(f"Failed to delete template file: {e}")

    db.session.delete(template)
    db.session.commit()

    return jsonify({'message': '模板删除成功'})


@admin_bp.route('/documents/<int:doc_id>/download')
@login_required
def download_document(doc_id):
    """Download an applicant document."""
    from flask import send_file
    document = Document.query.get_or_404(doc_id)

    if not document.file_path or not os.path.exists(document.file_path):
        flash('文件不存在', 'error')
        return redirect(request.referrer or url_for('admin.approvals'))

    return send_file(
        document.file_path,
        as_attachment=True,
        download_name=document.original_filename or document.filename
    )
