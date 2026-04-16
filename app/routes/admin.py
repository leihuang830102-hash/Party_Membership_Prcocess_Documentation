"""
Admin routes for the Party Membership Application Management System.
Handles admin dashboard, user management, branch management, template management, and approvals.
"""

import os
from datetime import datetime, date, timezone, timedelta
from functools import wraps
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func
from app import db
from app.models import User, Branch, Template, Application, StepRecord, StepDefinition, Document, Notification

# 导入工作流辅助函数
# Import workflow helper functions
try:
    from app.workflow_helpers import has_required_documents, sync_document_statuses, all_documents_approved
    _HAS_WORKFLOW_HELPERS = True
except ImportError:
    _HAS_WORKFLOW_HELPERS = False
    # 降级实现，以防 workflow_helpers 不可用
    def has_required_documents(app_id, step_code):
        return Document.query.filter_by(application_id=app_id, step_code=step_code).count() > 0
    def sync_document_statuses(app_id, step_code, review_status):
        docs = Document.query.filter_by(application_id=app_id, step_code=step_code).all()
        for doc in docs:
            doc.review_status = review_status
        return len(docs)

# China Standard Time (UTC+8) - used for consistent timestamp display
CHINA_TZ = timezone(timedelta(hours=8))


def cn_time_str(dt, fmt='%Y-%m-%d %H:%M'):
    """Format a UTC datetime to China Standard Time string."""
    if dt is None:
        return None if fmt != '' else ''
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CHINA_TZ).strftime(fmt)

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

    # Count documents pending admin review:
    # - secretary_approved: two_level steps waiting for final admin approval
    # - pending for one_level steps: secretary-submitted docs waiting for admin review
    one_level_step_codes = [sd.step_code for sd in StepDefinition.query.filter_by(approval_type='one_level').all()]
    pending_doc_count = Document.query.filter(
        db.or_(
            Document.review_status == 'secretary_approved',
            db.and_(
                Document.review_status == 'pending',
                Document.step_code.in_(one_level_step_codes)
            ) if one_level_step_codes else False
        )
    ).count()

    # Count applications by current_stage (only in_progress ones)
    # Maps each of the 5 stages to a display name
    stage_names = {
        1: '入党申请阶段',
        2: '入党积极分子阶段',
        3: '发展对象阶段',
        4: '预备党员接收阶段',
        5: '预备党员考察和转正阶段',
    }
    stage_counts_raw = db.session.query(
        Application.current_stage, func.count(Application.id)
    ).filter(
        Application.status == 'in_progress'
    ).group_by(Application.current_stage).all()
    # Build a dict {stage_number: count}, default 0 for stages with no applications
    stage_counts = {}
    for stage_num in range(1, 6):
        stage_counts[stage_num] = 0
    for stage_num, count in stage_counts_raw:
        stage_counts[stage_num] = count

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
            'created_at': cn_time_str(app.created_at) or '',
            'todo_type': 'application',
            'todo_label': '申请审批',
        })

    # Query documents awaiting admin review:
    # - secretary_approved: two_level steps (waiting for final admin approval)
    # - pending + one_level steps: secretary-submitted docs (admin is sole approver)
    pending_documents_two_level = Document.query.filter(
        Document.review_status == 'secretary_approved'
    ).order_by(Document.reviewed_at.desc()).limit(10).all()

    # One-level steps: find pending documents where the step's approval_type is 'one_level'
    one_level_step_codes = [sd.step_code for sd in StepDefinition.query.filter_by(approval_type='one_level').all()]
    pending_documents_one_level = []
    if one_level_step_codes:
        pending_documents_one_level = Document.query.filter(
            Document.review_status == 'pending',
            Document.step_code.in_(one_level_step_codes)
        ).order_by(Document.uploaded_at.desc()).limit(10).all()

    # Combine both lists
    pending_documents = list(pending_documents_two_level) + pending_documents_one_level

    # Build document review items and add them to the recent_apps_data list
    for doc in pending_documents:
        applicant = doc.application.user if doc.application else None
        applicant_name = applicant.name if applicant else '未知'
        branch_name = doc.application.branch.name if doc.application and doc.application.branch else 'N/A'

        # Resolve step definition name and approval type
        step_def = StepDefinition.query.filter_by(step_code=doc.step_code).first()
        step_name = step_def.name if step_def else (doc.step_code or '')
        approval_type = step_def.approval_type if step_def else 'two_level'

        # Determine review status label and todo type based on approval type
        if approval_type == 'one_level':
            review_label = '一级审批待审'
            todo_label = '一级审批待审'
        else:
            review_label = '待审核文档'
            todo_label = '待审核文档'

        recent_apps_data.append({
            'id': doc.application.id if doc.application else 0,
            'doc_id': doc.id,
            'user_name': applicant_name,
            'branch_name': branch_name,
            'status': doc.review_status,
            'current_step': step_name,
            'created_at': cn_time_str(doc.reviewed_at) or cn_time_str(doc.uploaded_at) or '',
            'todo_type': 'document_review',
            'todo_label': todo_label,
            'doc_name': doc.original_filename or doc.filename,
            'stage': f'第{doc.application.current_stage}阶段' if doc.application else '',
            'approval_type': approval_type,
        })

    # Sort combined list by created_at descending
    recent_apps_data.sort(key=lambda x: x['created_at'] or '', reverse=True)
    # Keep only top 15 items
    recent_apps_data = recent_apps_data[:15]

    return render_template('admin/dashboard.html',
        stats={
            'pending': pending_count,
            'in_progress': in_progress_count,
            'monthly_new': monthly_new_count,
            'total_users': total_users,
            'pending_docs': pending_doc_count,
        },
        recent_applications=recent_apps_data,
        stage_counts=stage_counts,
        stage_names=stage_names,
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

        # Validate: only the current step can be approved (sequential enforcement)
        if application.current_step != step_code:
            if request.is_json:
                return jsonify({
                    'success': False,
                    'error': f'只能审批当前步骤（当前步骤: {application.current_step}），无法跳过或乱序审批'
                }), 400
            flash(f'只能审批当前步骤（当前步骤: {application.current_step}），无法跳过或乱序审批', 'error')
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

            # Advance to the next step in sequence (always, since we validated it is the current step)
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
            'created_at': cn_time_str(user.created_at, '%Y-%m-%d %H:%M:%S')
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
        'success': True,
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


@admin_bp.route('/api/users/<int:id>', methods=['GET'])
@admin_required
def get_user(id):
    """Get a single user by ID."""
    user = User.query.get(id)
    if not user:
        return jsonify({'error': '用户不存在'}), 404

    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'name': user.name,
            'employee_id': user.employee_id,
            'role': user.role,
            'branch_id': user.branch_id,
            'is_active': user.is_active
        }
    })


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
        'success': True,
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


