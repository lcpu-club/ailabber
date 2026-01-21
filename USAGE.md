# ailabber Usage Guide

Complete examples and usage patterns for the ailabber distributed Slurm task scheduler.

## Command Overview

```bash
ailabber whoami              # Show current user
ailabber submit              # Submit task to proxy
ailabber local-run           # Run command via Slurm (with logging)
ailabber status              # Check task status
ailabber list                # List tasks
ailabber fetch               # Download task results
ailabber cancel              # Cancel task
```

## Command Examples

### 1. whoami - Show Current User

```bash
# Display current username
ailabber whoami
```

**Output:**
```
Current user: username
```

---

### 2. submit - Submit Task to Proxy

Submit tasks to local or remote Slurm clusters using TOML configuration.

#### Submit to Remote Cluster

```bash
# Submit to remote cluster (default config)
ailabber submit -t remote

# Submit with custom config
ailabber submit -t remote custom_task.toml

# Submit with specific resources
ailabber submit --target remote task_config.toml
```

#### Submit to Local Cluster (via Proxy)

```bash
# Submit to local cluster (default)
ailabber submit

# Explicit local target
ailabber submit -t local task_config.toml
```

**Example task_config.toml:**
```toml
[resources]
gpus = 2
cpus = 8
memory = "32G"
time_limit = "4:00:00"

[submit]
upload = "."
ignore = [".git/", "__pycache__/", ".venv/"]

[run]
workdir = "./experiments"
commands = [
    "python train.py --config config.yaml",
    "python evaluate.py --checkpoint ./checkpoints/best.pt"
]

[fetch]
logs = ["./logs"]
results = ["./output", "./checkpoints"]
```

**Output:**
```
[username]
✓ Task submitted: abc123def456
```

---

### 3. local-run - Run Command via Slurm

Execute arbitrary commands through Slurm scheduler with resource specification. All executions are logged to database.

#### Basic Usage

```bash
# Run simple command (default resources: 0 GPU, 1 CPU, 4G memory, 1h)
ailabber local-run python script.py

# Run with arguments
ailabber local-run python train.py --epochs 100 --lr 0.001
```

#### Specify GPU Resources

```bash
# Run with 1 GPU
ailabber local-run --gpu 1 python train.py

# Run with 2 GPUs
ailabber local-run --gpu 2 python distributed_train.py

# Run with 4 GPUs for large model training
ailabber local-run --gpu 4 --cpu 16 --memory 64G python train_llm.py
```

#### Specify CPU and Memory

```bash
# Run with 8 CPUs and 16GB memory
ailabber local-run --cpu 8 --memory 16G python data_processing.py

# CPU-intensive job
ailabber local-run --cpu 32 --memory 128G python compute_heavy.py
```

#### Specify Time Limit

```bash
# Run with 30-minute limit
ailabber local-run --time 00:30:00 python quick_experiment.py

# Run with 8-hour limit
ailabber local-run --time 08:00:00 python long_training.py

# Run with 2-day limit
ailabber local-run --time 48:00:00 python extensive_simulation.py
```

#### Specify Working Directory

```bash
# Run in specific directory
ailabber local-run --workdir /path/to/project python run.py

# Run in subdirectory
ailabber local-run --workdir ./experiments/exp1 python train.py
```

#### Combined Resource Specification

```bash
# Full resource specification
ailabber local-run \
  --gpu 2 \
  --cpu 16 \
  --memory 64G \
  --time 12:00:00 \
  --workdir ./experiments \
  python train.py --config config.yaml --distributed

# Medium-scale job
ailabber local-run --gpu 1 --cpu 8 --memory 32G --time 4:00:00 python experiment.py

# Large-scale distributed training
ailabber local-run --gpu 8 --cpu 64 --memory 256G --time 24:00:00 torchrun --nproc_per_node=8 train.py
```

#### Run Shell Scripts

```bash
# Run bash script
ailabber local-run bash ./scripts/setup.sh

# Run script with arguments
ailabber local-run ./run_pipeline.sh --stage 1 --data /mnt/data

# Run with specific shell
ailabber local-run /bin/bash -c "source env.sh && python train.py"
```

#### Complex Commands

```bash
# Pipe commands
ailabber local-run bash -c "python generate_data.py | python process.py > output.txt"

# Multiple commands (using shell)
ailabber local-run bash -c "cd experiments && python train.py && python eval.py"

# Environment variables
ailabber local-run bash -c "export CUDA_VISIBLE_DEVICES=0,1 && python train.py"
```

