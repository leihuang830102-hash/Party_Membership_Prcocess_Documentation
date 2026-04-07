"""
Secretary routes for the Party Membership Application Management System.
Secretary can manage applicants and documents within their own branch.
"""

from datetime import date
from flask import Blueprint, render_template, jsonify, request, flash
from flask_login import login_required, current_user
from functools import wraps
from app.models import User, Application, StepRecord, Document, StepDefinition, Branch
from app import db

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

    # Statistics
    # Pending count: applications with status 'in_progress' in secretary's branch
    pending_count = Application.query.filter_by(
        branch_id=branch_id,
        status='in_progress'
    ).count()

    # In progress count: same as pending (applications in progress)
    in_progress_count = pending_count

    # This month new count: applications created this month
    this_month_new = Application.query.filter(
        Application.branch_id == branch_id,
        Application.status == 'in_progress',
        Application.created_at >= month_start
    ).count()

    # Pending applications list (latest 10)
    pending_applications = Application.query.filter_by(
        branch_id=branch_id,
        status='in_progress'
    ).order_by(Application.updated_at.desc()).limit(10).all()

    # Get user info for each application
    pending_list = []
    for app in pending_applications:
        pending_list.append({
            'id': app.id,
            'user_name': app.user.name,
            'current_step': app.current_step,
            'apply_date': app.apply_date,
            'updated_at': app.updated_at
        })

    return render_template('secretary/dashboard.html',
                         pending_count=pending_count,
                         in_progress_count=in_progress_count,
                         this_month_new=this_month_new,
                         pending_applications=pending_list)


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
            'status': record.status if record else 'not_started',
            'completed_at': record.completed_at if record else None,
            'result': record.result if record else None
        })

    # Get documents for this application
    documents = Document.query.filter_by(application_id=id).order_by(
        Document.uploaded_at.desc()
    ).all()

    return render_template('secretary/applicant_detail.html',
                         application=application,
                         user=application.user,
                         timeline=timeline,
                         documents=documents)


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
    Approve an application step.
    Request body:
    - step_code: the step to approve
    - result: optional result/notes
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
    result = data.get('result', '')

    if not step_code:
        return jsonify({'success': False, 'message': '缺少步骤代码'}), 400

    # Get step definition
    step_def = StepDefinition.query.filter_by(step_code=step_code).first()
    if not step_def:
        return jsonify({'success': False, 'message': '无效的步骤代码'}), 400

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

    # Update step record
    from datetime import datetime
    step_record.status = 'completed'
    step_record.result = result
    step_record.completed_at = datetime.utcnow()
    step_record.completed_by = current_user.id

    # Update application current step if this is the current step
    if application.current_step == step_code:
        # Find next step
        next_step = StepDefinition.query.filter(
            StepDefinition.order_num > step_def.order_num
        ).order_by(StepDefinition.order_num).first()

        if next_step:
            application.current_step = next_step.step_code
            application.current_stage = next_step.stage
        else:
            # All steps completed
            application.status = 'completed'

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '步骤已审批',
        'data': {
            'step_code': step_code,
            'status': 'completed',
            'completed_at': step_record.completed_at.isoformat()
        }
    })


@secretary_bp.route('/api/documents/<int:id>/review', methods=['POST'])
@secretary_required
def api_review_document(id):
    """
    Review a document.
    Request body:
    - action: 'approve' or 'reject'
    - comment: optional review comment
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

    # Update document status
    # Note: Document model doesn't have review fields, we'll use step_record to track
    # If document is linked to a step, update that step's record
    if document.step_code:
        step_record = StepRecord.query.filter_by(
            application_id=application.id,
            step_code=document.step_code
        ).first()

        if step_record:
            if action == 'reject':
                step_record.status = 'failed'
                step_record.result = f'文档审核不通过: {comment}'
            else:
                # Keep current status or set to completed if this was the pending review
                if step_record.result:
                    step_record.result += f'\n文档审核通过: {comment}'
                else:
                    step_record.result = f'文档审核通过: {comment}'

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '文档已审核',
        'data': {
            'document_id': id,
            'action': action
        }
    })
