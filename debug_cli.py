#!/usr/bin/env python3
"""
调试CLI问题的脚本
"""
import sys
import os

print("=== Ailabber CLI 调试信息 ===\n")

# 1. Python版本
print(f"Python版本: {sys.version}")
print(f"Python路径: {sys.executable}\n")

# 2. sys.argv
print(f"命令行参数: {sys.argv}\n")

# 3. sys.path
print("Python搜索路径:")
for p in sys.path[:5]:
    print(f"  - {p}")
print()

# 4. 尝试导入
try:
    from ailabber_cmd.cli import main, create_parser
    print("✅ 成功导入 ailabber_cmd.cli")
    print(f"   模块位置: {main.__code__.co_filename}\n")
    
    # 5. 测试parser
    parser = create_parser()
    print("✅ 成功创建parser\n")
    
    # 6. 显示可用命令
    print("可用的子命令:")
    if hasattr(parser, '_subparsers'):
        for action in parser._subparsers._actions:
            if hasattr(action, 'choices') and action.choices:
                for cmd_name in action.choices.keys():
                    print(f"  - {cmd_name}")
    print()
    
    # 7. 测试解析
    if len(sys.argv) > 1:
        print(f"尝试解析命令: {' '.join(sys.argv[1:])}")
        try:
            args = parser.parse_args(sys.argv[1:])
            print(f"✅ 解析成功!")
            print(f"   command: {args.command}")
            print(f"   args: {args}\n")
        except Exception as e:
            print(f"❌ 解析失败: {e}\n")
    
except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n=== 建议操作 ===")
print("1. 确保在项目根目录: cd /root/ailabber")
print("2. 重新安装: sudo pip3 install -e . --force-reinstall")
print("3. 测试: ailabber local-run python3 test.py")
