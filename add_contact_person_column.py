"""
手动添加 contact_person_id 列到 applications 表的迁移脚本
"""
import sqlite3
import os
import sys

# 获取数据库路径 - 使用实际存在的数据库位置
db_path = os.path.join(os.path.dirname(__file__), 'SQLite_DB', 'cpc.db')

print(f"Database path: {db_path}")
print(f"Database exists: {os.path.exists(db_path)}")

if not os.path.exists(db_path):
    print("Database file not found!")
    sys.exit(1)

# 连接数据库
conn = sqlite3.connect(db_path)

try:
    # 先检查列是否已存在
    cursor = conn.execute("PRAGMA table_info(applications)")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]
    print(f"Existing columns: {column_names}")

    if 'contact_person_id' in column_names:
        print("Column contact_person_id already exists, skipping migration.")
    else:
        # 添加 contact_person_id 列
        cursor = conn.execute('''
            ALTER TABLE applications
            ADD COLUMN contact_person_id INTEGER REFERENCES users(id)
        ''')

        print("Migration started: Adding contact_person_id column to applications table...")
        conn.commit()
        print("Migration completed successfully!")

except Exception as e:
    print(f"Migration failed: {e}")
    conn.rollback()
    sys.exit(1)

finally:
    conn.close()

print("Migration script finished.")
