"""
Applicant routes for the Party Membership Application Management System.
Handles applicant dashboard, progress tracking, and document management.
"""

import os
import json
from datetime import datetime, date, timezone, timedelta
from functools import wraps
from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import Application, StepDefinition, StepRecord, Document, Template, User

# 工作流辅助函数 - 提供步骤权限判断、审批状态文本等功能
# Workflow helpers - provide step permission checks, approval status text, etc.
try:
    from app.workflow_helpers import (
        can_submit, get_allowed_actions, get_step_config,
        get_step_templates, get_approval_status_text
    )
except ImportError:
    # 如果 workflow_helpers 不可用，定义降级函数
    can_submit = None
    get_allowed_actions = None
    get_step_config = None
    get_step_templates = None
    get_approval_status_text = None

# China Standard Time (UTC+8) - used for consistent timestamp display
CHINA_TZ = timezone(timedelta(hours=8))


def cn_time_str(dt, fmt='%Y-%m-%d %H:%M'):
    """Format a UTC datetime to China Standard Time string.

    Args:
        dt: datetime object (assumed UTC) or None
        fmt: strftime format string

    Returns:
        Formatted string in China time, or None if dt is None
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CHINA_TZ).strftime(fmt)

applicant_bp = Blueprint('applicant', __name__)


def applicant_required(f):
    """Decorator to require applicant role."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_applicant():
            return jsonify({'error': '无权访问'}), 403
        return f(*args, **kwargs)
    return decorated_function


def allowed_file(filename):
    """Check if file extension is allowed."""
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_stage_name(stage):
    """Get stage name by stage number."""
    stage_names = {
        1: '第一阶段：递交入党申请书',
        2: '第二阶段：确定入党积极分子',
        3: '第三阶段：确定发展对象',
        4: '第四阶段：确定预备党员',
        5: '第五阶段：确定正式党员'
    }
    return stage_names.get(stage, '未知阶段')


def get_phase_name(stage):
    """Alias for get_stage_name for template compatibility."""
    return get_stage_name(stage)


# ============================================
# Page Routes (Render Templates)
# ============================================

