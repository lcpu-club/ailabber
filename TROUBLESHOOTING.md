# Ailabber 故障排查

## 问题：命令不工作或显示旧的帮助信息

### 症状
```bash
ailabber local-run python3 t.py
# 显示帮助信息，但命令不执行
```

### 原因
安装的版本与当前代码不一致（可能是缓存的旧版本）。

### 解决方案

#### 方法1：强制重新安装（推荐）

```bash
cd /path/to/ailabber

# 1. 先卸载
sudo pip3 uninstall -y ailabber

# 2. 清理缓存
sudo pip3 cache purge

# 3. 重新安装
sudo pip3 install -e .

# 4. 验证
ailabber --help
ailabber local-run --help
```

#### 方法2：清理Python缓存

```bash
cd /path/to/ailabber

# 删除所有__pycache__目录
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

# 删除.pyc文件
find . -name "*.pyc" -delete

# 重新安装
sudo pip3 install -e . --force-reinstall --no-deps
```

#### 方法3：检查安装位置

```bash
# 查看安装位置
which ailabber
# 应该显示: /usr/local/bin/ailabber

# 查看实际执行的脚本
cat $(which ailabber)

# 如果路径不对，检查是否有多个版本
pip3 list | grep ailabber
```

## 验证安装成功

运行以下命令验证：

```bash
# 1. 基本命令
ailabber --help

# 2. 子命令帮助（这个很重要！）
ailabber local-run --help

# 应该显示:
# usage: ailabber local-run [-h] [--gpu GPU] [--cpu CPU] [--memory MEMORY]
#                           [--time TIME] [--workdir WORKDIR]
#                           command [command ...]

# 3. 测试执行
ailabber local-run echo "Hello World"
```

## 常见问题

### Q1: `ailabber: command not found`

**解决：**
```bash
# 检查PATH
echo $PATH | grep -o '/usr/local/bin'

# 如果没有，添加到PATH
export PATH="/usr/local/bin:$PATH"

# 永久添加
echo 'export PATH="/usr/local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Q2: 权限错误

**解决：**
```bash
# 使用sudo安装
sudo pip3 install -e /path/to/ailabber

# 或者检查目录权限
ls -la /usr/local/bin/ailabber
```

### Q3: 模块导入错误

**症状：**
```
ModuleNotFoundError: No module named 'ailabber_cmd'
```

**解决：**
```bash
cd /path/to/ailabber

# 确保目录结构正确
ls -la ailabber_cmd/
# 应该包含: __init__.py, cli.py, local_run.py, 等

# 重新安装
sudo pip3 install -e . --force-reinstall
```

### Q4: 两个版本冲突

**症状：**不同用户看到不同的版本

**解决：**
```bash
# 清理所有安装
sudo pip3 uninstall ailabber
pip3 uninstall ailabber  # 用户级

# 只做系统级安装
cd /path/to/ailabber
sudo pip3 install -e .
```

## 完整重置步骤

如果以上都不行，完整重置：

```bash
# 1. 完全卸载
sudo pip3 uninstall -y ailabber
pip3 uninstall -y ailabber

# 2. 删除可能的残留
sudo rm -f /usr/local/bin/ailabber
sudo rm -f ~/.local/bin/ailabber

# 3. 清理缓存
sudo pip3 cache purge
rm -rf ~/.cache/pip

# 4. 进入项目目录
cd /root/ailabber  # 或你的项目路径

# 5. 清理Python缓存
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete

# 6. 重新安装
sudo pip3 install -e .

# 7. 验证
which ailabber
ailabber --help
ailabber local-run --help

# 8. 测试
ailabber local-run echo "Success"
```

## 调试技巧

### 查看详细错误信息

```bash
# 使用Python直接运行
python3 -c "from ailabber_cmd.cli import main; main()" local-run --help

# 或
python3 /path/to/ailabber/ailabber_cmd/cli.py local-run --help
```

### 检查sys.path

```bash
python3 -c "import sys; print('\n'.join(sys.path))"
```

### 确认模块可导入

```bash
python3 -c "from ailabber_cmd.cli import main; print('OK')"
```

## 预防措施

1. **始终在项目根目录安装**
   ```bash
   cd /root/ailabber  # 确保在正确目录
   sudo pip3 install -e .
   ```

2. **使用-e参数（开发模式）**
   - 这样代码更新后无需重新安装
   - 但需要确保项目目录不被删除

3. **定期清理缓存**
   ```bash
   find /root/ailabber -name "*.pyc" -delete
   find /root/ailabber -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
   ```

## 联系支持

如果问题仍然存在，请提供以下信息：

```bash
# 系统信息
uname -a
python3 --version
pip3 --version

# 安装信息
which ailabber
pip3 show ailabber

# 文件内容
cat $(which ailabber)

# 目录结构
ls -la /root/ailabber/ailabber_cmd/
```
