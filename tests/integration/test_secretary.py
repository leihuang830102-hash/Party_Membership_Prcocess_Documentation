# -*- coding: utf-8 -*-
"""
Integration tests for secretary functionality
"""
import re
import pytest
from playwright.sync_api import Page, expect


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
        page.goto("http://127.0.0.1:5003/secretary/documents")

        # Check page loaded without errors
        expect(page).not_to_have_url(re.compile(r".*error.*"))
