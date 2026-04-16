"""
Secretary routes for the Party Membership Application Management System.
Secretary can manage applicants and documents within their own branch.
"""

import os
from datetime import date, datetime, timezone, timedelta
from flask import Blueprint, render_template, jsonify, request, flash, current_app
from flask_login import login_required, current_user
from functools import wraps
from werkzeug.utils import secure_filename
from app.models import User, Application, StepRecord, Document, StepDefinition, Branch, ContactAssignment, Notification
from app import db

# 尝试导入 workflow_helpers 辅助模块（该模块可能尚未创建）
# 如果模块不存在，使用本地的简化实现
try:
    from app.workflow_helpers import can_submit, get_allowed_actions, get_step_config, get_step_templates, has_required_documents, sync_document_statuses, all_documents_approved
    _HAS_WORKFLOW_HELPERS = True
except ImportError:
    _HAS_WORKFLOW_HELPERS = False
    # 提供降级实现，以防 workflow_helpers 不可用
    def has_required_documents(app_id, step_code):
        from app.models import Document
        return Document.query.filter_by(application_id=app_id, step_code=step_code).count() > 0
    def sync_document_statuses(app_id, step_code, review_status):
        from app.models import Document
        docs = Document.query.filter_by(application_id=app_id, step_code=step_code).all()
        for doc in docs:
            doc.review_status = review_status
        return len(docs)

# China Standard Time (UTC+8) - used for consistent timestamp display
CHINA_TZ = timezone(timedelta(hours=8))

# 允许上传的文件扩展名
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png'}


def allowed_file(filename):
    """检查文件扩展名是否允许上传"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def cn_time_str(dt, fmt='%Y-%m-%d %H:%M'):
    """Format a UTC datetime to China Standard Time string."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CHINA_TZ).strftime(fmt)

secretary_bp = Blueprint('secretary', __name__)