@applicant_bp.route('/dashboard')
@applicant_required
def dashboard():
    """Applicant dashboard page.

    Displays:
    - Current application status
    - Development timeline (5 stages, 26 steps)
    - Todo items
    - Contact person information
    """
    # Get or create application for current user
    application = Application.query.filter_by(user_id=current_user.id).first()

    current_step_info = None
    completed_steps = []
    failed_step = None  # Will hold info about a rejected/failed step if any
    todos = []
    contact_person = None
    has_application = application is not None
    step_roles = {}  # Maps step_code -> {'submitter_role': ..., 'action_label': ...}
    current_step_submitter_role = 'applicant'  # Default for backward compatibility
    current_step_action_label = '你的操作'
    current_step_templates = []

    if application:
        # Get current step definition
        current_step_def = StepDefinition.query.filter_by(
            step_code=application.current_step
        ).first()

        if current_step_def:
            current_step_info = {
                'code': current_step_def.step_code,
                'name': current_step_def.name,
                'phase': current_step_def.stage,
                'phase_name': get_phase_name(current_step_def.stage),
                'needs_document': True  # Default to True for simplicity
            }
            # Determine submitter_role and action_label for the current step
            current_step_submitter_role = getattr(current_step_def, 'submitter_role', 'applicant')
            if current_step_submitter_role == 'applicant':
                current_step_action_label = '你的操作'
            elif current_step_submitter_role == 'secretary':
                current_step_action_label = '等待书记操作'
            elif current_step_submitter_role == 'admin':
                current_step_action_label = '等待党委操作'
            else:
                current_step_action_label = '等待处理'

        # Build step_roles mapping for ALL steps so the timeline can use it
        all_step_defs = StepDefinition.query.order_by(
            StepDefinition.stage, StepDefinition.order_num
        ).all()
        for sd in all_step_defs:
            role = getattr(sd, 'submitter_role', 'applicant')
            if role == 'applicant':
                label = '你的操作'
            elif role == 'secretary':
                label = '等待书记操作'
            elif role == 'admin':
                label = '等待党委操作'
            else:
                label = '等待处理'
            step_roles[sd.step_code] = {
                'submitter_role': role,
                'action_label': label
            }

        # Get templates for the current step (only relevant for applicant steps)
        if current_step_def and current_step_submitter_role == 'applicant':
            templates_for_step = Template.query.filter(
                db.or_(
                    Template.step_code == application.current_step,
                    Template.step_code.is_(None)
                ),
                Template.is_active == True
            ).all()
            current_step_templates = [{
                'id': t.id,
                'name': t.name,
                'description': t.description
            } for t in templates_for_step]

        # Get completed steps
        step_records = StepRecord.query.filter_by(
            application_id=application.id,
            status='completed'
        ).all()
        completed_steps = [record.step_code for record in step_records]

        # Check for failed (rejected) step on the current step
        # A failed step means the secretary/admin rejected this step,
        # and the applicant needs to re-upload documents and re-apply.
        failed_record = StepRecord.query.filter_by(
            application_id=application.id,
            step_code=application.current_step,
            status='failed'
        ).order_by(StepRecord.completed_at.desc()).first()

        if failed_record:
            # Get the step definition for the failed step to show its name
            failed_step_def = StepDefinition.query.filter_by(
                step_code=failed_record.step_code
            ).first()
            # Get the reviewer's name
            reviewer_name = None
            if failed_record.completed_by:
                reviewer = User.query.get(failed_record.completed_by)
                reviewer_name = reviewer.name if reviewer else None

            failed_step = {
                'step_code': failed_record.step_code,
                'step_name': failed_step_def.name if failed_step_def else failed_record.step_code,
                'reason': failed_record.result or '未提供原因',
                'rejected_at': failed_record.completed_at,
                'reviewer_name': reviewer_name,
            }

        # Generate todos based on current status
        todos = generate_todos(application, current_step_def, failed_step)

        # Get contact person
        if application.contact_person_id:
            contact_person = User.query.get(application.contact_person_id)
    else:
        # No application yet, show initial todo
        todos = [{
            'title': '开始入党申请',
            'description': '点击下方"开始入党申请"按钮启动您的入党申请流程',
            'priority': 'urgent',
            'action_url': None
        }]

    return render_template('applicant/dashboard.html',
                         current_step=current_step_info,
                         completed_steps=completed_steps,
                         failed_step=failed_step,
                         todos=todos,
                         contact_person=contact_person,
                         has_application=has_application,
                         step_roles=step_roles,
                         current_step_submitter_role=current_step_submitter_role,
                         current_step_action_label=current_step_action_label,
                         current_step_templates=current_step_templates)


@applicant_bp.route('/progress')
@applicant_required
def progress():
    """Detailed progress page showing development timeline."""
    application = Application.query.filter_by(user_id=current_user.id).first()

    # Get all step definitions ordered by stage and order
    all_steps = StepDefinition.query.order_by(
        StepDefinition.stage, StepDefinition.order_num
    ).all()

    completed_steps = []
    current_step_code = None

    if application:
        # Get completed steps
        step_records = StepRecord.query.filter_by(
            application_id=application.id,
            status='completed'
        ).all()
        completed_steps = [record.step_code for record in step_records]
        current_step_code = application.current_step

    # Group steps by stage
    stages = {}
    for step in all_steps:
        if step.stage not in stages:
            stages[step.stage] = {
                'name': get_stage_name(step.stage),
                'steps': []
            }

        # 根据步骤的 submitter_role 确定面向申请人的操作标签
        # Determine action label for applicant based on step's submitter_role
        submitter_role = getattr(step, 'submitter_role', 'applicant')
        if submitter_role == 'applicant':
            action_label = '你的操作'
        elif submitter_role == 'secretary':
            action_label = '等待书记操作'
        elif submitter_role == 'admin':
            action_label = '等待党委操作'
        else:
            action_label = '等待处理'

        stages[step.stage]['steps'].append({
            'code': step.step_code,
            'name': step.name,
            'description': step.description,
            'is_completed': step.step_code in completed_steps,
            'is_current': step.step_code == current_step_code,
            'submitter_role': submitter_role,
            'action_label': action_label
        })

    return render_template('applicant/progress.html',
                         stages=stages,
                         application=application,
                         completed_steps=completed_steps)


