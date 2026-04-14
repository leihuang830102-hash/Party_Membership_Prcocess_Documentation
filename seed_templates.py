#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Seed script: Import DOCX template files into the Template database table.

Reads template .docx files from New_Features/Doc_Templates/, copies them
to app/static/uploads/templates/ with secure timestamped filenames, and
creates corresponding Template records in the database.

Usage:
    python seed_templates.py              # Import templates (idempotent)
    python seed_templates.py --clean      # Remove all existing templates first
    python seed_templates.py --list       # List current templates in DB

Stage mapping (from StepDefinition convention):
    L1-L6  -> Stage 1  (递交入党申请书)
    L7-L12 -> Stage 2  (入党积极分子培养)
    L13-L14 -> Stage 3 (确定发展对象)
    L15-L20 -> Stage 4 (接收预备党员)
    L21-L26 -> Stage 5 (预备党员转正)

Note: L15 and L26 have no template files.
      L9 and L16 each have two template files.
"""

import os
import sys
import shutil
import argparse
from datetime import datetime

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so that `app` package is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# Source and destination directories (relative to project root)
SOURCE_DIR = os.path.join(PROJECT_ROOT, 'New_Features', 'Doc_Templates')
UPLOAD_DIR = os.path.join(PROJECT_ROOT, 'app', 'static', 'uploads', 'templates')

# ---------------------------------------------------------------------------
# Template file -> step_code mapping
# Derived from the filenames in New_Features/Doc_Templates/
# ---------------------------------------------------------------------------
TEMPLATE_FILES = [
    ('L1样张1.docx',              'L1'),
    ('L2样张2.docx',              'L2'),
    ('L3样张3、4、5.docx',        'L3'),
    ('L4样张6.docx',              'L4'),
    ('L5样张7、8.docx',           'L5'),
    ('L6样张9、10.docx',          'L6'),
    ('L7样张11.docx',             'L7'),
    ('L8样张12-15.docx',          'L8'),
    ('L9样张16-17.docx',          'L9'),
    ('L9样张18（党委批复）.docx',  'L9'),
    ('L10样张19-25.docx',         'L10'),
    ('L11样张26、27.docx',        'L11'),
    ('L12样张28（党委批复）.docx', 'L12'),
    ('L13样张29（入党志愿书）.docx', 'L13'),
    ('L14样张30-35.docx',         'L14'),
    ('L16样张36.docx',            'L16'),
    ('L16样张37、38（党委）.docx', 'L16'),
    ('L17样张39、40（党委）.docx', 'L17'),
    ('L18样张41.docx',            'L18'),
    ('L19样张42.docx',            'L19'),
    ('L20样张43.docx',            'L20'),
    ('L21样张44.docx',            'L21'),
    ('L22样张45-49.docx',         'L22'),
    ('L23样张50.docx',            'L23'),
    ('L24样张51-55.docx',         'L24'),
    ('L25样张62-64.docx',         'L25'),
]

# ---------------------------------------------------------------------------
# Stage mapping: step_code prefix -> stage number
# ---------------------------------------------------------------------------
def get_stage(step_code):
    """Derive the stage number (1-5) from a step_code like 'L1', 'L14', etc."""
    # Extract numeric part after 'L'
    try:
        num = int(step_code[1:])
    except (ValueError, IndexError):
        return None

    if 1 <= num <= 6:
        return 1
    elif 7 <= num <= 12:
        return 2
    elif 13 <= num <= 14:
        return 3
    elif 15 <= num <= 20:
        return 4
    elif 21 <= num <= 26:
        return 5
    return None


STAGE_NAMES = {
    1: '递交入党申请书',
    2: '入党积极分子培养',
    3: '确定发展对象',
    4: '接收预备党员',
    5: '预备党员转正',
}


def list_templates(app):
    """List all templates currently in the database."""
    from app.models import Template

    with app.app_context():
        templates = Template.query.order_by(Template.stage, Template.step_code).all()

        if not templates:
            print("\n=== No templates found in database ===\n")
            return

        print(f"\n{'='*80}")
        print(f"  Current Templates in Database ({len(templates)} total)")
        print(f"{'='*80}")
        print(f"  {'ID':<5} {'Step':<6} {'Stage':<7} {'Name':<40} {'Active'}")
        print(f"  {'-'*70}")

        for t in templates:
            stage_display = f"{t.stage}" if t.stage else '-'
            step_display = t.step_code or '-'
            active_display = 'Yes' if t.is_active else 'No'
            # Truncate long names for display
            name_display = t.name[:38] + '..' if len(t.name) > 40 else t.name
            print(f"  {t.id:<5} {step_display:<6} {stage_display:<7} {name_display:<40} {active_display}")

        print(f"{'='*80}\n")


def clean_templates(app):
    """Remove all existing templates from the database and their files."""
    from app.models import Template
    from app import db

    with app.app_context():
        templates = Template.query.all()
        count = len(templates)

        if count == 0:
            print("\n=== No templates to clean ===\n")
            return 0

        # Delete associated files from disk
        deleted_files = 0
        for t in templates:
            if t.file_path and os.path.exists(t.file_path):
                try:
                    os.remove(t.file_path)
                    deleted_files += 1
                except OSError as e:
                    print(f"  Warning: Could not delete file {t.file_path}: {e}")

        # Delete all DB records
        Template.query.delete()
        db.session.commit()

        print(f"\n=== Cleaned: deleted {count} template records, {deleted_files} files ===\n")
        return count


def seed_templates(app):
    """
    Import DOCX template files into the database.

    For each template file:
      1. Check if a Template record with same step_code + name already exists
         (idempotency guard).
      2. Copy the DOCX file to the upload directory with a secure timestamped
         filename.
      3. Create a Template record in the database.
    """
    from app.models import Template
    from app import db

    with app.app_context():
        # Ensure the upload directory exists
        os.makedirs(UPLOAD_DIR, exist_ok=True)

        # Counters for summary
        imported = 0
        skipped = 0
        errors = 0
        error_details = []

        print(f"\n{'='*70}")
        print(f"  Template Seed Script")
        print(f"  Source: {SOURCE_DIR}")
        print(f"  Upload: {UPLOAD_DIR}")
        print(f"{'='*70}\n")

        # Check that the source directory exists
        if not os.path.isdir(SOURCE_DIR):
            print(f"ERROR: Source directory not found: {SOURCE_DIR}")
            sys.exit(1)

        for filename, step_code in TEMPLATE_FILES:
            source_path = os.path.join(SOURCE_DIR, filename)

            # --- Validate source file exists ---
            if not os.path.exists(source_path):
                msg = f"SKIP (file not found): {filename}"
                print(f"  [SKIP] {msg}")
                error_details.append(msg)
                errors += 1
                continue

            # Derive metadata
            stage = get_stage(step_code)
            # Use original filename (without .docx extension) as the descriptive name
            name = os.path.splitext(filename)[0]

            # --- Idempotency: skip if template already exists ---
            existing = Template.query.filter_by(
                step_code=step_code,
                name=name
            ).first()
            if existing:
                print(f"  [SKIP] Already exists: {name} (step={step_code}, id={existing.id})")
                skipped += 1
                continue

            # --- Build a secure timestamped filename ---
            # Replace characters that are problematic in filenames
            safe_name = filename.replace(' ', '_')
            # Remove or replace characters not safe for filenames
            # Keep Chinese chars, alphanumeric, dots, dashes, underscores, parens
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            name_part, ext = os.path.splitext(safe_name)
            dest_filename = f"{name_part}_{timestamp}{ext}"
            dest_path = os.path.join(UPLOAD_DIR, dest_filename)

            # --- Copy file to upload directory ---
            try:
                shutil.copy2(source_path, dest_path)
            except OSError as e:
                msg = f"ERROR (copy failed): {filename} -> {e}"
                print(f"  [ERROR] {msg}")
                error_details.append(msg)
                errors += 1
                continue

            # --- Get file size ---
            file_size = os.path.getsize(dest_path)

            # --- Create Template database record ---
            try:
                template = Template(
                    name=name,
                    stage=stage,
                    step_code=step_code,
                    filename=dest_filename,
                    file_path=dest_path,
                    description=f"样张模板 - 步骤{step_code}",
                    is_active=True,
                )
                db.session.add(template)
                db.session.commit()

                stage_name = STAGE_NAMES.get(stage, 'Unknown') if stage else 'N/A'
                print(f"  [OK]   {name}")
                print(f"         step_code={step_code}, stage={stage} ({stage_name})")
                print(f"         file={dest_filename} ({file_size:,} bytes)")
                imported += 1

            except Exception as e:
                db.session.rollback()
                # Clean up the copied file since the DB insert failed
                if os.path.exists(dest_path):
                    try:
                        os.remove(dest_path)
                    except OSError:
                        pass
                msg = f"ERROR (DB insert failed): {filename} -> {e}"
                print(f"  [ERROR] {msg}")
                error_details.append(msg)
                errors += 1

        # --- Print summary ---
        print(f"\n{'='*70}")
        print(f"  Import Summary")
        print(f"{'='*70}")
        print(f"  Imported : {imported}")
        print(f"  Skipped  : {skipped} (already existed)")
        print(f"  Errors   : {errors}")
        print(f"  Total    : {len(TEMPLATE_FILES)} template files processed")
        print(f"{'='*70}")

        if error_details:
            print(f"\n  Error details:")
            for detail in error_details:
                print(f"    - {detail}")
            print()

        return imported, skipped, errors


def main():
    parser = argparse.ArgumentParser(
        description='Import DOCX template files into the CPCWebIII Template database table.'
    )
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Remove all existing templates from the database before importing.'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all current templates in the database and exit.'
    )
    args = parser.parse_args()

    # Import Flask app factory and create the app
    from app import create_app
    app = create_app()

    # --list mode: just show templates and exit
    if args.list:
        list_templates(app)
        return

    # --clean mode: remove all templates first
    if args.clean:
        clean_templates(app)

    # Seed templates
    imported, skipped, errors = seed_templates(app)

    # Exit with non-zero status if there were errors
    if errors > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
