#!/usr/bin/env python3
"""
ailabber - 分布式 Slurm 任务调度系统

轻量级的任务提交工具，支持本地和远程 Slurm 集群。
"""
import os
import sys
import json
import argparse
import requests
import tomllib
from pathlib import Path

from shared.config import LOCAL_PROXY_URL

current_dir = Path.cwd()
current_username = os.environ.get('USER', 'unknown')


# ============ 命令处理函数 ============

def cmd_whoami(args):
    """查看当前用户"""
    print(f"当前用户: {current_username}")
    return current_username


def cmd_submit(args) -> str:
    """提交任务到代理服务器"""
    target = args.target
    config_path = args.config
    
    # 读取任务配置
    try:
        with open(config_path, "rb") as f:
            task_config = tomllib.load(f)
    except FileNotFoundError:
        print(f"ERROR: 任务配置文件未找到: {config_path}")
        return ""
    except tomllib.TOMLDecodeError as e:
        print(f"ERROR: 任务配置文件解析失败: {e}")
        return ""
    
    # 验证必要的配置字段
    required_sections = ["resources", "run"]
    for section in required_sections:
        if section not in task_config:
            print(f"ERROR: 配置文件缺少 [{section}] 部分")
            return ""
    
    if "commands" not in task_config["run"]:
        print("ERROR: [run] 缺少 commands 配置")
        return ""
    
    # 提交任务到本地代理服务器
    try:
        submit_data = {
            "username": current_username,
            "target": target,
            "upload": str(Path(task_config.get("submit", {}).get("upload", ".")).resolve()),
            "ignore": task_config.get("submit", {}).get("ignore", []),
            "workdir": task_config.get("run", {}).get("workdir", "."),
            "commands": task_config["run"]["commands"],
            "logs": task_config.get("fetch", {}).get("logs", []),
            "results": task_config.get("fetch", {}).get("results", []),
            "gpus": task_config["resources"].get("gpus", 0),
            "cpus": task_config["resources"].get("cpus", 1),
            "memory": task_config["resources"].get("memory", "4G"),
            "time_limit": task_config["resources"].get("time_limit", "1:00:00")
        }
        
        resp = requests.post(f"{LOCAL_PROXY_URL}/api/submit", json=submit_data)
        
        resp.raise_for_status()  # 检查 HTTP 状态码
        data = resp.json()
        
        if "task_id" in data:
            task_id = data['task_id']
            print(f"SUCCESS: 任务已提交: {task_id}")
            return task_id
        else:
            print("ERROR: 任务提交失败")
            print(f"\t{data.get('message', data.get('error', '未知错误'))}")
            return ""
            
    except requests.exceptions.ConnectionError:
        print(f"ERROR: 无法连接到 {LOCAL_PROXY_URL}")
        print("  请确保本地代理服务器正在运行")
        return ""
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP 错误 {resp.status_code}")
        print(f"\t{resp.json().get('message', str(e))}")
        return ""
    except KeyError as e:
        print(f"ERROR: 缺少关键Config: {e}")
        return ""
    except Exception as e:
        print(f"ERROR: 提交任务失败: {e}")
        return ""


def cmd_status(args):
    """查看任务状态"""
    task_id = args.task_id
    
    try:
        resp = requests.get(
            f"{LOCAL_PROXY_URL}/api/status/{task_id}",
            params={"username": current_username},
            timeout=5
        )
        resp.raise_for_status()
        
        data = resp.json()
        if "task" in data:
            task = data["task"]
            print(f"\n{'='*50}")
            print(f"任务ID:     {task['task_id']}")
            print(f"用户:       {task['username']}")
            print(f"目标:       {task.get('target', 'N/A')}")
            print(f"状态:       {task['status']}")
            print(f"创建时间:   {task['created_at']}")
            if task.get('started_at'):
                print(f"开始时间:   {task['started_at']}")
            if task.get('completed_at'):
                print(f"完成时间:   {task['completed_at']}")
            if task.get('exit_code') is not None:
                print(f"退出码:     {task['exit_code']}")
            if task.get('slurm_job_id'):
                print(f"Slurm ID:   {task['slurm_job_id']}")
            print(f"{'='*50}\n")
        else:
            print(f"ERROR: 查询任务状态失败")
            print(f"\t{data.get('message', data.get('error', '未知错误'))}")
            
    except requests.exceptions.ConnectionError:
        print(f"ERROR: 无法连接到 {LOCAL_PROXY_URL}")
    except requests.exceptions.Timeout:
        print("ERROR: 请求超时")
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP 错误 {resp.status_code}")
        print(f"\t{resp.json().get('message', str(e))}")
    except Exception as e:
        print(f"ERROR: 查询任务状态失败: {e}")