@admin_bp.route('/api/users/<int:id>/toggle-status', methods=['POST'])
@admin_required
def toggle_user_status(id):
    """Toggle user active status."""
    user = User.query.get(id)
    if not user:
        return jsonify({'error': '用户不存在'}), 404

    # Prevent disabling yourself
    if user.id == current_user.id:
        return jsonify({'error': '不能禁用当前登录的用户'}), 400

    user.is_active = not user.is_active
    db.session.commit()

    status_text = '启用' if user.is_active else '禁用'
    return jsonify({
        'success': True,
        'message': f'用户已{status_text}',
        'is_active': user.is_active
    })


@admin_bp.route('/api/users/<int:id>/reset-password', methods=['POST'])
@admin_required
def reset_user_password(id):
    """Reset a user's password."""
    user = User.query.get(id)
    if not user:
        return jsonify({'error': '用户不存在'}), 404

    data = request.get_json(silent=True) or {}
    # Use default password if not provided
    default_password = '123456'
    new_password = data.get('new_password') or default_password

    # Validate password length
    if len(new_password) < 6:
        return jsonify({'error': '密码长度至少为6位'}), 400

    user.set_password(new_password)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '密码重置成功',
        'default_password': default_password
    })


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
            'created_at': cn_time_str(branch.created_at, '%Y-%m-%d %H:%M:%S')
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
            'created_at': cn_time_str(template.created_at, '%Y-%m-%d %H:%M:%S')
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

    # Build safe filename preserving original extension (even for Chinese filenames)
    # secure_filename() strips Chinese characters, losing the file extension entirely
    # e.g. "入党申请书模板.docx" -> "docx" (no dot). Use os.path.splitext instead.
    original_filename = file.filename
    original_ext = os.path.splitext(original_filename)[1]  # e.g. ".docx"
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f"template_{timestamp}{original_ext}"

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


