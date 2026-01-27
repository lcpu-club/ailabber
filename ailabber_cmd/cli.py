#!/usr/bin/env python3
"""
ailabber - Distributed Slurm Task Scheduler

Lightweight task submission tool for local and remote Slurm clusters.
"""
import os
import sys
import argparse

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入所有命令
from aillabber_cmd.whoami import cmd_whoami
from aillabber_cmd.submit import cmd_submit
from aillabber_cmd.status import cmd_status
from aillabber_cmd.list import cmd_list
from aillabber_cmd.fetch import cmd_fetch
from aillabber_cmd.cancel import cmd_cancel
from aillabber_cmd.local_run import cmd_local_run

current_username = os.environ.get('USER', 'unknown')


# ============ Argparse 配置 ============

def create_parser():
    """Create argument parser"""
    parser = argparse.ArgumentParser(
        prog='ailabber',
        description='Distributed Slurm task scheduler',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="See USAGE.md for detailed examples and usage patterns."
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # whoami
    parser_whoami = subparsers.add_parser('whoami', help='Show current user')
    
    # submit
    parser_submit = subparsers.add_parser('submit', help='Submit task to proxy')
    parser_submit.add_argument(
        '-t', '--target',
        choices=['local', 'remote'],
        default='local',
        help='Target cluster (default: local)'
    )
    parser_submit.add_argument(
        'config',
        nargs='?',
        default='./task_config.toml',
        help='Task config file (default: ./task_config.toml)'
    )
    
    # local-run
    parser_local_run = subparsers.add_parser('local-run', help='Run command via Slurm (with logging)')
    parser_local_run.add_argument(
        '--gpu',
        type=int,
        default=0,
        help='Number of GPUs (default: 0)'
    )
    parser_local_run.add_argument(
        '--cpu',
        type=int,
        default=1,
        help='Number of CPUs (default: 1)'
    )
    parser_local_run.add_argument(
        '--memory',
        default='4G',
        help='Memory size (default: 4G)'
    )
    parser_local_run.add_argument(
        '--time',
        default='1:00:00',
        help='Time limit (default: 1:00:00)'
    )
    parser_local_run.add_argument(
        '--workdir',
        default='.',
        help='Working directory (default: .)'
    )
    parser_local_run.add_argument(
        'command',
        nargs='+',
        help='Command and arguments to execute'
    )
    
    # status
    parser_status = subparsers.add_parser('status', help='Check task status')
    parser_status.add_argument('task_id', help='Task ID')
    
    # list
    parser_list = subparsers.add_parser('list', help='List tasks')
    parser_list.add_argument(
        '-s', '--status',
        help='Filter by status (pending/running/completed/failed/canceled)'
    )
    
    # fetch
    parser_fetch = subparsers.add_parser('fetch', help='Download task results')
    parser_fetch.add_argument('task_id', help='Task ID')
    parser_fetch.add_argument(
        '-o', '--output-dir',
        help='Output directory (default: current directory)'
    )
    
    # cancel
    parser_cancel = subparsers.add_parser('cancel', help='Cancel task')
    parser_cancel.add_argument('task_id', help='Task ID')
    
    return parser


# ============ 主入口 ============

def main():
    """Main entry point"""
    parser = create_parser()
    
    # 如果没有参数，显示帮助
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    
    args = parser.parse_args()
    
    # 显示用户信息（除了 whoami 命令）
    if args.command and args.command != 'whoami' and current_username != 'unknown':
        print(f"[{current_username}]")
    
    # 路由到对应的命令处理函数
    if args.command == 'whoami':
        cmd_whoami(args)
    elif args.command == 'submit':
        cmd_submit(args)
    elif args.command == 'local-run':
        cmd_local_run(args)
    elif args.command == 'status':
        cmd_status(args)
    elif args.command == 'list':
        cmd_list(args)
    elif args.command == 'fetch':
        cmd_fetch(args)
    elif args.command == 'cancel':
        cmd_cancel(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperation canceled")
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