**Output Example:**
```
[username]
✓ Command submitted to Slurm
  Task ID:      abc123def456
  Slurm ID:    12345
  Command:     python train.py --epochs 100
  Resources:   GPU=2, CPU=8, Memory=32G, Time=4:00:00
  Workdir:     ./experiments

Use following command to check status:
  ailabber status abc123def456
```

---

### 4. status - Check Task Status

Check detailed status of submitted tasks.

```bash
# Check task status
ailabber status abc123def456

# Check multiple tasks (run separately)
ailabber status task_id_1
ailabber status task_id_2
```

**Output Example:**
```
[username]

==================================================
Task ID:     abc123def456
User:        username
Target:      local
Status:      running
Created:     2026-01-22 10:30:15
Started:     2026-01-22 10:30:20
Slurm ID:    12345
==================================================
```

**Status Values:**
- `pending` - Queued in Slurm, waiting for resources
- `running` - Currently executing
- `completed` - Successfully finished
- `failed` - Execution failed (check logs)
- `canceled` - Manually canceled

---

### 5. list - List Tasks

List all tasks with optional filtering.

```bash
# List all tasks
ailabber list

# Filter by status
ailabber list -s running
ailabber list -s completed
ailabber list -s failed
ailabber list -s pending
ailabber list -s canceled

# Alternative syntax
ailabber list --status running
```

**Output Example:**
```
[username]

username's task list (5 tasks):
------------------------------------------------------------------------------------------
Task ID      Target   Status       GPU  CPU  Created
------------------------------------------------------------------------------------------
abc123def    local    running      2    8    2026-01-22 10:30:15
xyz789ghi    remote   completed    1    4    2026-01-22 09:15:32
def456uvw    local    pending      0    1    2026-01-22 10:45:01
ghi789abc    local    failed       1    8    2026-01-22 08:20:10
jkl012mno    remote   canceled     4    16   2026-01-22 07:10:55
------------------------------------------------------------------------------------------
```

---

### 6. fetch - Download Task Results

Download task outputs and logs as ZIP archive.

```bash
# Download to current directory
ailabber fetch abc123def456

# Download to specific directory
ailabber fetch abc123def456 -o ./results

# Download to specific directory (alternative)
ailabber fetch abc123def456 --output-dir /path/to/results
```

**Output Example:**
```
[username]
✓ Task output downloaded
  Location: ./abc123def456_logs.zip
  Size: 15.32 MB
```

**ZIP Contents:**
```
abc123def456_logs.zip
├── logs/
│   ├── train.log
│   └── error.log
└── output/
    ├── model.pt
    └── metrics.json
```

---

### 7. cancel - Cancel Running Task

Cancel pending or running tasks.

```bash
# Cancel task
ailabber cancel abc123def456
```

**Output Example:**
```
[username]
✓ Task canceled successfully
  New status: canceled
```

---

## Workflow Examples

### Example 1: Quick GPU Training

```bash
# Run training with 2 GPUs
ailabber local-run --gpu 2 --memory 32G python train.py

# Check status
ailabber status <task_id>

# Monitor progress
watch -n 5 "ailabber status <task_id>"

# Download results after completion
ailabber fetch <task_id> -o ./results
```

### Example 2: Batch Experiments

```bash
# Run multiple experiments
ailabber local-run --gpu 1 python experiment.py --config exp1.yaml
ailabber local-run --gpu 1 python experiment.py --config exp2.yaml
ailabber local-run --gpu 1 python experiment.py --config exp3.yaml

# List all running experiments
ailabber list -s running

# Check specific experiment
ailabber status <task_id>
```

### Example 3: Long-Running Simulation

```bash
# Submit long simulation (48 hours)
ailabber local-run \
  --cpu 32 \
  --memory 128G \
  --time 48:00:00 \
  python simulation.py --iterations 1000000

# Check periodically
ailabber status <task_id>

# If needed, cancel
ailabber cancel <task_id>
```

### Example 4: Distributed Training

```bash
# Submit distributed training job
ailabber local-run \
  --gpu 8 \
  --cpu 64 \
  --memory 256G \
  --time 24:00:00 \
  torchrun --nproc_per_node=8 --master_port=29500 train.py

# Monitor status
ailabber status <task_id>

# Fetch results
ailabber fetch <task_id> -o ./training_results
```

