"""submit command - Submit task to proxy server"""
import os
import tomllib
import requests
from pathlib import Path

from core.config import LOCAL_PROXY_URL

current_username = os.environ.get('USER', 'unknown')


def cmd_submit(args) -> str:
    """Submit task to proxy server"""
    target = args.target
    config_path = args.config
    
    # Read task config
    try:
        with open(config_path, "rb") as f:
            task_config = tomllib.load(f)
    except FileNotFoundError:
        print(f"ERROR: Task config file not found: {config_path}")
        return ""
    except tomllib.TOMLDecodeError as e:
        print(f"ERROR: Failed to parse task config: {e}")
        return ""
    
    # Validate required sections
    required_sections = ["resources", "run"]
    for section in required_sections:
        if section not in task_config:
            print(f"ERROR: Missing [{section}] section in config")
            return ""
    
    if "commands" not in task_config["run"]:
        print("ERROR: Missing commands in [run] section")
        return ""
    
    # Submit task to local proxy server
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
        
        resp.raise_for_status()  # Check HTTP status code
        data = resp.json()
        
        if "task_id" in data:
            task_id = data['task_id']
            print(f"✓ Task submitted: {task_id}")
            return task_id
        else:
            print("ERROR: Task submission failed")
            print(f"\t{data.get('message', data.get('error', 'Unknown error'))}")
            return ""
            
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Cannot connect to {LOCAL_PROXY_URL}")
        print("  Please ensure local proxy is running")
        return ""
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP error {resp.status_code}")
        print(f"\t{resp.json().get('message', str(e))}")
        return ""
    except KeyError as e:
        print(f"ERROR: Missing config key: {e}")
        return ""
    except Exception as e:
        print(f"ERROR: Task submission failed: {e}")
        return ""
