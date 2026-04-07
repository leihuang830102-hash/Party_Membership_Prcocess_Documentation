"""
Authentication routes for the Party Membership Application Management System.
Handles login, logout, and authentication-related functionality.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from app.models import User
from app import db

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    # If user is already authenticated, redirect to appropriate dashboard
    if current_user.is_authenticated:
        return redirect_to_dashboard(current_user)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Validate input
        if not username or not password:
            flash('请输入用户名和密码', 'error')
            return render_template('auth/login.html')

        # Find user
        user = User.query.filter_by(username=username).first()

        # Check if user exists and password is correct
        if user is None or not user.check_password(password):
            flash('用户名或密码错误', 'error')
            return render_template('auth/login.html')

        # Check if user account is active
        if not user.is_active:
            flash('该账号已被禁用，请联系管理员', 'error')
            return render_template('auth/login.html')

        # Log in the user
        login_user(user)
        flash('登录成功', 'success')

        # Redirect to appropriate dashboard based on role
        return redirect_to_dashboard(user)

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    """Handle user logout."""
    logout_user()
    flash('您已成功登出', 'success')
    return redirect(url_for('auth.login'))


def redirect_to_dashboard(user):
    """Redirect user to the appropriate dashboard based on their role."""
    if user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif user.role == 'secretary':
        return redirect(url_for('secretary.dashboard'))
    else:  # applicant
        return redirect(url_for('applicant.dashboard'))
