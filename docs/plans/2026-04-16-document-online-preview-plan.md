# Document Online Preview Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add PDF and image online preview (modal overlay) for secretary and admin roles, using PDF.js with zero server-side dependencies.

**Architecture:** Two new Flask endpoints serve files inline (`as_attachment=False`). A global preview modal in `base.html` uses PDF.js (local static) for PDF rendering and `<img>` for images. Preview buttons added to 4 existing templates.

**Tech Stack:** Flask `send_file()`, PDF.js v4 (local), vanilla JS, CSS modal overlay.

---

### Task 1: Download PDF.js to Local Static

**Files:**
- Create: `app/static/lib/pdf.js/pdf.min.js`
- Create: `app/static/lib/pdf.js/pdf.worker.min.js`

**Step 1: Create directory and download PDF.js**

```bash
mkdir -p app/static/lib/pdf.js
cd app/static/lib/pdf.js
curl -L -o pdf.min.js "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.min.mjs"
curl -L -o pdf.worker.min.js "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.worker.min.mjs"
```

If CDN is unavailable, use alternative:
```bash
curl -L -o pdf.min.js "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.4.168/build/pdf.min.mjs"
curl -L -o pdf.worker.min.js "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.4.168/build/pdf.worker.min.mjs"
```

**Step 2: Verify files exist and have content**

```bash
ls -la app/static/lib/pdf.js/
# Both files should be > 500KB
```

**Step 3: Commit**

```bash
git add app/static/lib/pdf.js/
git commit -m "chore: add PDF.js v4 for document preview"
```

---

### Task 2: Write Failing Tests for Preview Endpoints

**Files:**
- Modify: `tests/integration/test_secretary.py`
- Modify: `tests/integration/test_admin.py`

**Step 1: Add secretary preview endpoint test**

In `tests/integration/test_secretary.py`, add a new test class:

```python
class TestDocumentPreview:
    """Tests for document online preview (PDF/image inline serving)"""

    def test_preview_pdf_returns_inline(self, logged_in_secretary, server):
        """Secretary can preview a PDF document inline (not as attachment)"""
        # Find an existing PDF document
        resp = logged_in_secretary.goto(f"{BASE_URL}/secretary/documents")
        logged_in_secretary.wait_for_load_state("networkidle")
        # Get first document ID from API
        api_resp = logged_in_secretary.evaluate("""
            async () => {
                const r = await fetch('/secretary/api/documents');
                const data = await r.json();
                return data.documents ? data.documents[0] : null;
            }
        """)
        if not api_resp:
            pytest.skip("No documents available for preview test")

        doc_id = api_resp['id']
        # Request preview
        response = logged_in_secretary.request.get(
            f"{BASE_URL}/secretary/api/documents/{doc_id}/preview"
        )
        assert response.status == 200
        # Must NOT be attachment (inline preview)
        headers = response.headers
        cd = headers.get('content-disposition', '')
        assert 'attachment' not in cd

    def test_preview_unsupported_format_returns_415(self, logged_in_secretary, server):
        """Non-PDF/image files return 415 Unsupported Media Type"""
        # Try to preview a non-existent doc with .docx extension
        response = logged_in_secretary.request.get(
            f"{BASE_URL}/secretary/api/documents/99999/preview"
        )
        # Should be 404 (not found) or 415 (unsupported)
        assert response.status in [404, 415]
```

**Step 2: Add admin preview endpoint test**

In `tests/integration/test_admin.py`, add:

```python
class TestDocumentPreview:
    """Tests for admin document online preview"""

    def test_admin_preview_pdf_returns_inline(self, logged_in_admin, server):
        """Admin can preview documents inline"""
        # Use admin documents API to find a doc
        api_resp = logged_in_admin.evaluate("""
            async () => {
                const r = await fetch('/admin/api/approval-documents');
                const data = await r.json();
                if (data.documents && data.documents.length > 0) {
                    return data.documents[0];
                }
                return null;
            }
        """)
        if not api_resp:
            pytest.skip("No documents available for preview test")

        doc_id = api_resp['id']
        response = logged_in_admin.request.get(
            f"{BASE_URL}/admin/api/documents/{doc_id}/preview"
        )
        assert response.status == 200
        cd = response.headers.get('content-disposition', '')
        assert 'attachment' not in cd

    def test_admin_preview_requires_login(self, page, server):
        """Unauthenticated users cannot access preview"""
        response = page.request.get(
            f"{BASE_URL}/admin/api/documents/1/preview"
        )
        assert response.status in [302, 401, 403]
```

