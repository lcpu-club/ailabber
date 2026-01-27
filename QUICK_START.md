# Ailabber 快速使用指南

## ❌ 常见错误

```bash
# 错误：使用引号包裹整个命令
ailabber local-run "python3 t.py"
```

## ✅ 正确用法

```bash
# 正确：不使用引号，或者分开写
ailabber local-run python3 t.py

# 或者使用 -- 分隔符（推荐）
ailabber local-run -- python3 t.py

# 带参数的命令
ailabber local-run python3 train.py --epochs 100

# 指定资源
ailabber local-run --gpu 2 --cpu 8 --memory 16G -- python3 train.py
```

## 📝 完整命令示例

### 1. 基础命令
```bash
# 运行Python脚本
ailabber local-run python3 script.py

# 运行bash脚本
ailabber local-run bash run.sh

# 运行其他命令
ailabber local-run nvidia-smi
```

### 2. 带参数的命令
```bash
# Python脚本带参数
ailabber local-run python3 train.py --batch-size 32 --lr 0.001

# 运行命令带参数
ailabber local-run python3 -m torch.distributed.launch train.py
```

### 3. 指定Slurm资源
```bash
# 2个GPU，8核CPU，16G内存
ailabber local-run --gpu 2 --cpu 8 --memory 16G -- python3 train.py

# 指定时间限制
ailabber local-run --time 2:00:00 --gpu 1 -- python3 long_task.py

# 指定工作目录
ailabber local-run --workdir /path/to/project -- python3 script.py
```

### 4. 复杂命令（需要使用 -- ）
```bash
# 命令中包含管道或重定向时，使用引号并通过bash运行
ailabber local-run -- bash -c "python3 train.py | tee output.log"

# 或者
ailabber local-run -- bash -c 'echo "Starting..." && python3 script.py'
```

## 🔍 其他常用命令

```bash
# 查看当前用户
ailabber whoami

# 查看所有任务
ailabber list

# 查看特定任务状态
ailabber status <task_id>

# 取消任务
ailabber cancel <task_id>

# 获取任务结果
ailabber fetch <task_id>
```

## 💡 为什么不能用引号？

在shell中：
- `ailabber local-run "python3 t.py"` → 传递1个参数：`"python3 t.py"`
- `ailabber local-run python3 t.py` → 传递2个参数：`python3` 和 `t.py`

`argparse` 的 `nargs='+'` 需要接收多个独立的参数，而不是一个包含空格的字符串。

## 🎯 最佳实践

1. **简单命令**：直接写，不用引号
   ```bash
   ailabber local-run python3 script.py
   ```

2. **带选项的命令**：使用 `--` 分隔符（可选但推荐）
   ```bash
   ailabber local-run --gpu 1 -- python3 train.py --epochs 100
   ```

3. **复杂命令**：通过 bash -c 执行
   ```bash
   ailabber local-run -- bash -c "your complex command here"
   ```
