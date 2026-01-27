"""list command - List tasks"""
import os
import requests

from core.config import LOCAL_PROXY_URL

current_username = os.environ.get('USER', 'unknown')


def cmd_list(args):
    """List tasks"""
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
            print(f"\nNo tasks found for user {current_username}")
            return
        
        print(f"\n{current_username}'s task list ({len(tasks)} tasks):")
        print(f"{'-'*90}")
        print(f"{'Task ID':<12} {'Target':<8} {'Status':<12} {'GPU':<4} {'CPU':<4} {'Created':<20}")
        print(f"{'-'*90}")
        
        for task in tasks:
            target = task.get('target', 'N/A')
            print(f"{task['task_id']:<12} {target:<8} {task['status']:<12} {task['gpus']:<4} {task['cpus']:<4} {task['created_at'][:19]:<20}")
        
        print(f"{'-'*90}\n")
        
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Cannot connect to {LOCAL_PROXY_URL}")
    except requests.exceptions.Timeout:
        print("ERROR: Request timeout")
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP error {resp.status_code}")
        print(f"\t{resp.json().get('message', str(e))}")
    except Exception as e:
        print(f"ERROR: Failed to list tasks: {e}")