### Example 5: Remote Task Submission

```bash
# Create task configuration
cat > remote_task.toml << EOF
[resources]
gpus = 4
cpus = 32
memory = "128G"
time_limit = "12:00:00"

[submit]
upload = "./project"
ignore = [".git/", "data/", "__pycache__/"]

[run]
workdir = "./project"
commands = [
    "pip install -r requirements.txt",
    "python train.py --distributed"
]

[fetch]
logs = ["./logs"]
results = ["./checkpoints", "./results"]
EOF

# Submit to remote cluster
ailabber submit -t remote remote_task.toml

# Check status
ailabber status <task_id>

# List all remote tasks
ailabber list -s running

# Download results
ailabber fetch <task_id> -o ./remote_results
```

---

## Tips and Best Practices

### Resource Specification

1. **GPU allocation**: Use `--gpu N` based on your model size
   - Small models: `--gpu 1`
   - Medium models: `--gpu 2-4`
   - Large models/distributed: `--gpu 4-8`

2. **Memory estimation**: Rule of thumb
   - Model parameters (GB) × 4 for training
   - Add extra for data loading and gradients
   - Example: 7B model → `--memory 32G` minimum

3. **Time limits**: Add buffer time
   - Estimate runtime + 20-30% buffer
   - Use `--time HH:MM:SS` format
   - Example: Expected 6h → `--time 08:00:00`

### Command Patterns

1. **Use absolute paths** when possible
   ```bash
   ailabber local-run --workdir /absolute/path python script.py
   ```

2. **Escape special characters** in shell commands
   ```bash
   ailabber local-run bash -c "echo \"Hello Slurm\""
   ```

3. **Source environment** for conda/venv
   ```bash
   ailabber local-run bash -c "source activate myenv && python train.py"
   ```

### Monitoring

1. **Check status regularly** during long runs
   ```bash
   watch -n 60 "ailabber status <task_id>"
   ```

2. **List tasks by status** to track progress
   ```bash
   ailabber list -s running
   ailabber list -s completed
   ```

3. **Download logs early** if task fails
   ```bash
   ailabber fetch <task_id> -o ./debug_logs
   ```

---

## Troubleshooting

### Common Issues

1. **Connection Error**
   ```
   ERROR: Cannot connect to http://localhost:5000
   ```
   **Solution**: Start local proxy first
   ```bash
   python -m server.local_proxy
   ```

2. **Task Stuck in Pending**
   - Check Slurm queue: `squeue -u $USER`
   - Verify resource availability
   - Reduce resource requirements

3. **Task Failed**
   ```bash
   # Check task status
   ailabber status <task_id>
   
   # Download logs to debug
   ailabber fetch <task_id> -o ./failed_task_logs
   ```

4. **Out of Memory**
   - Increase `--memory` parameter
   - Reduce batch size in your code
   - Use gradient checkpointing

5. **Time Limit Exceeded**
   - Increase `--time` parameter
   - Optimize code for faster execution
   - Use checkpointing to resume

---

## Advanced Usage

### Custom Slurm Options

For advanced Slurm configurations, modify the task TOML or use shell scripts with sbatch directly.

### Parallel Job Submission

```bash
# Submit multiple jobs in parallel
for i in {1..10}; do
  ailabber local-run --gpu 1 python exp.py --seed $i &
done
wait
```

### Integration with Shell Scripts

```bash
#!/bin/bash
# run_experiments.sh

TASK_ID=$(ailabber local-run --gpu 2 python train.py | grep "Task ID" | awk '{print $3}')
echo "Submitted task: $TASK_ID"

# Wait for completion
while true; do
  STATUS=$(ailabber status $TASK_ID | grep "Status:" | awk '{print $2}')
  if [[ "$STATUS" == "completed" ]]; then
    echo "Task completed!"
    ailabber fetch $TASK_ID -o ./results
    break
  elif [[ "$STATUS" == "failed" ]]; then
    echo "Task failed!"
    exit 1
  fi
  sleep 60
done
```

---

## Environment Variables

- `USER`: Current username (auto-detected)
- `LOCAL_PROXY_URL`: Local proxy server URL (default: `http://localhost:5000`)

---

## See Also

- [README.md](README.md) - Project overview and setup
- [task_config.toml](task_config.toml) - Configuration template
- Server documentation: Local proxy and remote server setup
