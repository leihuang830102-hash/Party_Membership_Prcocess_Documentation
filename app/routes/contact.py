"""
Contact person routes for the Party Membership Application System.
Handles the 入党联系人 dashboard showing assigned applicants.
"""

from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db
from app.models import User, Application, StepDefinition, StepRecord, ContactAssignment

# China Standard Time (UTC+8)
CHINA_TZ = timezone(timedelta(hours=8))

contact_bp = Blueprint('contact', __name__)


def contact_required(f):
    """Decorator to require contact_person role."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_contact_person():
            return jsonify({'error': '无权访问'}), 403
        return f(*args, **kwargs)
    return decorated_function


def cn_time_str(dt, fmt='%Y-%m-%d %H:%M'):
    """Format a UTC datetime to China Standard Time string."""
    if dt is None:
        return '-'
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CHINA_TZ).strftime(fmt)


# Stage display names
STAGE_NAMES = {
    1: '入党申请阶段',
    2: '入党积极分子阶段',
    3: '发展对象阶段',
    4: '预备党员接收阶段',
    5: '预备党员考察和转正阶段',
}


@contact_bp.route('/dashboard')
@login_required
def dashboard():
    """Contact person dashboard showing assigned applicants and their progress."""
    # Get active assignments for this contact person
    assignments = ContactAssignment.query.filter_by(
        contact_user_id=current_user.id,
        is_active=True
    ).order_by(ContactAssignment.assigned_at.desc()).all()

    assigned_applicants = []
    for assignment in assignments:
        app = Application.query.get(assignment.application_id)
        if not app:
            continue

        applicant_user = User.query.get(app.user_id)
        if not applicant_user:
            continue

        # Resolve current step name
        step_def = StepDefinition.query.filter_by(step_code=app.current_step).first()
        step_name = step_def.name if step_def else app.current_step

        # Count completed steps
        completed_count = StepRecord.query.filter_by(
            application_id=app.id, status='completed'
        ).count()
        total_steps = StepDefinition.query.count()

        assigned_applicants.append({
            'app_id': app.id,
            'applicant_name': applicant_user.name,
            'applicant_username': applicant_user.username,
            'branch_name': app.branch.name if app.branch else '-',
            'current_stage': app.current_stage,
            'stage_name': STAGE_NAMES.get(app.current_stage, '未知'),
            'current_step': app.current_step,
            'step_name': step_name,
            'status': app.status,
            'progress': f'{completed_count}/{total_steps}',
            'progress_pct': round(completed_count / total_steps * 100) if total_steps else 0,
            'apply_date': app.apply_date.strftime('%Y-%m-%d') if app.apply_date else '-',
            'assigned_at': cn_time_str(assignment.assigned_at),
        })

    return render_template('contact/dashboard.html',
        assigned_applicants=assigned_applicants,
        total_assigned=len(assigned_applicants),
    )
