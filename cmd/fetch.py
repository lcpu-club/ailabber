"""fetch command - Download task outputs"""
import os
import requests
from pathlib import Path

from shared.config import LOCAL_PROXY_URL

current_username = os.environ.get('USER', 'unknown')
current_dir = Path.cwd()


def cmd_fetch(args):
    """Download task outputs"""
    task_id = args.task_id
    output_dir = args.output_dir if hasattr(args, 'output_dir') and args.output_dir else str(current_dir)
    
    try:
        resp = requests.get(
            f"{LOCAL_PROXY_URL}/api/fetch/{task_id}",
            params={"username": current_username},
            timeout=30
        )
        resp.raise_for_status()
        
        # Save file
        output_path = Path(output_dir) / f"{task_id}_logs.zip"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'wb') as f:
            f.write(resp.content)
        
        print(f"✓ Task output downloaded")
        print(f"  Location: {output_path}")
        print(f"  Size: {output_path.stat().st_size / 1024:.2f} KB")
        
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Cannot connect to {LOCAL_PROXY_URL}")
    except requests.exceptions.Timeout:
        print("ERROR: Download timeout, please retry later")
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP error {resp.status_code}")
        print(f"\t{resp.json().get('message', str(e))}")
    except Exception as e:
        print(f"ERROR: Failed to download task output: {e}")
