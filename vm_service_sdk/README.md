# VM Service SDK

基于E2B Desktop封装的VM和Sandbox服务SDK，为其他微服务提供统一的VM操作接口。

## 特性

- 🚀 **基于E2B Desktop**: 利用E2B的150ms快速启动和硬件级隔离
- 🔒 **多租户安全**: 完善的用户隔离和权限控制
- 🎯 **简单易用**: 统一的异步API接口
- 📱 **桌面交互**: 鼠标、键盘、截图、流媒体完整支持
- 📁 **文件管理**: 完整的文件系统操作能力
- 🖥️ **应用管理**: 启动和管理桌面应用程序
- ⚡ **高性能**: 异步架构，支持高并发
- 🛠️ **企业就绪**: 完善的错误处理和监控支持

## 快速开始

### 安装依赖

```bash
pip install e2b-desktop
```

### 环境设置

```bash
export E2B_API_KEY="your_e2b_api_key_here"
```

### 基础使用

```python
import asyncio
from vm_service_sdk import VMServiceClient, SandboxConfig

async def main():
    async with VMServiceClient(api_key="your_key") as client:
        # 创建用户沙箱
        sandbox_info = await client.create_sandbox(
            user_id="user123",
            config=SandboxConfig(template="desktop")
        )
        
        # 桌面操作
        await client.click(sandbox_info.sandbox_id, 100, 200)
        await client.type_text(sandbox_info.sandbox_id, "Hello World!")
        
        # 截图
        screenshot = await client.screenshot(sandbox_info.sandbox_id)
        
        # 启动应用
        await client.launch_application(sandbox_info.sandbox_id, "firefox")
        
        # 启动流媒体
        stream_url, auth_key = await client.start_stream(sandbox_info.sandbox_id)
        print(f"Stream URL: {stream_url}")

if __name__ == "__main__":
    asyncio.run(main())
```

## API 参考

### VMServiceClient

主要的客户端类，提供所有VM和Sandbox操作功能。

#### 初始化

```python
client = VMServiceClient(
    api_key="your_e2b_api_key",
    default_template="desktop",
    max_concurrent_sandboxes=10,
    default_timeout=300
)
```

#### 沙箱管理

```python
# 创建沙箱
sandbox_info = await client.create_sandbox(
    user_id="user123",
    config=SandboxConfig(
        template="desktop",
        cpu_count=2,
        memory_mb=2048,
        timeout_seconds=1800
    )
)

# 获取沙箱信息
info = await client.get_sandbox_info(sandbox_id)

# 列出用户沙箱
user_sandboxes = await client.list_user_sandboxes(user_id="user123")

# 销毁沙箱
await client.destroy_sandbox(sandbox_id)
```

#### 桌面交互

```python
# 鼠标操作
await client.click(sandbox_id, x=100, y=200, button="left")
await client.move_mouse(sandbox_id, x=300, y=400)
await client.drag(sandbox_id, from_x=100, from_y=100, to_x=200, to_y=200)
await client.scroll(sandbox_id, direction=1, amount=3)

# 键盘操作
await client.type_text(sandbox_id, "Hello World!", chunk_size=25, delay_ms=75)
await client.press_key(sandbox_id, "enter")
await client.press_key_combination(sandbox_id, ["ctrl", "c"])
```

#### 文件操作

```python
# 写文件
await client.write_file(sandbox_id, "/home/user/test.txt", "Hello E2B!")

# 读文件
content = await client.read_file(sandbox_id, "/home/user/test.txt")

# 打开文件
await client.open_file(sandbox_id, "/home/user/test.txt")
```

#### 应用管理

```python
# 启动应用
await client.launch_application(sandbox_id, "google-chrome")
await client.launch_application(sandbox_id, "firefox")
await client.launch_application(sandbox_id, "vscode")

# 获取窗口信息
window_id = await client.get_current_window_id(sandbox_id)
windows = await client.get_application_windows(sandbox_id, "Firefox")
```

#### 命令执行

```python
# 执行命令
result = await client.run_command(
    sandbox_id, 
    "ls -la /home/user",
    timeout=30
)

print(f"Exit Code: {result.exit_code}")
print(f"Stdout: {result.stdout}")
print(f"Stderr: {result.stderr}")
```

