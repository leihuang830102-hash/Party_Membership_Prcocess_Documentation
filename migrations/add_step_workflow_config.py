"""
Migration: Add submitter_role and approval_type columns to step_definitions table.

This migration adds two new columns to control step-level workflow:
  - submitter_role: who can submit/perform the step (applicant/secretary/admin)
  - approval_type: the approval flow for the step (two_level/one_level/none)

Matrix mapping for all 26 steps (from Matrix.xlsx):
  applicant / two_level:   L1, L7, L13, L21           (4 steps, 申请人提交，两级审批)
  secretary / one_level:   L2-L6, L8-L11, L14, L18-L20, L22-L24  (16 steps, 书记提交，一级审批)
  admin / none:            L12, L15-L17, L25, L26      (6 steps, 管理员自办)

Usage:
    python migrations/add_step_workflow_config.py          # 迁移默认数据库
    python migrations/add_step_workflow_config.py --db path/to/cpc.db  # 指定数据库

该脚本是幂等的（idempotent）：重复运行不会出错。
"""

import sqlite3
import os
import sys
import argparse

# ---------------------------------------------------------------------------
# 步骤工作流配置矩阵（来自 Matrix.xlsx）
# ---------------------------------------------------------------------------

# step_code -> (submitter_role, approval_type)
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
    # 第三阶段：确定发展对象
    'L12': ('admin', 'none'),             # 上级党委预审
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

# 完整的步骤定义数据:
# (step_code, stage, name, description, order_num, submitter_role, approval_type)
STEP_DEFINITIONS_FULL = [
    # 第一阶段：入党申请阶段 (L1-L2)
    ('L1', 1, '递交入党申请', '申请人向党组织递交书面入党申请', 1, 'applicant', 'two_level'),
    ('L2', 1, '党组织派人谈话', '党组织派人同入党申请人谈话', 2, 'secretary', 'one_level'),
    # 第二阶段：入党积极分子阶段 (L3-L6)
    ('L3', 2, '推荐入党积极分子', '推荐入党积极分子', 3, 'secretary', 'one_level'),
    ('L4', 2, '确定入党积极分子', '确定入党积极分子', 4, 'secretary', 'one_level'),
    ('L5', 2, '报上级党委备案', '报上级党委备案', 5, 'secretary', 'one_level'),
    ('L6', 2, '积极分子培养、教育、考察', '入党积极分子培养、教育、考察', 6, 'secretary', 'one_level'),
    # 第三阶段：发展对象阶段 (L7-L10)
    ('L7', 3, '填写《自传书》', '填写《自传书》', 7, 'applicant', 'two_level'),
    ('L8', 3, '推荐发展对象', '推荐发展对象', 8, 'secretary', 'one_level'),
    ('L9', 3, '发展对象确定并向上级党委备案', '发展对象确定并向上级党委备案', 9, 'secretary', 'one_level'),
    ('L10', 3, '发展对象培养、教育、考察', '发展对象培养、教育、考察', 10, 'secretary', 'one_level'),
    # 第四阶段：预备党员接收阶段 (L11-L17)
    ('L11', 4, '支委会审查', '支委会审查', 11, 'secretary', 'one_level'),
    ('L12', 4, '上级党委预审', '上级党委预审', 12, 'admin', 'none'),
    ('L13', 4, '填写《入党志愿书》', '填写《入党志愿书》', 13, 'applicant', 'two_level'),
    ('L14', 4, '接收预备党员支部大会', '接收预备党员支部大会', 14, 'secretary', 'one_level'),
    ('L15', 4, '上级党委派人谈话', '上级党委派人谈话', 15, 'admin', 'none'),
    ('L16', 4, '上级党委审批', '上级党委审批', 16, 'admin', 'none'),
    ('L17', 4, '逐级上报党委组织部门备案', '逐级上报党委组织部门备案', 17, 'admin', 'none'),
    # 第五阶段：预备党员考察和转正阶段 (L18-L26)
    ('L18', 5, '编入党支部、党小组', '编入党支部、党小组', 18, 'secretary', 'one_level'),
    ('L19', 5, '入党宣誓', '入党宣誓', 19, 'secretary', 'one_level'),
    ('L20', 5, '预备党员培养、教育、考察', '预备党员培养、教育、考察', 20, 'secretary', 'one_level'),
    ('L21', 5, '提出转正申请', '提出转正申请', 21, 'applicant', 'two_level'),
    ('L22', 5, '转正前考察', '转正前考察', 22, 'secretary', 'one_level'),
    ('L23', 5, '支委会审查', '支委会审查（转正）', 23, 'secretary', 'one_level'),
    ('L24', 5, '预备党员转正支部大会', '预备党员转正支部大会', 24, 'secretary', 'one_level'),
    ('L25', 5, '上级党委审批', '上级党委审批（转正）', 25, 'admin', 'none'),
    ('L26', 5, '材料归档', '材料归档', 26, 'admin', 'none'),
]


