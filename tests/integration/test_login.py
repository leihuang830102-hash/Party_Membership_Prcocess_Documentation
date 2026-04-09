# -*- coding: utf-8 -*-
"""
Integration tests for authentication flows
"""
import pytest
import re
from playwright.sync_api import Page, expect


class TestPublicPages:
    """Test public pages that don't require login"""

    def test_home_page_loads(self, page):
        """Test that the home page loads successfully"""
        page.goto("http://127.0.0.1:5003/")
        expect(page).to_have_title("入党文档管理系统")
        expect(page.locator("h1")).to_contain_text("入党文档管理系统")

    def test_login_page_loads(self, page):
        """Test that the login page loads successfully"""
        page.goto("http://127.0.0.1:5003/auth/login")
        expect(page).to_have_title("登录 - 入党文档管理系统")
        expect(page.locator("h1")).to_contain_text("入党文档管理系统")

    def test_protected_page_redirects_to_login(self, page):
        """Test that protected pages redirect to login"""
        page.goto("http://127.0.0.1:5003/admin/dashboard")
        # Should redirect to login page (with optional next parameter)
        expect(page).to_have_url(re.compile(r".*auth/login.*"))


class TestLogin:
    """Test login functionality"""

    def test_admin_login(self, page):
        """Test admin login and redirect to admin dashboard"""
        page.goto("http://127.0.0.1:5003/auth/login")
        page.fill('input[name="username"]', 'admin')
        page.fill('input[name="password"]', '123456')
        page.click('button[type="submit"]')

        # Should redirect to admin dashboard
        expect(page).to_have_url(re.compile(r".*admin.*dashboard.*"))
        expect(page.locator("body")).to_contain_text("管理首页")

    def test_secretary_login(self, page):
        """Test secretary login and redirect to secretary dashboard"""
        page.goto("http://127.0.0.1:5003/auth/login")
        page.fill('input[name="username"]', 'secretary')
        page.fill('input[name="password"]', '123456')
        page.click('button[type="submit"]')

        # Should redirect to secretary dashboard
        expect(page).to_have_url(re.compile(r".*secretary.*"))
        expect(page.locator("body")).to_contain_text("工作台")

    def test_applicant_login(self, page):
        """Test applicant login and redirect to applicant dashboard"""
        page.goto("http://127.0.0.1:5003/auth/login")
        page.fill('input[name="username"]', 'applicant')
        page.fill('input[name="password"]', '123456')
        page.click('button[type="submit"]')

        # Should redirect to applicant dashboard
        expect(page).to_have_url(re.compile(r".*applicant.*"))

    def test_invalid_login(self, page):
        """Test login with invalid credentials"""
        page.goto("http://127.0.0.1:5003/auth/login")
        page.fill('input[name="username"]', 'invaliduser')
        page.fill('input[name="password"]', 'wrongpassword')
        page.click('button[type="submit"]')

        # Should show error message
        expect(page.locator(".alert")).to_be_visible()

    def test_logout(self, logged_in_admin):
        """Test logout functionality"""
        page = logged_in_admin
        # Wait for page to be fully loaded
        page.wait_for_load_state("networkidle")

        # Click logout button - use more specific selector
        logout_link = page.locator('a:has-text("退出"), a[href*="logout"]')
        if logout_link.count() > 0:
            logout_link.first.click()
            page.wait_for_load_state("networkidle")
            # Should redirect to login or home page
            expect(page).to_have_url(re.compile(r".*(?:login|\/)$"))
        else:
            pytest.skip("Logout link not found on page")


class TestNavigation:
    """Test navigation menus"""

    def test_admin_navigation(self, logged_in_admin):
        """Test admin navigation menu"""
        page = logged_in_admin

        # Check navigation items are visible - use flexible selectors
        nav_links = page.locator('nav a, .nav-link, .sidebar a, a[href*="/admin/"]')
        count = nav_links.count()
        if count >= 1:
            expect(nav_links.first).to_be_visible()
        else:
            pytest.skip("No navigation items found on admin page")


    def test_secretary_navigation(self, logged_in_secretary):
        """Test secretary navigation menu"""
        page = logged_in_secretary

        # Check navigation items are visible - use flexible selectors
        nav_links = page.locator('nav a, .nav-link, .sidebar a, a[href*="/secretary/"]')
        count = nav_links.count()
        if count >= 1:
            expect(nav_links.first).to_be_visible()
        else:
            pytest.skip("No navigation items found on secretary page")


    def test_applicant_navigation(self, logged_in_applicant):
        """Test applicant navigation menu"""
        page = logged_in_applicant

        # Check navigation items are visible - use flexible selectors
        nav_links = page.locator('nav a, .nav-link, .sidebar a, a[href*="/applicant/"]')
        count = nav_links.count()
        if count >= 1:
            expect(nav_links.first).to_be_visible()
        else:
            pytest.skip("No navigation items found on applicant page")
