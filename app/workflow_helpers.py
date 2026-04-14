"""
工作流辅助函数模块 / Workflow Helper Functions Module

提供工作流相关的可复用工具函数，包括：
- 步骤配置查询
- 权限判断（谁可以提交/审批）
- 允许操作列表计算
- 步骤推进逻辑
- 模板查询
- 审批状态文本生成

These reusable helper functions handle workflow logic including:
step configuration lookup, permission checks, allowed-action computation,
step advancement, template retrieval, and human-readable status text.
"""

from flask import current_app
from app import db
from app.models import StepDefinition, StepRecord, Document, Template, Application


def get_step_config(step_code):
    """获取步骤的工作流配置 / Get StepDefinition with workflow config.

    根据步骤代码查询 StepDefinition 表，返回该步骤的完整配置对象，
    包含 submitter_role（提交者角色）和 approval_type（审批类型）等信息。

    Args:
        step_code: 步骤代码，例如 'L1', 'L2', 'A1' 等
                   Step code string, e.g. 'L1', 'L2', 'A1'

    Returns:
        StepDefinition 对象，如果 step_code 为空或不存在则返回 None
        StepDefinition object, or None if step_code is invalid or not found
    """
    if not step_code:
        return None
    return StepDefinition.query.filter_by(step_code=step_code).first()


def can_submit(user_role, step_code):
    """判断指定角色是否可以提交该步骤 / Check if user_role can submit for this step.

    权限规则：
    - applicant（申请人）：只能提交 submitter_role='applicant' 的步骤
    - secretary（书记）：只能提交 submitter_role='secretary' 的步骤
    - admin（管理员）：可以提交任何步骤（最高权限）
    - contact_person（入党联系人）：与 secretary 权限相同

    Permission rules:
    - applicant: can only submit steps where submitter_role='applicant'
    - secretary: can only submit steps where submitter_role='secretary'
    - admin: can submit any step (highest authority)
    - contact_person: same permissions as secretary

    Args:
        user_role: 用户角色字符串，如 'admin', 'secretary', 'applicant', 'contact_person'
                   User role string
        step_code: 步骤代码 / Step code string

    Returns:
        bool: 该角色是否可以提交此步骤，输入无效时返回 False
          Whether the role can submit this step; False for invalid inputs
    """
    # 输入校验：角色或步骤代码为空则无法提交
    if not user_role or not step_code:
        return False

    step_config = get_step_config(step_code)
    if not step_config:
        return False

    # 管理员拥有最高权限，可以提交任何步骤
    if user_role == 'admin':
        return True

    submitter_role = step_config.submitter_role

    # 申请人只能提交属于自己的步骤
    if user_role == 'applicant':
        return submitter_role == 'applicant'

    # 书记和入党联系人可以提交属于书记角色的步骤
    if user_role in ('secretary', 'contact_person'):
        return submitter_role == 'secretary'

    # 其他未知角色默认不可提交
    return False


