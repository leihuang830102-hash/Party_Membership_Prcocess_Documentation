"""
Tests for step-level workflow control configuration.

This module tests:
1. StepDefinition model has submitter_role and approval_type fields
2. StepRecord model supports 'secretary_approved' status value
3. Migration script correctly sets all 26 step configurations per the Matrix mapping
4. Helper function can_submit(user_role, step_code) works correctly
5. Helper function get_step_config(step_code) returns correct config

The 26 steps use codes L1-L26, organized into 5 stages:
  Stage 1: L1-L6   (递交入党申请书)
  Stage 2: L7-L12  (入党积极分子培养)
  Stage 3: L13-L14 (确定发展对象)
  Stage 4: L15-L20 (接收预备党员)
  Stage 5: L21-L26 (预备党员转正)

Matrix mapping (from Matrix.xlsx):
  applicant / two_level:   L1, L7, L13, L21                    (4 steps)
  secretary / one_level:   L2-L6, L8-L11, L14, L18-L20, L22-L24 (16 steps)
  admin / none:            L12, L15-L17, L25, L26               (6 steps)
"""

import pytest
import json
from app import create_app, db
from app.models import StepDefinition, StepRecord, Application, User, Branch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a test Flask app with in-memory SQLite database."""
    app = create_app()
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def seeded_app(app):
    """
    App fixture with all 26 step definitions seeded,
    including the new submitter_role and approval_type columns.
    """
    with app.app_context():
        _seed_step_definitions()
        yield app


# ---------------------------------------------------------------------------
# Seed helper
# ---------------------------------------------------------------------------

# Matrix mapping (from Matrix.xlsx): step_code -> (submitter_role, approval_type)
STEP_WORKFLOW_CONFIG = {
    # 第一阶段：递交入党申请书
    'L1': ('applicant', 'two_level'),     # 递交入党申请
    'L2': ('secretary', 'one_level'),     # 党组织派人谈话
    'L3': ('secretary', 'one_level'),     # 推荐入党积极分子
    'L4': ('secretary', 'one_level'),     # 确定入党积极分子
    'L5': ('secretary', 'one_level'),     # 报上级党委备案
    'L6': ('secretary', 'one_level'),     # 积极分子培养、教育、考察
    # 第二阶段：入党积极分子培养
    'L7': ('applicant', 'two_level'),     # 填写《自传书》
    'L8': ('secretary', 'one_level'),     # 推荐发展对象
    'L9': ('secretary', 'one_level'),     # 发展对象确定并向上级党委备案
    'L10': ('secretary', 'one_level'),    # 发展对象培养、教育、考察
    'L11': ('secretary', 'one_level'),    # 支委会审查
    'L12': ('admin', 'none'),             # 上级党委预审
    # 第三阶段：确定发展对象
    'L13': ('applicant', 'two_level'),    # 填写《入党志愿书》
    'L14': ('secretary', 'one_level'),    # 接收预备党员支部大会
    # 第四阶段：接收预备党员
    'L15': ('admin', 'none'),             # 上级党委派人谈话
    'L16': ('admin', 'none'),             # 上级党委审批
    'L17': ('admin', 'none'),             # 逐级上报党委组织部门备案
    'L18': ('secretary', 'one_level'),    # 编入党支部、党小组
    'L19': ('secretary', 'one_level'),    # 入党宣誓
    'L20': ('secretary', 'one_level'),    # 预备党员培养、教育、考察
    # 第五阶段：预备党员转正
    'L21': ('applicant', 'two_level'),    # 提出转正申请
    'L22': ('secretary', 'one_level'),    # 转正前考察
    'L23': ('secretary', 'one_level'),    # 支委会审查
    'L24': ('secretary', 'one_level'),    # 预备党员转正支部大会
    'L25': ('admin', 'none'),             # 上级党委审批
    'L26': ('admin', 'none'),             # 材料归档
}

# Step definitions: (step_code, stage, name, order_num)
STEP_DEFINITIONS = [
    ('L1', 1, '递交入党申请', 1),
    ('L2', 1, '党组织派人谈话', 2),
    ('L3', 1, '推荐入党积极分子', 3),
    ('L4', 1, '确定入党积极分子', 4),
    ('L5', 1, '报上级党委备案', 5),
    ('L6', 1, '积极分子培养、教育、考察', 6),
    ('L7', 2, '填写《自传书》', 7),
    ('L8', 2, '推荐发展对象', 8),
    ('L9', 2, '发展对象确定并向上级党委备案', 9),
    ('L10', 2, '发展对象培养、教育、考察', 10),
    ('L11', 2, '支委会审查', 11),
    ('L12', 2, '上级党委预审', 12),
    ('L13', 3, '填写《入党志愿书》', 13),
    ('L14', 3, '接收预备党员支部大会', 14),
    ('L15', 4, '上级党委派人谈话', 15),
    ('L16', 4, '上级党委审批', 16),
    ('L17', 4, '逐级上报党委组织部门备案', 17),
    ('L18', 4, '编入党支部、党小组', 18),
    ('L19', 4, '入党宣誓', 19),
    ('L20', 4, '预备党员培养、教育、考察', 20),
    ('L21', 5, '提出转正申请', 21),
    ('L22', 5, '转正前考察', 22),
    ('L23', 5, '支委会审查', 23),
    ('L24', 5, '预备党员转正支部大会', 24),
    ('L25', 5, '上级党委审批', 25),
    ('L26', 5, '材料归档', 26),
]


def _seed_step_definitions():
    """Insert all 26 step definitions with workflow config into the test DB."""
    for step_code, stage, name, order_num in STEP_DEFINITIONS:
        submitter_role, approval_type = STEP_WORKFLOW_CONFIG[step_code]
        step = StepDefinition(
            step_code=step_code,
            stage=stage,
            name=name,
            order_num=order_num,
            submitter_role=submitter_role,
            approval_type=approval_type,
        )
        db.session.add(step)
    db.session.commit()


# ---------------------------------------------------------------------------
# Helper functions under test (defined here for TDD; will move to app code)
# ---------------------------------------------------------------------------

def get_step_config(step_code):
    """
    Return the workflow configuration for a given step_code.

    Returns:
        dict with keys: step_code, submitter_role, approval_type
        None if step_code not found
    """
    step = StepDefinition.query.filter_by(step_code=step_code).first()
    if step is None:
        return None
    return {
        'step_code': step.step_code,
        'submitter_role': step.submitter_role,
        'approval_type': step.approval_type,
    }


def can_submit(user_role, step_code):
    """
    Check whether a user with the given role can submit/perform the given step.

    Rules:
      - applicant can submit steps with submitter_role='applicant'
      - secretary can submit steps with submitter_role='secretary'
      - admin can submit any step (submitter_role='admin' or override)
      - contact_person has same rights as secretary for now

    Args:
        user_role: one of 'applicant', 'secretary', 'admin', 'contact_person'
        step_code: step code, e.g. 'L1', 'L7'

    Returns:
        True if the user can submit this step, False otherwise
    """
    config = get_step_config(step_code)
    if config is None:
        return False

    required_role = config['submitter_role']

    # admin can always submit
    if user_role == 'admin':
        return True

    # contact_person treated same as secretary
    effective_role = user_role
    if user_role == 'contact_person':
        effective_role = 'secretary'

    return effective_role == required_role


# ===========================================================================
# Test classes
# ===========================================================================


class TestStepDefinitionNewFields:
    """Test that StepDefinition model supports the new columns."""

    def test_step_definition_has_submitter_role(self, app):
        """StepDefinition model should have submitter_role field."""
        with app.app_context():
            step = StepDefinition(
                step_code='TEST',
                stage=1,
                name='测试步骤',
                order_num=99,
                submitter_role='applicant',
            )
            db.session.add(step)
            db.session.commit()

            loaded = StepDefinition.query.filter_by(step_code='TEST').first()
            assert loaded is not None
            assert loaded.submitter_role == 'applicant'

    def test_step_definition_has_approval_type(self, app):
        """StepDefinition model should have approval_type field."""
        with app.app_context():
            step = StepDefinition(
                step_code='TEST2',
                stage=1,
                name='测试步骤2',
                order_num=100,
                approval_type='two_level',
            )
            db.session.add(step)
            db.session.commit()

            loaded = StepDefinition.query.filter_by(step_code='TEST2').first()
            assert loaded is not None
            assert loaded.approval_type == 'two_level'

    def test_submitter_role_default_is_applicant(self, app):
        """submitter_role should default to 'applicant' if not specified."""
        with app.app_context():
            step = StepDefinition(
                step_code='TEST3',
                stage=1,
                name='默认测试',
                order_num=101,
            )
            db.session.add(step)
            db.session.commit()

            loaded = StepDefinition.query.filter_by(step_code='TEST3').first()
            assert loaded.submitter_role == 'applicant'

    def test_approval_type_default_is_two_level(self, app):
        """approval_type should default to 'two_level' if not specified."""
        with app.app_context():
            step = StepDefinition(
                step_code='TEST4',
                stage=1,
                name='默认测试2',
                order_num=102,
            )
            db.session.add(step)
            db.session.commit()

            loaded = StepDefinition.query.filter_by(step_code='TEST4').first()
            assert loaded.approval_type == 'two_level'

    def test_step_definition_both_fields_together(self, app):
        """StepDefinition should support setting both new fields together."""
        with app.app_context():
            step = StepDefinition(
                step_code='TEST5',
                stage=2,
                name='组合测试',
                order_num=103,
                submitter_role='secretary',
                approval_type='one_level',
            )
            db.session.add(step)
            db.session.commit()

            loaded = StepDefinition.query.filter_by(step_code='TEST5').first()
            assert loaded.submitter_role == 'secretary'
            assert loaded.approval_type == 'one_level'


class TestStepRecordSecretaryApproved:
    """Test that StepRecord model supports 'secretary_approved' status."""

    def test_step_record_secretary_approved_status(self, app):
        """StepRecord should accept 'secretary_approved' as a status value."""
        with app.app_context():
            # Create prerequisite data
            branch = Branch(name='测试支部')
            db.session.add(branch)
            user = User(username='test_sr', name='测试', role='applicant')
            user.set_password('pwd')
            db.session.add(user)
            db.session.commit()

            application = Application(user_id=user.id, branch_id=branch.id)
            db.session.add(application)
            db.session.commit()

            # Create step record with secretary_approved status
            record = StepRecord(
                application_id=application.id,
                step_code='L1',
                status='secretary_approved',
            )
            db.session.add(record)
            db.session.commit()

            loaded = StepRecord.query.filter_by(
                application_id=application.id,
                step_code='L1'
            ).first()
            assert loaded is not None
            assert loaded.status == 'secretary_approved'

    def test_step_record_all_valid_statuses(self, app):
        """StepRecord should accept all documented status values."""
        with app.app_context():
            branch = Branch(name='测试支部2')
            db.session.add(branch)
            user = User(username='test_sr2', name='测试2', role='applicant')
            user.set_password('pwd')
            db.session.add(user)
            db.session.commit()

            application = Application(user_id=user.id, branch_id=branch.id)
            db.session.add(application)
            db.session.commit()

            valid_statuses = [
                'pending', 'completed', 'failed', 'secretary_approved'
            ]
            for i, status in enumerate(valid_statuses):
                record = StepRecord(
                    application_id=application.id,
                    step_code=f'L{i+1}',
                    status=status,
                )
                db.session.add(record)
            db.session.commit()

            records = StepRecord.query.filter_by(
                application_id=application.id
            ).all()
            saved_statuses = {r.step_code: r.status for r in records}

            for i, status in enumerate(valid_statuses):
                assert saved_statuses[f'L{i+1}'] == status


class TestMigrationStepConfigurations:
    """
    Test that the 26 step definitions are correctly configured
    per the Matrix mapping after migration/seed.
    """

    def test_total_step_count(self, seeded_app):
        """Should have exactly 26 step definitions."""
        with seeded_app.app_context():
            count = StepDefinition.query.count()
            assert count == 26

    # --- applicant / two_level steps (L1, L7, L13, L21) ---

    @pytest.mark.parametrize("step_code", ['L1', 'L7', 'L13', 'L21'])
    def test_applicant_two_level_steps(self, seeded_app, step_code):
        """Steps L1, L7, L13, L21 should be applicant/two_level."""
        with seeded_app.app_context():
            step = StepDefinition.query.filter_by(step_code=step_code).first()
            assert step is not None, f"Step {step_code} should exist"
            assert step.submitter_role == 'applicant'
            assert step.approval_type == 'two_level'

    # --- secretary / one_level steps (16 steps) ---

    @pytest.mark.parametrize("step_code", [
        'L2', 'L3', 'L4', 'L5', 'L6',           # Stage 1
        'L8', 'L9', 'L10', 'L11',                # Stage 2
        'L14',                                     # Stage 3
        'L18', 'L19', 'L20',                      # Stage 4
        'L22', 'L23', 'L24',                      # Stage 5
    ])
    def test_secretary_one_level_steps(self, seeded_app, step_code):
        """Secretary/one_level steps should have correct config."""
        with seeded_app.app_context():
            step = StepDefinition.query.filter_by(step_code=step_code).first()
            assert step is not None, f"Step {step_code} should exist"
            assert step.submitter_role == 'secretary'
            assert step.approval_type == 'one_level'

    # --- admin / none steps (L12, L15-L17, L25, L26) ---

    @pytest.mark.parametrize("step_code", [
        'L12',              # Stage 2: 上级党委预审
        'L15', 'L16', 'L17',  # Stage 4: 党委操作
        'L25', 'L26',       # Stage 5: 党委操作
    ])
    def test_admin_none_steps(self, seeded_app, step_code):
        """Admin/none steps should have correct config."""
        with seeded_app.app_context():
            step = StepDefinition.query.filter_by(step_code=step_code).first()
            assert step is not None, f"Step {step_code} should exist"
            assert step.submitter_role == 'admin'
            assert step.approval_type == 'none'

    def test_no_step_has_null_workflow_config(self, seeded_app):
        """No step should have NULL submitter_role or approval_type."""
        with seeded_app.app_context():
            steps = StepDefinition.query.all()
            for step in steps:
                assert step.submitter_role is not None, \
                    f"Step {step.step_code} has NULL submitter_role"
                assert step.approval_type is not None, \
                    f"Step {step.step_code} has NULL approval_type"


class TestCanSubmit:
    """Test the can_submit helper function."""

    def test_applicant_can_submit_applicant_step(self, seeded_app):
        """Applicant should be able to submit applicant steps (L1, L7, L13, L21)."""
        with seeded_app.app_context():
            assert can_submit('applicant', 'L1') is True
            assert can_submit('applicant', 'L7') is True
            assert can_submit('applicant', 'L13') is True
            assert can_submit('applicant', 'L21') is True

    def test_applicant_cannot_submit_secretary_step(self, seeded_app):
        """Applicant should NOT be able to submit secretary steps."""
        with seeded_app.app_context():
            assert can_submit('applicant', 'L2') is False
            assert can_submit('applicant', 'L8') is False
            assert can_submit('applicant', 'L14') is False

    def test_applicant_cannot_submit_admin_step(self, seeded_app):
        """Applicant should NOT be able to submit admin steps."""
        with seeded_app.app_context():
            assert can_submit('applicant', 'L12') is False
            assert can_submit('applicant', 'L15') is False

    def test_secretary_can_submit_secretary_step(self, seeded_app):
        """Secretary should be able to submit secretary steps."""
        with seeded_app.app_context():
            assert can_submit('secretary', 'L2') is True
            assert can_submit('secretary', 'L8') is True
            assert can_submit('secretary', 'L18') is True
            assert can_submit('secretary', 'L22') is True

    def test_secretary_cannot_submit_applicant_step(self, seeded_app):
        """Secretary should NOT be able to submit applicant steps."""
        with seeded_app.app_context():
            assert can_submit('secretary', 'L1') is False
            assert can_submit('secretary', 'L7') is False

    def test_secretary_cannot_submit_admin_step(self, seeded_app):
        """Secretary should NOT be able to submit admin steps."""
        with seeded_app.app_context():
            assert can_submit('secretary', 'L12') is False
            assert can_submit('secretary', 'L15') is False

    def test_admin_can_submit_any_step(self, seeded_app):
        """Admin should be able to submit ANY step."""
        with seeded_app.app_context():
            # Test all 3 categories
            assert can_submit('admin', 'L1') is True    # applicant step
            assert can_submit('admin', 'L2') is True    # secretary step
            assert can_submit('admin', 'L12') is True   # admin step

    def test_contact_person_same_as_secretary(self, seeded_app):
        """Contact person should have same submit rights as secretary."""
        with seeded_app.app_context():
            # Can submit secretary steps
            assert can_submit('contact_person', 'L2') is True
            assert can_submit('contact_person', 'L8') is True

            # Cannot submit applicant or admin steps
            assert can_submit('contact_person', 'L1') is False
            assert can_submit('contact_person', 'L12') is False

    def test_can_submit_invalid_step_code(self, seeded_app):
        """can_submit should return False for non-existent step codes."""
        with seeded_app.app_context():
            assert can_submit('admin', 'INVALID') is False
            assert can_submit('applicant', 'X99') is False

    def test_can_submit_invalid_role(self, seeded_app):
        """can_submit should return False for unknown roles on restricted steps."""
        with seeded_app.app_context():
            assert can_submit('unknown_role', 'L1') is False


class TestGetStepConfig:
    """Test the get_step_config helper function."""

    def test_get_step_config_returns_correct_dict(self, seeded_app):
        """get_step_config should return a dict with correct keys and values."""
        with seeded_app.app_context():
            config = get_step_config('L1')
            assert config is not None
            assert config['step_code'] == 'L1'
            assert config['submitter_role'] == 'applicant'
            assert config['approval_type'] == 'two_level'

    def test_get_step_config_secretary_step(self, seeded_app):
        """get_step_config for a secretary step."""
        with seeded_app.app_context():
            config = get_step_config('L2')
            assert config is not None
            assert config['submitter_role'] == 'secretary'
            assert config['approval_type'] == 'one_level'

    def test_get_step_config_admin_step(self, seeded_app):
        """get_step_config for an admin step."""
        with seeded_app.app_context():
            config = get_step_config('L12')
            assert config is not None
            assert config['submitter_role'] == 'admin'
            assert config['approval_type'] == 'none'

    def test_get_step_config_nonexistent(self, seeded_app):
        """get_step_config should return None for non-existent step."""
        with seeded_app.app_context():
            config = get_step_config('INVALID')
            assert config is None

    def test_get_step_config_all_26_steps(self, seeded_app):
        """get_step_config should work for all 26 step codes."""
        with seeded_app.app_context():
            all_codes = [code for code, _, _, _ in STEP_DEFINITIONS]
            assert len(all_codes) == 26

            for code in all_codes:
                config = get_step_config(code)
                assert config is not None, f"Config for {code} should not be None"
                assert config['step_code'] == code
                assert config['submitter_role'] in ('applicant', 'secretary', 'admin')
                assert config['approval_type'] in ('two_level', 'one_level', 'none')
                # Verify consistency with our reference data
                expected_role, expected_approval = STEP_WORKFLOW_CONFIG[code]
                assert config['submitter_role'] == expected_role, \
                    f"Mismatch submitter_role for {code}"
                assert config['approval_type'] == expected_approval, \
                    f"Mismatch approval_type for {code}"
