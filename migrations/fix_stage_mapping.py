"""Fix stage mapping for all step definitions and applications.

Correct mapping:
Stage 1: L1-L2 (入党申请阶段)
Stage 2: L3-L6 (入党积极分子阶段)
Stage 3: L7-L10 (发展对象阶段)
Stage 4: L11-L17 (预备党员接收阶段)
Stage 5: L18-L26 (预备党员考察和转正阶段)
"""
import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'SQLite_DB', 'cpc.db')

STAGE_MAP = {
    'L1': 1, 'L2': 1,
    'L3': 2, 'L4': 2, 'L5': 2, 'L6': 2,
    'L7': 3, 'L8': 3, 'L9': 3, 'L10': 3,
    'L11': 4, 'L12': 4, 'L13': 4, 'L14': 4, 'L15': 4, 'L16': 4, 'L17': 4,
    'L18': 5, 'L19': 5, 'L20': 5, 'L21': 5, 'L22': 5, 'L23': 5, 'L24': 5, 'L25': 5, 'L26': 5,
}

def fix_stages():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Update step_definitions
    for step_code, stage in STAGE_MAP.items():
        cursor.execute('UPDATE step_definitions SET stage = ? WHERE step_code = ?', (stage, step_code))

    # Update templates that have stage set
    for step_code, stage in STAGE_MAP.items():
        cursor.execute('UPDATE templates SET stage = ? WHERE step_code = ?', (stage, step_code))

    conn.commit()
    print(f"Updated stage mapping in database")

    # Verify
    cursor.execute('SELECT step_code, stage FROM step_definitions ORDER BY step_code')
    print("\nVerified step_definitions:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: stage {row[1]}")

    conn.close()
    print("\nDone.")

if __name__ == '__main__':
    fix_stages()
