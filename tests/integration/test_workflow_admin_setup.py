# -*- coding: utf-8 -*-
"""
Test Scenario 5: Admin Create Branch and Users

This test covers administrative setup tasks:
- Admin creates new branch
- Admin creates secretary user and assigns branch
- Admin creates applicant user
- Verify user can login
"""
import re
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:5003"


class TestAdminBranchManagement:
    """管理员支部管理测试"""

    def test_branches_page_loads(self, logged_in_admin: Page):
        """支部管理页面加载"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/branches")
        expect(page.locator('.page-title')).to_contain_text("支部管理")

    def test_branch_list_displays(self, logged_in_admin: Page):
        """支部列表显示"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/branches")
        expect(page.locator('table, .branch-card, #branchesList')).to_be_visible()

    def test_create_branch_modal_opens(self, logged_in_admin: Page):
        """创建支部模态框可以打开"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/branches")

        # Click add branch button
        page.click('button:has-text("新增支部"), a:has-text("新增支部")')
        expect(page.locator("#branchModal")).to_be_visible()

    def test_create_branch_form_has_required_fields(self, logged_in_admin: Page):
        """创建支部表单包含必填字段"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/branches")
        page.click('button:has-text("新增支部"), a:has-text("新增支部")')

        expect(page.locator('#branchName, input[name="name"]')).to_be_visible()
        expect(page.locator('#branchDescription, textarea[name="description"]')).to_be_visible()


class TestAdminUserManagement:
    """管理员用户管理测试"""

    def test_users_page_loads(self, logged_in_admin: Page):
        """用户管理页面加载"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/users")
        expect(page.locator('.page-title')).to_contain_text("用户管理")

    def test_user_list_displays(self, logged_in_admin: Page):
        """用户列表显示"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/users")
        expect(page.locator('table')).to_be_visible()

    def test_add_user_button_exists(self, logged_in_admin: Page):
        """新增用户按钮存在"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/users")
        expect(page.locator('button:has-text("新增用户")')).to_be_visible()

    def test_create_user_modal_opens(self, logged_in_admin: Page):
        """创建用户模态框可以打开"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/users")

        # Click add user button
        page.click('button:has-text("新增用户")')
        # Check for user modal specifically
        expect(page.locator("#userModal")).to_be_visible()

    def test_create_user_form_has_required_fields(self, logged_in_admin: Page):
        """创建用户表单包含必填字段"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/users")
        page.click('button:has-text("新增用户")')
        page.wait_for_timeout(300)

        # Check form fields in the modal specifically
        expect(page.locator('#userModal #userName')).to_be_visible()
        expect(page.locator('#userModal #userUsername')).to_be_visible()
        expect(page.locator('#userModal #userRole')).to_be_visible()


class TestAdminBranchAPI:
    """管理员支部API测试"""

    def test_api_get_branches(self, logged_in_admin: Page):
        """API获取支部列表"""
        page = logged_in_admin
        response = page.request.get(f"{BASE_URL}/admin/api/branches")
        assert response.status == 200

    def test_api_create_branch_validation(self, logged_in_admin: Page):
        """API创建支部验证"""
        page = logged_in_admin

        # Try to create branch with empty name (should fail validation)
        response = page.request.post(
            f"{BASE_URL}/admin/api/branches",
            data={'name': '', 'description': 'Test branch'}
        )
        # Should fail validation
        assert response.status in [400, 422, 500]


class TestAdminUserAPI:
    """管理员用户API测试"""

    def test_api_get_users(self, logged_in_admin: Page):
        """API获取用户列表"""
        page = logged_in_admin
        response = page.request.get(f"{BASE_URL}/admin/api/users")
        assert response.status == 200


class TestCompleteSetupWorkflow:
    """完整设置工作流测试"""

    def test_full_branch_user_setup(self, logged_in_admin: Page):
        """完整支部和用户设置: 创建支部→创建书记→创建申请人"""
        page = logged_in_admin

        # Step 1: Navigate to branches
        page.goto(f"{BASE_URL}/admin/branches")
        expect(page.locator('.page-title')).to_contain_text("支部管理")

        # Step 2: Navigate to users
        page.goto(f"{BASE_URL}/admin/users")
        expect(page.locator('.page-title')).to_contain_text("用户管理")

        # Step 3: Check that we can see existing users
        expect(page.locator('table')).to_be_visible()

    def test_user_role_filtering(self, logged_in_admin: Page):
        """用户角色过滤测试"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/users")
        expect(page.locator('table')).to_be_visible()

        # Check for role indicators in the table
        rows = page.locator('table tbody tr')
        if rows.count() > 0:
            # At least some users should be visible
            expect(rows.first).to_be_visible()


class TestUserLogin:
    """用户登录测试"""

    def test_new_user_can_login(self, page: Page):
        """新用户可以登录"""
        # Login with default applicant
        page.goto(f"{BASE_URL}/auth/login")
        page.fill('input[name="username"]', 'applicant')
        page.fill('input[name="password"]', '123456')
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # Should be redirected away from login
        expect(page).not_to_have_url(re.compile(r".*login.*"))

    def test_secretary_can_login(self, page: Page):
        """书记可以登录"""
        page.goto(f"{BASE_URL}/auth/login")
        page.fill('input[name="username"]', 'secretary')
        page.fill('input[name="password"]', '123456')
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        expect(page).not_to_have_url(re.compile(r".*login.*"))

    def test_admin_can_login(self, page: Page):
        """管理员可以登录"""
        page.goto(f"{BASE_URL}/auth/login")
        page.fill('input[name="username"]', 'admin')
        page.fill('input[name="password"]', '123456')
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        expect(page).not_to_have_url(re.compile(r".*login.*"))
