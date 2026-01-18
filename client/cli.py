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
    
    如果不指定 task_config.toml 路径，则默认使用当前目录下的 task_config.toml
    
    Args:
        args: 任务配置文件路径，默认为 None
    
    Returns:
        task_id: 提交的任务ID
    """
    if not args:
        task_config_toml_path = "./task_config.toml"
    else:
        task_config_toml_path = args[0]
    # 读取任务配置
    try:
        with open(task_config_toml_path, "rb") as f:
            task_config = tomllib.load(f) # return dict
    except FileNotFoundError:
        print(f"ERROR: 任务配置文件未找到: {task_config_toml_path}")
        return None
    except tomllib.TOMLDecodeError as e:
        print(f"ERROR: 任务配置文件解析失败: {e}")
        return None
    # 将 uploads 路径转化为绝对路径
    uploads = task_config.get("uploads", [])
    uploads_abs = str(Path().resolve())
    
    try:
        resp = requests.post(f"{LOCAL_PROXY_URL}/api/submit", json={
            "username": current_username,
            "pyproject_toml": task_config["environment"]["pyproject_toml"],
            "uv_lock": task_config["environment"]["uv_lock"],
            "extra_wheels": task_config["environment"]["extra_wheels"],
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
    except Exception as e:
        print(f"ERROR: 提交任务失败:\n{e}")
        return None
    data = resp.json()
    if "task_id" in data:
        print(f"SUCCESS: 任务已提交: {data['task_id']}")
    else:
        print("ERROR: 任务提交失败")
        print(data.get("message", None))


def cmd_status(args):
    """查看任务状态"""
    if not args:
        print("ERROR: 缺少task_id参数")
        print(">>> hint: ailabber status <task_id> <<<".center(40))
        return
    task_id = args[0]
    resp = requests.get(f"{LOCAL_PROXY_URL}/api/status/{task_id}", params={"username": current_username})
    data = resp.json()
    if "task" in data:
        task = data["task"]
        print(f"任务ID: {task['task_id']}")
        print(f"用户: {task['username']}")
        print(f"状态: {task['status']}")
        print(f"创建时间: {task['created_at']}")
    else:
        print("ERROR: 查询任务状态失败")
        print(data.get("message", None))


def cmd_list(args):
    """列出我的任务"""
    resp = requests.get(f"{LOCAL_PROXY_URL}/api/tasks", params={"username": current_username})
    data = resp.json()
    
    tasks = data.get("tasks", [])
    if not tasks:
        print(f"{current_username}:")
        print("\t无任务记录")
        return
    
    print(f"{'任务ID':<12} {'状态':<12} {'创建时间'}")
    print("-" * 80)
    for task in tasks:
        print(f"{task['task_id']:<12} {task['status']:<12} {task['created_at'][:19]}")


def cmd_fetch(args):
    """下载任务输出（日志和结果）"""
    if not args:
        print("ERROR: 缺少task_id参数")
        print(">>> hint: ailabber fetch <task_id> <<<".center(40))
        return
    task_id = args[0]
    resp = requests.get(f"{LOCAL_PROXY_URL}/api/logs/{task_id}", params={"username": current_username})
    # TODO:格式化日志文件名称并下载日志
    pass
    print(f"SUCCESS: 任务输出已下载到{str(current_dir)}/{task_id}_logs.zip")


def cmd_cancel(args):
    """取消任务"""
    if not args:
        print("ERROR: 缺少task_id参数")
        print(">>> hint: ailabber cancel <task_id> <<<".center(40))
        return
    task_id = args[0]
    resp = requests.post(f"{LOCAL_PROXY_URL}/api/cancel/{task_id}", params={"username": current_username})
    # TODO: 处理取消任务的响应， 未开始则canceled，已开始则terminated
    print(resp.json().get("message", "操作完成"))


def cmd_help(args):
    """显示帮助"""
    help_text = """ailabber - LFS任务提交系统
        命令:
        whoami                     查看当前用户
        submit <task_config.toml>  提交任务
        status <task_id>           查看任务状态  
        list                       列出我的任务
        fetch <task_id>            下载任务输出（日志+结果）
        cancel <task_id>           取消任务
        help                       显示帮助
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
            print("ERROR: 无法连接到本地代理服务器，请联系管理员")
    else:
        print(f"ERROR: 未知命令: {command}")
        cmd_help([])


if __name__ == "__main__":
    main()
