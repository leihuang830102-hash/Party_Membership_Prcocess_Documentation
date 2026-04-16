# Document Online Preview Design

## Date: 2026-04-16

## Summary

Add in-browser document preview (modal overlay) for secretary and admin roles. Supports PDF (via PDF.js) and images (JPG/PNG). No server-side dependencies.

## Requirements

- Secretary and admin can preview PDF and image documents inline without downloading
- Preview opens in a modal overlay on the current page (no navigation)
- Non-supported formats (DOC/DOCX/XLS/XLSX) show "not supported" message with download option
- PDF.js loaded locally (offline-capable, no CDN dependency)
- Applicant role does NOT get preview access

## Architecture

### Backend: Inline File Serving Endpoints

Two new endpoints that serve files with `Content-Disposition: inline`:

| Endpoint | Blueprint | Auth |
|----------|-----------|------|
| `/secretary/api/documents/<id>/preview` | secretary | Secretary role + branch access check |
| `/admin/api/documents/<id>/preview` | admin | Admin role |

Logic:
1. Look up Document by ID, get `file_path`
2. Validate file exists on disk
3. Validate file extension is PDF/JPG/JPEG/PNG
4. Return `send_file(file_path, as_attachment=False, mimetype=...)`
5. For unsupported formats: return 415 with message "该格式不支持预览，请下载查看"

### Frontend: Global Preview Modal in base.html

A single reusable modal component added to `base.html`:

```
+------------------------------------------+
|  filename.pdf                  [X] Close |
|  --------------------------------------- |
|                                          |
|    +---------------------------+         |
|    |                           |         |
|    |    PDF.js canvas          |         |
|    |    or <img> for images    |         |
|    |                           |         |
|    +---------------------------+         |
|                                          |
|  [< Prev]  Page 1/5  [Next >]           |
|  [+] Zoom In  [-] Zoom Out  [Download]  |
+------------------------------------------+
```

Features:
- PDF: PDF.js renders to `<canvas>`, supports page navigation and zoom
- Images: Direct `<img>` tag with zoom
- Unsupported formats: "Cannot preview" message + download button
- Modal size: 90% viewport width/height, highest z-index
- Close: X button, overlay click, ESC key

### PDF.js Resources

Download PDF.js v4.x to `app/static/lib/pdf.js/`:
- `pdf.min.js` - core library
- `pdf.worker.min.js` - web worker

### UI Integration Points

Add "Preview" button in these templates (secretary + admin only):

| Page | Template File | Button Location |
|------|---------------|-----------------|
| Secretary - Applicant Detail | `secretary/applicant_detail.html` | Document card actions |
| Secretary - Documents | `secretary/documents.html` | Document card actions |
| Admin - Approval Detail | `admin/approval_detail.html` | Document list rows |
| Admin - Approval Review | `admin/approval_review.html` | Per-document review area |

Button visibility:
- PDF/image files: show "Preview" button
- DOC/DOCX/XLS/XLSX: show only "Download" button, no "Preview"

## Files to Create/Modify

| File | Change |
|------|--------|
| `app/routes/secretary.py` | Add `/api/documents/<id>/preview` endpoint |
| `app/routes/admin.py` | Add `/api/documents/<id>/preview` endpoint |
| `app/templates/base.html` | Add global preview modal + CSS + JS |
| `app/templates/secretary/applicant_detail.html` | Add preview button to doc cards |
| `app/templates/secretary/documents.html` | Add preview button to doc cards |
| `app/templates/admin/approval_detail.html` | Add preview button to doc list |
| `app/templates/admin/approval_review.html` | Add preview button to doc review area |
| `app/static/lib/pdf.js/pdf.min.js` | NEW - PDF.js core |
| `app/static/lib/pdf.js/pdf.worker.min.js` | NEW - PDF.js worker |

## Out of Scope (YAGNI)

- Office document preview (DOC/DOCX/XLS/XLSX online rendering)
- Document editing or annotation
- Watermarking or screenshot prevention
- Full-text search within documents
- Applicant role preview access