@admin_bp.route('/api/templates/<int:id>', methods=['PUT'])
@admin_required
def update_template(id):
    """Update template metadata."""
    template = Template.query.get(id)
    if not template:
        return jsonify({'error': '模板不存在'}), 404

    data = request.get_json(silent=True) or {}

    if 'name' in data:
        name = data['name'].strip()
        if not name:
            return jsonify({'error': '模板名称不能为空'}), 400
        template.name = name

    if 'stage' in data:
        template.stage = data['stage']

    if 'step_code' in data:
        template.step_code = data['step_code'].strip() or None

    if 'description' in data:
        template.description = data['description'].strip() or None

    if 'is_active' in data:
        template.is_active = bool(data['is_active'])

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '模板更新成功',
        'template': {
            'id': template.id,
            'name': template.name,
            'stage': template.stage,
            'step_code': template.step_code,
            'description': template.description,
            'is_active': template.is_active
        }
    })


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


@admin_bp.route('/api/documents/<int:doc_id>/preview')
@login_required
def preview_document(doc_id):
    """管理员在线预览文档（PDF/图片内联显示）
    仅支持 PDF 和图片格式（jpg/jpeg/png）
    """
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': '无权访问'}), 403

    doc = Document.query.get_or_404(doc_id)

    ext = os.path.splitext(doc.filename)[1].lower()
    supported = {'.pdf', '.jpg', '.jpeg', '.png'}
    if ext not in supported:
        return jsonify({'success': False, 'message': f'该格式（{ext}）不支持在线预览，请下载查看'}), 415

    if not os.path.exists(doc.file_path):
        return jsonify({'success': False, 'message': '文件不存在'}), 404

    mime_map = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
    }

    from flask import send_file as _send_file
    return _send_file(
        doc.file_path,
        as_attachment=False,
        mimetype=mime_map.get(ext, 'application/octet-stream')
    )


# ==================== Step Approval API (unified) ====================
# 统一步骤审批接口：管理员审批/驳回整个步骤，自动处理所有关联文档
# Unified step approval: admin approves/rejects the entire step,
# automatically handling all associated documents.

