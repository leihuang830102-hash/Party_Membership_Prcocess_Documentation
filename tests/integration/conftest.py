import pytest
from playwright.sync_api import Page, BrowserContext
import subprocess
import time
import requests
import os
import sys
import threading

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BASE_URL = "http://127.0.0.1:5003"

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context"""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "locale": "zh-CN",
    }

@pytest.fixture(scope="session")
def server():
    """Start Flask server for testing"""
    # Check if server already running
    try:
        response = requests.get(f"{BASE_URL}/", timeout=2)
        if response.status_code == 200:
            yield BASE_URL
            return
    except:
        pass

    # Start server
    from run import app
    app.config['TESTING'] = True

    def run_server():
        app.run(debug=False, port=5003, host='0.0.0.0', use_reloader=False)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    # Wait for server to start
    for _ in range(30):
        try:
            response = requests.get(f"{BASE_URL}/", timeout=1)
            if response.status_code == 200:
                break
        except:
            time.sleep(0.5)

    yield BASE_URL


@pytest.fixture
def page(page: Page, server):
    """Page fixture with base URL"""
    page.set_default_timeout(10000)
    return page


@pytest.fixture
def logged_in_admin(page: Page):
    """Login as admin user"""
    page.goto(f"{BASE_URL}/auth/login")
    page.fill('input[name="username"]', 'admin')
    page.fill('input[name="password"]', '123456')
    page.click('button[type="submit"]')
    # Wait for redirect after login
    try:
        page.wait_for_url(lambda url: 'login' not in url, timeout=5000)
    except:
        pass
    return page


@pytest.fixture
def logged_in_secretary(page: Page):
    """Login as secretary user"""
    page.goto(f"{BASE_URL}/auth/login")
    page.fill('input[name="username"]', 'secretary')
    page.fill('input[name="password"]', '123456')
    page.click('button[type="submit"]')
    try:
        page.wait_for_url(lambda url: 'login' not in url, timeout=5000)
    except:
        pass
    return page


@pytest.fixture
def logged_in_applicant(page: Page):
    """Login as applicant user"""
    page.goto(f"{BASE_URL}/auth/login")
    page.fill('input[name="username"]', 'applicant')
    page.fill('input[name="password"]', '123456')
    page.click('button[type="submit"]')
    try:
        page.wait_for_url(lambda url: 'login' not in url, timeout=5000)
    except:
        pass
    return page
