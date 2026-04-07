# -*- coding: utf-8 -*-
"""
Integration tests for applicant functionality
"""
import re
import pytest
from playwright.sync_api import Page, expect


class TestApplicantDashboard:
    """Test applicant dashboard"""

    def test_dashboard_loads(self, logged_in_applicant):
        """Test that applicant dashboard loads"""
        page = logged_in_applicant
        page.goto("http://127.0.0.1:5003/applicant/dashboard")

        # Check page loaded without errors
        expect(page).not_to_have_url(re.compile(r".*error.*"))


class TestApplicantProgress:
    """Test applicant progress view"""

    def test_progress_page_loads(self, logged_in_applicant):
        """Test that progress page loads"""
        page = logged_in_applicant
        page.goto("http://127.0.0.1:5003/applicant/progress")

        # Check page loaded without errors
        expect(page).not_to_have_url(re.compile(r".*error.*"))


class TestApplicantDocuments:
    """Test applicant documents"""

    def test_documents_page_loads(self, logged_in_applicant):
        """Test that documents page loads"""
        page = logged_in_applicant
        page.goto("http://127.0.0.1:5003/applicant/documents")

        # Check page loaded without errors
        expect(page).not_to_have_url(re.compile(r".*error.*"))