def get_default_db_path():
    """获取默认数据库路径（项目根目录下的 SQLite_DB/cpc.db）"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, 'SQLite_DB', 'cpc.db')


def check_columns_exist(cursor):
    """检查列是否已经存在（幂等性检查）"""
    cursor.execute("PRAGMA table_info(step_definitions)")
    columns = {row[1] for row in cursor.fetchall()}
    return 'submitter_role' in columns and 'approval_type' in columns


def add_columns(cursor):
    """添加 submitter_role 和 approval_type 列"""
    # 添加 submitter_role 列，默认值 'applicant'
    cursor.execute("""
        ALTER TABLE step_definitions
        ADD COLUMN submitter_role VARCHAR(20) DEFAULT 'applicant'
    """)

    # 添加 approval_type 列，默认值 'two_level'
    cursor.execute("""
        ALTER TABLE step_definitions
        ADD COLUMN approval_type VARCHAR(20) DEFAULT 'two_level'
    """)


def update_step_configs(cursor):
    """根据矩阵映射更新所有 26 个步骤的配置"""
    updated_count = 0
    for step_code, (submitter_role, approval_type) in STEP_WORKFLOW_CONFIG.items():
        cursor.execute("""
            UPDATE step_definitions
            SET submitter_role = ?, approval_type = ?
            WHERE step_code = ?
        """, (submitter_role, approval_type, step_code))

        if cursor.rowcount > 0:
            updated_count += 1

    return updated_count


def seed_step_definitions(cursor):
    """当 step_definitions 表为空时，插入所有 26 个步骤定义"""
    inserted_count = 0
    for step_code, stage, name, description, order_num, submitter_role, approval_type in STEP_DEFINITIONS_FULL:
        cursor.execute("""
            INSERT INTO step_definitions
                (step_code, stage, name, description, order_num, submitter_role, approval_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (step_code, stage, name, description, order_num, submitter_role, approval_type))
        inserted_count += 1

    return inserted_count


def get_existing_step_count(cursor):
    """获取 step_definitions 表中的记录数"""
    cursor.execute("SELECT COUNT(*) FROM step_definitions")
    return cursor.fetchone()[0]


def verify_migration(cursor):
    """验证迁移结果：确认所有步骤都已正确更新"""
    cursor.execute("""
        SELECT step_code, submitter_role, approval_type
        FROM step_definitions
        ORDER BY stage, order_num
    """)
    rows = cursor.fetchall()

    errors = []

    # 检查总数
    if len(rows) != 26:
        errors.append(f"Expected 26 steps, found {len(rows)}")

    # 检查每个步骤的配置
    for step_code, submitter_role, approval_type in rows:
        if step_code not in STEP_WORKFLOW_CONFIG:
            errors.append(f"Unknown step_code: {step_code}")
            continue

        expected_role, expected_approval = STEP_WORKFLOW_CONFIG[step_code]
        if submitter_role != expected_role:
            errors.append(
                f"Step {step_code}: submitter_role is '{submitter_role}', "
                f"expected '{expected_role}'"
            )
        if approval_type != expected_approval:
            errors.append(
                f"Step {step_code}: approval_type is '{approval_type}', "
                f"expected '{expected_approval}'"
            )

    # 检查没有 NULL 值
    cursor.execute("""
        SELECT step_code FROM step_definitions
        WHERE submitter_role IS NULL OR approval_type IS NULL
    """)
    null_rows = cursor.fetchall()
    for row in null_rows:
        errors.append(f"Step {row[0]} has NULL workflow config")

    return errors


def run_migration(db_path):
    """执行迁移"""
    print(f"[Migration] 数据库路径: {db_path}")

    if not os.path.exists(db_path):
        print(f"[ERROR] 数据库文件不存在: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Step 1: 检查列是否已存在（幂等性）
        if check_columns_exist(cursor):
            print("[Migration] 列已存在，跳过 ALTER TABLE")
        else:
            print("[Migration] 添加 submitter_role 和 approval_type 列...")
            add_columns(cursor)
            conn.commit()
            print("[Migration] 列添加完成")

        # Step 2: 检查表是否为空，如果是则插入种子数据
        existing_count = get_existing_step_count(cursor)
        if existing_count == 0:
            print("[Migration] step_definitions 表为空，插入 26 个步骤定义...")
            inserted = seed_step_definitions(cursor)
            conn.commit()
            print(f"[Migration] 已插入 {inserted} 个步骤定义")
        else:
            print(f"[Migration] step_definitions 表已有 {existing_count} 条记录")
            if existing_count != 26:
                print(f"[WARNING] 预期 26 条记录，实际 {existing_count} 条")

        # Step 3: 更新所有步骤的工作流配置（确保幂等）
        print("[Migration] 更新步骤的工作流配置...")
        updated_count = update_step_configs(cursor)
        conn.commit()
        print(f"[Migration] 已更新 {updated_count} 个步骤的配置")

        # Step 4: 验证
        print("[Migration] 验证迁移结果...")
        errors = verify_migration(cursor)

        if errors:
            print("[Migration] 验证失败:")
            for error in errors:
                print(f"  - {error}")
            return False
        else:
            print("[Migration] 验证通过: 所有 26 个步骤配置正确")

            # 打印配置摘要
            print("\n[Migration] 配置摘要:")
            print(f"  applicant / two_level: L1, L7, L13, L21 (4 steps)")
            print(f"  secretary / one_level: L2-L6, L8-L11, L14, L18-L20, L22-L24 (16 steps)")
            print(f"  admin / none: L12, L15-L17, L25, L26 (6 steps)")
            return True

    except Exception as e:
        print(f"[ERROR] 迁移失败: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Add submitter_role and approval_type to step_definitions'
    )
    parser.add_argument(
        '--db',
        default=None,
        help='Path to the SQLite database file (default: SQLite_DB/cpc.db)'
    )
    args = parser.parse_args()

    db_path = args.db or get_default_db_path()
    success = run_migration(db_path)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