def get_allowed_actions(step_code, user_role, application):
    """获取该角色在当前步骤下允许的操作列表 / Return list of allowed actions for this role at this step.

    根据 approval_type（审批类型）和 user_role（用户角色）的组合，
    返回该用户在此步骤可以执行的操作列表。

    可能的操作 / Possible actions:
    - 'submit': 提交/上传文档
    - 'approve': 审批通过
    - 'reject': 审批驳回
    - 'confirm': 确认完成（管理员直接操作）
    - 'view': 仅查看
    - 'download_template': 下载模板

    操作规则 / Action rules by approval_type:
    - two_level（两级审批）+ applicant 步骤:
        applicant  -> ['submit', 'download_template']
        secretary  -> ['approve', 'reject', 'download_template']
        admin      -> ['approve', 'reject', 'download_template']
                    （admin 仅在 secretary 审批通过后才能操作）
    - one_level（一级审批）+ secretary 步骤:
        secretary  -> ['submit', 'download_template']
        admin      -> ['approve', 'reject', 'download_template']
        applicant  -> ['view', 'download_template']
    - none（无需审批）+ admin 步骤:
        admin      -> ['submit', 'confirm', 'download_template']
        其他       -> ['view', 'download_template']

    Args:
        step_code: 步骤代码 / Step code string
        user_role: 用户角色 / User role string
        application: Application 对象，用于判断当前审批状态
                     Application object, used to determine current approval state

    Returns:
        list[str]: 允许的操作名称列表，输入无效时返回 ['view']
                   List of allowed action strings; defaults to ['view'] for invalid inputs
    """
    # 默认只读操作
    view_only = ['view', 'download_template']

    # 输入校验
    if not step_code or not user_role:
        return view_only

    step_config = get_step_config(step_code)
    if not step_config:
        return view_only

    approval_type = step_config.approval_type
    submitter_role = step_config.submitter_role

    # --- none 类型：管理员直接操作，无需审批 ---
    if approval_type == 'none':
        if user_role == 'admin':
            return ['submit', 'confirm', 'download_template']
        return view_only

    # --- two_level 类型：两级审批（书记 -> 管理员）---
    if approval_type == 'two_level':
        if submitter_role == 'applicant':
            if user_role == 'applicant':
                return ['submit', 'download_template']
            if user_role == 'secretary' or user_role == 'contact_person':
                return ['approve', 'reject', 'download_template']
            if user_role == 'admin':
                # 管理员在两级审批中，需要书记先审批通过后才能操作
                return ['approve', 'reject', 'download_template']
        # 如果 submitter_role 不是 applicant 但审批类型为 two_level，
        # 回退到基本权限判断
        if can_submit(user_role, step_code):
            return ['submit', 'download_template']
        return view_only

    # --- one_level 类型：一级审批（管理员直接审批）---
    if approval_type == 'one_level':
        if submitter_role == 'secretary':
            if user_role == 'secretary' or user_role == 'contact_person':
                return ['submit', 'download_template']
            if user_role == 'admin':
                return ['approve', 'reject', 'download_template']
            if user_role == 'applicant':
                return view_only
        # 如果 submitter_role 不是 secretary 但审批类型为 one_level，
        # 回退到基本权限判断
        if can_submit(user_role, step_code):
            return ['submit', 'download_template']
        return view_only

    # 未知审批类型，回退到只读
    return view_only


def advance_step(application, step_code):
    """推进申请到下一步骤 / Advance application to next step after completion.

    在当前步骤完成后，按 order_num 顺序查找下一个 StepDefinition，
    更新 Application 的 current_step 和 current_stage。
    如果没有下一步骤，则将申请状态标记为 'completed'（已完成）。

    After the current step is completed, find the next StepDefinition
    by order_num. Update application.current_step and current_stage.
    If no next step exists, mark application.status = 'completed'.

    Args:
        application: Application 对象，需要推进的申请记录
                     Application object to advance
        step_code: 当前刚完成的步骤代码
                   Step code of the step that was just completed

    Returns:
        StepDefinition: 下一步骤的配置对象，如果申请已全部完成则返回 None
                        Next step's StepDefinition, or None if application is completed
    """
    if not application or not step_code:
        return None

    current_config = get_step_config(step_code)
    if not current_config:
        return None

    # 按 order_num 查找下一个步骤（order_num 大于当前步骤的最小值）
    next_step = StepDefinition.query.filter(
        StepDefinition.order_num > current_config.order_num
    ).order_by(StepDefinition.order_num.asc()).first()

    if next_step:
        # 更新申请的当前步骤和阶段
        application.current_step = next_step.step_code
        application.current_stage = next_step.stage
        application.status = 'in_progress'
        db.session.commit()
        return next_step
    else:
        # 没有下一步骤，标记申请为已完成
        application.status = 'completed'
        db.session.commit()
        return None


def get_step_templates(step_code):
    """获取与步骤关联的所有模板 / Get all templates associated with a step.

    查询 Template 表中与指定 step_code 匹配且处于激活状态的模板列表，
    用于前端展示可下载的文档模板。

    Query the Template table for active templates matching the given step_code,
    used to display downloadable document templates in the frontend.

    Args:
        step_code: 步骤代码，例如 'L1', 'A1' 等
                   Step code string, e.g. 'L1', 'A1'

    Returns:
        list[Template]: 该步骤的模板对象列表，输入无效时返回空列表
                        List of Template objects for this step; empty list for invalid inputs
    """
    if not step_code:
        return []

    return Template.query.filter_by(
        step_code=step_code,
        is_active=True
    ).all()


