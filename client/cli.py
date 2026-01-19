#!/usr/bin/env python3
"""
ailabber CLI - 命令行客户端
用法: ailabber <command> [args]
"""
import os
import sys
import json
import requests
import tomllib
from pathlib import Path

from shared.config import LOCAL_PROXY_URL

current_dir = Path.cwd()
current_username = os.environ.get('USER')
# 全局用户信息
if current_username:
    print(f"当前用户: {current_username}")
else:
    print("ERROR: 无法获取当前用户信息")


# ============ 命令处理函数 ============

def cmd_whoami(args):
    """查看当前用户"""
    print(f"当前用户: {current_username}")
    return current_username


def cmd_submit(args) -> str:
    """提交任务到代理服务器
    
    用法:
        submit [remote|local] [task_config.toml]
    
    Args:
        args: 可选的目标(remote/local)和任务配置文件路径
    
    Returns:
        task_id: 提交的任务ID
    """
    # 解析参数
    target = "local"  # 默认提交到本地代理
    config_path = "./task_config.toml"
    
    if args:
        if args[0] in ["remote", "local"]:
            target = args[0]
            config_path = args[1] if len(args) > 1 else "./task_config.toml"
        else:
            config_path = args[0]
    
    # 读取任务配置
    try:
        with open(config_path, "rb") as f:
            task_config = tomllib.load(f)
    except FileNotFoundError:
        print(f"ERROR: 任务配置文件未找到: {config_path}")
        return None
    except tomllib.TOMLDecodeError as e:
        print(f"ERROR: 任务配置文件解析失败: {e}")
        return None
    
    # 验证必要的配置字段
    required_keys = {
        "resources": ["gpus", "cpus", "memory", "time_limit"],
        "environment": ["pyproject_toml", "uv_lock"],
        "files": ["upload", "ignore", "workdir"],
        "run": ["commands", "logs", "results"]
    }
    
    for section, keys in required_keys.items():
        if section not in task_config:
            print(f"ERROR: 配置文件缺少 [{section}] 部分")
            return None
        for key in keys:
            if key not in task_config[section]:
                print(f"ERROR: [{section}] 缺少 {key} 配置")
                return None
    
    # 提交任务到本地代理服务器
    try:
        resp = requests.post(f"{LOCAL_PROXY_URL}/api/submit", json={
            "username": current_username,
            "target": target,
            "pyproject_toml": task_config["environment"]["pyproject_toml"],
            "uv_lock": task_config["environment"]["uv_lock"],
            "extra_wheels": task_config["environment"].get("extra_wheels", []),
            "upload": str(Path(task_config["files"]["upload"]).resolve()),
            "ignore": [str(Path(ig).resolve()) for ig in task_config["files"]["ignore"]],
            "workdir": task_config["files"]["workdir"],
            "commands": task_config["run"]["commands"],
            "logs": task_config["run"]["logs"],
            "results": task_config["run"]["results"],
            "gpus": task_config["resources"]["gpus"],
            "cpus": task_config["resources"]["cpus"],
            "memory": task_config["resources"]["memory"],
            "time_limit": task_config["resources"]["time_limit"]  
        })
        
        resp.raise_for_status()  # 检查 HTTP 状态码
        data = resp.json()
        
        if "task_id" in data:
            task_id = data['task_id']
            print(f"SUCCESS: 任务已提交: {task_id}")
            return task_id
        else:
            print("ERROR: 任务提交失败")
            print(f"\t{data.get('message', data.get('error', '未知错误'))}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"ERROR: 无法连接到 {LOCAL_PROXY_URL}")
        print("  请确保本地代理服务器正在运行")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP 错误 {resp.status_code}")
        print(f"\t{resp.json().get('message', str(e))}")
        return None
    except Exception as e:
        print(f"ERROR: 提交任务失败: {e}")
        return None


def cmd_status(args):
    """查看任务状态
    
    用法:
        status <task_id>
    """
    if not args:
        print("ERROR: 缺少task_id参数")
        print(">>> hint: ailabber status <task_id> <<<".center(40))
        return
    
    task_id = args[0]
    
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
            print(f"状态:       {task['status']}")
            print(f"创建时间:   {task['created_at']}")
            if task.get('started_at'):
                print(f"开始时间:   {task['started_at']}")
            if task.get('completed_at'):
                print(f"完成时间:   {task['completed_at']}")
            if task.get('exit_code') is not None:
                print(f"退出码:     {task['exit_code']}")
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
    """列出我的任务
    
    默认全列出，可选按状态过滤

    用法:
        list [status]
    """
    status_filter = args[0] if args else None
    
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
        print(f"{'-'*80}")
        print(f"{'任务ID':<12} {'状态':<12} {'GPU':<4} {'CPU':<4} {'创建时间':<20}")
        print(f"{'-'*80}")
        
        for task in tasks:
            print(f"{task['task_id']:<12} {task['status']:<12} {task['gpus']:<4} {task['cpus']:<4} {task['created_at'][:19]:<20}")
        
        print(f"{'-'*80}\n")
        
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
    """下载任务输出（日志和结果）

    默认输出到当前目录
    
    用法:
        fetch <task_id> [output_dir]
    """
    if not args:
        print("ERROR: 缺少task_id参数")
        print(">>> hint: ailabber fetch <task_id> [output_dir] <<<".center(40))
        return
    

    task_id = args[0]
    output_dir = args[1] if len(args) > 1 else str(current_dir)
    
    try:
        resp = requests.get(
            f"{LOCAL_PROXY_URL}/api/fetch/{task_id}",
            params={"username": current_username},
            timeout=30  # 下载可能需要更长时间
        )
        resp.raise_for_status()
        
        # 保存文件
        output_path = Path(output_dir) / f"{task_id}_logs.zip"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'wb') as f:
            f.write(resp.content)
        
        print(f"SUCCESS: 任务输出已下载")
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
    """取消任务
    
    用法:
        cancel <task_id>
    """
    if not args:
        print("ERROR: 缺少task_id参数")
        print(">>> hint: ailabber cancel <task_id> <<<".center(40))
        return
    
    task_id = args[0]
    
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
        
        print(f"SUCCESS: {message}")
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