@admin_bp.route('/api/applications/<int:app_id>/approve-step', methods=['POST'])
@admin_required
def api_approve_step(app_id):
    """
    统一步骤审批接口：管理员审批或驳回整个步骤，自动同步所有关联文档状态。

    根据步骤的 approval_type 执行不同的审批逻辑：
    - two_level: 要求 StepRecord 为 secretary_approved（书记已审批通过）
                 审批通过 -> 步骤完成，所有文档 admin_approved，推进到下一步
                 驳回 -> 步骤失败，所有文档 admin_rejected，不推进
    - one_level: 要求 StepRecord 为 pending 且至少有一个文档存在
                 审批通过 -> 步骤完成，所有文档 admin_approved，推进到下一步
                 驳回 -> 步骤失败，所有文档 admin_rejected，不推进

    在任何审批操作前，必须确保至少存在一个文档（文件为必填项）。

    Request body:
    - step_code: 要审批的步骤代码（必需）
    - action: 'approve' 或 'reject'（必需）
    - result: 可选的备注/驳回原因
    """
    application = Application.query.get_or_404(app_id)

    # 检查申请是否在进行中
    if application.status != 'in_progress':
        return jsonify({'success': False, 'message': '该申请已结束'}), 400

    data = request.get_json()
    step_code = data.get('step_code')
    action = data.get('action')
    result_text = data.get('result', '')

    if not step_code:
        return jsonify({'success': False, 'message': '缺少步骤代码'}), 400

    if action not in ('approve', 'reject'):
        return jsonify({'success': False, 'message': '无效的操作类型，必须为 approve 或 reject'}), 400

    # 验证：只能审批当前步骤（顺序执行）
    if application.current_step != step_code:
        return jsonify({
            'success': False,
            'message': f'只能审批当前步骤（当前步骤: {application.current_step}），无法跳过或乱序审批'
        }), 400

    # 获取步骤定义
    step_def = StepDefinition.query.filter_by(step_code=step_code).first()
    if not step_def:
        return jsonify({'success': False, 'message': '无效的步骤代码'}), 400

    approval_type = getattr(step_def, 'approval_type', 'two_level')

    # none 类型步骤不应通过此接口审批（应使用 self-service-step）
    if approval_type == 'none':
        return jsonify({
            'success': False,
            'message': '无需审批的步骤请使用自助服务接口操作'
        }), 400

    # === 文件检查：审批前必须存在至少一个文档 ===
    if not has_required_documents(app_id, step_code):
        return jsonify({
            'success': False,
            'message': '请先上传相关文件'
        }), 400

    # 查找步骤记录
    step_record = StepRecord.query.filter_by(
        application_id=app_id,
        step_code=step_code
    ).first()

    # 根据 approval_type 验证步骤记录状态
    if approval_type == 'two_level':
        # 两级审批：要求步骤已通过书记审批（secretary_approved）
        if not step_record or step_record.status != 'secretary_approved':
            current_status = step_record.status if step_record else '未创建'
            return jsonify({
                'success': False,
                'message': f'两级审批步骤需先通过书记审核（当前状态: {current_status}）'
            }), 400

    elif approval_type == 'one_level':
        # 一级审批：要求步骤记录存在且有文档（已在上方检查）
        if not step_record:
            return jsonify({
                'success': False,
                'message': '步骤记录不存在，请先提交文档'
            }), 400
        # 步骤记录应为 pending 或 failed（驳回后重新提交）
        if step_record.status not in ('pending', 'failed'):
            return jsonify({
                'success': False,
                'message': f'步骤状态不正确（当前状态: {step_record.status}）'
            }), 400

    # 创建步骤记录（如果不存在且验证通过）
    if not step_record:
        step_record = StepRecord(
            application_id=app_id,
            step_code=step_code,
            status='pending'
        )
        db.session.add(step_record)

    if action == 'approve':
        # === 逐个文档审批前置检查：所有文档必须已逐个通过最终审核 ===
        # Gate check: all documents must have been individually reviewed and
        # approved at the admin level before step-level approval is allowed.
        all_approved, status_msg = all_documents_approved(
            step_code, app_id, required_status='admin_approved'
        )
        if not all_approved:
            return jsonify({
                'success': False,
                'message': f'请先审核所有文档（{status_msg}）'
            }), 400

        # 审批通过：标记步骤完成
        step_record.status = 'completed'
        step_record.result = result_text if result_text else '审批通过'
        step_record.completed_at = datetime.utcnow()
        step_record.completed_by = current_user.id

        # 注意：文档已经是 admin_approved 状态（通过逐个审批完成），
        # 无需再调用 sync_document_statuses() 批量更新。
        # 保留 sync_document_statuses 仅作为管理覆盖用。

        # 推进到下一步
        next_step = StepDefinition.query.filter(
            StepDefinition.order_num > step_def.order_num
        ).order_by(StepDefinition.order_num).first()

        next_step_info = None
        if next_step:
            application.current_step = next_step.step_code
            application.current_stage = next_step.stage
            next_step_info = {
                'step_code': next_step.step_code,
                'step_name': next_step.name,
                'stage': next_step.stage
            }
        else:
            # 所有步骤完成
            application.status = 'completed'

        # 创建通知给申请人
        notification = Notification(
            user_id=application.user_id,
            title=f'步骤审批通过: {step_def.name}',
            content=f'管理员已审批通过步骤「{step_def.name}」' +
                    (f'，备注: {result_text}' if result_text else ''),
            link=f'/applicant/applications/{application.id}',
            is_read=False
        )
        db.session.add(notification)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '步骤审批通过',
            'data': {
                'step_code': step_code,
                'step_name': step_def.name,
                'status': 'completed',
                'next_step': next_step_info,
                'application_status': application.status
            }
        })

    else:
        # 驳回：标记步骤失败
        step_record.status = 'failed'
        step_record.result = result_text if result_text else '审批不通过'
        step_record.completed_at = datetime.utcnow()
        step_record.completed_by = current_user.id

        # 统一审批模型：同步更新该步骤所有文档为 admin_rejected
        sync_document_statuses(app_id, step_code, 'admin_rejected')
        # 记录审核人和审核时间
        all_docs = Document.query.filter_by(
            application_id=app_id,
            step_code=step_code
        ).all()
        for doc in all_docs:
            doc.reviewed_by = current_user.id
            doc.reviewed_at = datetime.utcnow()

        # 不推进步骤，保持当前步骤不变

        # 创建通知给申请人
        notification = Notification(
            user_id=application.user_id,
            title=f'步骤被驳回: {step_def.name}',
            content=f'管理员驳回了步骤「{step_def.name}」' +
                    (f'，原因: {result_text}' if result_text else ''),
            link=f'/applicant/applications/{application.id}',
            is_read=False
        )
        db.session.add(notification)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '步骤已驳回',
            'data': {
                'step_code': step_code,
                'step_name': step_def.name,
                'status': 'failed',
                'result': step_record.result,
                'current_step': application.current_step
            }
        })


