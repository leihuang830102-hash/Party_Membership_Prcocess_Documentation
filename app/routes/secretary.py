"""
Secretary routes for the Party Membership Application Management System.
Secretary can manage applicants and documents within their own branch.
"""

from datetime import date, datetime, timezone, timedelta
from flask import Blueprint, render_template, jsonify, request, flash
from flask_login import login_required, current_user
from functools import wraps
from app.models import User, Application, StepRecord, Document, StepDefinition, Branch, ContactAssignment
from app import db

# China Standard Time (UTC+8) - used for consistent timestamp display
CHINA_TZ = timezone(timedelta(hours=8))


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
    pending_list = []
    for app in pending_applications:
        # Resolve the step definition name for a readable step label
        step_def = StepDefinition.query.filter_by(step_code=app.current_step).first()
        step_name = step_def.name if step_def else app.current_step

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
            # Default todo type/label for pending items on the dashboard
            'todo_type': 'review',
            'todo_label': '待审核',
        })

    # Query pending documents awaiting secretary review in this branch
    pending_documents = Document.query.join(Application).filter(
        Application.branch_id == branch_id,
        Document.review_status == 'pending'
    ).order_by(Document.uploaded_at.desc()).limit(10).all()

    # Add document review items to the pending list
    for doc in pending_documents:
        # Resolve step definition name for the document's step
        step_def = StepDefinition.query.filter_by(step_code=doc.step_code).first()
        step_name = step_def.name if step_def else (doc.step_code or '')

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
            'todo_type': 'document_review',
            'todo_label': '待审核文档',
            # Extra fields specific to document review items
            'doc_name': doc.original_filename or doc.filename,
            'doc_id': doc.id,
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
            'status': record.status if record else 'not_started',
            'completed_at': record.completed_at if record else None,
            'result': record.result if record else None
        })

    # Get documents for this application
    documents = Document.query.filter_by(application_id=id).order_by(
        Document.uploaded_at.desc()
    ).all()

    # Get current contact person (if assigned)
    contact_person = application.contact_person

    # Get candidate contact persons: contact_person, secretary, and admin users in the same branch
    # These are users who can serve as 入党联系人 (party membership contacts)
    candidate_contacts = User.query.filter(
        User.branch_id == application.branch_id,
        User.role.in_(['contact_person', 'secretary', 'admin']),
        User.is_active == True
    ).all()

    return render_template('secretary/applicant_detail.html',
                         application=application,
                         user=application.user,
                         timeline=timeline,
                         documents=documents,
                         contact_person=contact_person,
                         candidate_contacts=candidate_contacts)


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
    Approve or reject an application step.

    Request body:
    - step_code: the step to approve/reject
    - action: 'approve' or 'reject' (default: 'approve' for backward compatibility)
    - result: optional result/notes/rejection reason

    Behavior:
    - Approve: marks step as completed, advances current_step to next step
    - Reject: marks step as failed, keeps current_step unchanged so applicant can re-apply
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
        # Approve: mark step as completed and advance to next step
        step_record.status = 'completed'
        step_record.result = result
        step_record.completed_at = datetime.utcnow()
        step_record.completed_by = current_user.id

        # Advance to the next step in sequence
        next_step = StepDefinition.query.filter(
            StepDefinition.order_num > step_def.order_num
        ).order_by(StepDefinition.order_num).first()

        if next_step:
            application.current_step = next_step.step_code
            application.current_stage = next_step.stage
        else:
            # All steps completed - mark application as completed
            application.status = 'completed'

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '步骤已通过',
            'data': {
                'step_code': step_code,
                'status': 'completed',
                'completed_at': step_record.completed_at.isoformat(),
                'next_step': next_step.step_code if next_step else None
            }
        })

    else:
        # Reject: mark step as failed, keep current_step at this step
        # Applicant can re-upload documents and re-apply for this step
        step_record.status = 'failed'
        step_record.result = result if result else '步骤被驳回'
        step_record.completed_at = datetime.utcnow()
        step_record.completed_by = current_user.id

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
        result.append({
            'id': doc.id,
            'filename': doc.original_filename or doc.filename,
            'doc_type': doc.doc_type,
            'step_code': doc.step_code,
            'file_size': doc.file_size,
            'uploaded_at': cn_time_str(doc.uploaded_at),
            'applicant_name': applicant_name,
            'status': doc.review_status or 'pending',
        })

    return jsonify({'success': True, 'documents': result})


@secretary_bp.route('/api/documents/<int:id>/review', methods=['POST'])
@secretary_required
def api_review_document(id):
    """
    Review a document (approve or reject).
    Updates the Document's review_status, reviewed_by, reviewed_at, review_comment,
    and also updates the linked StepRecord if the document has a step_code.

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

    # Update Document's own review status using two-level status values.
    # Secretary approve: pending -> secretary_approved (waits for admin review)
    # Secretary reject: pending -> secretary_rejected (applicant can delete & resubmit)
    # Also handles re-review after admin rejection:
    #   admin_rejected -> secretary_approved (re-submitted to admin)
    document.review_status = 'secretary_approved' if action == 'approve' else 'secretary_rejected'
    document.reviewed_by = current_user.id
    document.reviewed_at = datetime.utcnow()
    document.review_comment = comment if comment else None

    # If document is linked to a step, also update the step record
    if document.step_code:
        step_record = StepRecord.query.filter_by(
            application_id=application.id,
            step_code=document.step_code
        ).first()

        if step_record:
            if action == 'reject':
                step_record.status = 'failed'
                step_record.result = f'文档审核不通过: {comment}' if comment else '文档审核不通过'
            else:
                # Mark step as completed on approval
                step_record.status = 'completed'
                step_record.result = f'文档审核通过: {comment}' if comment else '文档审核通过'
                step_record.completed_at = datetime.utcnow()
                step_record.completed_by = current_user.id

                # Advance application to next step if this was the current step
                if application.current_step == document.step_code:
                    step_def = StepDefinition.query.filter_by(step_code=document.step_code).first()
                    if step_def:
                        next_step = StepDefinition.query.filter(
                            StepDefinition.order_num > step_def.order_num
                        ).order_by(StepDefinition.order_num).first()
                        if next_step:
                            application.current_step = next_step.step_code
                            application.current_stage = next_step.stage
                        else:
                            application.status = 'completed'

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '文档已审核通过' if action == 'approve' else '文档已驳回',
        'data': {
            'document_id': id,
            'review_status': document.review_status
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

    if contact_user.branch_id != application.branch_id:
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
    candidates = User.query.filter(
        User.branch_id == application.branch_id,
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
