# -*- coding: utf-8 -*-
"""
Integration tests for admin functionality
"""
import pytest
from playwright.sync_api import Page, expect


class TestAdminDashboard:
    """Test admin dashboard"""

    def test_dashboard_loads(self, logged_in_admin):
        """Test that admin dashboard loads"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/dashboard")

        expect(page.locator(".page-title")).to_contain_text("管理首页")

    def test_stats_cards_visible(self, logged_in_admin):
        """Test that statistics cards are visible"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/dashboard")

        expect(page.locator(".stat-card")).to_have_count(4)

    def test_quick_actions_visible(self, logged_in_admin):
        """Test that quick action cards are visible"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/dashboard")

        expect(page.locator('.action-card:has-text("用户管理")')).to_be_visible()
        expect(page.locator('.action-card:has-text("支部管理")')).to_be_visible()
        expect(page.locator('.action-card:has-text("模板管理")')).to_be_visible()


class TestUserManagement:
    """Test user management functionality"""

    def test_users_page_loads(self, logged_in_admin):
        """Test that users list page loads"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/users")

        expect(page.locator(".page-title")).to_contain_text("用户管理")

    def test_user_list_displays(self, logged_in_admin):
        """Test that user list displays users"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/users")

        # Check table exists
        expect(page.locator("table")).to_be_visible()

    def test_add_user_button_exists(self, logged_in_admin):
        """Test that add user button exists"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/users")

        # Check for "新增用户" button
        expect(page.locator('button:has-text("新增用户")')).to_be_visible()


class TestBranchManagement:
    """Test branch management functionality"""

    def test_branches_page_loads(self, logged_in_admin):
        """Test that branches list page loads"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/branches")

        expect(page.locator(".page-title")).to_contain_text("支部管理")

    def test_branch_list_displays(self, logged_in_admin):
        """Test that branch list displays branches"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/branches")

        # Check table exists
        expect(page.locator("table")).to_be_visible()


class TestTemplateManagement:
    """Test template management functionality"""

    def test_templates_page_loads(self, logged_in_admin):
        """Test that templates list page loads"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/templates")

        expect(page.locator(".page-title")).to_contain_text("模板管理")

    def test_template_list_displays(self, logged_in_admin):
        """Test that template list displays"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/templates")

        # Check templates grid or empty state exists
        expect(page.locator("#templatesGrid")).to_be_visible()


class TestApprovalManagement:
    """Test approval management functionality"""

    def test_approvals_page_loads(self, logged_in_admin):
        """Test that approvals list page loads"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/approvals")

        expect(page.locator(".page-title, h1.page-title")).to_contain_text("审批")