#### 截图和流媒体

```python
# 截图
screenshot_bytes = await client.screenshot(sandbox_id)

# 启动流媒体
stream_url, auth_key = await client.start_stream(
    sandbox_id,
    config=StreamConfig(
        window_id=None,  # 全桌面
        require_auth=True,
        quality="medium",
        frame_rate=30
    )
)
```

### 配置类

#### SandboxConfig

```python
config = SandboxConfig(
    template="desktop",          # E2B模板名称
    cpu_count=2,                 # CPU核心数 (1-8)
    memory_mb=2048,              # 内存大小MB (512-8192)
    timeout_seconds=1800,        # 超时时间秒
    allow_internet_access=True,  # 是否允许互联网访问
    environment={"KEY": "value"}, # 环境变量
    working_directory="/home/user" # 工作目录
)
```

#### StreamConfig

```python
stream_config = StreamConfig(
    window_id=None,        # 特定窗口ID，None表示全桌面
    require_auth=True,     # 是否需要认证
    quality="medium",      # 流媒体质量: low, medium, high
    frame_rate=30         # 帧率
)
```

## 错误处理

```python
from vm_service_sdk.exceptions import (
    VMServiceError,
    SandboxCreationError,
    SandboxNotFoundError,
    AuthenticationError,
    QuotaExceededError
)

try:
    sandbox_info = await client.create_sandbox(user_id="user123")
except SandboxCreationError as e:
    print(f"沙箱创建失败: {e.message}")
    print(f"错误详情: {e.to_dict()}")
except QuotaExceededError as e:
    print(f"配额超限: 当前使用 {e.current_usage}, 限制 {e.limit}")
except VMServiceError as e:
    print(f"一般错误: {e.error_code} - {e.message}")
```

## 与其他微服务集成

### FastAPI 集成

```python
from fastapi import FastAPI, HTTPException
from vm_service_sdk import VMServiceClient
import os

app = FastAPI()
vm_client = VMServiceClient(api_key=os.environ["E2B_API_KEY"])

@app.post("/api/sessions")
async def create_session(user_id: str):
    try:
        sandbox_info = await vm_client.create_sandbox(user_id=user_id)
        return {
            "session_id": sandbox_info.session_id,
            "sandbox_id": sandbox_info.sandbox_id
        }
    except VMServiceError as e:
        raise HTTPException(status_code=400, detail=e.to_dict())

@app.post("/api/sessions/{sandbox_id}/click")
async def click(sandbox_id: str, x: int, y: int):
    try:
        await vm_client.click(sandbox_id, x, y)
        return {"success": True}
    except VMServiceError as e:
        raise HTTPException(status_code=400, detail=e.to_dict())

@app.get("/api/sessions/{sandbox_id}/screenshot")
async def screenshot(sandbox_id: str):
    try:
        screenshot_data = await vm_client.screenshot(sandbox_id)
        return {"data": screenshot_data.hex(), "size": len(screenshot_data)}
    except VMServiceError as e:
        raise HTTPException(status_code=400, detail=e.to_dict())
```

### Flask 集成

```python
from flask import Flask, request, jsonify
from vm_service_sdk import VMServiceClient
import asyncio
import os

app = Flask(__name__)
vm_client = VMServiceClient(api_key=os.environ["E2B_API_KEY"])

def run_async(coro):
    """Flask中运行异步函数的辅助方法"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route('/api/sessions', methods=['POST'])
def create_session():
    user_id = request.json.get('user_id')
    try:
        sandbox_info = run_async(vm_client.create_sandbox(user_id=user_id))
        return jsonify({
            "session_id": sandbox_info.session_id,
            "sandbox_id": sandbox_info.sandbox_id
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400
```

### Celery 异步任务集成

