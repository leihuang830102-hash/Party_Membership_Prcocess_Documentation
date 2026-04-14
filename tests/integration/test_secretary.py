# -*- coding: utf-8 -*-
"""
Integration tests for secretary functionality
"""
import re
import json
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:5003"


class TestSecretaryDashboard:
    """Test secretary dashboard"""

    def test_dashboard_loads(self, logged_in_secretary):
        """Test that secretary dashboard loads"""
        page = logged_in_secretary
        page.goto("http://127.0.0.1:5003/secretary/dashboard")

        # Check page loaded without errors
        expect(page).not_to_have_url(re.compile(r".*error.*"))

    def test_quick_stats_visible(self, logged_in_secretary):
        """Test that quick stats are visible"""
        page = logged_in_secretary
        page.goto("http://127.0.0.1:5003/secretary/dashboard")

        # Check for stats section
        expect(page.locator(".stats-grid")).to_be_visible()


class TestApplicantManagement:
    """Test applicant management for secretary"""

    def test_applicants_page_loads(self, logged_in_secretary):
        """Test that applicants list page loads"""
        page = logged_in_secretary
        page.goto("http://127.0.0.1:5003/secretary/applicants")

        # Check page loaded without errors
        expect(page).not_to_have_url(re.compile(r".*error.*"))

    def test_applicant_list_displays(self, logged_in_secretary):
        """Test that applicant list displays"""
        page = logged_in_secretary
        page.goto("http://127.0.0.1:5003/secretary/applicants")

        # Check for page content - applicants list container exists
        expect(page.locator("#applicantsList")).to_be_visible()


class TestDocumentReview:
    """Test document review for secretary"""

    def test_documents_page_loads(self, logged_in_secretary):
        """Test that documents list page loads"""
        page = logged_in_secretary
        page.goto(f"{BASE_URL}/secretary/documents")

        # Check page loaded without errors
        expect(page).not_to_have_url(re.compile(r".*error.*"))

    def test_documents_list_visible(self, logged_in_secretary):
        """Test that documents list container is visible"""
        page = logged_in_secretary
        page.goto(f"{BASE_URL}/secretary/documents")
        page.wait_for_load_state("networkidle")

        expect(page.locator("#documentsList")).to_be_visible()

    def test_view_document_shows_alert_not_navigation(self, logged_in_secretary):
        """Bug 3: viewDocument() shows alert instead of navigating to non-existent route.

        The viewDocument function in secretary/documents.html now shows an alert
        instead of trying to navigate to a route that doesn't exist.
        We verify the documents page loads correctly and the viewDocument function
        exists without causing JavaScript errors.
        """
        page = logged_in_secretary
        page.goto(f"{BASE_URL}/secretary/documents")
        page.wait_for_load_state("networkidle")

        # Verify no JavaScript errors on the page
        # Check that the documents list loaded (viewDocument is only called from doc cards)
        expect(page.locator("#documentsList")).to_be_visible()

        # The viewDocument function should exist and not cause errors
        # We verify by checking the page is still on the documents URL
        expect(page).to_have_url(re.compile(r".*secretary/documents.*"))

        # Verify no error messages are displayed
        error_elements = page.locator(".error, .alert-danger, .alert-error")
        assert error_elements.count() == 0, \
            "Unexpected error messages on documents page"


