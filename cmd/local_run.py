"""local-run command - Run command via Slurm (with logging)"""
import os
import requests
import json
from pathlib import Path

from core.config import LOCAL_PROXY_URL
from utils.slurm import generate_slurm_script, submit_slurm_job

current_username = os.environ.get('USER', 'unknown')


def cmd_local_run(args):
    """Run command via Slurm and log to database"""
    # Get resource parameters
    gpus = args.gpu if hasattr(args, 'gpu') and args.gpu else 0
    cpus = args.cpu if hasattr(args, 'cpu') and args.cpu else 1
    memory = args.memory if hasattr(args, 'memory') and args.memory else '4G'
    time_limit = args.time if hasattr(args, 'time') and args.time else '1:00:00'
    workdir = args.workdir if hasattr(args, 'workdir') and args.workdir else '.'
    
    # Get command to execute
    if not args.command:
        print("ERROR: Command is required")
        return
    
    # Build complete command string
    command_str = ' '.join(args.command)
    
    # Step 1: Create DB record via proxy API
    try:
        create_data = {
            "username": current_username,
            "workdir": workdir,
            "commands": [command_str],
            "gpus": gpus,
            "cpus": cpus,
            "memory": memory,
            "time_limit": time_limit
        }
        
        resp = requests.post(f"{LOCAL_PROXY_URL}/api/local-run", json=create_data, timeout=30)
        resp.raise_for_status()
        
        data = resp.json()
        task_id = data.get('task_id')
        
        if not task_id:
            print("ERROR: Failed to create task record")
            return
            
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Cannot connect to {LOCAL_PROXY_URL}")
        print("Please ensure local proxy is running")
        return
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTP error {resp.status_code}")
        try:
            print(f"\t{resp.json().get('error', str(e))}")
        except:
            print(f"\t{str(e)}")
        return
    except Exception as e:
        print(f"ERROR: Failed to create task: {e}")
        return
    
    # Step 2: Submit Slurm job directly
    try:
        work_path = Path(workdir).resolve()
        work_path.mkdir(parents=True, exist_ok=True)
        
        # Create .slurm directory for logs
        slurm_dir = work_path / ".slurm"
        slurm_dir.mkdir(exist_ok=True)
        
        output_file = str(slurm_dir / f"{task_id}.out")
        error_file = str(slurm_dir / f"{task_id}.err")
        script_file = str(slurm_dir / f"{task_id}.sh")
        
        # Generate Slurm script
        script_content = generate_slurm_script(
            task_id=task_id,
            username=current_username,
            workdir=str(work_path),
            commands=[command_str],
            gpus=gpus,
            cpus=cpus,
            memory=memory,
            time_limit=time_limit,
            output_file=output_file,
            error_file=error_file
        )
        
        # Write script
        with open(script_file, 'w') as f:
            f.write(script_content)
        
        # Submit to Slurm
        success, result, stdout = submit_slurm_job(script_file)
        
        if not success:
            print(f"ERROR: Slurm submission failed: {result}")
            return
        
        slurm_job_id = result
        
        # Step 3: Update DB with Slurm job ID
        update_data = {"slurm_job_id": slurm_job_id}
        resp = requests.post(
            f"{LOCAL_PROXY_URL}/api/local-run/{task_id}/slurm",
            json=update_data,
            timeout=30
        )
        resp.raise_for_status()
        
        # Success
        print(f"✓ Command submitted to Slurm")
        print(f"  Task ID:      {task_id}")
        print(f"  Slurm ID:     {slurm_job_id}")
        print(f"  Command:      {command_str}")
        print(f"  Resources:    GPU={gpus}, CPU={cpus}, Memory={memory}, Time={time_limit}")
        print(f"  Workdir:      {work_path}")
        print(f"\nUse following command to check status:")
        print(f"  ailabber status {task_id}")
        
    except Exception as e:
        print(f"ERROR: Failed to submit Slurm job: {e}")