def cmd_help(args):
    """显示帮助"""
    help_text = """ailabber - LFS分布式任务提交系统

用法: ailabber <command> [options]

命令:
  whoami                                查看当前用户
  
  submit [remote|local] [task_config]   提交任务
                                        默认使用 ./task_config.toml
                                        默认提交到 local 代理
  
  status <task_id>                      查看任务状态
  
  list [status]                         列出我的任务
                                        可选 status: pending, running, completed, failed 等
  
  fetch <task_id>                       下载任务日志和结果
    [output_dir]                        可选指定输出目录，默认为当前目录
  
  cancel <task_id>                      取消任务
  
  help                                  显示帮助信息
"""
    print(help_text)

# ============ 命令路由 ============

COMMANDS = {
    "whoami": cmd_whoami,
    "submit": cmd_submit,
    "status": cmd_status,
    "list": cmd_list,
    "fetch": cmd_fetch,
    "cancel": cmd_cancel,
    "help": cmd_help,
}


def main():
    if len(sys.argv) < 2:
        cmd_help([])
        return
    
    command = sys.argv[1]
    args = sys.argv[2:]
    
    if command in COMMANDS:
        try:
            COMMANDS[command](args)
        except requests.exceptions.ConnectionError:
            print("ERROR: 无法连接到本地代理服务器")
            print(f"  请确保服务器运行在 {LOCAL_PROXY_URL}")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\n\n操作已取消")
            sys.exit(0)
        except Exception as e:
            print(f"ERROR: 命令执行失败: {e}")
            sys.exit(1)
    else:
        print(f"ERROR: 未知命令: {command}")
        print(f"运行 'ailabber help' 查看可用命令")
        sys.exit(1)


if __name__ == "__main__":
    main()