@applicant_bp.route('/documents')
@applicant_required
def documents():
    """My documents page showing required and uploaded documents."""
    application = Application.query.filter_by(user_id=current_user.id).first()

    documents_list = []
    available_templates = []

    if application:
        # Get uploaded documents
        uploaded_docs = Document.query.filter_by(
            application_id=application.id
        ).order_by(Document.uploaded_at.desc()).all()

        documents_list = []
        for doc in uploaded_docs:
            # Resolve reviewer name if the document has been reviewed
            reviewer_name = None
            if doc.reviewed_by:
                reviewer = User.query.get(doc.reviewed_by)
                reviewer_name = reviewer.name if reviewer else None

            documents_list.append({
                'id': doc.id,
                'filename': doc.original_filename or doc.filename,
                'doc_type': doc.doc_type,
                'step_code': doc.step_code,
                'file_size': doc.file_size,
                'uploaded_at': cn_time_str(doc.uploaded_at),
                # Review status fields so the applicant can see approvals/rejections
                'review_status': doc.review_status or 'pending',  # pending, approved, rejected
                'review_comment': doc.review_comment,
                'reviewer_name': reviewer_name,
                'reviewed_at': cn_time_str(doc.reviewed_at),
            })

    # 获取可用模板：优先按当前步骤 step_code 过滤，同时显示通用模板
    # Get available templates: prefer filtering by current step_code, also show general templates
    templates_query = Template.query.order_by(Template.stage, Template.name)
    if application and application.current_step:
        # 精确过滤：当前步骤的模板 + 通用模板（无 step_code）+ 当前阶段模板
        # Precise filter: templates for current step + general templates (no step_code) + current stage templates
        templates_query = templates_query.filter(
            db.or_(
                Template.step_code == application.current_step,
                Template.step_code.is_(None),
                Template.stage == application.current_stage if application.current_stage else False
            )
        )
    elif application and application.current_stage:
        # 回退：仅按阶段过滤（兼容旧数据）
        # Fallback: filter by stage only (backward compatible)
        templates_query = templates_query.filter(
            db.or_(Template.stage == application.current_stage, Template.stage.is_(None))
        )

    templates = templates_query.all()
    available_templates = [{
        'id': t.id,
        'name': t.name,
        'description': t.description,
        'step_code': t.step_code,
        'stage': t.stage
    } for t in templates]

    # 获取当前步骤的 submitter_role，供模板判断是否显示上传操作
    # Get current step's submitter_role so template can decide whether to show upload actions
    current_step_submitter_role = 'applicant'  # 默认值
    if application and application.current_step:
        current_step_def = StepDefinition.query.filter_by(
            step_code=application.current_step
        ).first()
        if current_step_def:
            current_step_submitter_role = getattr(current_step_def, 'submitter_role', 'applicant')

    return render_template('applicant/documents.html',
                         documents=documents_list,
                         available_templates=available_templates,
                         application=application,
                         current_step_submitter_role=current_step_submitter_role)


@applicant_bp.route('/template/<int:id>/download')
@applicant_required
def download_template(id):
    """Download a template file."""
    from flask import send_file

    template = Template.query.get(id)
    if not template:
        return jsonify({'error': '模板不存在'}), 404

    if not template.file_path or not os.path.exists(template.file_path):
        return jsonify({'error': '文件不存在'}), 404

    return send_file(
        template.file_path,
        as_attachment=True,
        download_name=template.filename
    )


# ============================================
# API Routes (Return JSON)
# ============================================

