"""
Applicant routes for the Party Membership Application Management System.
Handles applicant dashboard, progress tracking, and document management.
"""

import os
import json
from datetime import datetime
from functools import wraps
from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import Application, StepDefinition, StepRecord, Document, Template

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
    """
    # Get or create application for current user
    application = Application.query.filter_by(user_id=current_user.id).first()

    current_step_info = None
    completed_steps = []
    todos = []

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

        # Get completed steps
        step_records = StepRecord.query.filter_by(
            application_id=application.id,
            status='completed'
        ).all()
        completed_steps = [record.step_code for record in step_records]

        # Generate todos based on current status
        todos = generate_todos(application, current_step_def)
    else:
        # No application yet, show initial todo
        todos = [{
            'title': '开始入党申请',
            'description': '您尚未开始入党申请流程，请联系党支部获取申请资格',
            'priority': 'urgent',
            'action_url': None
        }]

    return render_template('applicant/dashboard.html',
                         current_step=current_step_info,
                         completed_steps=completed_steps,
                         todos=todos)


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
        stages[step.stage]['steps'].append({
            'code': step.step_code,
            'name': step.name,
            'description': step.description,
            'is_completed': step.step_code in completed_steps,
            'is_current': step.step_code == current_step_code
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
    required_templates = []

    if application:
        # Get uploaded documents
        uploaded_docs = Document.query.filter_by(
            application_id=application.id
        ).order_by(Document.uploaded_at.desc()).all()

        documents_list = [{
            'id': doc.id,
            'filename': doc.original_filename or doc.filename,
            'doc_type': doc.doc_type,
            'step_code': doc.step_code,
            'file_size': doc.file_size,
            'uploaded_at': doc.uploaded_at.strftime('%Y-%m-%d %H:%M')
        } for doc in uploaded_docs]

        # Get required templates for current step
        current_step_def = StepDefinition.query.filter_by(
            step_code=application.current_step
        ).first()

        if current_step_def and current_step_def.required_templates:
            try:
                template_ids = json.loads(current_step_def.required_templates)
                if template_ids:
                    templates = Template.query.filter(
                        Template.id.in_(template_ids)
                    ).all()
                    required_templates = [{
                        'id': t.id,
                        'name': t.name,
                        'description': t.description,
                        'step_code': t.step_code
                    } for t in templates]
            except json.JSONDecodeError:
                pass

    return render_template('applicant/documents.html',
                         documents=documents_list,
                         required_templates=required_templates,
                         application=application)


# ============================================
# API Routes (Return JSON)
# ============================================

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
        'uploaded_at': doc.uploaded_at.strftime('%Y-%m-%d %H:%M:%S') if doc.uploaded_at else None
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
                'uploaded_at': document.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')
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

    todos = generate_todos(application, current_step_def)

    return jsonify({
        'success': True,
        'data': todos,
        'count': len(todos)
    })


# ============================================
# Helper Functions
# ============================================

def generate_todos(application, current_step_def):
    """Generate todo items based on application status.

    Args:
        application: Application object
        current_step_def: Current StepDefinition object or None

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

    # Check for missing documents at current step
    if current_step_def:
        # Check if documents are uploaded for current step
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
