"""E2E tests for document online preview feature."""
import pytest

BASE_URL = "http://127.0.0.1:5003"


class TestPreviewEndpoints:
    """Tests for document preview API endpoints"""

    def test_secretary_preview_pdf_returns_inline(self, logged_in_secretary, server):
        """Secretary preview endpoint returns PDF inline (not attachment)"""
        page = logged_in_secretary
        # Find a PDF document via API
        doc = page.evaluate("""
            async () => {
                const r = await fetch('/secretary/api/documents');
                const data = await r.json();
                if (data.documents) {
                    const pdf = data.documents.find(d => d.filename && d.filename.toLowerCase().endsWith('.pdf'));
                    return pdf || null;
                }
                return null;
            }
        """)
        if not doc:
            pytest.skip("No PDF documents in system")

        response = page.request.get(f"{BASE_URL}/secretary/api/documents/{doc['id']}/preview")
        assert response.status == 200
        cd = response.headers.get('content-disposition', '')
        assert 'attachment' not in cd.lower()
        ct = response.headers.get('content-type', '')
        assert 'pdf' in ct.lower()

    def test_admin_preview_pdf_returns_inline(self, logged_in_admin, server):
        """Admin preview endpoint returns PDF inline"""
        page = logged_in_admin
        # Find a PDF document via secretary API (admin role also accepted)
        doc = page.evaluate("""
            async () => {
                let r = await fetch('/secretary/api/documents');
                if (!r.ok) return null;
                let data = await r.json();
                if (data.documents) {
                    const pdf = data.documents.find(d => d.filename && d.filename.toLowerCase().endsWith('.pdf'));
                    if (pdf) return pdf;
                }
                return null;
            }
        """)
        if not doc:
            pytest.skip("No PDF documents in system")

        response = page.request.get(f"{BASE_URL}/admin/api/documents/{doc['id']}/preview")
        assert response.status == 200
        cd = response.headers.get('content-disposition', '')
        assert 'attachment' not in cd.lower()

    def test_preview_nonexistent_doc_returns_404(self, logged_in_admin, server):
        """Preview returns 404 for non-existent document"""
        response = logged_in_admin.request.get(f"{BASE_URL}/admin/api/documents/99999/preview")
        assert response.status == 404

    def test_unauthenticated_preview_blocked(self, page, server):
        """Unauthenticated users are redirected to login"""
        # page.request follows redirects, so 302 -> login page -> 200
        # Just verify the endpoint exists and redirects properly
        response = page.request.get(f"{BASE_URL}/admin/api/documents/1/preview")
        # If it returns 200, check we're on login page (means redirect happened)
        if response.status == 200:
            url = response.url
            assert 'login' in url, "Should be redirected to login page"
        else:
            assert response.status in [302, 401, 403]

    def test_applicant_cannot_access_secretary_preview(self, logged_in_applicant, server):
        """Applicant role is blocked from secretary preview endpoint"""
        response = logged_in_applicant.request.get(f"{BASE_URL}/secretary/api/documents/1/preview")
        assert response.status == 403

    def test_applicant_cannot_access_admin_preview(self, logged_in_applicant, server):
        """Applicant role is blocked from admin preview endpoint"""
        response = logged_in_applicant.request.get(f"{BASE_URL}/admin/api/documents/1/preview")
        assert response.status == 403


class TestPreviewButtons:
    """Tests for preview button visibility in UI"""

    def test_secretary_documents_page_has_preview_css(self, logged_in_secretary, server):
        """Secretary documents page loads with preview modal available"""
        page = logged_in_secretary
        page.goto(f"{BASE_URL}/secretary/documents")
        page.wait_for_load_state("networkidle")
        # The global preview modal should be in the DOM (from base.html)
        assert page.locator('#docPreviewModal').count() == 1

    def test_admin_approvals_page_has_preview_modal(self, logged_in_admin, server):
        """Admin approvals page loads with preview modal available"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/approvals")
        page.wait_for_load_state("networkidle")
        assert page.locator('#docPreviewModal').count() == 1

    def test_preview_modal_closed_by_default(self, logged_in_secretary, server):
        """Preview modal is hidden by default"""
        page = logged_in_secretary
        page.goto(f"{BASE_URL}/secretary/documents")
        page.wait_for_load_state("networkidle")
        modal = page.locator('#docPreviewModal')
        assert modal.is_hidden()

    def test_applicant_no_preview_buttons(self, logged_in_applicant, server):
        """Applicant pages do NOT show preview buttons"""
        page = logged_in_applicant
        page.goto(f"{BASE_URL}/applicant/documents")
        page.wait_for_load_state("networkidle")
        # Preview modal exists in base.html but applicant should have no preview onclick buttons
        preview_links = page.locator('a[onclick*="openPreview"]')
        assert preview_links.count() == 0