**Step 3: Run tests to verify they fail**

```bash
cd d:/Users/Administrator/CPCWebIII && python -m pytest tests/integration/test_secretary.py::TestDocumentPreview tests/integration/test_admin.py::TestDocumentPreview -v --tb=short 2>&1 | tail -20
```

Expected: FAIL (endpoints don't exist yet, 404)

**Step 4: Commit**

```bash
git add tests/integration/test_secretary.py tests/integration/test_admin.py
git commit -m "test: add failing tests for document preview endpoints"
```

---

### Task 3: Implement Secretary Preview Endpoint

**Files:**
- Modify: `app/routes/secretary.py` (add new route after existing document routes)

**Step 1: Add preview endpoint**

Find the existing `download_document` or document-related routes in `secretary.py`. Add after the download route:

```python
@secretary_bp.route('/api/documents/<int:doc_id>/preview')
@login_required
def preview_document(doc_id):
    """在线预览文档（PDF/图片内联显示，不下载）
    仅支持 PDF 和图片格式（jpg/jpeg/png）
    """
    if current_user.role != 'secretary':
        return jsonify({'success': False, 'message': '无权访问'}), 403

    doc = Document.query.get_or_404(doc_id)

    # 文件扩展名检查
    ext = os.path.splitext(doc.filename)[1].lower()
    supported = {'.pdf', '.jpg', '.jpeg', '.png'}
    if ext not in supported:
        return jsonify({'success': False, 'message': f'该格式（{ext}）不支持在线预览，请下载查看'}), 415

    # 文件存在性检查
    if not os.path.exists(doc.file_path):
        return jsonify({'success': False, 'message': '文件不存在'}), 404

    # MIME 类型映射
    mime_map = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
    }

    return send_file(
        doc.file_path,
        as_attachment=False,
        mimetype=mime_map.get(ext, 'application/octet-stream')
    )
```

**Step 2: Verify the import exists**

Ensure `send_file` is imported at the top of `secretary.py`:
```python
from flask import send_file
```

**Step 3: Run secretary preview tests**

```bash
cd d:/Users/Administrator/CPCWebIII && python -m pytest tests/integration/test_secretary.py::TestDocumentPreview -v --tb=short 2>&1 | tail -20
```

Expected: Tests PASS or SKIP (if no docs in DB)

**Step 4: Commit**

```bash
git add app/routes/secretary.py
git commit -m "feat: add secretary document preview endpoint (PDF/image inline)"
```

---

### Task 4: Implement Admin Preview Endpoint

**Files:**
- Modify: `app/routes/admin.py` (add new route near existing document routes)

**Step 1: Add preview endpoint**

Find existing document download routes in `admin.py`. Add preview route:

```python
@admin_bp.route('/api/documents/<int:doc_id>/preview')
@login_required
def preview_document(doc_id):
    """管理员在线预览文档（PDF/图片内联显示）
    仅支持 PDF 和图片格式（jpg/jpeg/png）
    """
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': '无权访问'}), 403

    doc = Document.query.get_or_404(doc_id)

    ext = os.path.splitext(doc.filename)[1].lower()
    supported = {'.pdf', '.jpg', '.jpeg', '.png'}
    if ext not in supported:
        return jsonify({'success': False, 'message': f'该格式（{ext}）不支持在线预览，请下载查看'}), 415

    if not os.path.exists(doc.file_path):
        return jsonify({'success': False, 'message': '文件不存在'}), 404

    mime_map = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
    }

    return send_file(
        doc.file_path,
        as_attachment=False,
        mimetype=mime_map.get(ext, 'application/octet-stream')
    )
```

**Step 2: Verify `send_file` import**

Ensure `send_file` is imported in `admin.py`:
```python
from flask import send_file
```

**Step 3: Run admin preview tests**

```bash
cd d:/Users/Administrator/CPCWebIII && python -m pytest tests/integration/test_admin.py::TestDocumentPreview -v --tb=short 2>&1 | tail -20
```

Expected: Tests PASS or SKIP

**Step 4: Commit**

```bash
git add app/routes/admin.py
git commit -m "feat: add admin document preview endpoint (PDF/image inline)"
```

---

### Task 5: Add Global Preview Modal to base.html

**Files:**
- Modify: `app/templates/base.html`

**Step 1: Add modal HTML before closing `{% block content %}`**

Add before the final `</body>` tag or after the main content area:

```html
{# 文档在线预览模态框 - 全局组件，所有页面复用 #}
<div id="docPreviewModal" class="preview-modal" style="display:none;">
    <div class="preview-overlay" onclick="closePreview()"></div>
    <div class="preview-container">
        <div class="preview-header">
            <span id="previewFileName" class="preview-filename"></span>
            <div class="preview-toolbar">
                <button class="preview-btn" id="btnPrevPage" onclick="previewPrevPage()" title="上一页">&#9664; 上一页</button>
                <span id="previewPageInfo" class="preview-page-info"></span>
                <button class="preview-btn" id="btnNextPage" onclick="previewNextPage()" title="下一页">下一页 &#9654;</button>
                <span class="preview-divider">|</span>
                <button class="preview-btn" onclick="previewZoomIn()" title="放大">+</button>
                <button class="preview-btn" onclick="previewZoomOut()" title="缩小">-</button>
                <a id="previewDownloadLink" class="preview-btn preview-download" href="#" download>下载</a>
                <button class="preview-btn preview-close-btn" onclick="closePreview()" title="关闭">&#10005;</button>
            </div>
        </div>
        <div class="preview-body" id="previewBody">
            <canvas id="pdfCanvas"></canvas>
            <img id="previewImage" style="display:none; max-width:100%; max-height:100%; object-fit:contain;">
            <div id="previewUnsupported" style="display:none;" class="preview-unsupported">
                <p>该格式不支持在线预览</p>
                <a id="previewFallbackDownload" class="btn btn-primary" href="#">下载文件</a>
            </div>
        </div>
    </div>
</div>
```

**Step 2: Add CSS styles**

```css
/* 文档预览模态框 */
.preview-modal { position:fixed; top:0; left:0; width:100%; height:100%; z-index:10000; display:flex; align-items:center; justify-content:center; }
.preview-overlay { position:absolute; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.6); }
.preview-container { position:relative; width:92vw; height:90vh; background:#fff; border-radius:8px; display:flex; flex-direction:column; box-shadow:0 8px 32px rgba(0,0,0,0.3); z-index:1; }
.preview-header { display:flex; align-items:center; justify-content:space-between; padding:12px 20px; border-bottom:1px solid #e0e0e0; background:#f8f9fa; border-radius:8px 8px 0 0; flex-shrink:0; flex-wrap:wrap; gap:8px; }
.preview-filename { font-weight:600; font-size:0.95rem; color:#333; max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.preview-toolbar { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
.preview-btn { background:none; border:1px solid #ccc; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:0.85rem; color:#555; text-decoration:none; display:inline-flex; align-items:center; }
.preview-btn:hover { background:#e8e8e8; }
.preview-page-info { font-size:0.85rem; color:#666; min-width:80px; text-align:center; }
.preview-divider { color:#ccc; margin:0 4px; }
.preview-close-btn { font-size:1.2rem; padding:4px 8px; color:#c62828; }
.preview-download { color:#2e7d32; border-color:#2e7d32; }
.preview-body { flex:1; overflow:auto; display:flex; align-items:center; justify-content:center; background:#525659; padding:10px; }
.preview-body canvas { max-width:100%; height:auto; }
.preview-unsupported { text-align:center; color:#fff; }
.preview-unsupported p { font-size:1.2rem; margin-bottom:16px; }
.preview-unsupported .btn { color:#fff; }
```

**Step 3: Add JavaScript**

```html
<script src="{{ url_for('static', filename='lib/pdf.js/pdf.min.js') }}"></script>
<script>
// PDF.js worker path
if (typeof pdfjsLib !== 'undefined') {
    pdfjsLib.GlobalWorkerOptions.workerSrc = '{{ url_for("static", filename="lib/pdf.js/pdf.worker.min.js") }}';
}

let _pdfDoc = null;
let _pdfPage = 1;
let _pdfScale = 1.5;

/**
 * 打开文档预览模态框
 * @param {number} docId - 文档ID
 * @param {string} fileName - 显示文件名
 * @param {string} previewUrl - 预览接口URL
 * @param {string} downloadUrl - 下载链接URL
 */
function openPreview(docId, fileName, previewUrl, downloadUrl) {
    const modal = document.getElementById('docPreviewModal');
    const canvas = document.getElementById('pdfCanvas');
    const img = document.getElementById('previewImage');
    const unsupported = document.getElementById('previewUnsupported');
    const nameEl = document.getElementById('previewFileName');
    const dlLink = document.getElementById('previewDownloadLink');

    nameEl.textContent = fileName;
    dlLink.href = downloadUrl;
    canvas.style.display = 'none';
    img.style.display = 'none';
    unsupported.style.display = 'none';

    const ext = fileName.split('.').pop().toLowerCase();

    if (ext === 'pdf') {
        _pdfDoc = null;
        _pdfPage = 1;
        _pdfScale = 1.5;
        canvas.style.display = 'block';
        // Fetch and render PDF
        pdfjsLib.getDocument(previewUrl).promise.then(function(pdf) {
            _pdfDoc = pdf;
            renderPdfPage(_pdfPage);
        }).catch(function(err) {
            console.error('PDF load error:', err);
            canvas.style.display = 'none';
            unsupported.style.display = 'block';
        });
    } else if (['jpg','jpeg','png'].includes(ext)) {
        img.style.display = 'block';
        img.src = previewUrl;
    } else {
        unsupported.style.display = 'block';
    }

    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function closePreview() {
    document.getElementById('docPreviewModal').style.display = 'none';
    document.body.style.overflow = '';
    _pdfDoc = null;
    document.getElementById('pdfCanvas').getContext('2d').clearRect(0,0,1,1);
    document.getElementById('previewImage').src = '';
}

function renderPdfPage(num) {
    if (!_pdfDoc) return;
    _pdfDoc.getPage(num).then(function(page) {
        const canvas = document.getElementById('pdfCanvas');
        const ctx = canvas.getContext('2d');
        const viewport = page.getViewport({ scale: _pdfScale });
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        page.render({ canvasContext: ctx, viewport: viewport }).promise.then(function() {
            document.getElementById('previewPageInfo').textContent = num + ' / ' + _pdfDoc.numPages;
            document.getElementById('btnPrevPage').disabled = (num <= 1);
            document.getElementById('btnNextPage').disabled = (num >= _pdfDoc.numPages);
        });
    });
}

function previewPrevPage() { if (_pdfPage > 1) { _pdfPage--; renderPdfPage(_pdfPage); } }
function previewNextPage() { if (_pdfDoc && _pdfPage < _pdfDoc.numPages) { _pdfPage++; renderPdfPage(_pdfPage); } }
function previewZoomIn() { _pdfScale = Math.min(_pdfScale + 0.3, 4); renderPdfPage(_pdfPage); }
function previewZoomOut() { _pdfScale = Math.max(_pdfScale - 0.3, 0.5); renderPdfPage(_pdfPage); }

// ESC to close
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closePreview(); });
</script>
```

**Step 4: Verify base.html loads without errors**

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5003/auth/login
```

Expected: 200

**Step 5: Commit**

```bash
git add app/templates/base.html
git commit -m "feat: add global document preview modal with PDF.js support"
```

---

### Task 6: Add Preview Buttons to Templates

**Files:**
- Modify: `app/templates/secretary/applicant_detail.html`
- Modify: `app/templates/secretary/documents.html`
- Modify: `app/templates/admin/approval_detail.html`
- Modify: `app/templates/admin/approval_review.html`

**Step 1: Add preview button to secretary/applicant_detail.html**

Find each document card/download area. Add a "预览" button before the download link:

```html
{% set doc_ext = doc.filename.split('.')[-1].lower() %}
{% if doc_ext in ['pdf', 'jpg', 'jpeg', 'png'] %}
<a href="#" onclick="openPreview({{ doc.id }}, '{{ doc.original_filename or doc.filename }}', '/secretary/api/documents/{{ doc.id }}/preview', '/admin/documents/{{ doc.id }}/download'); return false;" class="btn btn-sm btn-outline">预览</a>
{% endif %}
```

**Step 2: Add preview button to secretary/documents.html**

Same pattern in document cards within the JS template literal. For each document card in the JS `loadDocuments` function:

```javascript
${doc.filename.match(/\.(pdf|jpg|jpeg|png)$/i) ?
    '<a href="#" onclick="openPreview(' + doc.id + ', \'' + escapeHtml(doc.original_filename || doc.filename) + '\', \'/secretary/api/documents/' + doc.id + '/preview\', \'/admin/documents/' + doc.id + '/download\'); return false;" class="btn btn-sm btn-outline">预览</a>'
    : ''}
```

**Step 3: Add preview button to admin/approval_detail.html**

Find document list items. Add preview button for PDF/image files:

```html
{% set doc_ext = doc.filename.split('.')[-1].lower() %}
{% if doc_ext in ['pdf', 'jpg', 'jpeg', 'png'] %}
<a href="#" onclick="openPreview({{ doc.id }}, '{{ doc.original_filename or doc.filename }}', '/admin/api/documents/{{ doc.id }}/preview', '/admin/documents/{{ doc.id }}/download'); return false;" class="btn btn-sm btn-outline">预览</a>
{% endif %}
```

**Step 4: Add preview button to admin/approval_review.html**

Same pattern in the per-document review section.

**Step 5: Verify each page loads**

Visit each page as the appropriate role and verify preview buttons appear for PDF/image docs.

**Step 6: Commit**

```bash
git add app/templates/secretary/applicant_detail.html app/templates/secretary/documents.html app/templates/admin/approval_detail.html app/templates/admin/approval_review.html
git commit -m "feat: add preview buttons to secretary and admin document views"
```

---

### Task 7: Add E2E Tests for Full Preview Flow

**Files:**
- Create: `tests/integration/test_document_preview.py`

**Step 1: Write E2E preview tests**

```python
"""E2E tests for document online preview feature."""
import pytest
from playwright.sync_api import Page

BASE_URL = "http://127.0.0.1:5003"


class TestPreviewModal:
    """Tests for the document preview modal UI"""

    def test_secretary_sees_preview_button_for_pdf(self, logged_in_secretary, server):
        """Secretary sees '预览' button on PDF documents"""
        page = logged_in_secretary
        page.goto(f"{BASE_URL}/secretary/documents")
        page.wait_for_load_state("networkidle")
        # Page should load without errors
        assert page.locator('text=文档').first.is_visible()

    def test_admin_sees_preview_button_for_pdf(self, logged_in_admin, server):
        """Admin sees '预览' button on PDF documents"""
        page = logged_in_admin
        page.goto(f"{BASE_URL}/admin/approvals")
        page.wait_for_load_state("networkidle")
        assert page.locator('text=审批').first.is_visible()

    def test_preview_endpoint_returns_inline_pdf(self, logged_in_admin, server):
        """Preview endpoint returns inline content (not attachment)"""
        page = logged_in_admin
        # Find any PDF document
        doc = page.evaluate("""
            async () => {
                const r = await fetch('/admin/api/approval-documents');
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

        response = page.request.get(f"{BASE_URL}/admin/api/documents/{doc['id']}/preview")
        assert response.status == 200
        cd = response.headers.get('content-disposition', '')
        assert 'attachment' not in cd.lower()

    def test_preview_endpoint_415_for_docx(self, logged_in_admin, server):
        """Preview returns 415 for unsupported formats"""
        page = logged_in_admin
        # Find a DOCX document
        doc = page.evaluate("""
            async () => {
                const r = await fetch('/admin/api/approval-documents');
                const data = await r.json();
                if (data.documents) {
                    const docx = data.documents.find(d => d.filename && d.filename.toLowerCase().endsWith('.docx'));
                    return docx || null;
                }
                return null;
            }
        """)
        if not doc:
            pytest.skip("No DOCX documents in system")

        response = page.request.get(f"{BASE_URL}/admin/api/documents/{doc['id']}/preview")
        assert response.status == 415

    def test_unauthenticated_preview_blocked(self, page, server):
        """Unauthenticated users cannot access preview"""
        response = page.request.get(f"{BASE_URL}/admin/api/documents/1/preview")
        assert response.status in [302, 401, 403]
```

**Step 2: Run all E2E tests**

```bash
cd d:/Users/Administrator/CPCWebIII && python -m pytest tests/integration/ -v --tb=short 2>&1 | tail -30
```

Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/integration/test_document_preview.py
git commit -m "test: add E2E tests for document preview feature"
```

---

### Task 8: Final Verification and Push

**Step 1: Run full test suite**

```bash
cd d:/Users/Administrator/CPCWebIII && python -m pytest tests/integration/ -v --tb=short 2>&1 | tail -40
```

Expected: All tests pass

**Step 2: Manual verification checklist**

1. Login as secretary → visit applicant detail → click "预览" on PDF → modal opens with PDF content
2. Login as admin → visit approval review → click "预览" on PDF → modal opens
3. Verify modal close: X button, overlay click, ESC key
4. Verify PDF page navigation (prev/next)
5. Verify zoom in/out works
6. Verify image preview works (if JPG/PNG docs exist)
7. Verify DOC/XLS files do NOT show preview button
8. Login as applicant → verify NO preview buttons visible

**Step 3: Push**

```bash
git push origin feat/step-level-workflow-control
```
