import pytest
from app import create_app, db
from app.models import User, Branch

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            db.session.remove()
        yield client

@pytest.fixture
def setup_users(client):
    """创建测试用户和支部"""
    with client.application.app_context():
        # 检查是否已存在支部
        branch = Branch.query.filter_by(name='测试支部').first()
        if not branch:
            branch = Branch(name='测试支部')
            db.session.add(branch)
            db.session.commit()

        # 检查是否已存在用户
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', name='管理员', role='admin', branch_id=branch.id)
            admin.set_password('admin123')
            db.session.add(admin)

        secretary = User.query.filter_by(username='secretary').first()
        if not secretary:
            secretary = User(username='secretary', name='书记', role='secretary', branch_id=branch.id)
            secretary.set_password('sec123')
            db.session.add(secretary)

        applicant = User.query.filter_by(username='applicant').first()
        if not applicant:
            applicant = User(username='applicant', name='申请人', role='applicant', branch_id=branch.id)
            applicant.set_password('app123')
            db.session.add(applicant)

        db.session.commit()

class TestLogin:
    def test_login_page_loads(self, client):
        response = client.get('/auth/login')
        assert response.status_code == 200

    def test_login_success_admin(self, client, setup_users):
        response = client.post('/auth/login', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'admin' in response.data or b'Admin' in response.data or b'\xe7\xae\xa1\xe7\x90\x86' in response.data

    def test_login_success_applicant(self, client, setup_users):
        response = client.post('/auth/login', data={
            'username': 'applicant',
            'password': 'app123'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_login_wrong_password(self, client, setup_users):
        response = client.post('/auth/login', data={
            'username': 'admin',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        assert b'\xe7\x94\xa8\xe6\x88\xb7\xe5\x90\x8d\xe6\x88\x96\xe5\xaf\x86\xe7\xa0\x81\xe9\x94\x99\xe8\xaf\xaf' in response.data  # 用户名或密码错误

    def test_login_invalid_user(self, client, setup_users):
        response = client.post('/auth/login', data={
            'username': 'nonexistent',
            'password': 'password'
        }, follow_redirects=True)
        assert b'\xe7\x94\xa8\xe6\x88\xb7\xe5\x90\x8d\xe6\x88\x96\xe5\xaf\x86\xe7\xa0\x81\xe9\x94\x99\xe8\xaf\xaf' in response.data

class TestLogout:
    def test_logout(self, client, setup_users):
        client.post('/auth/login', data={'username': 'admin', 'password': 'admin123'})
        response = client.get('/auth/logout', follow_redirects=True)
        assert response.status_code == 200
        # 检查已登出（可能重定向到登录页）
        assert b'login' in response.data or b'\xe7\x99\xbb\xe5\xbd\x95' in response.data

class TestAuthRequired:
    def test_protected_route_redirects(self, client):
        response = client.get('/admin/dashboard')
        assert response.status_code == 302  # Redirect to login