# ==================== Document Review API ====================

@admin_bp.route('/api/documents/<int:doc_id>', methods=['DELETE'])
@admin_required
def api_delete_document(doc_id):
    """
    Delete a document as admin.

    Admin has full permission to delete any document regardless of review status.
    This is the highest privilege level with no restrictions.
    """
    document = Document.query.get_or_404(doc_id)

    try:
        # Delete physical file from disk
        if document.file_path and os.path.exists(document.file_path):
            os.remove(document.file_path)

        # Delete database record
        db.session.delete(document)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '文档已删除'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'删除失败：{str(e)}'
        }), 500


@admin_bp.route('/api/documents/<int:doc_id>/review', methods=['POST'])
@admin_required
def api_review_document(doc_id):
    """
    逐文档审批接口 - 管理员对单个文档进行通过或驳回操作。

    支持 two_level 和 one_level 两种审批类型:
    - two_level: 审核状态为 secretary_approved 的文档（书记已审批，管理员最终审批）
                 Approve -> admin_approved
                 Reject  -> admin_rejected, 书记可重新提交
    - one_level: 审核状态为 pending 的文档（书记提交，管理员为唯一审批人）
                 Approve -> admin_approved
                 Reject  -> admin_rejected, 书记可重新提交
    - none:      不通过此接口处理（使用自助服务接口操作）

    审批单个文档后，会检查该步骤下的所有文档是否都已通过。
    如果全部通过，自动完成步骤并推进到下一步。
    如果任何文档被驳回，将步骤标记为 failed 以便提交者重新上传。

    Request body:
    - action: 'approve' or 'reject'
    - comment: optional review comment
    """
    document = Document.query.get_or_404(doc_id)

    # 获取关联的申请
    application = document.application

    data = request.get_json()
    action = data.get('action')
    comment = data.get('comment', '')

    if action not in ['approve', 'reject']:
        return jsonify({'success': False, 'message': '无效的操作类型'}), 400

    # 防止重复审核：已审核的文档不允许再次操作
    if document.review_status in ('admin_approved', 'admin_rejected'):
        return jsonify({
            'success': False,
            'message': f'文档已审核（当前状态: {document.review_status}），不可重复操作'
        }), 400

    # 查找对应的步骤定义以确定审批类型
    step_def = None
    if document.step_code:
        step_def = StepDefinition.query.filter_by(step_code=document.step_code).first()

    # 根据 approval_type 确定期望的文档状态和审批逻辑
    approval_type = step_def.approval_type if step_def else 'two_level'

    if approval_type == 'two_level':
        # 两级审批：管理员审核已通过书记审批的文档
        if document.review_status != 'secretary_approved':
            return jsonify({
                'success': False,
                'message': f'两级审批步骤的文档需先通过书记审核（当前状态: {document.review_status}）'
            }), 400
    elif approval_type == 'one_level':
        # 一级审批：管理员直接审核书记提交的文档（pending状态）
        if document.review_status != 'pending':
            return jsonify({
                'success': False,
                'message': f'一级审批步骤的文档状态不正确（当前状态: {document.review_status}，需为 pending）'
            }), 400
    else:
        # none 类型不应通过此接口审批
        return jsonify({
            'success': False,
            'message': '无需审批的步骤请使用自助服务接口操作'
        }), 400

    # 更新文档审核状态
    document.review_status = 'admin_approved' if action == 'approve' else 'admin_rejected'
    document.reviewed_by = current_user.id
    document.reviewed_at = datetime.utcnow()
    document.review_comment = comment if comment else None

    # 检查该步骤下所有文档的审核状态，决定步骤是否可以推进
    if document.step_code:
        step_record = StepRecord.query.filter_by(
            application_id=application.id,
            step_code=document.step_code
        ).first()

        if step_record:
            # 查询该步骤下所有文档
            all_step_docs = Document.query.filter_by(
                application_id=application.id,
                step_code=document.step_code
            ).all()

            if action == 'reject':
                # 任何文档被驳回，步骤标记为 failed，提交者可重新上传
                step_record.status = 'failed'
                step_record.result = f'文档审核不通过: {comment}' if comment else '文档审核不通过'
            else:
                # 文档通过，检查是否所有文档都已 admin_approved
                all_approved = all(
                    d.review_status == 'admin_approved' for d in all_step_docs
                )

                if all_approved:
                    # 所有文档都通过了，自动完成步骤并推进
                    step_record.status = 'completed'
                    step_record.result = '所有文档审核通过'
                    step_record.completed_at = datetime.utcnow()
                    step_record.completed_by = current_user.id

                    # 如果该步骤是申请的当前步骤，则推进到下一步
                    if application.current_step == document.step_code:
                        if step_def:
                            next_step = StepDefinition.query.filter(
                                StepDefinition.order_num > step_def.order_num
                            ).order_by(StepDefinition.order_num).first()
                            if next_step:
                                application.current_step = next_step.step_code
                                application.current_stage = next_step.stage
                            else:
                                application.status = 'completed'
                else:
                    # 还有未审核的文档，步骤保持 in_progress 不变
                    pass

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '文档已审核通过' if action == 'approve' else '文档已驳回',
        'data': {
            'document_id': doc_id,
            'review_status': document.review_status
        }
    })


