"""cancel command - Cancel task"""
import os
import requests

from core.config import LOCAL_PROXY_URL

current_username = os.environ.get('USER', 'unknown')


def cmd_cancel(args):
    """Cancel task"""
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
        message = data.get("message", "Operation completed")
        
        print(f"✓ {message}")
        print(f"  New status: {status}")
        
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Cannot connect to {LOCAL_PROXY_URL}")
    except requests.exceptions.Timeout:
        print("ERROR: Request timeout")
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP error {resp.status_code}")
        try:
            data = resp.json()
            print(f"  {data.get('message', str(e))}")
        except:
            print(f"  {e}")
    except Exception as e:
        print(f"ERROR: Failed to cancel task: {e}")