@applicant_bp.route('/api/start-application', methods=['POST'])
@applicant_required
def api_start_application():
    """Start a new party membership application.

    Creates an Application record for the current user if they don't have one.

    Returns:
        JSON with success status and application info
    """
    # Check if user already has an application
    existing = Application.query.filter_by(user_id=current_user.id).first()
    if existing:
        return jsonify({
            'success': False,
            'error': '您已开始入党申请流程'
        }), 400

    # Check if user has a branch
    if not current_user.branch_id:
        return jsonify({
            'success': False,
            'error': '您尚未分配到任何支部，请联系管理员'
        }), 400

    # Create new application
    application = Application(
        user_id=current_user.id,
        branch_id=current_user.branch_id,
        current_stage=1,
        current_step='L1',
        status='in_progress',
        apply_date=date.today()
    )

    db.session.add(application)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '入党申请已启动',
        'data': {
            'id': application.id,
            'current_stage': application.current_stage,
            'current_step': application.current_step,
            'status': application.status
        }
    })


@applicant_bp.route('/api/progress')
@applicant_required
def api_progress():
    """API endpoint to get current application progress.

    Returns:
        JSON with progress information including:
        - current_stage: Current stage number (1-5)
        - current_step: Current step code
        - total_steps: Total number of steps (26)
        - completed_steps: Number of completed steps
        - progress_percentage: Progress as percentage
        - stages: Detailed stage information
    """
    application = Application.query.filter_by(user_id=current_user.id).first()

    if not application:
        return jsonify({
            'success': False,
            'error': '未找到申请记录',
            'data': None
        })

    # Get all step definitions
    all_steps = StepDefinition.query.order_by(
        StepDefinition.stage, StepDefinition.order_num
    ).all()

    total_steps = len(all_steps)

    # Get completed step records
    completed_records = StepRecord.query.filter_by(
        application_id=application.id,
        status='completed'
    ).all()
    completed_step_codes = {r.step_code for r in completed_records}

    # Calculate current position
    current_step_index = 0
    for i, step in enumerate(all_steps):
        if step.step_code == application.current_step:
            current_step_index = i
            break

    # Group by stages
    stages_info = []
    for stage_num in range(1, 6):
        stage_steps = [s for s in all_steps if s.stage == stage_num]
        completed_in_stage = sum(1 for s in stage_steps if s.step_code in completed_step_codes)

        stages_info.append({
            'stage': stage_num,
            'name': get_stage_name(stage_num),
            'total_steps': len(stage_steps),
            'completed_steps': completed_in_stage,
            'is_current': application.current_stage == stage_num
        })

    # Calculate progress percentage
    progress_percentage = round((current_step_index / total_steps) * 100, 1) if total_steps > 0 else 0

    return jsonify({
        'success': True,
        'data': {
            'current_stage': application.current_stage,
            'current_step': application.current_step,
            'total_steps': total_steps,
            'completed_steps': len(completed_step_codes),
            'progress_percentage': progress_percentage,
            'stages': stages_info,
            'status': application.status,
            'apply_date': application.apply_date.strftime('%Y-%m-%d') if application.apply_date else None
        }
    })


@applicant_bp.route('/api/documents')
@applicant_required
def api_documents():
    """API endpoint to get document list for current applicant.

    Returns:
        JSON with list of documents including:
        - id: Document ID
        - filename: Original filename
        - doc_type: Document type
        - step_code: Associated step code
        - file_size: File size in bytes
        - uploaded_at: Upload timestamp
    """
    application = Application.query.filter_by(user_id=current_user.id).first()

    if not application:
        return jsonify({
            'success': False,
            'error': '未找到申请记录',
            'data': []
        })

    # Get all documents for this application
    documents = Document.query.filter_by(
        application_id=application.id
    ).order_by(Document.uploaded_at.desc()).all()

    docs_list = [{
        'id': doc.id,
        'filename': doc.original_filename or doc.filename,
        'doc_type': doc.doc_type,
        'step_code': doc.step_code,
        'file_size': doc.file_size,
        'file_size_readable': format_file_size(doc.file_size),
        'uploaded_at': cn_time_str(doc.uploaded_at, '%Y-%m-%d %H:%M:%S')
    } for doc in documents]

    return jsonify({
        'success': True,
        'data': docs_list,
        'count': len(docs_list)
    })


