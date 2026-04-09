# 业务流程测试计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 创建完整的业务流程自动化测试，覆盖入党申请全流程

**Architecture:** 使用 Playwright + pytest 进行端到端测试，模拟真实用户操作

**Tech Stack:** Playwright, pytest, pytest-asyncio

---

## 测试场景列表

### 场景1: 申请人A完整审批流程 (步骤1→步骤7)
**优先级:** 高
**文件:** `tests/integration/test_workflow_applicant_a.py`

- 申请人A登录
- 查看当前阶段(步骤1-申请人)
- 上传入党申请书
- 书记审批通过
- 阶段变为步骤2(入党积极分子)
- 上传思想汇报
- 书记审批通过
- 阶段变为步骤3-7
- 最终完成所有步骤
- 导出A的文档

### 场景2: 申请人B跳步骤被驳回
**优先级:** 高
**文件:** `tests/integration/test_workflow_applicant_b.py`

- 管理员创建申请人B，直接设置步骤5
- 书记发现跳步骤
- 书记驳回申请
- 申请人B被退回到正确步骤
- 申请人B重新提交

### 场景3: 驳回再通过流程
**优先级:** 高
**文件:** `tests/integration/test_workflow_rejection.py`

- 申请人上传文档
- 书记驳回
- 申请人重新提交
- 书记通过

### 场景4: 管理员上传/更新文档模板
**优先级:** 中
**文件:** `tests/integration/test_workflow_templates.py`

- 管理员上传新模板
- 管理员更新现有模板
- 书记和申请人可以看到模板变化

### 场景5: 管理员创建支部和用户
**优先级:** 中
**文件:** `tests/integration/test_workflow_admin_setup.py`

- 管理员创建新支部
- 管理员创建书记用户并分配支部
- 管理员创建申请人用户

---

## Task 1: 场景1 - 申请人A完整审批流程

**Files:**
- Create: `tests/integration/test_workflow_applicant_a.py`

**Step 1: 编写测试骨架**

```python
# -*- coding: utf-8 -*-
"""Test complete approval workflow for Applicant A"""
import pytest
from playwright.sync_api import Page, expect

class TestApplicantACompleteWorkflow:
    """申请人A完整审批流程: 步骤1→步骤7"""
    
    def test_applicant_a_login_and_check_stage(self, page):
        """测试申请人A登录并查看初始阶段"""
        # Login as applicant
        page.goto("http://127.0.0.1:5003/auth/login")
        page.fill('input[name="username"]', 'applicant')
        page.fill('input[name="password"]', '123456')
        page.click('button[type="submit"]')
        
        # Check initial stage
        page.goto("http://127.0.0.1:5003/applicant/progress")
        expect(page.locator('.progress-title')).to_be_visible()
```

**Step 2: 运行测试验证**

Run: `pytest tests/integration/test_workflow_applicant_a.py -v --headed`
Expected: PASS

**Step 3: 添加文档上传测试**

```python
def test_applicant_a_upload_document(self, logged_in_applicant):
    """测试申请人A上传文档"""
    page = logged_in_applicant
    page.goto("http://127.0.0.1:5003/applicant/documents")
    # ... upload logic
```

**Step 4: 提交代码**

```bash
git add tests/integration/test_workflow_applicant_a.py
git commit -m "test: add applicant A complete workflow test"
```

---

## Task 2: 场景2 - 申请人B跳步骤被驳回

**Files:**
- Create: `tests/integration/test_workflow_applicant_b.py`

(类似结构...)

---

## Task 3: 场景3 - 驳回再通过流程

**Files:**
- Create: `tests/integration/test_workflow_rejection.py`

(类似结构...)

---

## Task 4: 场景4 - 模板管理流程

**Files:**
- Create: `tests/integration/test_workflow_templates.py`

(类似结构...)

---

## Task 5: 场景5 - 管理员创建支部和用户

**Files:**
- Create: `tests/integration/test_workflow_admin_setup.py`

(类似结构...)

---

## 执行策略

1. **第一个任务**: 使用单个subagent完成场景1测试
2. **经验总结**: 完成后记录最佳实践
3. **并行执行**: 剩余4个场景使用并行subagents加速