# ==================== Self-Service Step API (none-type steps) ====================
# 对于 approval_type='none' 的步骤（如 L12, L15-L17, L25, L26），
# 管理员直接操作完成，无需文档审批流程。

@admin_bp.route('/api/self-service-step/<int:app_id>', methods=['POST'])
@admin_required
def api_self_service_step(app_id):
    """
    管理员自助完成无需审批的步骤（approval_type='none'）。

    用于管理员直接操作完成的步骤，如 L12（上级党委预审）等。
    可选附带文件上传（multipart form）或仅确认完成（JSON）。

    JSON body:
    - step_code: 要完成的步骤代码（如 'L12'）
    - result: 可选的备注说明

    Multipart form:
    - step_code: 要完成的步骤代码
    - result: 可选备注
    - file: 可选的文件上传
    - doc_type: 文件类型（如 'general'）
    """
    application = Application.query.get_or_404(app_id)

    # 支持两种请求格式：JSON 或 multipart form
    if request.is_json:
        data = request.get_json()
        step_code = data.get('step_code', '').strip()
        result_text = data.get('result', '').strip()
    else:
        step_code = request.form.get('step_code', '').strip()
        result_text = request.form.get('result', '').strip()

    if not step_code:
        return jsonify({'success': False, 'error': '缺少步骤代码'}), 400

    # 验证：步骤定义必须存在且 approval_type 为 'none'
    step_def = StepDefinition.query.filter_by(step_code=step_code).first()
    if not step_def:
        return jsonify({'success': False, 'error': f'步骤 {step_code} 不存在'}), 400

    if step_def.approval_type != 'none':
        return jsonify({
            'success': False,
            'error': f'步骤 {step_code} 不是自助服务步骤（approval_type={step_def.approval_type}）'
        }), 400

    # 验证：只能完成当前步骤（顺序执行）
    if application.current_step != step_code:
        return jsonify({
            'success': False,
            'error': f'只能操作当前步骤（当前步骤: {application.current_step}，请求步骤: {step_code}）'
        }), 400

    # 处理可选的文件上传（multipart form 中包含 file 字段时）
    uploaded_doc = None
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:
            # 检查文件扩展名
            doc_allowed_ext = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png'}
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            if ext not in doc_allowed_ext:
                return jsonify({
                    'success': False,
                    'error': '不支持的文件类型，请上传 PDF、Word、Excel 或图片文件'
                }), 400

            # Build safe filename preserving original extension (even for Chinese filenames)
            # secure_filename() strips Chinese characters, losing the file extension entirely
            doc_type = request.form.get('doc_type', 'general')
            original_filename = file.filename
            original_ext = os.path.splitext(file.filename)[1]  # e.g. ".pdf"
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{current_user.id}_{timestamp}{original_ext}"

            # 确保上传目录存在
            upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'documents')
            os.makedirs(upload_dir, exist_ok=True)

            file_path = os.path.join(upload_dir, unique_filename)
            file.save(file_path)
            file_size = os.path.getsize(file_path)

            # 创建文档记录（管理员自助上传直接标记为 admin_approved）
            uploaded_doc = Document(
                application_id=application.id,
                step_code=step_code,
                doc_type=doc_type,
                filename=unique_filename,
                original_filename=original_filename,
                file_path=file_path,
                file_size=file_size,
                uploaded_by=current_user.id,
                review_status='admin_approved'  # 自助上传自动通过
            )
            db.session.add(uploaded_doc)

    # === 文件检查：确认完成前必须存在至少一个文档 ===
    # 统一审批模型要求：任何步骤完成操作都必须有文档支撑
    # 如果本次请求没有上传文件（uploaded_doc is None），检查是否已有之前的文档
    if uploaded_doc is None and not has_required_documents(application.id, step_code):
        return jsonify({
            'success': False,
            'error': '请先上传相关文件后再确认完成'
        }), 400

    # 查找或创建步骤记录
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

    # 标记步骤完成
    step_record.status = 'completed'
    step_record.result = result_text if result_text else '管理员自助完成'
    step_record.completed_at = datetime.utcnow()
    step_record.completed_by = current_user.id

    # 推进到下一步
    next_step = StepDefinition.query.filter(
        StepDefinition.order_num > step_def.order_num
    ).order_by(StepDefinition.order_num).first()

    next_step_info = None
    if next_step:
        application.current_step = next_step.step_code
        application.current_stage = next_step.stage
        next_step_info = {
            'step_code': next_step.step_code,
            'step_name': next_step.name,
            'stage': next_step.stage
        }
    else:
        application.status = 'completed'

    # 创建通知给申请人
    notification = Notification(
        user_id=application.user_id,
        title=f'步骤已完成: {step_def.name}',
        content=f'管理员已确认完成步骤「{step_def.name}」' +
                (f'，备注: {result_text}' if result_text else ''),
        link=f'/applicant/applications/{application.id}',
        is_read=False
    )
    db.session.add(notification)

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'步骤「{step_def.name}」已完成',
        'data': {
            'step_code': step_code,
            'step_name': step_def.name,
            'status': 'completed',
            'next_step': next_step_info,
            'document': {
                'id': uploaded_doc.id,
                'filename': uploaded_doc.original_filename
            } if uploaded_doc else None
        }
    })