def secretary_required(f):
    """Decorator to require secretary role."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_secretary():
            return "无权访问", 403
        return f(*args, **kwargs)
    return decorated_function


# ==================== Page Routes ====================

@secretary_bp.route('/dashboard')
@secretary_required
def dashboard():
    """
    Secretary dashboard page.
    Display statistics: pending count, in progress count, this month new count.
    Display pending applications list.
    """
    # Get secretary's branch
    branch_id = current_user.branch_id
    today = date.today()
    month_start = date(today.year, today.month, 1)

    # Statistics: count pending (in_progress) applications in secretary's branch
    pending_count = Application.query.filter_by(
        branch_id=branch_id,
        status='in_progress'
    ).count()

    # This month new count: applications created this month
    this_month_new = Application.query.filter(
        Application.branch_id == branch_id,
        Application.status == 'in_progress',
        Application.created_at >= month_start
    ).count()

    # Count pending documents awaiting secretary review in this branch
    pending_doc_count = Document.query.join(Application).filter(
        Application.branch_id == branch_id,
        Document.review_status == 'pending'
    ).count()

    # Build a stats dict matching the template's expected {{ stats.pending }} etc.
    stats = {
        'pending': pending_count,
        'in_progress': pending_count,
        'monthly_new': this_month_new,
        'pending_docs': pending_doc_count,
    }

    # Pending applications list (latest 10), ordered by most recently updated
    pending_applications = Application.query.filter_by(
        branch_id=branch_id,
        status='in_progress'
    ).order_by(Application.updated_at.desc()).limit(10).all()

    # Build pending_list items matching the template's expected structure:
    #   item.applicant.name, item.applicant.username,
    #   item.stage, item.step, item.submit_time,
    #   item.todo_type, item.todo_label, item.applicant.id
    #   item.secretary_role - NEW: 'approver'/'submitter'/'none'
    pending_list = []
    for app in pending_applications:
        # Resolve the step definition name for a readable step label
        step_def = StepDefinition.query.filter_by(step_code=app.current_step).first()
        step_name = step_def.name if step_def else app.current_step

        # === 步骤级别工作流控制：判断 secretary 在当前步骤的角色 ===
        approval_type = getattr(step_def, 'approval_type', 'two_level') if step_def else 'two_level'
        submitter_role = getattr(step_def, 'submitter_role', 'applicant') if step_def else 'applicant'

        if approval_type == 'two_level':
            # 书记作为初审人，可以审批/驳回申请人提交的文档
            secretary_role = 'approver'
            todo_type = 'review'
            todo_label = '待审核'
        elif approval_type == 'one_level' and submitter_role == 'secretary':
            # 书记作为提交者，需要上传文档提交给管理员审批
            secretary_role = 'submitter'
            todo_type = 'submit'
            todo_label = '待提交'
        else:
            # approval_type == 'none' 或其他：书记无角色，不显示操作
            secretary_role = 'none'
            todo_type = 'none'
            todo_label = '管理员处理中'

        pending_list.append({
            'applicant': {
                'id': app.user.id,
                'application_id': app.id,
                'name': app.user.name,
                'username': app.user.username,
            },
            'stage': f'第{app.current_stage}阶段',
            'step': step_name,
            'submit_time': app.updated_at,
            'todo_type': todo_type,
            'todo_label': todo_label,
            # 新增字段：书记在当前步骤的角色
            'secretary_role': secretary_role,
            'approval_type': approval_type,
        })

    # Query pending documents awaiting secretary review in this branch
    # Only include documents for steps where secretary has a review role (two_level steps)
    pending_documents = Document.query.join(Application).filter(
        Application.branch_id == branch_id,
        Document.review_status == 'pending'
    ).order_by(Document.uploaded_at.desc()).limit(10).all()

    # Add document review items to the pending list
    for doc in pending_documents:
        # Resolve step definition name for the document's step
        step_def = StepDefinition.query.filter_by(step_code=doc.step_code).first()
        step_name = step_def.name if step_def else (doc.step_code or '')

        # 判断文档所属步骤的审批类型，确定书记角色
        doc_approval_type = getattr(step_def, 'approval_type', 'two_level') if step_def else 'two_level'
        if doc_approval_type == 'two_level':
            doc_secretary_role = 'approver'
            doc_todo_type = 'document_review'
            doc_todo_label = '待审核文档'
        elif doc_approval_type == 'one_level':
            # one_level 文档由书记自己上传，不需要书记审核
            # 这些文档在列表中显示为"已提交"状态而非待审核
            doc_secretary_role = 'submitter'
            doc_todo_type = 'document_submitted'
            doc_todo_label = '已提交待审批'
        else:
            doc_secretary_role = 'none'
            doc_todo_type = 'none'
            doc_todo_label = '管理员处理中'

        # Get the applicant (user who owns the application)
        applicant = doc.application.user if doc.application else None
        applicant_name = applicant.name if applicant else '未知'

        pending_list.append({
            'applicant': {
                'id': applicant.id if applicant else 0,
                'application_id': doc.application.id if doc.application else 0,
                'name': applicant_name,
                'username': applicant.username if applicant else '',
            },
            'stage': f'第{doc.application.current_stage}阶段' if doc.application else '',
            'step': step_name,
            'submit_time': doc.uploaded_at,
            'todo_type': doc_todo_type,
            'todo_label': doc_todo_label,
            # Extra fields specific to document review items
            'doc_name': doc.original_filename or doc.filename,
            'doc_id': doc.id,
            # 新增字段：文档所属步骤的工作流信息
            'secretary_role': doc_secretary_role,
            'approval_type': doc_approval_type,
        })

    # Sort combined list by submit_time descending (most recent first)
    pending_list.sort(key=lambda x: x['submit_time'] or datetime.min, reverse=True)
    # Keep only top 15 items to avoid an overly long list
    pending_list = pending_list[:15]

    return render_template('secretary/dashboard.html',
                         stats=stats,
                         pending_list=pending_list)


@secretary_bp.route('/applicants')
@secretary_required
def applicants():
    """Applicant management page."""
    return render_template('secretary/applicants.html')


@secretary_bp.route('/documents')
@secretary_required
def documents():
    """Document review page."""
    return render_template('secretary/documents.html')


@secretary_bp.route('/applicant/<int:id>')
@secretary_required
def applicant_detail(id):
    """
    Applicant detail page.
    Display complete development timeline, step statuses, and documents.
    """
    # Get application and verify branch access
    application = Application.query.get_or_404(id)

    # Secretary can only view applicants from their own branch
    if application.branch_id != current_user.branch_id:
        return "无权访问该申请人", 403

    # Get all step definitions ordered by stage and order
    step_definitions = StepDefinition.query.order_by(
        StepDefinition.stage, StepDefinition.order_num
    ).all()

    # Get step records for this application
    step_records = {sr.step_code: sr for sr in application.step_records}

    # Build timeline data
    timeline = []
    for step_def in step_definitions:
        record = step_records.get(step_def.step_code)
        timeline.append({
            'step_code': step_def.step_code,
            'stage': step_def.stage,
            'name': step_def.name,
            'description': step_def.description,
            'approval_type': getattr(step_def, 'approval_type', 'two_level'),
            'status': record.status if record else 'not_started',
            'completed_at': record.completed_at if record else None,
            'result': record.result if record else None
        })

    # Get documents for this application
    documents = Document.query.filter_by(application_id=id).order_by(
        Document.uploaded_at.desc()
    ).all()

    # Build lookup dictionaries for per-document review UI:
    # - doc_step_approval_types: maps step_code -> approval_type for each document's step
    # - doc_step_record_statuses: maps step_code -> StepRecord.status for each document's step
    doc_step_approval_types = {}
    doc_step_record_statuses = {}
    for doc in documents:
        if doc.step_code and doc.step_code not in doc_step_approval_types:
            sd = StepDefinition.query.filter_by(step_code=doc.step_code).first()
            doc_step_approval_types[doc.step_code] = getattr(sd, 'approval_type', 'two_level') if sd else 'two_level'
            sr = StepRecord.query.filter_by(application_id=id, step_code=doc.step_code).first()
            doc_step_record_statuses[doc.step_code] = sr.status if sr else 'not_started'

    # Get current contact person (if assigned)
    contact_person = application.contact_person

    # Get candidate contact persons: contact_person, secretary, and admin users in the same branch
    # Also include admin users regardless of branch (admin has branch_id=None, would be excluded otherwise)
    # These are users who can serve as 入党联系人 (party membership contacts)
    candidate_contacts = User.query.filter(
        db.or_(
            User.branch_id == application.branch_id,
            User.role == 'admin'  # admins can be contacts for any branch
        ),
        User.role.in_(['contact_person', 'secretary', 'admin']),
        User.is_active == True
    ).all()

    return render_template('secretary/applicant_detail.html',
                         application=application,
                         user=application.user,
                         timeline=timeline,
                         documents=documents,
                         contact_person=contact_person,
                         candidate_contacts=candidate_contacts,
                         doc_step_approval_types=doc_step_approval_types,
                         doc_step_record_statuses=doc_step_record_statuses)


# ==================== API Routes ====================

@secretary_bp.route('/api/applicants', methods=['GET'])
@secretary_required
def api_get_applicants():
    """
    Get applicants list for secretary's branch.
    Query params:
    - status: filter by status (optional)
    - stage: filter by current_stage (optional)
    - search: search by name (optional)
    """
    branch_id = current_user.branch_id

    # Base query
    query = Application.query.filter_by(branch_id=branch_id)

    # Filter by status
    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)

    # Filter by stage
    stage = request.args.get('stage', type=int)
    if stage:
        query = query.filter_by(current_stage=stage)

    # Search by name
    search = request.args.get('search')
    if search:
        query = query.join(User).filter(User.name.contains(search))

    applications = query.order_by(Application.updated_at.desc()).all()

    result = []
    for app in applications:
        result.append({
            'id': app.id,
            'user_id': app.user_id,
            'name': app.user.name if app.user else None,
            'username': app.user.username if app.user else None,
            'employee_id': app.user.employee_id if app.user else None,
            'current_stage': app.current_stage,
            'current_step': app.current_step,
            'status': app.status,
            'apply_date': app.apply_date.isoformat() if app.apply_date else None,
            'created_at': app.created_at.isoformat() if app.created_at else None,
            'updated_at': app.updated_at.isoformat() if app.updated_at else None
        })

    return jsonify({'success': True, 'applicants': result})


@secretary_bp.route('/api/applicants/<int:id>', methods=['GET'])
@secretary_required
def api_get_applicant(id):
    """Get applicant detail by ID."""
    application = Application.query.get_or_404(id)

    # Secretary can only view applicants from their own branch
    if application.branch_id != current_user.branch_id:
        return jsonify({'success': False, 'message': '无权访问该申请人'}), 403

    # Get step records
    step_records = []
    for sr in application.step_records:
        step_records.append({
            'step_code': sr.step_code,
            'status': sr.status,
            'result': sr.result,
            'completed_at': sr.completed_at.isoformat() if sr.completed_at else None,
            'completer_name': sr.completer.name if sr.completer else None
        })

    # Get documents
    documents = []
    for doc in application.documents:
        documents.append({
            'id': doc.id,
            'doc_type': doc.doc_type,
            'step_code': doc.step_code,
            'filename': doc.original_filename or doc.filename,
            'file_size': doc.file_size,
            'uploaded_at': doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            'uploader_name': doc.uploader.name if doc.uploader else None
        })

    result = {
        'id': application.id,
        'user': {
            'id': application.user.id,
            'name': application.user.name,
            'employee_id': application.user.employee_id,
            'username': application.user.username
        },
        'branch': {
            'id': application.branch.id,
            'name': application.branch.name
        },
        'current_stage': application.current_stage,
        'current_step': application.current_step,
        'status': application.status,
        'apply_date': application.apply_date.isoformat() if application.apply_date else None,
        'created_at': application.created_at.isoformat() if application.created_at else None,
        'updated_at': application.updated_at.isoformat() if application.updated_at else None,
        'step_records': step_records,
        'documents': documents
    }

    return jsonify({'success': True, 'data': result})


@secretary_bp.route('/api/applicants/<int:id>/approve-step', methods=['POST'])
@secretary_required
def api_approve_step(id):
    """
    Approve or reject an application step (secretary as L1 approver for two_level steps).

    Secretary only has approval authority for 'two_level' approval_type steps,
    where the secretary acts as the first-level reviewer before admin final approval.

    For 'one_level' steps, secretary is the submitter (not approver) — use submit-step endpoint.
    For 'none' steps, secretary has no role — admin-only.

    Request body:
    - step_code: the step to approve/reject
    - action: 'approve' or 'reject' (default: 'approve' for backward compatibility)
    - result: optional result/notes/rejection reason

    Behavior (two_level steps):
    - Approve: marks step as 'secretary_approved', does NOT advance step — waits for admin
    - Reject: marks step as 'failed', keeps current_step unchanged so applicant can re-apply
    """
    application = Application.query.get_or_404(id)

    # Secretary can only approve applicants from their own branch
    if application.branch_id != current_user.branch_id:
        return jsonify({'success': False, 'message': '无权操作该申请人'}), 403

    # Check application is in progress
    if application.status != 'in_progress':
        return jsonify({'success': False, 'message': '该申请已结束'}), 400

    data = request.get_json()
    step_code = data.get('step_code')
    action = data.get('action', 'approve')  # default to approve for backward compatibility
    result = data.get('result', '')

    if not step_code:
        return jsonify({'success': False, 'message': '缺少步骤代码'}), 400

    if action not in ('approve', 'reject'):
        return jsonify({'success': False, 'message': '无效的操作类型，必须为 approve 或 reject'}), 400

    # Validate: only the current step can be approved/rejected (sequential enforcement)
    # This prevents skipping ahead or approving steps out of order.
    if application.current_step != step_code:
        return jsonify({
            'success': False,
            'message': f'只能审批当前步骤（当前步骤: {application.current_step}），无法跳过或乱序审批'
        }), 400

    # Get step definition
    step_def = StepDefinition.query.filter_by(step_code=step_code).first()
    if not step_def:
        return jsonify({'success': False, 'message': '无效的步骤代码'}), 400

    # === 步骤级别工作流控制：检查 secretary 是否有审批权限 ===
    approval_type = getattr(step_def, 'approval_type', 'two_level')  # 向后兼容：旧数据默认 two_level

    # 对于 one_level 步骤，secretary 是提交者而非审批者
    if approval_type == 'one_level':
        return jsonify({
            'success': False,
            'message': '该步骤由书记提交，需使用提交接口（submit-step）'
        }), 400

    # 对于 none 步骤，secretary 无角色
    if approval_type == 'none':
        return jsonify({
            'success': False,
            'message': '该步骤为管理员专用，书记无权操作'
        }), 400

    # 只有 two_level 步骤，secretary 才能审批（作为初审人）
    # approval_type == 'two_level' — 继续处理

    # === 文件检查：审批前必须存在至少一个文档 ===
    # 统一审批模型要求：任何步骤的审批操作都必须有文档支撑
    if not has_required_documents(id, step_code):
        return jsonify({
            'success': False,
            'message': '请先上传相关文件'
        }), 400

    # Find or create step record
    step_record = StepRecord.query.filter_by(
        application_id=id,
        step_code=step_code
    ).first()

    if not step_record:
        step_record = StepRecord(
            application_id=id,
            step_code=step_code,
            status='pending'
        )
        db.session.add(step_record)

    if action == 'approve':
        # === 逐个文档审批前置检查：所有文档必须已逐个通过书记审核 ===
        # Gate check: all documents must have been individually reviewed and
        # approved by secretary before step-level approval is allowed.
        all_approved, status_msg = all_documents_approved(
            step_code, id, required_status='secretary_approved'
        )
        if not all_approved:
            return jsonify({
                'success': False,
                'message': f'请先审核所有文档（{status_msg}）'
            }), 400

        # two_level 审批：书记初审通过，设置为 'secretary_approved'
        # 步骤不推进，等待管理员最终审批后才完成
        step_record.status = 'secretary_approved'
        step_record.result = result
        step_record.completed_at = datetime.utcnow()
        step_record.completed_by = current_user.id

        # 注意：文档已经是 secretary_approved 状态（通过逐个审批完成），
        # 无需再调用 sync_document_statuses() 批量更新。
        # 保留 sync_document_statuses 仅作为管理覆盖用。

        # 注意：不推进 application.current_step，等待管理员最终审批

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '步骤已通过初审，等待党委最终审批',
            'data': {
                'step_code': step_code,
                'status': 'secretary_approved',
                'completed_at': step_record.completed_at.isoformat(),
                # current_step 不变，等待管理员审批
                'current_step': application.current_step,
                'needs_admin_approval': True
            }
        })

    else:
        # Reject: mark step as failed, keep current_step at this step
        # Applicant can re-upload documents and re-apply for this step
        step_record.status = 'failed'
        step_record.result = result if result else '步骤被驳回'
        step_record.completed_at = datetime.utcnow()
        step_record.completed_by = current_user.id

        # 统一审批模型：书记驳回步骤时，同步更新该步骤所有文档状态
        # 所有文档统一设置为 secretary_rejected
        sync_document_statuses(id, step_code, 'secretary_rejected')
        # 同时记录审核人和审核时间
        all_docs = Document.query.filter_by(
            application_id=id,
            step_code=step_code
        ).all()
        for doc in all_docs:
            doc.reviewed_by = current_user.id
            doc.reviewed_at = datetime.utcnow()

        # IMPORTANT: Do NOT advance current_step. The step stays as current
        # so the applicant can see the rejection and re-apply.
        # current_step and current_stage remain unchanged.

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '步骤已驳回',
            'data': {
                'step_code': step_code,
                'status': 'failed',
                'result': step_record.result,
                # current_step stays the same after rejection
                'current_step': application.current_step
            }
        })


@secretary_bp.route('/api/applicants/<int:id>/submit-step', methods=['POST'])
@secretary_required
def api_submit_step(id):
    """
    Secretary submits a document for a one_level approval step.
    For one_level steps, secretary is the submitter and admin is the approver.

    Expects multipart/form-data with:
        - file: The document file (required)
        - step_code: The step code to submit for (required)
        - doc_type: Document type (optional, default 'general')

    Behavior:
    - Validates step_def.submitter_role == 'secretary' and approval_type == 'one_level'
    - Validates application.current_step matches step_code
    - Uploads file to the same directory structure as applicant uploads
    - Creates Document with review_status='pending'
    - Creates/updates StepRecord with status='pending'
    - Creates notification to admin users in the same branch
    """
    application = Application.query.get_or_404(id)

    # Secretary can only submit for applicants from their own branch
    if application.branch_id != current_user.branch_id:
        return jsonify({'success': False, 'message': '无权操作该申请人'}), 403

    # Check application is in progress
    if application.status != 'in_progress':
        return jsonify({'success': False, 'message': '该申请已结束'}), 400

    # Get form data
    step_code = request.form.get('step_code')
    doc_type = request.form.get('doc_type', 'general')

    if not step_code:
        return jsonify({'success': False, 'message': '缺少步骤代码'}), 400

    # Get step definition and validate workflow config
    step_def = StepDefinition.query.filter_by(step_code=step_code).first()
    if not step_def:
        return jsonify({'success': False, 'message': '无效的步骤代码'}), 400

    approval_type = getattr(step_def, 'approval_type', 'two_level')
    submitter_role = getattr(step_def, 'submitter_role', 'applicant')

    # 验证：只有 one_level + submitter_role=secretary 的步骤才能用此接口
    if approval_type != 'one_level':
        return jsonify({
            'success': False,
            'message': f'该步骤审批类型为 {approval_type}，不适用书记提交接口'
        }), 400

    if submitter_role != 'secretary':
        return jsonify({
            'success': False,
            'message': f'该步骤提交者为 {submitter_role}，非书记角色'
        }), 400

    # Validate: only the current step can be submitted
    if application.current_step != step_code:
        return jsonify({
            'success': False,
            'message': f'只能提交当前步骤（当前步骤: {application.current_step}）'
        }), 400

    # Check file is present
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '请选择要上传的文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '请选择要上传的文件'}), 400

    # Check file extension
    if not allowed_file(file.filename):
        return jsonify({
            'success': False,
            'message': '不支持的文件类型，请上传 PDF、Word、Excel 或图片文件'
        }), 400

    # Build safe filename preserving original extension (even for Chinese filenames)
    # secure_filename() strips Chinese characters, losing the file extension entirely
    # e.g. "入党申请书.pdf" -> "pdf" (no dot, no extension). Use os.path.splitext instead.
    original_filename = file.filename
    original_ext = os.path.splitext(file.filename)[1]  # e.g. ".pdf"
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_filename = f"sec_{current_user.id}_{timestamp}{original_ext}"

    # Create upload directory if not exists
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'documents')
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, unique_filename)

    try:
        # Save file
        file.save(file_path)
        file_size = os.path.getsize(file_path)

        # Create document record
        document = Document(
            application_id=application.id,
            step_code=step_code,
            doc_type=doc_type,
            filename=unique_filename,
            original_filename=original_filename,
            file_path=file_path,
            file_size=file_size,
            uploaded_by=current_user.id,
            review_status='pending'  # 等待管理员审批
        )
        db.session.add(document)

        # Create or update step record
        step_record = StepRecord.query.filter_by(
            application_id=id,
            step_code=step_code
        ).first()

        if not step_record:
            step_record = StepRecord(
                application_id=id,
                step_code=step_code,
                status='pending'
            )
            db.session.add(step_record)
        else:
            # 如果之前被驳回，重置为 pending
            step_record.status = 'pending'
            step_record.result = None
            step_record.completed_at = None
            step_record.completed_by = None

        # Create notification to admin users in the same branch
        # 通知管理员：书记已提交文档，请审批
        admin_users = User.query.filter_by(
            branch_id=application.branch_id,
            role='admin',
            is_active=True
        ).all()

        applicant_name = application.user.name if application.user else '未知'
        step_name = step_def.name or step_code

        for admin in admin_users:
            notification = Notification(
                user_id=admin.id,
                title=f'书记提交文档待审批 - {applicant_name}',
                content=f'{current_user.name} 已为 {applicant_name} 提交了 {step_name} 的文档，请及时审批。',
                link=f'/admin/applicant/{application.id}'
            )
            db.session.add(notification)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '文档提交成功，等待管理员审批',
            'data': {
                'document_id': document.id,
                'filename': original_filename,
                'doc_type': doc_type,
                'step_code': step_code,
                'step_name': step_name,
                'file_size': file_size,
                'review_status': 'pending'
            }
        })

    except Exception as e:
        db.session.rollback()
        # Clean up file if database save fails
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({
            'success': False,
            'message': f'提交失败：{str(e)}'
        }), 500


@secretary_bp.route('/api/applicants/<int:id>/step-actions', methods=['GET'])
@secretary_required
def api_get_step_actions(id):
    """
    Get allowed actions for the current step of an application.
    This tells the frontend what the secretary can do with the current step:
    - 'approve'/'reject': for two_level steps where secretary is L1 approver
    - 'submit': for one_level steps where secretary is submitter
    - nothing: for none steps (admin-only)

    Returns JSON with step config and allowed actions:
    {
        "step_code": "L2",
        "approval_type": "one_level",
        "submitter_role": "secretary",
        "allowed_actions": ["submit", "download_template"]
    }
    """
    application = Application.query.get_or_404(id)

    # Secretary can only view applicants from their own branch
    if application.branch_id != current_user.branch_id:
        return jsonify({'success': False, 'message': '无权访问该申请人'}), 403

    step_code = application.current_step
    step_def = StepDefinition.query.filter_by(step_code=step_code).first()

    if not step_def:
        return jsonify({'success': False, 'message': '未找到步骤定义'}), 404

    approval_type = getattr(step_def, 'approval_type', 'two_level')
    submitter_role = getattr(step_def, 'submitter_role', 'applicant')

    # Determine allowed actions based on workflow config
    allowed_actions = []

    if approval_type == 'two_level':
        # Secretary is L1 approver — can approve or reject applicant submissions
        allowed_actions = ['approve', 'reject']
    elif approval_type == 'one_level' and submitter_role == 'secretary':
        # Secretary is submitter — can upload/submit documents
        allowed_actions = ['submit', 'download_template']
    elif approval_type == 'none':
        # Admin-only step — secretary has no actions
        allowed_actions = []

    # Check if there are templates available for this step
    has_templates = False
    if _HAS_WORKFLOW_HELPERS:
        try:
            templates = get_step_templates(step_code)
            has_templates = bool(templates)
        except Exception:
            has_templates = False
    else:
        # 如果 workflow_helpers 不存在，检查 step_def.required_templates
        if step_def.required_templates:
            try:
                import json as _json
                tmpl = _json.loads(step_def.required_templates)
                has_templates = bool(tmpl)
            except (ValueError, TypeError):
                has_templates = False

    # 获取当前步骤的 step_record 状态（用于前端显示）
    step_record = StepRecord.query.filter_by(
        application_id=id,
        step_code=step_code
    ).first()
    current_status = step_record.status if step_record else 'not_started'

    result = {
        'step_code': step_code,
        'step_name': step_def.name,
        'stage': step_def.stage,
        'approval_type': approval_type,
        'submitter_role': submitter_role,
        'allowed_actions': allowed_actions,
        'has_templates': has_templates,
        'current_status': current_status,
        # secretary 在此步骤的角色描述
        'secretary_role': (
            'approver' if approval_type == 'two_level'
            else 'submitter' if (approval_type == 'one_level' and submitter_role == 'secretary')
            else 'none'
        )
    }

    return jsonify({'success': True, 'data': result})


@secretary_bp.route('/api/documents', methods=['GET'])
@secretary_required
def api_get_documents():
    """
    Get documents list for secretary's branch that need review.
    By default, shows documents with review_status='pending' (awaiting secretary review).
    Also includes re-submitted documents after rejection.

    Query params:
    - search: search by applicant name or filename (optional)
    - type: filter by doc_type (optional)
    - status: filter by review_status (optional, default: shows pending)
    """
    branch_id = current_user.branch_id

    # Base query: documents belonging to applications in secretary's branch
    query = Document.query.join(Application).filter(Application.branch_id == branch_id)

    # Get filter parameters
    search = request.args.get('search', '').strip()
    doc_type = request.args.get('type', '').strip()
    status_filter = request.args.get('status', '').strip()

    # Apply search filter
    if search:
        query = query.join(User, Application.user_id == User.id).filter(
            db.or_(
                User.name.contains(search),
                Document.original_filename.contains(search)
            )
        )

    # Apply doc_type filter
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)

    # Apply review_status filter
    # Map the template's simple status values to actual DB values
    if status_filter:
        if status_filter == 'pending':
            # "pending" in the UI means documents that need secretary review
            query = query.filter(Document.review_status == 'pending')
        elif status_filter == 'approved':
            # "approved" in the UI means secretary already approved
            query = query.filter(Document.review_status.in_(['secretary_approved', 'admin_approved']))
        elif status_filter == 'rejected':
            # "rejected" in the UI means secretary or admin rejected
            query = query.filter(Document.review_status.in_(['secretary_rejected', 'admin_rejected']))
        else:
            query = query.filter(Document.review_status == status_filter)
    else:
        # Default: show documents needing secretary review (pending status)
        query = query.filter(Document.review_status == 'pending')

    # Order by most recent first
    documents = query.order_by(Document.uploaded_at.desc()).all()

    result = []
    for doc in documents:
        # Get applicant name from the document's application
        applicant_name = doc.application.user.name if doc.application and doc.application.user else None

        # 获取文档所属步骤的工作流配置
        doc_step_def = StepDefinition.query.filter_by(step_code=doc.step_code).first() if doc.step_code else None
        doc_approval_type = getattr(doc_step_def, 'approval_type', 'two_level') if doc_step_def else 'two_level'
        doc_submitter_role = getattr(doc_step_def, 'submitter_role', 'applicant') if doc_step_def else 'applicant'

        result.append({
            'id': doc.id,
            'filename': doc.original_filename or doc.filename,
            'doc_type': doc.doc_type,
            'step_code': doc.step_code,
            'file_size': doc.file_size,
            'uploaded_at': cn_time_str(doc.uploaded_at),
            'applicant_name': applicant_name,
            'status': doc.review_status or 'pending',
            # 新增字段：工作流信息，供前端判断可执行操作
            'approval_type': doc_approval_type,
            'secretary_role': (
                'approver' if doc_approval_type == 'two_level'
                else 'submitter' if (doc_approval_type == 'one_level' and doc_submitter_role == 'secretary')
                else 'none'
            ),
        })

    return jsonify({'success': True, 'documents': result})


@secretary_bp.route('/api/documents/<int:id>/review', methods=['POST'])
@secretary_required
def api_review_document(id):
    """
    Per-document review endpoint for secretary (restored).

    Allows the secretary to review individual documents for two_level steps.
    After reviewing each document, the system checks whether ALL documents for
    the same step have been reviewed, and auto-updates the StepRecord status:
      - If all docs are secretary_approved -> StepRecord.status = 'secretary_approved'
      - If any doc is secretary_rejected -> StepRecord.status = 'failed'

    For one_level steps, returns 403 (secretary is the submitter, not reviewer).
    For none steps, returns 403 (admin-only, secretary has no role).

    Request body:
    - action: 'approve' or 'reject'
    - comment: optional review comment (recommended for rejections)
    """
    document = Document.query.get_or_404(id)

    # Get application and verify branch access
    application = document.application
    if application.branch_id != current_user.branch_id:
        return jsonify({'success': False, 'message': '无权审核该文档'}), 403

    data = request.get_json()
    action = data.get('action')
    comment = data.get('comment', '')

    if action not in ['approve', 'reject']:
        return jsonify({'success': False, 'message': '无效的操作类型'}), 400

    # === 检查文档所属步骤的工作流配置 ===
    step_def = StepDefinition.query.filter_by(step_code=document.step_code).first() if document.step_code else None
    approval_type = getattr(step_def, 'approval_type', 'two_level') if step_def else 'two_level'

    # 对于 one_level 步骤的文档，书记是提交者，不能审核自己的文档
    if approval_type == 'one_level':
        return jsonify({
            'success': False,
            'message': '该文档属于书记提交步骤，由管理员审批'
        }), 403

    # 对于 none 步骤，书记无角色
    if approval_type == 'none':
        return jsonify({
            'success': False,
            'message': '该步骤为管理员专用，书记无权审核'
        }), 403

    # 检查文档是否已被审核过（避免重复审核）
    if document.review_status in ('secretary_approved', 'secretary_rejected'):
        return jsonify({
            'success': False,
            'message': f'该文档已审核（当前状态: {document.review_status}），不能重复操作'
        }), 400

    # === 更新文档的审核状态 ===
    document.review_status = 'secretary_approved' if action == 'approve' else 'secretary_rejected'
    document.reviewed_by = current_user.id
    document.reviewed_at = datetime.utcnow()
    document.review_comment = comment if comment else None

    # === 检查同一步骤的所有文档状态，自动更新 StepRecord ===
    if document.step_code:
        step_record = StepRecord.query.filter_by(
            application_id=application.id,
            step_code=document.step_code
        ).first()

        # 获取该步骤的所有文档
        all_step_docs = Document.query.filter_by(
            application_id=application.id,
            step_code=document.step_code
        ).all()

        if action == 'reject':
            # 任一文档被驳回 -> StepRecord 标记为 failed，申请人/提交者可重新上传
            if step_record:
                step_record.status = 'failed'
                step_record.result = f'文档审核不通过: {comment}' if comment else '文档审核不通过'
        else:
            # 文档通过 -> 检查是否所有文档都已 secretary_approved
            all_approved = all(
                doc.review_status == 'secretary_approved'
                for doc in all_step_docs
            )
            if all_approved:
                # 所有文档都已通过书记审核 -> 更新 StepRecord 为 secretary_approved
                if not step_record:
                    step_record = StepRecord(
                        application_id=application.id,
                        step_code=document.step_code,
                        status='pending'
                    )
                    db.session.add(step_record)
                step_record.status = 'secretary_approved'
                step_record.result = '所有文档初审通过'
                step_record.completed_at = datetime.utcnow()
                step_record.completed_by = current_user.id
                # 注意：不推进 application.current_step，等待管理员最终审批

    db.session.commit()

    # 构建响应：返回文档状态和步骤整体状态
    step_record_status = None
    if document.step_code:
        sr = StepRecord.query.filter_by(
            application_id=application.id,
            step_code=document.step_code
        ).first()
        step_record_status = sr.status if sr else None

    return jsonify({
        'success': True,
        'message': '文档已审核通过' if action == 'approve' else '文档已驳回',
        'data': {
            'document_id': id,
            'review_status': document.review_status,
            'step_status': step_record_status
        }
    })


@secretary_bp.route('/api/documents/<int:id>', methods=['DELETE'])
@secretary_required
def api_delete_document(id):
    """
    Delete a document as secretary.

    Permission rules:
    - Secretary can ONLY delete documents that admin has rejected (admin_rejected).
      This allows secretary to adjust and resubmit the document.
    - Secretary CANNOT delete documents they approved that are pending admin review (secretary_approved).
    - Secretary CANNOT delete documents approved by admin (admin_approved).
    - Secretary CANNOT delete documents in pending or secretary_rejected status
      (those belong to applicant's control).
    """
    import os
    document = Document.query.get_or_404(id)

    # Get application and verify branch access
    application = document.application
    if application.branch_id != current_user.branch_id:
        return jsonify({'success': False, 'message': '无权操作该文档'}), 403

    # Secretary can only delete admin-rejected documents
    if document.review_status != 'admin_rejected':
        if document.review_status in ('secretary_approved', 'admin_approved'):
            return jsonify({'success': False, 'message': '已通过的文档不能删除'}), 403
        elif document.review_status == 'pending':
            return jsonify({'success': False, 'message': '待审核的文档不能由书记删除'}), 403
        elif document.review_status == 'secretary_rejected':
            return jsonify({'success': False, 'message': '已驳回的文档由申请人自行处理'}), 403
        else:
            return jsonify({'success': False, 'message': '当前状态的文档不能删除'}), 403

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


@secretary_bp.route('/api/documents/<int:doc_id>/preview')
@login_required
def preview_document(doc_id):
    """在线预览文档（PDF/图片内联显示，不下载）
    仅支持 PDF 和图片格式（jpg/jpeg/png），书记和管理员可用。
    """
    if current_user.role not in ('secretary', 'admin'):
        return jsonify({'success': False, 'message': '无权访问'}), 403

    doc = Document.query.get_or_404(doc_id)

    # 文件扩展名检查
    ext = os.path.splitext(doc.filename)[1].lower()
    supported = {'.pdf', '.jpg', '.jpeg', '.png'}
    if ext not in supported:
        return jsonify({'success': False, 'message': f'该格式（{ext}）不支持在线预览，请下载查看'}), 415

    # 文件存在性检查
    if not os.path.exists(doc.file_path):
        return jsonify({'success': False, 'message': '文件不存在'}), 404

    # MIME 类型映射
    mime_map = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
    }

    from flask import send_file
    return send_file(
        doc.file_path,
        as_attachment=False,
        mimetype=mime_map.get(ext, 'application/octet-stream')
    )


@secretary_bp.route('/api/applicants/<int:id>/set-contact', methods=['POST'])
@secretary_required
def api_set_contact_person(id):
    """Assign a contact person (入党联系人) to an applicant's application.

    Request body:
    - contact_person_id: ID of the user to assign as contact person (required)

    The contact person must be a contact_person, secretary, or admin in the same branch as the application.
    """
    application = Application.query.get_or_404(id)

    # Secretary can only modify applicants from their own branch
    if application.branch_id != current_user.branch_id:
        return jsonify({'success': False, 'message': '无权操作该申请人'}), 403

    data = request.get_json()
    contact_person_id = data.get('contact_person_id')

    if not contact_person_id:
        return jsonify({'success': False, 'message': '缺少联系人ID'}), 400

    # Validate the contact person exists and has appropriate role
    contact_user = User.query.get(contact_person_id)
    if not contact_user:
        return jsonify({'success': False, 'message': '联系人不存在'}), 404

    if contact_user.role not in ('contact_person', 'secretary', 'admin'):
        return jsonify({'success': False, 'message': '只能指定联系人、书记或管理员作为入党联系人'}), 400

    # Admin users have branch_id=None but can serve as contacts for any branch
    if contact_user.role != 'admin' and contact_user.branch_id != application.branch_id:
        return jsonify({'success': False, 'message': '联系人必须属于同一支部'}), 400

    # Update the application's contact_person_id
    application.contact_person_id = contact_person_id

    # Also create/update a ContactAssignment record for history tracking
    # Deactivate any previous active assignments
    ContactAssignment.query.filter_by(
        application_id=id,
        is_active=True
    ).update({'is_active': False})

    # Create new active assignment
    new_assignment = ContactAssignment(
        application_id=id,
        contact_user_id=contact_person_id,
        is_active=True
    )
    db.session.add(new_assignment)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'已指定 {contact_user.name} 为入党联系人',
        'data': {
            'contact_person_id': contact_person_id,
            'contact_person_name': contact_user.name
        }
    })


@secretary_bp.route('/api/applicants/<int:id>/contact-candidates', methods=['GET'])
@secretary_required
def api_get_contact_candidates(id):
    """Get available contact person candidates for an application.

    Returns contact_person, secretary, and admin users in the same branch who can serve as 入党联系人.
    """
    application = Application.query.get_or_404(id)

    # Secretary can only view applicants from their own branch
    if application.branch_id != current_user.branch_id:
        return jsonify({'success': False, 'message': '无权访问该申请人'}), 403

    # Query candidate users: contact_person, secretary, and admin users in the same branch
    # Also include admin users regardless of branch (admin has branch_id=None, would be excluded otherwise)
    candidates = User.query.filter(
        db.or_(
            User.branch_id == application.branch_id,
            User.role == 'admin'  # admins can be contacts for any branch
        ),
        User.role.in_(['contact_person', 'secretary', 'admin']),
        User.is_active == True
    ).all()

    result = []
    for user in candidates:
        result.append({
            'id': user.id,
            'name': user.name,
            'username': user.username,
            'employee_id': user.employee_id,
            'role': user.role
        })

    return jsonify({
        'success': True,
        'candidates': result,
        'current_contact_id': application.contact_person_id
    })
