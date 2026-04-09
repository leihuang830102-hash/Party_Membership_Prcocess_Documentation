# -*- coding: utf-8 -*-
"""
集成测试运行脚本
运行所有业务流程集成测试

使用方法:
    python tests/run_integration_tests.py              # 运行所有集成测试
    python tests/run_integration_tests.py --workflow   # 只运行完整工作流测试
    python tests/run_integration_tests.py --setup      # 只运行设置测试
    python tests/run_integration_tests.py --smoke      # 快速冒烟测试
"""
import subprocess
import sys
import os
import time
import requests
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://127.0.0.1:5003"

def check_server():
    """检查服务器是否运行"""
    try:
        response = requests.get(f"{BASE_URL}/", timeout=2)
        return response.status_code == 200
    except:
        return False

def run_tests(test_paths, extra_args=None):
    """运行指定的测试"""
    cmd = [sys.executable, "-m", "pytest"] + test_paths
    if extra_args:
        cmd.extend(extra_args)

    print(f"\n{'='*60}")
    print(f"运行测试: {' '.join(test_paths)}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    start_time = time.time()
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    elapsed = time.time() - start_time

    print(f"\n测试耗时: {elapsed:.2f} 秒")
    return result.returncode

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='运行集成测试')
    parser.add_argument('--workflow', action='store_true', help='只运行完整工作流测试')
    parser.add_argument('--setup', action='store_true', help='只运行设置测试')
    parser.add_argument('--smoke', action='store_true', help='快速冒烟测试')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    parser.add_argument('--headless', action='store_true', default=True, help='无头模式运行浏览器')
    parser.add_argument('--html', type=str, help='生成HTML报告')

    args = parser.parse_args()

    # 检查服务器
    print(f"检查服务器状态: {BASE_URL}")
    if not check_server():
        print("警告: 服务器未运行，某些测试可能会失败")
        print("请先启动服务器: python run.py")
        print()
    else:
        print("服务器运行中 [OK]")
        print()

    # 构建额外参数
    extra_args = []
    if args.verbose:
        extra_args.append('-v')
    if args.html:
        extra_args.extend(['--html', args.html, '--self-contained-html'])

    # 根据参数选择测试
    if args.workflow:
        # 只运行完整工作流测试
        test_paths = ['tests/integration/test_full_workflow.py']
        return run_tests(test_paths, extra_args)

    elif args.setup:
        # 只运行设置测试
        test_paths = [
            'tests/integration/test_full_workflow.py::TestSetupData',
        ]
        return run_tests(test_paths, extra_args)

    elif args.smoke:
        # 快速冒烟测试 - 只测试基本功能
        test_paths = [
            'tests/integration/test_login.py',
            'tests/integration/test_full_workflow.py::TestUserAuthentication',
        ]
        return run_tests(test_paths, extra_args)

    else:
        # 运行所有集成测试
        print("="*60)
        print("运行完整集成测试套件")
        print("="*60)

        all_test_paths = [
            # ========================
            # 基础登录测试
            # ========================
            'tests/integration/test_login.py',

            # ========================
            # 管理员功能测试
            # ========================
            'tests/integration/test_admin_template_upload.py',

            # ========================
            # 申请人功能测试
            # ========================
            'tests/integration/test_applicant_document_upload.py',

            # ========================
            # 书记审批功能测试
            # ========================
            'tests/integration/test_secretary_approval.py',

            # ========================
            # 工作流测试
            # ========================
            'tests/integration/test_full_workflow.py',

            # ========================
            # 驳回重提流程测试（待实现）
            # ========================
            # 'tests/integration/test_rejection_flow.py',
        ]

        total_start = time.time()
        results = {}

        for path in all_test_paths:
            if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), path)):
                returncode = run_tests([path], extra_args)
                results[path] = '[PASS] 通过' if returncode == 0 else '[FAIL] 失败'
            else:
                results[path] = '- 跳过 (文件不存在)'

        total_elapsed = time.time() - total_start

        # 打印汇总
        print("\n" + "="*60)
        print("测试汇总")
        print("="*60)

        for path, status in results.items():
            test_name = os.path.basename(path)
            print(f"  {status}  {test_name}")

        passed = sum(1 for s in results.values() if '通过' in s)
        failed = sum(1 for s in results.values() if '失败' in s)
        skipped = sum(1 for s in results.values() if '跳过' in s)

        print(f"\n总计: {passed} 通过, {failed} 失败, {skipped} 跳过")
        print(f"总耗时: {total_elapsed:.2f} 秒")
        print("="*60)

        return 1 if failed > 0 else 0

if __name__ == '__main__':
    sys.exit(main())