def cmd_list(args):
    """列出任务"""
    status_filter = args.status if hasattr(args, 'status') else None
    
    try:
        params = {"username": current_username}
        if status_filter:
            params["status"] = status_filter
        
        resp = requests.get(
            f"{LOCAL_PROXY_URL}/api/tasks",
            params=params,
            timeout=5
        )
        resp.raise_for_status()
        
        data = resp.json()
        tasks = data.get("tasks", [])
        
        if not tasks:
            print(f"\n用户 {current_username} 暂无任务")
            return
        
        print(f"\n{current_username} 的任务列表 ({len(tasks)} 个):")
        print(f"{'-'*90}")
        print(f"{'任务ID':<12} {'目标':<8} {'状态':<12} {'GPU':<4} {'CPU':<4} {'创建时间':<20}")
        print(f"{'-'*90}")
        
        for task in tasks:
            target = task.get('target', 'N/A')
            print(f"{task['task_id']:<12} {target:<8} {task['status']:<12} {task['gpus']:<4} {task['cpus']:<4} {task['created_at'][:19]:<20}")
        
        print(f"{'-'*90}\n")
        
    except requests.exceptions.ConnectionError:
        print(f"ERROR: 无法连接到 {LOCAL_PROXY_URL}")
    except requests.exceptions.Timeout:
        print("ERROR: 请求超时")
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP 错误 {resp.status_code}")
        print(f"\t{resp.json().get('message', str(e))}")
    except Exception as e:
        print(f"ERROR: 列出任务失败: {e}")


def cmd_fetch(args):
    """下载任务输出"""
    task_id = args.task_id
    output_dir = args.output_dir if hasattr(args, 'output_dir') and args.output_dir else str(current_dir)
    
    try:
        resp = requests.get(
            f"{LOCAL_PROXY_URL}/api/fetch/{task_id}",
            params={"username": current_username},
            timeout=30
        )
        resp.raise_for_status()
        
        # 保存文件
        output_path = Path(output_dir) / f"{task_id}_logs.zip"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'wb') as f:
            f.write(resp.content)
        
        print(f"✓ 任务输出已下载")
        print(f"  位置: {output_path}")
        print(f"  大小: {output_path.stat().st_size / 1024:.2f} KB")
        
    except requests.exceptions.ConnectionError:
        print(f"ERROR: 无法连接到 {LOCAL_PROXY_URL}")
    except requests.exceptions.Timeout:
        print("ERROR: 下载超时，请稍后重试")
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP 错误 {resp.status_code}")
        print(f"\t{resp.json().get('message', str(e))}")
    except Exception as e:
        print(f"ERROR: 下载任务输出失败: {e}")


def cmd_cancel(args):
    """取消任务"""
    task_id = args.task_id
    
    try:
        resp = requests.post(
            f"{LOCAL_PROXY_URL}/api/cancel/{task_id}",
            params={"username": current_username},
            timeout=5
        )
        resp.raise_for_status()
        
        data = resp.json()
        status = data.get("status", "unknown")
        message = data.get("message", "操作完成")
        
        print(f"✓ {message}")
        print(f"  新状态: {status}")
        
    except requests.exceptions.ConnectionError:
        print(f"ERROR: 无法连接到 {LOCAL_PROXY_URL}")
    except requests.exceptions.Timeout:
        print("ERROR: 请求超时")
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP 错误 {resp.status_code}")
        try:
            data = resp.json()
            print(f"  {data.get('message', str(e))}")
        except:
            print(f"  {e}")
    except Exception as e:
        print(f"ERROR: 取消任务失败: {e}")


