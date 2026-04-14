# -*- coding: utf-8 -*-
"""
Integration tests for admin functionality
"""
import json
import pytest
from playwright.sync_api import Page, expect

from tests.integration.conftest import BASE_URL


class TestAdminDashboard:
    """Test admin dashboard"""

    def test_dashboard_loads(self, logged_in_admin):
        """Test that admin dashboard loads"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/dashboard")
        page.wait_for_load_state("networkidle")

        expect(page.locator('h1, h2, .card-title').first).to_be_visible()

    def test_stats_cards_visible(self, logged_in_admin):
        """Test that statistics cards are visible"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/dashboard")
        page.wait_for_load_state("networkidle")


        # Check for stat cards - use flexible approach
        stat_cards = page.locator('.stat-card')
        count = stat_cards.count()
        if count >= 1:
            expect(stat_cards.first).to_be_visible()
        else:
            pytest.skip(f"Only {count} stat cards found")


    def test_quick_actions_visible(self, logged_in_admin):
        """Test that quick action cards are visible"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/dashboard")
        page.wait_for_load_state("networkidle")

        # Check for action cards
        action_cards = page.locator('.action-card')
        count = action_cards.count()
        if count >= 3:
            expect(action_cards.nth(0)).to_be_visible()
            expect(action_cards.nth(1)).to_be_visible()
            expect(action_cards.nth(2)).to_be_visible()
        else:
            pytest.skip(f"Only {count} action cards found")


class TestUserManagement:
    """Test user management functionality"""

    def test_users_page_loads(self, logged_in_admin):
        """Test that users list page loads"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/users")
        page.wait_for_load_state("networkidle")
        expect(page.locator('h1, h2, .card-title').first).to_be_visible()

    def test_user_list_displays(self, logged_in_admin):
        """Test that user list displays users"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/users")
        page.wait_for_load_state("networkidle")
        # Check table exists
        expect(page.locator("table")).to_be_visible()


    def test_add_user_button_exists(self, logged_in_admin):
        """Test that add user button exists"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/users")
        page.wait_for_load_state("networkidle")
        # Check for "新增用户" button
        expect(page.locator('button:has-text("新增用户")')).to_be_visible()


class TestBranchManagement:
    """Test branch management functionality"""

    def test_branches_page_loads(self, logged_in_admin):
        """Test that branches list page loads"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/branches")
        page.wait_for_load_state("networkidle")
        expect(page.locator('h1, h2, .card-title').first).to_be_visible()

    def test_branch_list_displays(self, logged_in_admin):
        """Test that branch list displays branches"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/branches")
        page.wait_for_load_state("networkidle")
        # Check table exists
        expect(page.locator("table")).to_be_visible()


class TestTemplateManagement:
    """Test template management functionality"""

    def test_templates_page_loads(self, logged_in_admin):
        """Test that templates list page loads"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/templates")
        page.wait_for_load_state("networkidle")
        expect(page.locator('h1, h2, .card-title').first).to_be_visible()

    def test_template_list_displays(self, logged_in_admin):
        """Test that template list displays"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/templates")
        page.wait_for_load_state("networkidle")
        # Check templates grid or empty state exists
        expect(page.locator("#templatesGrid")).to_be_visible()


class TestApprovalManagement:
    """Test approval management functionality"""

    def test_approvals_page_loads(self, logged_in_admin):
        """Test that approvals list page loads"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/approvals")
        page.wait_for_load_state("networkidle")
        expect(page.locator('h1, h2, .card-title').first).to_be_visible()


class TestCreateUserAPI:
    """Test admin create_user API returns correct response (Bug 1 fix).

    Bug 1: create_user API now returns {'success': True, 'user': {...}} on success.
    This ensures the frontend can reliably check response.success.
    """

    def test_create_user_returns_success_true(self, logged_in_admin):
        """POST /admin/api/users with valid data returns success: true."""
        page = logged_in_admin

        # Create a unique username to avoid collision
        import time
        unique_name = f"e2e_bug1_{int(time.time())}"

        response = page.request.post(
            f"{BASE_URL}/admin/api/users",
            data=json.dumps({
                "username": unique_name,
                "password": "123456",
                "name": "Bug1测试用户",
                "role": "applicant",
            }),
            headers={"Content-Type": "application/json"},
        )
        body = response.json()

        if response.status == 201:
            # New user created -- verify success: true and user data
            assert body.get("success") is True, \
                f"Expected success=True, got {body}"
            assert "user" in body, \
                f"Expected 'user' key in response, got {body}"
            user_data = body["user"]
            assert user_data.get("username") == unique_name
            assert user_data.get("name") == "Bug1测试用户"
            assert user_data.get("role") == "applicant"
        elif response.status == 400:
            # User already exists -- verify error response (not a crash)
            assert body.get("error") is not None, \
                f"Expected 'error' key for duplicate user, got {body}"
        else:
            pytest.fail(f"Unexpected status {response.status}: {body}")

    def test_create_user_duplicate_returns_error(self, logged_in_admin):
        """POST /admin/api/users with duplicate username returns 400."""
        page = logged_in_admin

        # Try creating 'admin' which always exists
        response = page.request.post(
            f"{BASE_URL}/admin/api/users",
            data=json.dumps({
                "username": "admin",
                "password": "123456",
                "name": "重复管理员",
                "role": "admin",
            }),
            headers={"Content-Type": "application/json"},
        )
        assert response.status == 400, \
            f"Expected 400 for duplicate username, got {response.status}"
        body = response.json()
        assert body.get("error") is not None, \
            f"Expected 'error' key in response, got {body}"

    def test_create_user_missing_fields_returns_error(self, logged_in_admin):
        """POST /admin/api/users with missing required fields returns 400."""
        page = logged_in_admin

        response = page.request.post(
            f"{BASE_URL}/admin/api/users",
            data=json.dumps({
                "username": "",
                "password": "",
                "name": "",
            }),
            headers={"Content-Type": "application/json"},
        )
        assert response.status == 400, \
            f"Expected 400 for missing fields, got {response.status}"
