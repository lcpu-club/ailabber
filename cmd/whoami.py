"""whoami 命令 - 查看当前用户"""
import os

current_username = os.environ.get('USER', 'unknown')


def cmd_whoami(args):
    """查看当前用户"""
    print(f"当前用户: {current_username}")
    return current_username