def cmd_run(args):
    """直接运行本地slurm，不经过代理（类似uv run）"""
    config_path = args.config
    
    # 读取配置
    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
    except Exception as e:
        print(f"ERROR: 读取配置失败: {e}")
        return
    
    # 导入slurm工具
    try:
        from utils.slurm import generate_slurm_script, submit_slurm_job
        import shortuuid
        import uuid
    except ImportError as e:
        print(f"ERROR: 导入模块失败: {e}")
        print("请确保在项目根目录运行此命令")
        return
    
    # 生成任务ID
    task_id = str(shortuuid.encode(uuid.uuid4()))
    
    # 解析配置
    workdir = Path(config.get("run", {}).get("workdir", ".")).resolve()
    commands = config.get("run", {}).get("commands", [])
    gpus = config.get("resources", {}).get("gpus", 0)
    cpus = config.get("resources", {}).get("cpus", 1)
    memory = config.get("resources", {}).get("memory", "4G")
    time_limit = config.get("resources", {}).get("time_limit", "1:00:00")
    
    # 创建slurm输出目录
    slurm_dir = workdir / ".slurm"
    slurm_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = str(slurm_dir / f"{task_id}.out")
    error_file = str(slurm_dir / f"{task_id}.err")
    script_file = str(slurm_dir / f"{task_id}.sh")
    
    # 生成slurm脚本
    script_content = generate_slurm_script(
        task_id=task_id,
        username=current_username,
        workdir=str(workdir),
        commands=commands,
        gpus=gpus,
        cpus=cpus,
        memory=memory,
        time_limit=time_limit,
        output_file=output_file,
        error_file=error_file
    )
    
    # 写入脚本
    with open(script_file, 'w') as f:
        f.write(script_content)
    
    # 提交到slurm
    success, result, stdout = submit_slurm_job(script_file)
    
    if success:
        print(f"✓ Slurm 作业已提交")
        print(f"  任务ID:      {task_id}")
        print(f"  Slurm ID:    {result}")
        print(f"  输出日志:    {output_file}")
        print(f"  错误日志:    {error_file}")
    else:
        print(f"ERROR: 提交失败")
        print(f"  {result}")


# ============ Argparse 配置 ============

def create_parser():
    """创建参数解析器"""
    parser = argparse.ArgumentParser(
        prog='ailabber',
        description='分布式 Slurm 任务调度系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  ailabber submit -t remote task.toml    提交到远程集群
  ailabber submit -t local task.toml     提交到本地集群（通过代理）
  ailabber run task.toml                 直接运行本地 slurm（不经过代理）
  ailabber status abc123                 查看任务状态
  ailabber list -s running               列出运行中的任务
  ailabber fetch abc123 -o ./results     下载任务结果

更多帮助: https://github.com/your-repo/ailabber
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # whoami
    parser_whoami = subparsers.add_parser('whoami', help='查看当前用户')
    
    # submit
    parser_submit = subparsers.add_parser('submit', help='提交任务到代理')
    parser_submit.add_argument(
        '-t', '--target',
        choices=['local', 'remote'],
        default='local',
        help='目标集群 (默认: local)'
    )
    parser_submit.add_argument(
        'config',
        nargs='?',
        default='./task_config.toml',
        help='任务配置文件 (默认: ./task_config.toml)'
    )
    
    # run
    parser_run = subparsers.add_parser('run', help='直接运行本地 slurm（不经过代理）')
    parser_run.add_argument('config', help='任务配置文件')
    
    # status
    parser_status = subparsers.add_parser('status', help='查看任务状态')
    parser_status.add_argument('task_id', help='任务ID')
    
    # list
    parser_list = subparsers.add_parser('list', help='列出任务')
    parser_list.add_argument(
        '-s', '--status',
        help='按状态过滤 (pending/running/completed/failed/canceled)'
    )
    
    # fetch
    parser_fetch = subparsers.add_parser('fetch', help='下载任务结果')
    parser_fetch.add_argument('task_id', help='任务ID')
    parser_fetch.add_argument(
        '-o', '--output-dir',
        help='输出目录 (默认: 当前目录)'
    )
    
    # cancel
    parser_cancel = subparsers.add_parser('cancel', help='取消任务')
    parser_cancel.add_argument('task_id', help='任务ID')
    
    return parser


# ============ 主入口 ============

def main():
    """主函数"""
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
    elif args.command == 'run':
        cmd_run(args)
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
        print("\n\n操作已取消")
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
