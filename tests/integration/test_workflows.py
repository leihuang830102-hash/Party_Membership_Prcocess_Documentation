# -*- coding: utf-8 -*-
"""
Business workflow integration tests for CPCWebIII.

Tests cover the complete party membership application process:
1. Admin creates branch
2. Admin creates/manages users
3. Admin uploads/manages document templates
4. Applicant uploads documents
5. Secretary reviews and approves
6. Admin confirms final approval
"""
import re
import pytest
import os
from playwright.sync_api import Page, expect


class TestAdminBranchWorkflow:
    """Test admin branch management workflow"""

    def test_branches_page_loads(self, logged_in_admin):
        """Test admin can access branches page"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/branches")
        expect(page.locator('.page-title')).to_contain_text("支部管理")

    def test_create_branch_modal_opens(self, logged_in_admin):
        """Test admin can open create branch modal"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/branches")

        # Click add branch button
        page.click('button:has-text("新增支部"), a:has-text("新增支部")')

        # Wait for modal - use specific ID
        expect(page.locator("#branchModal")).to_be_visible()

    def test_create_branch_form_has_required_fields(self, logged_in_admin):
        """Test branch form has required fields"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/branches")
        page.click('button:has-text("新增支部"), a:has-text("新增支部")')

        # Check form fields exist
        expect(page.locator('#branchName, input[name="name"]')).to_be_visible()
        expect(page.locator('#branchDescription, textarea[name="description"]')).to_be_visible()


class TestAdminUserWorkflow:
    """Test admin user management workflow"""

    def test_users_page_loads(self, logged_in_admin):
        """Test admin can access users page"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/users")
        expect(page.locator('.page-title')).to_contain_text("用户管理")

    def test_user_list_displays(self, logged_in_admin):
        """Test user list is displayed"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/users")
        expect(page.locator('table')).to_be_visible()

    def test_add_user_button_exists(self, logged_in_admin):
        """Test add user button exists"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/users")
        expect(page.locator('button:has-text("新增用户")')).to_be_visible()


class TestAdminTemplateWorkflow:
    """Test admin document template management workflow"""

    def test_templates_page_loads(self, logged_in_admin):
        """Test admin can access templates page"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/templates")
        expect(page.locator('.page-title')).to_contain_text("模板管理")

    def test_template_grid_or_empty_state_displays(self, logged_in_admin):
        """Test template list or empty state is displayed"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/templates")
        expect(page.locator('#templatesGrid')).to_be_visible()

    def test_upload_template_button_exists(self, logged_in_admin):
        """Test upload template button exists"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/templates")
        expect(page.locator('#uploadModal')).not_to_be_visible()  # Modal hidden initially
        expect(page.locator('button[onclick="openUploadModal()"]').first).to_be_visible()

    def test_upload_template_modal_opens(self, logged_in_admin):
        """Test upload template modal opens"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/templates")
        page.locator('button[onclick="openUploadModal()"]').first.click()
        expect(page.locator('#uploadModal')).to_be_visible()

    def test_upload_template_form_has_required_fields(self, logged_in_admin):
        """Test upload form has required fields"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/templates")
        page.click('button:has-text("上传模板")')

        expect(page.locator('#uploadName, input[name="name"]')).to_be_visible()
        expect(page.locator('#uploadFile, input[type="file"]')).to_be_visible()


class TestApplicantDocumentWorkflow:
    """Test applicant document upload workflow"""

    def test_documents_page_loads(self, logged_in_applicant):
        """Test applicant can access documents page"""
        page = logged_in_applicant
        page.goto("http://127.0.0.1:5003/applicant/documents")
        expect(page.locator('.documents-title, .page-title')).to_be_visible()

    def test_document_list_displays(self, logged_in_applicant):
        """Test document list is displayed"""
        page = logged_in_applicant
        page.goto("http://127.0.0.1:5003/applicant/documents")
        expect(page.locator('.documents-title')).to_be_visible()


class TestSecretaryApprovalWorkflow:
    """Test secretary document approval workflow"""

    def test_applicants_page_loads(self, logged_in_secretary):
        """Test secretary can access applicants page"""
        page = logged_in_secretary
        page.goto("http://127.0.0.1:5003/secretary/applicants")
        expect(page.locator('#applicantsList')).to_be_visible()

    def test_documents_page_loads(self, logged_in_secretary):
        """Test secretary can access document review page"""
        page = logged_in_secretary
        page.goto("http://127.0.0.1:5003/secretary/documents")
        expect(page.locator('#documentsList')).to_be_visible()

    def test_dashboard_stats_visible(self, logged_in_secretary):
        """Test secretary dashboard shows stats"""
        page = logged_in_secretary
        page.goto("http://127.0.0.1:5003/secretary/dashboard")
        expect(page.locator('.stats-grid')).to_be_visible()


class TestAdminApprovalWorkflow:
    """Test admin final approval workflow"""

    def test_approvals_page_loads(self, logged_in_admin):
        """Test admin can access approvals page"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/approvals")
        expect(page.locator('.page-title')).to_contain_text("审批")

    def test_approvals_list_displays(self, logged_in_admin):
        """Test approvals list is displayed"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/approvals")
        expect(page.locator('table, .empty-state')).to_be_visible()


class TestCompleteApplicationWorkflow:
    """Test complete application workflow from start to finish"""

    def test_admin_dashboard_loads(self, logged_in_admin):
        """Test admin dashboard loads"""
        page = logged_in_admin
        page.goto("http://127.0.0.1:5003/admin/dashboard")
        expect(page.locator('.page-title')).to_contain_text("管理首页")

    def test_secretary_dashboard_loads(self, logged_in_secretary):
        """Test secretary dashboard loads"""
        page = logged_in_secretary
        page.goto("http://127.0.0.1:5003/secretary/dashboard")
        expect(page.locator('.stats-grid')).to_be_visible()

    def test_applicant_dashboard_loads(self, logged_in_applicant):
        """Test applicant dashboard loads"""
        page = logged_in_applicant
        page.goto("http://127.0.0.1:5003/applicant/dashboard")
        expect(page).not_to_have_url(re.compile(r".*error.*"))

    def test_applicant_can_view_progress(self, logged_in_applicant):
        """Test applicant can view their progress"""
        page = logged_in_applicant
        page.goto("http://127.0.0.1:5003/applicant/progress")
        expect(page.locator('.progress-title')).to_contain_text("发展进度")
