@echo off
chcp 65001 >nul
REM ====================================
REM 集成测试运行脚本 (Windows)
REM ====================================

echo ====================================
echo 入党文档管理系统 - 集成测试
echo ====================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python，请先安装 Python
    exit /b 1
)

REM 检查是否在项目根目录
if not exist "app\__init__.py" (
    echo 错误: 请在项目根目录运行此脚本
    exit /b 1
)

REM 解析参数
set TEST_TYPE=%1
if "%TEST_TYPE%"=="" set TEST_TYPE=all

REM 运行测试
if "%TEST_TYPE%"=="workflow" (
    echo 运行完整工作流测试...
    python tests/run_integration_tests.py --workflow
) else if "%TEST_TYPE%"=="setup" (
    echo 运行设置测试...
    python tests/run_integration_tests.py --setup
) else if "%TEST_TYPE%"=="smoke" (
    echo 运行冒烟测试...
    python tests/run_integration_tests.py --smoke
) else (
    echo 运行所有集成测试...
    python tests/run_integration_tests.py
)

echo.
echo 测试完成!
pause