@admin_bp.route('/api/self-service-step/<int:app_id>/upload', methods=['POST'])
@admin_required
def api_self_service_step_upload(app_id):
    """
    管理员自助上传文档（不推进步骤）。

    用于 none 类型步骤的文件上传，上传后文档自动标记为 admin_approved。
    管理员上传文件后仍需通过 self-service-step 接口确认完成步骤。

    Multipart form:
    - file: 上传的文件（必需）
    - step_code: 步骤代码（必需）
    - doc_type: 文件类型（可选，默认 'general'）
    """
    application = Application.query.get_or_404(app_id)

    # 验证文件上传
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '未上传文件'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'}), 400

    # 获取表单参数
    step_code = request.form.get('step_code', '').strip()
    doc_type = request.form.get('doc_type', 'general')

    if not step_code:
        return jsonify({'success': False, 'error': '缺少步骤代码'}), 400

    # 验证步骤定义
    step_def = StepDefinition.query.filter_by(step_code=step_code).first()
    if not step_def:
        return jsonify({'success': False, 'error': f'步骤 {step_code} 不存在'}), 400

    if step_def.approval_type != 'none':
        return jsonify({
            'success': False,
            'error': f'步骤 {step_code} 不是自助服务步骤'
        }), 400

    # 验证文件扩展名
    doc_allowed_ext = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png'}
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in doc_allowed_ext:
        return jsonify({
            'success': False,
            'error': '不支持的文件类型，请上传 PDF、Word、Excel 或图片文件'
        }), 400

    # Build safe filename preserving original extension (even for Chinese filenames)
    # secure_filename() strips Chinese characters, losing the file extension entirely
    original_filename = file.filename
    original_ext = os.path.splitext(file.filename)[1]  # e.g. ".pdf"
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_filename = f"{current_user.id}_{timestamp}{original_ext}"

    # 确保上传目录存在
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'documents')
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, unique_filename)

    try:
        file.save(file_path)
        file_size = os.path.getsize(file_path)

        # 创建文档记录（自助上传自动标记为 admin_approved）
        document = Document(
            application_id=application.id,
            step_code=step_code,
            doc_type=doc_type,
            filename=unique_filename,
            original_filename=original_filename,
            file_path=file_path,
            file_size=file_size,
            uploaded_by=current_user.id,
            review_status='admin_approved'  # 自助上传自动通过
        )
        db.session.add(document)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '文件上传成功',
            'data': {
                'id': document.id,
                'filename': original_filename,
                'file_size': file_size,
                'step_code': step_code,
                'review_status': document.review_status
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'文件上传失败: {str(e)}'
        }), 500


