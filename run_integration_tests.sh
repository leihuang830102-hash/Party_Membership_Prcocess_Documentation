#!/bin/bash
# ====================================
# 集成测试运行脚本 (Linux/Mac)
# ====================================

set -e

echo "===================================="
echo "入党文档管理系统 - 集成测试"
echo "===================================="
echo

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 Python3，请先安装 Python"
    exit 1
fi

# 检查是否在项目根目录
if [ ! -f "app/__init__.py" ]; then
    echo "错误: 请在项目根目录运行此脚本"
    exit 1
fi

# 解析参数
TEST_TYPE=${1:-all}

# 运行测试
case $TEST_TYPE in
    workflow)
        echo "运行完整工作流测试..."
        python3 tests/run_integration_tests.py --workflow
        ;;
    setup)
        echo "运行设置测试..."
        python3 tests/run_integration_tests.py --setup
        ;;
    smoke)
        echo "运行冒烟测试..."
        python3 tests/run_integration_tests.py --smoke
        ;;
    *)
        echo "运行所有集成测试..."
        python3 tests/run_integration_tests.py
        ;;
esac

echo
echo "测试完成!"
