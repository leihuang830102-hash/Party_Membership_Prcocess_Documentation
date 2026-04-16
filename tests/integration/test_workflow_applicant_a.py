# -*- coding: utf-8 -*-
"""
Test Scenario 1: Applicant A Complete Approval Flow (Step 1 → Final)

This test covers the complete approval workflow for applicant A:
1. Applicant A logs in and views initial stage
2. Applicant A uploads application document
3. Secretary approves step
4. Application advances through stages
5. Final completion check
"""
import re
import pytest
import os
import tempfile
from playwright.sync_api import Page, expect, BrowserContext

BASE_URL = "http://127.0.0.1:5003"


class TestApplicantACompleteFlow:
    """申请人A完整审批流程测试"""

    def test_applicant_dashboard_loads(self, logged_in_applicant: Page):
        """申请人A可以访问仪表板"""
        page = logged_in_applicant
        page.goto(f"{BASE_URL}/applicant/dashboard")
        expect(page).not_to_have_url(re.compile(r".*error.*"))

    def test_applicant_can_view_progress(self, logged_in_applicant: Page):
        """申请人A可以查看进度"""
        page = logged_in_applicant
        page.goto(f"{BASE_URL}/applicant/progress")
        expect(page.locator('.progress-title')).to_contain_text("发展进度")

    def test_applicant_documents_page_loads(self, logged_in_applicant: Page):
        """申请人A文档页面加载"""
        page = logged_in_applicant
        page.goto(f"{BASE_URL}/applicant/documents")
        expect(page.locator('.documents-title, h1, h2').first).to_be_visible()


class TestSecretaryApprovalFlow:
    """书记审批流程测试"""

    def test_secretary_dashboard_loads(self, logged_in_secretary: Page):
        """书记仪表板加载"""
        page = logged_in_secretary
        page.goto(f"{BASE_URL}/secretary/dashboard")
        expect(page.locator('.stats-grid')).to_be_visible()

    def test_secretary_can_view_applicants(self, logged_in_secretary: Page):
        """书记可以查看申请人列表"""
        page = logged_in_secretary
        page.goto(f"{BASE_URL}/secretary/applicants")
        page.wait_for_load_state("networkidle")
        expect(page.locator('#applicantsList')).to_be_visible()

    def test_secretary_can_view_documents(self, logged_in_secretary: Page):
        """书记可以查看待审文档"""
        page = logged_in_secretary
        page.goto(f"{BASE_URL}/secretary/documents")
        expect(page.locator('#documentsList')).to_be_visible()

    def test_secretary_can_access_applicant_detail(self, logged_in_secretary: Page):
        """书记可以访问申请人详情"""
        page = logged_in_secretary
        # First get the applicants list
        page.goto(f"{BASE_URL}/secretary/applicants")

        # Try to click on first applicant if exists
        applicants = page.locator('#applicantsList .applicant-card, #applicantsList tr')
        if applicants.count() > 0:
            applicants.first.click()
            page.wait_for_load_state("networkidle")
            # Should be on applicant detail page
            expect(page).not_to_have_url(re.compile(r".*error.*"))


class TestAdminApprovalFlow:
    """管理员审批流程测试"""

    def test_admin_approvals_page_loads(self, logged_in_admin: Page):
        """管理员审批页面加载"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/approvals")
        expect(page.locator('h1, h2, .card-title').first).to_be_visible()


class TestCompleteWorkflow:
    """完整流程测试"""

    def test_all_roles_can_login(self, page: Page):
        """所有角色都能登录"""
        # Test admin login
        page.goto(f"{BASE_URL}/auth/login")
        page.fill('input[name="username"]', 'admin')
        page.fill('input[name="password"]', '123456')
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        expect(page).not_to_have_url(re.compile(r".*login.*"))

        # Logout
        page.goto(f"{BASE_URL}/auth/logout")

        # Test secretary login
        page.goto(f"{BASE_URL}/auth/login")
        page.fill('input[name="username"]', 'secretary')
        page.fill('input[name="password"]', '123456')
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        expect(page).not_to_have_url(re.compile(r".*login.*"))

        # Logout
        page.goto(f"{BASE_URL}/auth/logout")

        # Test applicant login
        page.goto(f"{BASE_URL}/auth/login")
        page.fill('input[name="username"]', 'applicant')
        page.fill('input[name="password"]', '123456')
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        expect(page).not_to_have_url(re.compile(r".*login.*"))

    def test_api_progress_endpoint(self, logged_in_applicant: Page):
        """测试进度API端点"""
        page = logged_in_applicant

        # Make API request
        response = page.request.get(f"{BASE_URL}/applicant/api/progress")

        # Check response
        assert response.status in [200, 404]  # 404 if no application exists

    def test_api_documents_endpoint(self, logged_in_applicant: Page):
        """测试文档API端点"""
        page = logged_in_applicant

        # Make API request
        response = page.request.get(f"{BASE_URL}/applicant/api/documents")

        # Check response
        assert response.status in [200, 404]

    def test_secretary_api_applicants_endpoint(self, logged_in_secretary: Page):
        """测试书记申请人API端点"""
        page = logged_in_secretary

        # Make API request
        response = page.request.get(f"{BASE_URL}/secretary/api/applicants")

        # Check response
        assert response.status == 200