@applicant_bp.route('/api/documents', methods=['POST'])
@applicant_required
def api_upload_document():
    """API endpoint to upload a document.

    Expects multipart/form-data with:
        - file: The document file
        - doc_type: Document type (optional)
        - step_code: Associated step code (optional)

    Returns:
        JSON with upload result and document info
    """
    application = Application.query.filter_by(user_id=current_user.id).first()

    if not application:
        return jsonify({
            'success': False,
            'error': '未找到申请记录，请先开始申请流程'
        }), 400

    # Check if file is present
    if 'file' not in request.files:
        return jsonify({
            'success': False,
            'error': '请选择要上传的文件'
        }), 400

    file = request.files['file']

    # Check if file was selected
    if file.filename == '':
        return jsonify({
            'success': False,
            'error': '请选择要上传的文件'
        }), 400

    # Check file extension
    if not allowed_file(file.filename):
        return jsonify({
            'success': False,
            'error': '不支持的文件类型，请上传 PDF、Word、Excel 或图片文件'
        }), 400

    # Get form data
    doc_type = request.form.get('doc_type', 'general')
    step_code = request.form.get('step_code', application.current_step)

    # 步骤级别权限校验：申请人只能在 submitter_role='applicant' 的步骤上传文档
    # Step-level permission check: applicant can only upload on steps where submitter_role='applicant'
    step_def = StepDefinition.query.filter_by(step_code=step_code).first()
    if step_def and step_def.submitter_role != 'applicant':
        # 根据步骤的提交者角色给出相应的等待提示
        if step_def.submitter_role == 'secretary':
            waiting_msg = '当前步骤需要书记处理，请等待书记完成操作'
        elif step_def.submitter_role == 'admin':
            waiting_msg = '当前步骤需要党委处理，请等待党委完成操作'
        else:
            waiting_msg = '当前步骤不允许申请人提交，请等待相关负责人处理'
        return jsonify({
            'success': False,
            'message': waiting_msg
        }), 403

    # Secure filename and create upload path
    original_filename = file.filename
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_filename = f"{current_user.id}_{timestamp}_{filename}"

    # Create upload directory if not exists
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'documents')
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, unique_filename)

    try:
        # Save file
        file.save(file_path)

        # Get file size
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
            uploaded_by=current_user.id
        )

        db.session.add(document)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '文件上传成功',
            'data': {
                'id': document.id,
                'filename': original_filename,
                'doc_type': doc_type,
                'step_code': step_code,
                'file_size': file_size,
                'uploaded_at': cn_time_str(document.uploaded_at, '%Y-%m-%d %H:%M:%S')
            }
        })

    except Exception as e:
        # Clean up file if database save fails
        if os.path.exists(file_path):
            os.remove(file_path)

        return jsonify({
            'success': False,
            'error': f'文件上传失败：{str(e)}'
        }), 500


@applicant_bp.route('/api/documents/<int:doc_id>/download')
@applicant_required
def api_download_document(doc_id):
    """API endpoint to download a document file."""
    from flask import send_file

    application = Application.query.filter_by(user_id=current_user.id).first()
    if not application:
        return jsonify({'error': '未找到申请记录'}), 400

    document = Document.query.filter_by(
        id=doc_id,
        application_id=application.id
    ).first()

    if not document:
        return jsonify({'error': '文档不存在'}), 404

    if not document.file_path or not os.path.exists(document.file_path):
        return jsonify({'error': '文件不存在'}), 404

    return send_file(
        document.file_path,
        as_attachment=True,
        download_name=document.original_filename or document.filename
    )


