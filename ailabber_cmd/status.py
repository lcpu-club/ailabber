"""status command - Check task status"""
import os
import requests

from core.config import LOCAL_PROXY_URL

current_username = os.environ.get('USER', 'unknown')


def cmd_status(args):
    """Check task status"""
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
            print(f"Task ID:     {task['task_id']}")
            print(f"User:        {task['username']}")
            print(f"Target:      {task.get('target', 'N/A')}")
            print(f"Status:      {task['status']}")
            print(f"Created:     {task['created_at']}")
            if task.get('started_at'):
                print(f"Started:     {task['started_at']}")
            if task.get('completed_at'):
                print(f"Completed:   {task['completed_at']}")
            if task.get('exit_code') is not None:
                print(f"Exit Code:   {task['exit_code']}")
            if task.get('slurm_job_id'):
                print(f"Slurm ID:    {task['slurm_job_id']}")
            print(f"{'='*50}\n")
        else:
            print(f"ERROR: Failed to query task status")
            print(f"\t{data.get('message', data.get('error', 'Unknown error'))}")
            
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Cannot connect to {LOCAL_PROXY_URL}")
    except requests.exceptions.Timeout:
        print("ERROR: Request timeout")
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP error {resp.status_code}")
        print(f"\t{resp.json().get('message', str(e))}")
    except Exception as e:
        print(f"ERROR: Failed to get task status: {e}")