@admin_bp.route('/api/self-service-applications', methods=['GET'])
@admin_required
def api_self_service_applications():
    """
    获取当前处于管理员自助服务步骤的申请列表。

    返回所有当前步骤为 approval_type='none' 的进行中申请，
    即需要管理员直接操作的步骤（如 L12, L15-L17, L25, L26）。

    可选过滤参数:
    - step_code: 按步骤代码过滤
    - branch_id: 按支部过滤
    """
    # 查找所有 approval_type='none' 的步骤代码
    none_step_defs = StepDefinition.query.filter_by(approval_type='none').all()
    none_step_codes = [sd.step_code for sd in none_step_defs]

    if not none_step_codes:
        return jsonify({'applications': []})

    # 构建步骤定义的映射，方便后续查找步骤名称
    step_def_map = {sd.step_code: sd for sd in none_step_defs}

    # 查询当前步骤为 none 类型的进行中申请
    query = Application.query.filter(
        Application.status == 'in_progress',
        Application.current_step.in_(none_step_codes)
    )

    # 可选过滤
    step_code_filter = request.args.get('step_code', '').strip()
    if step_code_filter:
        if step_code_filter not in none_step_codes:
            return jsonify({'applications': []})
        query = query.filter(Application.current_step == step_code_filter)

    branch_id = request.args.get('branch_id', type=int)
    if branch_id:
        query = query.filter(Application.branch_id == branch_id)

    applications = query.order_by(Application.updated_at.desc()).all()

    # 构建返回数据
    apps_data = []
    for app in applications:
        step_def = step_def_map.get(app.current_step)
        applicant = app.user
        branch = app.branch

        # 查找该步骤下是否已有上传的文档
        existing_docs = Document.query.filter_by(
            application_id=app.id,
            step_code=app.current_step
        ).all()

        apps_data.append({
            'id': app.id,
            'applicant_name': applicant.name if applicant else '未知',
            'applicant_id': applicant.id if applicant else None,
            'current_step': app.current_step,
            'step_name': step_def.name if step_def else app.current_step,
            'branch_name': branch.name if branch else 'N/A',
            'branch_id': app.branch_id,
            'stage': app.current_stage,
            'has_documents': len(existing_docs) > 0,
            'document_count': len(existing_docs),
            'updated_at': cn_time_str(app.updated_at, '%Y-%m-%d %H:%M:%S')
        })

    return jsonify({
        'applications': apps_data,
        'total': len(apps_data)
    })


@admin_bp.route('/api/applications/<int:app_id>/reset', methods=['POST'])
@admin_required
def api_reset_application(app_id):
    """Reset an application to its initial state (current_step=L1, stage=1).

    Deletes all step records and documents for the application, then resets
    the current_step and current_stage back to the beginning. This is used
    primarily for E2E test cleanup to ensure a clean starting state.

    Request body (optional JSON):
    - confirm: must be true to actually perform the reset
    """
    application = Application.query.get_or_404(app_id)

    # Safety check: require explicit confirmation
    data = request.get_json(silent=True) or {}
    if not data.get('confirm'):
        return jsonify({
            'success': False,
            'message': '必须设置 confirm=true 才能重置申请'
        }), 400

    # Delete all step records for this application
    StepRecord.query.filter_by(application_id=app_id).delete()

    # Delete all documents for this application
    Document.query.filter_by(application_id=app_id).delete()

    # Reset the application to its initial state
    application.current_step = 'L1'
    application.current_stage = 1
    application.status = 'in_progress'

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'申请 {app_id} 已重置到初始状态',
        'data': {
            'id': application.id,
            'current_step': application.current_step,
            'current_stage': application.current_stage,
            'status': application.status
        }
    })