@applicant_bp.route('/api/documents/<int:doc_id>', methods=['DELETE'])
@applicant_required
def api_delete_document(doc_id):
    """API endpoint to delete a document.

    Only allows deletion of documents that are in 'pending' or 'rejected' status.
    Approved documents cannot be deleted by the applicant.

    Returns:
        JSON with success status
    """
    application = Application.query.filter_by(user_id=current_user.id).first()

    if not application:
        return jsonify({
            'success': False,
            'error': '未找到申请记录'
        }), 400

    # Find the document and verify ownership (belongs to this applicant's application)
    document = Document.query.filter_by(
        id=doc_id,
        application_id=application.id
    ).first()

    if not document:
        return jsonify({
            'success': False,
            'error': '文档不存在'
        }), 404

    # Permission check: applicant can only delete documents that are:
    # - pending (not yet reviewed by anyone)
    # - secretary_rejected (secretary rejected, applicant can delete and resubmit)
    # - rejected (legacy value, treated same as secretary_rejected)
    # Any approved state (secretary_approved, admin_approved, approved) is not deletable.
    # admin_rejected is also not deletable by applicant (secretary handles that).
    deletable_statuses = ('pending', 'secretary_rejected', 'rejected')
    if document.review_status not in deletable_statuses:
        if document.review_status in ('secretary_approved', 'admin_approved', 'approved'):
            return jsonify({
                'success': False,
                'error': '已通过的文档不能删除'
            }), 403
        elif document.review_status == 'admin_rejected':
            return jsonify({
                'success': False,
                'error': '管理员驳回的文档请联系支部书记处理'
            }), 403
        else:
            return jsonify({
                'success': False,
                'error': '当前状态的文档不能删除'
            }), 403

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
            'error': f'删除失败：{str(e)}'
        }), 500


@applicant_bp.route('/api/todos')
@applicant_required
def api_todos():
    """API endpoint to get todo items for current applicant.

    Returns:
        JSON with list of todo items including:
        - title: Todo title
        - description: Todo description
        - priority: Priority level (urgent/normal/info)
        - action_url: URL to complete the action
    """
    application = Application.query.filter_by(user_id=current_user.id).first()

    if not application:
        return jsonify({
            'success': True,
            'data': [{
                'title': '开始入党申请',
                'description': '您尚未开始入党申请流程，请联系党支部获取申请资格',
                'priority': 'urgent',
                'action_url': None
            }]
        })

    # Get current step definition
    current_step_def = StepDefinition.query.filter_by(
        step_code=application.current_step
    ).first()

    # Check for failed (rejected) step on the current step
    failed_step = None
    failed_record = StepRecord.query.filter_by(
        application_id=application.id,
        step_code=application.current_step,
        status='failed'
    ).order_by(StepRecord.completed_at.desc()).first()

    if failed_record:
        failed_step_def = StepDefinition.query.filter_by(
            step_code=failed_record.step_code
        ).first()
        reviewer_name = None
        if failed_record.completed_by:
            reviewer = User.query.get(failed_record.completed_by)
            reviewer_name = reviewer.name if reviewer else None
        failed_step = {
            'step_code': failed_record.step_code,
            'step_name': failed_step_def.name if failed_step_def else failed_record.step_code,
            'reason': failed_record.result or '未提供原因',
            'reviewer_name': reviewer_name,
        }

    todos = generate_todos(application, current_step_def, failed_step)

    return jsonify({
        'success': True,
        'data': todos,
        'count': len(todos)
    })


# ============================================
# Helper Functions
# ============================================

