# 集成测试文档

## 测试结构

```
tests/
├── conftest.py              # Pytest配置和fixtures
├── test_models.py           # 数据模型单元测试
├── test_auth.py             # 认证单元测试
├── integration/
│   ├── conftest.py          # 集成测试配置
│   ├── test_login.py        # 登录测试
│   ├── test_admin.py        # 管理员页面测试
│   ├── test_applicant.py    # 申请人页面测试
│   ├── test_secretary.py    # 书记页面测试
│   ├── test_workflows.py    # 业务流程测试
│   ├── test_workflow_admin_setup.py    # 管理员设置流程
│   ├── test_workflow_templates.py      # 模板管理流程
│   ├── test_workflow_rejection.py      # 驳回重提流程
│   └── test_full_workflow.py           # 完整业务流程测试
└── run_integration_tests.py # 集成测试运行脚本
```

## 运行测试

### 方式一：使用集成测试脚本（推荐）

```bash
# Windows
run_integration_tests.bat          # 运行所有测试
run_integration_tests.bat smoke    # 快速冒烟测试
run_integration_tests.bat workflow # 完整工作流测试
run_integration_tests.bat setup    # 仅设置测试

# Linux/Mac
./run_integration_tests.sh          # 运行所有测试
./run_integration_tests.sh smoke    # 快速冒烟测试
./run_integration_tests.sh workflow # 完整工作流测试
```

### 方式二：直接使用 pytest

```bash
# 运行所有测试
pytest tests/ -v

# 只运行集成测试
pytest tests/integration/ -v

# 运行特定测试文件
pytest tests/integration/test_full_workflow.py -v

# 运行特定测试类
pytest tests/integration/test_full_workflow.py::TestSetupData -v

# 生成HTML报告
pytest tests/integration/ --html=report.html --self-contained-html
```

## 测试场景

### 1. 完整业务流程测试 (test_full_workflow.py)

这是最全面的测试，覆盖完整的入党申请流程：

| 测试类 | 描述 | 测试数 |
|-------|------|--------|
| TestSetupData | 创建支部AAA、申请人AAB、管理员BBB、书记CCC | 3 |
| TestTemplateUpload | 管理员上传模板 | 2 |
| TestApplicantWorkflow | 申请人登录、查看进度、上传文档 | 5 |
| TestSecretaryWorkflow | 书记查看申请人、审核文档 | 5 |
| TestAdminWorkflow | 管理员审批、搜索、筛选 | 5 |
| TestCompleteWorkflow | 端到端完整流程 | 1 |
| TestUserAuthentication | 多用户认证 | 1 |

### 2. 工作流测试

- `test_workflows.py` - 基础工作流测试
- `test_workflow_admin_setup.py` - 管理员设置流程
- `test_workflow_templates.py` - 模板上传流程
- `test_workflow_rejection.py` - 驳回重提流程

## 测试用户

测试过程中会创建以下测试用户：

| 用户名 | 密码 | 角色 | 所属支部 |
|-------|------|------|---------|
| admin | 123456 | 管理员 | - |
| secretary | 123456 | 书记 | 测试支部 |
| applicant | 123456 | 申请人 | 测试支部 |
| aab | 123456 | 申请人 | 测试支部AAA |
| bbb | 123456 | 管理员 | - |
| ccc | 123456 | 书记 | 测试支部AAA |

## 测试数据

测试会自动创建：
- 测试支部 "测试支部AAA"
- 测试用户 aab, bbb, ccc
- 测试文档和模板

## 运行前准备

1. **启动服务器**
   ```bash
   python run.py
   ```
   服务器应在 `http://127.0.0.1:5003` 运行

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   playwright install
   ```

3. **初始化数据库**（如果需要）
   ```bash
   python init_db.py
   ```

## 持续集成

可以将测试集成到CI/CD流程中：

```yaml
# .github/workflows/test.yml 示例
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: playwright install
      - run: python run.py &
      - run: sleep 5
      - run: pytest tests/integration/ -v
```

## 常见问题

### Q: 测试失败提示"服务器未运行"
A: 先启动Flask服务器: `python run.py`

### Q: 浏览器启动失败
A: 安装Playwright浏览器: `playwright install`

### Q: 数据库错误
A: 确保数据库已初始化: `python init_db.py`