def get_approval_status_text(step_code, step_record, document=None):
    """生成步骤的审批状态可读文本 / Return human-readable status text for a step.

    根据步骤配置（审批类型、提交者角色）、步骤记录状态和文档审批状态，
    生成面向用户的中文状态描述，用于在页面上显示当前步骤进展。

    Generate a Chinese status description based on the step's approval_type,
    submitter_role, step_record status, and document review_status.

    状态文本示例 / Status text examples:
    - '等待提交': 尚未有人提交 / pending, no one submitted yet
    - '等待书记审批': 两级审批，申请人已提交，等待书记审批 / two_level, waiting for secretary
    - '等待党委审批': 等待管理员审批（一级或两级第二阶段）/ waiting for admin
    - '书记已审批，等待党委': 书记已审批，两级审批的第二阶段 / secretary approved, two_level
    - '已完成': 步骤已完成 / completed
    - '已驳回': 步骤失败或文档被驳回 / failed/rejected
    - '等待党委操作': 无审批类型，等待管理员操作 / none type, waiting for admin

    Args:
        step_code: 步骤代码 / Step code string
        step_record: StepRecord 对象，可为 None（表示尚未创建记录）
                     StepRecord object, may be None (no record created yet)
        document: Document 对象，可选，用于判断文档级别的审批状态
                  Document object, optional, for document-level review status

    Returns:
        str: 中文状态描述文本
             Chinese status description string
    """
    # 获取步骤配置
    step_config = get_step_config(step_code)
    if not step_config:
        return '未知步骤'

    approval_type = step_config.approval_type
    submitter_role = step_config.submitter_role

    # --- 没有步骤记录：尚未提交 ---
    if not step_record:
        if approval_type == 'none':
            # 无审批类型，等待管理员操作
            return '等待党委操作'
        return '等待提交'

    record_status = step_record.status

    # --- 步骤已完成 ---
    if record_status == 'completed':
        return '已完成'

    # --- 步骤失败（整体被驳回） ---
    if record_status == 'failed':
        return '已驳回'

    # --- 书记已审批（两级审批中间状态） ---
    if record_status == 'secretary_approved':
        return '书记已审批，等待党委'

    # --- 记录状态为 pending，进一步判断 ---
    if record_status == 'pending':
        # 根据审批类型和提交者角色确定当前处于哪个审批阶段
        if approval_type == 'none':
            # 无审批类型，等待管理员直接操作
            return '等待党委操作'

        if approval_type == 'two_level':
            if submitter_role == 'applicant':
                # 两级审批 + 申请人提交：先判断文档审批状态
                if document:
                    doc_status = document.review_status
                    if doc_status == 'pending':
                        # 文档尚未被审批，等待书记审批
                        return '等待书记审批'
                    elif doc_status == 'secretary_approved':
                        # 书记已审批文档，等待管理员（党委）审批
                        return '等待党委审批'
                    elif doc_status == 'secretary_rejected':
                        # 书记已驳回文档
                        return '已驳回（书记驳回）'
                    elif doc_status == 'admin_approved':
                        # 管理员已审批通过
                        return '已完成'
                    elif doc_status == 'admin_rejected':
                        # 管理员已驳回
                        return '已驳回（党委驳回）'
                # 没有文档信息，默认等待书记审批
                return '等待书记审批'

        if approval_type == 'one_level':
            if submitter_role == 'secretary':
                # 一级审批 + 书记提交：直接等待管理员（党委）审批
                if document:
                    doc_status = document.review_status
                    if doc_status == 'pending':
                        return '等待党委审批'
                    elif doc_status == 'admin_approved':
                        return '已完成'
                    elif doc_status == 'admin_rejected':
                        return '已驳回（党委驳回）'
                return '等待党委审批'

    # 兜底：返回记录的原始状态
    return record_status or '未知状态'
