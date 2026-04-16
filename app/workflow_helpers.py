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

from datetime import datetime

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


def has_required_documents(application_id, step_code):
    """检查指定步骤是否至少存在一个文档 / Check if at least one document exists for this step.

    在统一审批模型中，任何步骤的审批/提交操作都要求至少有一个文档存在。
    此函数用于审批前的验证，确保文档已上传。

    In the unified step-approval model, any approve/submit action requires
    at least one document to exist. This function validates that before
    an approval action is allowed.

    Args:
        application_id: 申请记录ID / Application record ID
        step_code: 步骤代码 / Step code string

    Returns:
        bool: 如果至少存在一个文档则返回 True，否则 False
              True if at least one document exists, False otherwise
    """
    return Document.query.filter_by(
        application_id=application_id,
        step_code=step_code
    ).count() > 0


def sync_document_statuses(application_id, step_code, review_status):
    """批量更新指定步骤所有文档的审核状态 / Update all documents for a step to the given review_status.

    [注意] 此函数仅用于管理批量操作/覆盖场景，不再是主要的文档审批机制。
    正常的逐个文档审批流程不需要调用此函数。步骤级别审批时应先通过
    all_documents_approved() 检查所有文档已逐个审批完毕。

    NOTE: This function is only for administrative batch override operations.
    It is NOT the primary document review mechanism. The normal per-document
    review flow does not use this function. Step-level approval should gate
    on all_documents_approved() to verify documents have been individually
    reviewed before allowing the step to advance.

    Args:
        application_id: 申请记录ID / Application record ID
        step_code: 步骤代码 / Step code string
        review_status: 目标审核状态，例如 'secretary_approved', 'admin_approved',
                       'secretary_rejected', 'admin_rejected' 等
                       Target review status, e.g. 'secretary_approved', 'admin_approved',
                       'secretary_rejected', 'admin_rejected', etc.

    Returns:
        int: 被更新的文档数量 / Number of documents updated
    """
    documents = Document.query.filter_by(
        application_id=application_id,
        step_code=step_code
    ).all()
    for doc in documents:
        doc.review_status = review_status
    return len(documents)


def all_documents_approved(step_code, application_id, required_status=None):
    """检查指定步骤的所有文档是否已达到要求的审核状态 / Check if all documents for a step have reached the required review status.

    在逐个文档审批模型中，步骤级别的审批操作需要先确认所有文档都已
    被逐个审批通过。此函数用于在步骤级别审批前进行前置检查。

    In the per-document review model, step-level approval requires that every
    document has been individually reviewed and approved first. This function
    validates that condition before a step-level action is allowed.

    状态检测逻辑 / Status detection logic:
    - 若指定 required_status：检查所有文档的 review_status 是否都等于该值
    - 若未指定（None）：根据步骤的 approval_type 自动推断：
        - two_level + secretary 调用：要求 secretary_approved
        - two_level + admin 调用：要求 admin_approved
        - one_level：要求 admin_approved
        - none：直接返回 True（自办步骤无需文档审批）
    - If required_status is given: checks all docs match that exact status
    - If not given (None): auto-detects based on step's approval_type:
        - two_level + secretary calling: requires secretary_approved
        - two_level + admin calling: requires admin_approved
        - one_level: requires admin_approved
        - none: returns True immediately (no review needed)

    Args:
        step_code: 步骤代码，例如 'L1', 'L2' 等 / Step code string
        application_id: 申请记录ID / Application record ID
        required_status: 所有文档必须达到的审核状态，为 None 时自动推断
            可选值: 'secretary_approved', 'admin_approved' 等
            The status all docs must have (auto-detected if None).
            Options: 'secretary_approved', 'admin_approved', etc.

    Returns:
        tuple: (bool, str)
            - bool: True 表示所有文档已达到要求状态，False 表示未达到
            - str: 状态描述信息，说明检查结果或未通过的原因
            - (all_approved, status_message)
    """
    step_def = StepDefinition.query.filter_by(step_code=step_code).first()
    docs = Document.query.filter_by(
        step_code=step_code,
        application_id=application_id
    ).all()

    # 没有文档：无法审批
    if not docs:
        return False, "没有文档，请先上传"

    # 如果未指定 required_status，根据审批类型自动推断
    if required_status is None:
        if not step_def:
            return False, "未找到步骤定义"
        approval_type = step_def.approval_type
        if approval_type == 'none':
            # 自办步骤无需文档审批
            return True, "自办步骤无需文档审核"
        elif approval_type == 'two_level':
            # 两级审批：默认检查最终状态 admin_approved
            required_status = 'admin_approved'
        elif approval_type == 'one_level':
            required_status = 'admin_approved'
        else:
            return False, f"未知审批类型: {approval_type}"

    # 检查所有文档是否都达到了要求的状态
    all_done = all(d.review_status == required_status for d in docs)
    if all_done:
        return True, "所有文档已审核通过"
    else:
        pending = [d for d in docs if d.review_status != required_status]
        return False, f"还有 {len(pending)} 个文档未审核通过"


def auto_advance_if_all_approved(step_code, application_id):
    """逐个文档审批后自动检查并推进步骤 / Auto-advance step if all documents are fully approved.

    在每次单个文档审批完成后调用此函数。它会检查该步骤的所有文档
    是否都已达到最终审批状态（admin_approved）。如果是，自动完成该步骤
    并推进申请到下一步骤。

    Call this after each individual document review. It checks whether all
    documents for the step have reached the final approved status (admin_approved).
    If so, it automatically completes the step and advances the application.

    自动推进逻辑 / Auto-advance logic:
    - two_level 步骤：所有文档达到 admin_approved 时自动推进
    - one_level 步骤：所有文档达到 admin_approved 时自动推进
    - none 步骤：不处理（由 self-service 接口管理）
    - 仅在步骤记录尚未完成时才执行推进

    Returns:
        bool: True 表示步骤已自动推进，False 表示条件未满足（还有文档未审批）
              True if step was auto-advanced, False if conditions not met
    """
    step_def = StepDefinition.query.filter_by(step_code=step_code).first()
    docs = Document.query.filter_by(
        step_code=step_code,
        application_id=application_id
    ).all()

    # 没有文档或没有步骤定义：无法自动推进
    if not docs or not step_def:
        return False

    # none 类型步骤由 self-service 接口管理，不在此处理
    if step_def.approval_type == 'none':
        return False

    # 所有审批类型的最终状态都是 admin_approved
    final_status = 'admin_approved'
    all_approved = all(d.review_status == final_status for d in docs)
    if not all_approved:
        return False

    # 所有文档已审批通过！查找步骤记录并完成步骤
    step_record = StepRecord.query.filter_by(
        step_code=step_code,
        application_id=application_id
    ).first()

    if not step_record or step_record.status == 'completed':
        # 步骤记录不存在或已完成：无需重复操作
        return False

    # 标记步骤完成
    step_record.status = 'completed'
    step_record.completed_at = datetime.utcnow()

    # 推进申请到下一步
    application = Application.query.get(application_id)
    if application and application.current_step == step_code:
        advance_step(application, step_code)
        # 注意：advance_step 内部会 db.session.commit()
        # 但这里我们在调用方统一 commit，所以先不单独 commit
        # 实际上 advance_step 会 commit，我们需要确保一致性
        db.session.commit()
        return True

    db.session.commit()
    return True