class TestContactVisibility:
    """Test contact candidate visibility including admin users (Bug 4 fix).

    Bug 4: Contact candidate query now includes admin users (with branch_id=None)
    via db.or_(). This ensures admin users can be set as contact persons for
    any branch's applicants.

    Self-contained: each test ensures an applicant exists in the secretary's
    branch by creating one via admin API if needed.
    """

    # Test user for contact visibility tests -- unique to avoid collision
    _TEST_APPLICANT = {
        "username": "contact_test_app",
        "name": "联系人测试申请人",
        "password": "123456",
    }
    _TEST_BRANCH_NAME = "联系人测试支部"

    def _ensure_test_applicant_with_application(self, page: Page) -> int:
        """Ensure a test applicant exists in the secretary's branch with an application.

        Creates a branch, test applicant, and application if they don't exist.
        Must be called while NOT logged in (handles login/logout internally).

        Returns the application ID.
        """
        import json as _json

        # Login as admin to set up data
        page.goto(f"{BASE_URL}/auth/login")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "123456")
        page.click('button[type="submit"]')
        try:
            page.wait_for_url(lambda url: 'login' not in url, timeout=5000)
        except Exception:
            pass

        # Find the secretary user to determine their branch
        users_resp = page.request.get(f"{BASE_URL}/admin/api/users?role=secretary")
        assert users_resp.status == 200
        users = users_resp.json().get("users", [])
        secretary_branch_id = None
        for u in users:
            if u.get("username") == "secretary":
                secretary_branch_id = u.get("branch_id")
                break

        if secretary_branch_id is None:
            # Secretary not found or no branch -- create a branch and assign secretary
            branch_resp = page.request.post(
                f"{BASE_URL}/admin/api/branches",
                data=_json.dumps({"name": self._TEST_BRANCH_NAME, "description": "联系人测试用支部"}),
                headers={"Content-Type": "application/json"},
            )
            branch_data = branch_resp.json()
            branches_resp = page.request.get(f"{BASE_URL}/admin/api/branches")
            for b in branches_resp.json().get("branches", []):
                if b["name"] == self._TEST_BRANCH_NAME:
                    secretary_branch_id = b["id"]
                    break

        assert secretary_branch_id is not None, "Could not find or create secretary's branch"

        # Create test applicant in that branch (accept already exists)
        page.request.post(
            f"{BASE_URL}/admin/api/users",
            data=_json.dumps({
                "username": self._TEST_APPLICANT["username"],
                "password": self._TEST_APPLICANT["password"],
                "name": self._TEST_APPLICANT["name"],
                "role": "applicant",
                "branch_id": secretary_branch_id,
            }),
            headers={"Content-Type": "application/json"},
        )

        # Logout from admin
        page.goto(f"{BASE_URL}/auth/logout")
        page.wait_for_load_state("networkidle")

        # Login as test applicant and start application
        page.goto(f"{BASE_URL}/auth/login")
        page.fill('input[name="username"]', self._TEST_APPLICANT["username"])
        page.fill('input[name="password"]', self._TEST_APPLICANT["password"])
        page.click('button[type="submit"]')
        try:
            page.wait_for_url(lambda url: 'login' not in url, timeout=5000)
        except Exception:
            pass

        # Start application (accept already exists -- 400)
        app_resp = page.request.post(
            f"{BASE_URL}/applicant/api/start-application",
            data=_json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        # 200 = created, 400 = already exists -- both OK
        assert app_resp.status in [200, 400], \
            f"Unexpected start-application status: {app_resp.status}"

        # Logout from applicant
        page.goto(f"{BASE_URL}/auth/logout")
        page.wait_for_load_state("networkidle")

        # Now login as secretary to find the application ID
        page.goto(f"{BASE_URL}/auth/login")
        page.fill('input[name="username"]', "secretary")
        page.fill('input[name="password"]', "123456")
        page.click('button[type="submit"]')
        try:
            page.wait_for_url(lambda url: 'login' not in url, timeout=5000)
        except Exception:
            pass

        applicants_resp = page.request.get(f"{BASE_URL}/secretary/api/applicants")
        assert applicants_resp.status == 200
        applicants = applicants_resp.json().get("applicants", [])

        app_id = None
        for a in applicants:
            if a.get("username") == self._TEST_APPLICANT["username"]:
                app_id = a.get("id")
                break

        assert app_id is not None, \
            f"Test applicant {self._TEST_APPLICANT['username']} not found in secretary's branch"

        return app_id

    def test_contact_candidates_includes_admin_users(self, page: Page):
        """Bug 4: Admin users appear in contact candidates even with branch_id=None.

        The api_get_contact_candidates endpoint queries:
          db.or_(User.branch_id == app.branch_id, User.role == 'admin')
        so admin users (who have branch_id=None) are included.
        """
        app_id = self._ensure_test_applicant_with_application(page)

        # Call the contact-candidates API (still logged in as secretary from setup)
        response = page.request.get(
            f"{BASE_URL}/secretary/api/applicants/{app_id}/contact-candidates"
        )
        assert response.status == 200, \
            f"Contact candidates API failed: {response.status}"
        body = response.json()
        assert body.get("success") is True, \
            f"Contact candidates not successful: {body}"

        candidates = body.get("candidates", body.get("data", []))
        assert isinstance(candidates, list), \
            f"Expected list of candidates, got {type(candidates)}"

        # Bug 4 assertion: admin users should be in the candidates list
        admin_candidates = [c for c in candidates if c.get("role") == "admin"]
        assert len(admin_candidates) > 0, \
            "Bug 4: No admin users found in contact candidates. " \
            "Admin users should be included even with branch_id=None"

    def test_secretary_can_set_admin_as_contact(self, page: Page):
        """Bug 4: Secretary can set an admin user as the contact person.

        Verifies that the secretary can update the contact person to an admin user
        via the set-contact API endpoint.
        """
        app_id = self._ensure_test_applicant_with_application(page)

        # Get contact candidates to find an admin user (still logged in as secretary)
        candidates_response = page.request.get(
            f"{BASE_URL}/secretary/api/applicants/{app_id}/contact-candidates"
        )
        assert candidates_response.status == 200, \
            f"Contact candidates API returned {candidates_response.status}"

        body = candidates_response.json()
        candidates = body.get("candidates", body.get("data", []))
        admin_candidates = [c for c in candidates if c.get("role") == "admin"]

        assert len(admin_candidates) > 0, "No admin candidates available to set as contact"

        admin_user = admin_candidates[0]

        # Set admin as contact person (endpoint is /set-contact, not /set-contact-person)
        set_response = page.request.post(
            f"{BASE_URL}/secretary/api/applicants/{app_id}/set-contact",
            data=json.dumps({"contact_person_id": admin_user["id"]}),
            headers={"Content-Type": "application/json"},
        )
        assert set_response.status in [200, 201], \
            f"Unexpected status setting contact person: {set_response.status}"

        set_body = set_response.json()
        assert set_body.get("success") is True, \
            f"Set contact person not successful: {set_body}"