```python
from celery import Celery
from vm_service_sdk import VMServiceClient
import asyncio
import os

app = Celery('vm_tasks')
vm_client = VMServiceClient(api_key=os.environ["E2B_API_KEY"])

@app.task
def execute_automation_task(user_id: str, script_steps: list):
    """执行自动化任务"""
    async def async_task():
        async with vm_client:
            # 创建沙箱
            sandbox_info = await vm_client.create_sandbox(user_id=user_id)
            sandbox_id = sandbox_info.sandbox_id
            
            try:
                # 执行脚本步骤
                for step in script_steps:
                    if step["type"] == "click":
                        await vm_client.click(sandbox_id, step["x"], step["y"])
                    elif step["type"] == "type":
                        await vm_client.type_text(sandbox_id, step["text"])
                    elif step["type"] == "launch":
                        await vm_client.launch_application(sandbox_id, step["app"])
                    elif step["type"] == "wait":
                        await asyncio.sleep(step["seconds"])
                
                # 返回最终截图
                screenshot = await vm_client.screenshot(sandbox_id)
                return {
                    "success": True,
                    "screenshot_size": len(screenshot),
                    "sandbox_id": sandbox_id
                }
                
            finally:
                await vm_client.destroy_sandbox(sandbox_id)
    
    # 运行异步任务
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(async_task())
    finally:
        loop.close()

# 使用示例
# execute_automation_task.delay("user123", [
#     {"type": "click", "x": 100, "y": 200},
#     {"type": "type", "text": "Hello World"},
#     {"type": "launch", "app": "firefox"},
#     {"type": "wait", "seconds": 3}
# ])
```

## 监控和统计

```python
# 获取服务统计信息
stats = await client.get_stats()
print(f"活跃沙箱数: {stats['total_active_sandboxes']}")
print(f"用户数: {stats['total_users']}")
print(f"各用户沙箱数: {stats['sandboxes_by_user']}")

# 清理特定用户的所有沙箱
await client.cleanup_user_sandboxes(user_id="user123")

# 清理所有沙箱
await client.cleanup_all_sandboxes()
```

## 最佳实践

### 1. 资源管理

```python
# 推荐：使用上下文管理器确保资源清理
async with VMServiceClient(api_key=api_key) as client:
    sandbox_info = await client.create_sandbox(user_id="user123")
    # 执行操作...
    # 上下文退出时自动清理沙箱

# 或者手动管理
client = VMServiceClient(api_key=api_key)
try:
    sandbox_info = await client.create_sandbox(user_id="user123")
    # 执行操作...
finally:
    await client.cleanup_all_sandboxes()
```

### 2. 错误处理

```python
async def robust_operation(client, sandbox_id):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return await client.screenshot(sandbox_id)
        except VMServiceError as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # 指数退避
```

### 3. 并发控制

```python
import asyncio
from asyncio import Semaphore

# 限制并发操作数量
semaphore = Semaphore(5)  # 最多5个并发操作

async def limited_operation(client, sandbox_id):
    async with semaphore:
        return await client.screenshot(sandbox_id)

# 批量操作
tasks = []
for sandbox_id in sandbox_ids:
    task = asyncio.create_task(limited_operation(client, sandbox_id))
    tasks.append(task)

results = await asyncio.gather(*tasks, return_exceptions=True)
```

### 4. 配置管理

```python
import os
from dataclasses import dataclass

@dataclass
class VMServiceConfig:
    api_key: str = os.environ.get("E2B_API_KEY")
    default_template: str = "desktop"
    max_concurrent_sandboxes: int = 10
    default_timeout: int = 300
    
    def validate(self):
        if not self.api_key:
            raise ValueError("E2B_API_KEY is required")
        if self.max_concurrent_sandboxes < 1:
            raise ValueError("max_concurrent_sandboxes must be >= 1")

# 使用配置
config = VMServiceConfig()
config.validate()

client = VMServiceClient(
    api_key=config.api_key,
    default_template=config.default_template,
    max_concurrent_sandboxes=config.max_concurrent_sandboxes
)
```

## 注意事项

1. **API密钥安全**: 确保E2B API密钥的安全存储，不要在代码中硬编码
2. **资源清理**: 始终确保沙箱被正确销毁，避免资源泄漏
3. **并发限制**: 注意E2B的并发限制，合理设置max_concurrent_sandboxes
4. **错误处理**: 实现完善的错误处理和重试机制
5. **用户隔离**: 确保正确的用户ID传递，维护多租户安全
6. **网络访问**: 根据安全要求配置allow_internet_access
7. **超时设置**: 根据实际需求设置合适的超时时间

## 许可证

MIT License