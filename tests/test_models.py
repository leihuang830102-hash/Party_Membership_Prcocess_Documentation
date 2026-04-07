import pytest
from app import create_app, db
from app.models import User, Branch, StepDefinition, Application, StepRecord, Document, Template, ContactAssignment, QuarterlyReview, Notification

@pytest.fixture
def app():
    app = create_app()
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

class TestUser:
    def test_create_user(self, app):
        with app.app_context():
            user = User(username='test', name='测试用户', role='applicant')
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()

            assert user.id is not None
            assert user.check_password('password123') is True
            assert user.check_password('wrong') is False

    def test_user_roles(self, app):
        with app.app_context():
            admin = User(username='admin', name='管理员', role='admin')
            secretary = User(username='sec', name='书记', role='secretary')
            applicant = User(username='app', name='申请人', role='applicant')

            assert admin.is_admin() is True
            assert secretary.is_secretary() is True
            assert applicant.is_applicant() is True

class TestBranch:
    def test_create_branch(self, app):
        with app.app_context():
            branch = Branch(name='技术支部', description='技术部门党支部')
            db.session.add(branch)
            db.session.commit()

            assert branch.id is not None
            assert branch.name == '技术支部'

class TestApplication:
    def test_create_application(self, app):
        with app.app_context():
            branch = Branch(name='测试支部')
            db.session.add(branch)

            user = User(username='test', name='测试', role='applicant')
            user.set_password('pwd')
            db.session.add(user)
            db.session.commit()

            application = Application(user_id=user.id, branch_id=branch.id)
            db.session.add(application)
            db.session.commit()

            assert application.id is not None
            assert application.current_step == 'L1'
            assert application.current_stage == 1
            assert application.status == 'in_progress'

class TestStepDefinition:
    def test_create_step_definition(self, app):
        with app.app_context():
            step = StepDefinition(
                step_code='L1',
                stage=1,
                name='递交入党申请书',
                description='申请人递交入党申请书',
                order_num=1
            )
            db.session.add(step)
            db.session.commit()

            assert step.id is not None
            assert step.step_code == 'L1'
            assert step.stage == 1

class TestStepRecord:
    def test_create_step_record(self, app):
        with app.app_context():
            branch = Branch(name='测试支部')
            db.session.add(branch)

            user = User(username='test', name='测试', role='applicant')
            user.set_password('pwd')
            db.session.add(user)
            db.session.commit()

            application = Application(user_id=user.id, branch_id=branch.id)
            db.session.add(application)
            db.session.commit()

            record = StepRecord(application_id=application.id, step_code='L1', status='completed')
            db.session.add(record)
            db.session.commit()

            assert record.id is not None
            assert record.step_code == 'L1'
            assert record.status == 'completed'

class TestDocument:
    def test_create_document(self, app):
        with app.app_context():
            branch = Branch(name='测试支部')
            db.session.add(branch)

            user = User(username='test', name='测试', role='applicant')
            user.set_password('pwd')
            db.session.add(user)
            db.session.commit()

            application = Application(user_id=user.id, branch_id=branch.id)
            db.session.add(application)
            db.session.commit()

            doc = Document(
                application_id=application.id,
                step_code='L1',
                doc_type='application_letter',
                filename='test.pdf',
                file_path='/uploads/test.pdf',
                uploaded_by=user.id
            )
            db.session.add(doc)
            db.session.commit()

            assert doc.id is not None
            assert doc.filename == 'test.pdf'

class TestTemplate:
    def test_create_template(self, app):
        with app.app_context():
            template = Template(
                name='入党申请书模板',
                stage=1,
                step_code='L1',
                filename='template.docx',
                file_path='/templates/template.docx'
            )
            db.session.add(template)
            db.session.commit()

            assert template.id is not None
            assert template.name == '入党申请书模板'

class TestContactAssignment:
    def test_create_contact_assignment(self, app):
        with app.app_context():
            branch = Branch(name='测试支部')
            db.session.add(branch)

            applicant = User(username='applicant', name='申请人', role='applicant')
            applicant.set_password('pwd')
            contact = User(username='contact', name='联系人', role='secretary')
            contact.set_password('pwd')
            db.session.add_all([applicant, contact])
            db.session.commit()

            application = Application(user_id=applicant.id, branch_id=branch.id)
            db.session.add(application)
            db.session.commit()

            assignment = ContactAssignment(
                application_id=application.id,
                contact_user_id=contact.id
            )
            db.session.add(assignment)
            db.session.commit()

            assert assignment.id is not None
            assert assignment.is_active is True

class TestQuarterlyReview:
    def test_create_quarterly_review(self, app):
        with app.app_context():
            branch = Branch(name='测试支部')
            db.session.add(branch)

            user = User(username='test', name='测试', role='applicant')
            user.set_password('pwd')
            reviewer = User(username='reviewer', name='考察人', role='secretary')
            reviewer.set_password('pwd')
            db.session.add_all([user, reviewer])
            db.session.commit()

            application = Application(user_id=user.id, branch_id=branch.id)
            db.session.add(application)
            db.session.commit()

            review = QuarterlyReview(
                application_id=application.id,
                quarter='2024-Q1',
                review_type='regular',
                reviewer_id=reviewer.id,
                content='表现良好'
            )
            db.session.add(review)
            db.session.commit()

            assert review.id is not None
            assert review.quarter == '2024-Q1'

class TestNotification:
    def test_create_notification(self, app):
        with app.app_context():
            user = User(username='test', name='测试', role='applicant')
            user.set_password('pwd')
            db.session.add(user)
            db.session.commit()

            notification = Notification(
                user_id=user.id,
                title='测试通知',
                content='这是一条测试通知'
            )
            db.session.add(notification)
            db.session.commit()

            assert notification.id is not None
            assert notification.is_read is False
            assert notification.title == '测试通知'