def generate_todos(application, current_step_def, failed_step=None):
    """Generate todo items based on application status.

    Args:
        application: Application object
        current_step_def: Current StepDefinition object or None
        failed_step: Dict with rejected step info (step_code, step_name, reason, etc.) or None

    Returns:
        List of todo item dictionaries
    """
    todos = []

    if not application:
        return [{
            'title': '开始入党申请',
            'description': '您尚未开始入党申请流程，请联系党支部获取申请资格',
            'priority': 'urgent',
            'action_url': None
        }]

    # If the current step was rejected, show a prominent rejection notification
    # as the first todo item, and skip the normal document upload reminder.
    if failed_step:
        reviewer_info = ''
        if failed_step.get('reviewer_name'):
            reviewer_info = f'（审核人：{failed_step["reviewer_name"]}）'
        todos.append({
            'title': f'步骤 {failed_step["step_code"]}（{failed_step["step_name"]}）已被驳回',
            'description': f'驳回原因：{failed_step["reason"]}{reviewer_info}。请删除被驳回的文档，重新上传材料后提交审核。',
            'priority': 'urgent',
            'action_url': '/applicant/documents'
        })
    elif current_step_def:
        # 根据步骤的 submitter_role 判断申请人应该看到什么内容
        # Determine what the applicant sees based on the step's submitter_role
        submitter_role = getattr(current_step_def, 'submitter_role', 'applicant')

        if submitter_role == 'applicant':
            # 申请人步骤：显示上传/提交操作（原有行为）
            # Applicant step: show upload/submit actions (original behavior)
            uploaded_count = Document.query.filter_by(
                application_id=application.id,
                step_code=current_step_def.step_code
            ).count()

            if uploaded_count == 0:
                todos.append({
                    'title': f'上传{current_step_def.name}相关材料',
                    'description': f'当前步骤 "{current_step_def.name}" 需要上传相关证明材料',
                    'priority': 'urgent',
                    'action_url': '/applicant/documents'
                })
        elif submitter_role == 'secretary':
            # 书记步骤：显示等待提示
            # Secretary step: show waiting message
            todos.append({
                'title': f'等待书记处理 - {current_step_def.name}',
                'description': f'当前步骤 "{current_step_def.name}" 需要支部书记处理，请耐心等待',
                'priority': 'info',
                'action_url': None,
                'waiting_for': 'secretary'
            })
        elif submitter_role == 'admin':
            # 管理员步骤：显示等待提示
            # Admin step: show waiting message
            todos.append({
                'title': f'等待党委处理 - {current_step_def.name}',
                'description': f'当前步骤 "{current_step_def.name}" 需要党委处理，请耐心等待',
                'priority': 'info',
                'action_url': None,
                'waiting_for': 'admin'
            })
        else:
            # 未知角色：通用等待提示
            todos.append({
                'title': f'等待处理 - {current_step_def.name}',
                'description': f'当前步骤 "{current_step_def.name}" 正在由相关负责人处理中',
                'priority': 'info',
                'action_url': None
            })

    # Check for overdue quarterly reviews (for stages 2-4)
    if application.current_stage in [2, 3, 4]:
        # Add quarterly review reminder if applicable
        from app.models import QuarterlyReview
        latest_review = QuarterlyReview.query.filter_by(
            application_id=application.id
        ).order_by(QuarterlyReview.created_at.desc()).first()

        if not latest_review or (datetime.now() - latest_review.created_at).days > 90:
            todos.append({
                'title': '提交季度思想汇报',
                'description': '您需要定期提交季度思想汇报',
                'priority': 'normal',
                'action_url': '/applicant/documents'
            })

    # Add general reminders based on stage
    if application.current_stage == 1:
        todos.append({
            'title': '了解入党流程',
            'description': '仔细阅读入党申请书相关要求，准备申请材料',
            'priority': 'info',
            'action_url': '/applicant/progress'
        })
    elif application.current_stage == 2:
        todos.append({
            'title': '参加党课学习',
            'description': '积极参加党组织安排的党课和培训活动',
            'priority': 'normal',
            'action_url': None
        })
    elif application.current_stage == 3:
        todos.append({
            'title': '准备政治审查材料',
            'description': '配合党组织完成政治审查工作',
            'priority': 'normal',
            'action_url': '/applicant/documents'
        })
    elif application.current_stage == 4:
        todos.append({
            'title': '参加组织活动',
            'description': '积极参加预备党员期间的各项组织活动',
            'priority': 'normal',
            'action_url': None
        })
    elif application.current_stage == 5:
        todos.append({
            'title': '准备转正材料',
            'description': '撰写转正申请书，准备转正相关材料',
            'priority': 'urgent',
            'action_url': '/applicant/documents'
        })

    return todos


def format_file_size(size_bytes):
    """Format file size to human readable format.

    Args:
        size_bytes: File size in bytes

    Returns:
        Formatted string (e.g., '1.5 MB')
    """
    if size_bytes is None:
        return '未知'

    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0

    return f"{size_bytes:.1f} TB"
