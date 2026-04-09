"""
Notification routes for the Party Membership Application Management System.
Handles notification center page and notification API endpoints.
"""

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.models import Notification
from app import db

notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.route('/notifications')
@login_required
def notifications_page():
    """Render the notification center page."""
    return render_template('notifications/notifications.html')


@notifications_bp.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    """
    Get notifications for the current user.
    Query parameters:
        - status: 'all', 'unread', 'read' (default: 'all')
        - page: page number (default: 1)
        - per_page: items per page (default: 20)
    """
    status = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # Limit per_page to prevent excessive queries
    per_page = min(per_page, 100)

    # Build query for current user's notifications
    query = Notification.query.filter_by(user_id=current_user.id)

    # Filter by read status
    if status == 'unread':
        query = query.filter_by(is_read=False)
    elif status == 'read':
        query = query.filter_by(is_read=True)

    # Order by created_at descending (newest first)
    query = query.order_by(Notification.created_at.desc())

    # Paginate results
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    notifications = []
    for notification in pagination.items:
        notifications.append({
            'id': notification.id,
            'title': notification.title,
            'content': notification.content,
            'link': notification.link,
            'is_read': notification.is_read,
            'created_at': notification.created_at.isoformat() if notification.created_at else None
        })

    return jsonify({
        'success': True,
        'data': {
            'notifications': notifications,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }
    })


@notifications_bp.route('/api/notifications/<int:id>/read', methods=['POST'])
@login_required
def mark_notification_read(id):
    """Mark a single notification as read."""
    notification = Notification.query.filter_by(id=id, user_id=current_user.id).first()

    if notification is None:
        return jsonify({
            'success': False,
            'message': '通知不存在'
        }), 404

    if not notification.is_read:
        notification.is_read = True
        db.session.commit()

    return jsonify({
        'success': True,
        'message': '通知已标记为已读',
        'data': {
            'id': notification.id,
            'is_read': notification.is_read
        }
    })


@notifications_bp.route('/api/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications for the current user as read."""
    # Update all unread notifications for the current user
    updated_count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True})

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'已将 {updated_count} 条通知标记为已读',
        'data': {
            'updated_count': updated_count
        }
    })


@notifications_bp.route('/api/notifications/unread-count', methods=['GET'])
@login_required
def get_unread_count():
    """Get the count of unread notifications for the current user."""
    count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()

    return jsonify({
        'success': True,
        'data': {
            'unread_count': count
        }
    })
