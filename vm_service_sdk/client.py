"""
VM服务客户端
基于E2B Desktop的统一封装接口，为其他微服务提供VM和Sandbox操作能力
"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any, List, AsyncContextManager
from datetime import datetime
import uuid

# 环境变量加载
try:
    from dotenv import load_dotenv
    # 加载 .env 文件
    load_dotenv()
except ImportError:
    # 如果没有安装 python-dotenv，忽略
    pass

# E2B Desktop 导入
from e2b_desktop import Sandbox as E2BSandbox

from .models import (
    SandboxConfig, SandboxInfo, SandboxStatus, ExecutionResult,
    StreamConfig, MouseAction, KeyboardAction, FileOperation, ApplicationInfo,
    ProcessInfo, EnvironmentInfo, SystemHealth, ConnectionInfo
)
from .exceptions import (
    VMServiceError, SandboxCreationError, SandboxNotFoundError,
    AuthenticationError, QuotaExceededError, FileOperationError,
    ApplicationError, StreamError, ProcessError, EnvironmentError,
    ConnectionError, ResourceLimitError, HealthCheckError
)

logger = logging.getLogger(__name__)


class VMServiceClient:
    """
    VM服务客户端
    
    基于E2B Desktop封装的统一接口，提供：
    - 沙箱生命周期管理
    - 桌面交互操作
    - 文件系统操作  
    - 应用程序管理
    - 流媒体服务
    - 用户隔离和权限控制
    
    使用示例:
        async with VMServiceClient(api_key="your_key") as client:
            # 创建沙箱
            sandbox_info = await client.create_sandbox(
                user_id="user123",
                config=SandboxConfig(template="desktop")
            )
            
            # 桌面操作
            await client.click(sandbox_info.sandbox_id, 100, 200)
            await client.type_text(sandbox_info.sandbox_id, "Hello World")
            
            # 启动流媒体
            stream_url = await client.start_stream(sandbox_info.sandbox_id)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        default_template: str = "desktop",
        max_concurrent_sandboxes: int = 10,
        default_timeout: int = 300
    ):
        """
        初始化VM服务客户端
        
        Args:
            api_key: E2B API密钥，如未提供则从环境变量E2B_API_KEY获取
            default_template: 默认沙箱模板
            max_concurrent_sandboxes: 最大并发沙箱数量
            default_timeout: 默认超时时间（秒）
        """
        # 设置API密钥
        self.api_key = api_key or os.environ.get("E2B_API_KEY")
        if not self.api_key:
            raise AuthenticationError("E2B API key not provided")
        
        # 设置API密钥到环境变量（E2B Desktop需要）
        os.environ["E2B_API_KEY"] = self.api_key
        
        self.default_template = default_template
        self.max_concurrent_sandboxes = max_concurrent_sandboxes
        self.default_timeout = default_timeout
        
        # 内部状态管理
        self._active_sandboxes: Dict[str, E2BSandbox] = {}
        self._sandbox_info: Dict[str, SandboxInfo] = {}
        self._user_sandboxes: Dict[str, List[str]] = {}  # user_id -> sandbox_ids
        self._connections: Dict[str, ConnectionInfo] = {}  # sandbox_id -> connection_info
        
        logger.info(f"VM Service Client initialized with template: {default_template}")
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口 - 清理所有沙箱"""
        await self.cleanup_all_sandboxes()
    
    # ==================== 沙箱生命周期管理 ====================
    
    async def create_sandbox(
        self,
        user_id: str,
        config: Optional[SandboxConfig] = None,
        session_id: Optional[str] = None
    ) -> SandboxInfo:
        """
        创建新的沙箱
        
        Args:
            user_id: 用户ID，用于隔离和权限控制
            config: 沙箱配置，如未提供则使用默认配置
            session_id: 会话ID，可选
            
        Returns:
            SandboxInfo: 沙箱信息
        """
        # 检查用户配额
        await self._check_user_quota(user_id)
        
        # 使用默认配置或提供的配置
        if config is None:
            config = SandboxConfig(template=self.default_template)
        
        config.user_id = user_id
        config.session_id = session_id or str(uuid.uuid4())
        
        sandbox_id = f"{user_id}-{config.session_id}"
        
        try:
            logger.info(f"Creating sandbox for user {user_id} with config: {config.to_e2b_kwargs()}")
            
            # 创建E2B Desktop沙箱 - 根据E2B.md文档
            # 基础创建: desktop = Sandbox()
            e2b_kwargs = config.to_e2b_kwargs()
            if e2b_kwargs:
                # 有配置参数时传入
                e2b_sandbox = E2BSandbox(**e2b_kwargs)
                logger.info(f"E2B Sandbox created with config: {e2b_kwargs}")
            else:
                # 使用默认配置：desktop = Sandbox()
                e2b_sandbox = E2BSandbox()
                logger.info("E2B Sandbox created with default config")
            
            # E2B Desktop沙箱创建后会自动启动，无需手动等待
            logger.info("E2B Desktop sandbox created and started")
            
            # 保存沙箱实例
            self._active_sandboxes[sandbox_id] = e2b_sandbox
            
            # 创建沙箱信息
            sandbox_info = SandboxInfo(
                sandbox_id=sandbox_id,
                status=SandboxStatus.RUNNING,
                config=config,
                created_at=datetime.now(),
                user_id=user_id,
                session_id=config.session_id
            )
            
            self._sandbox_info[sandbox_id] = sandbox_info
            
            # 记录用户的沙箱
            if user_id not in self._user_sandboxes:
                self._user_sandboxes[user_id] = []
            self._user_sandboxes[user_id].append(sandbox_id)
            
            # 创建连接信息
            self._connections[sandbox_id] = ConnectionInfo(
                sandbox_id=sandbox_id,
                connected_at=datetime.now(),
                last_activity=datetime.now(),
                is_active=True,
                connection_type="desktop"
            )
            
            logger.info(f"Sandbox {sandbox_id} created successfully for user {user_id}")
            return sandbox_info
            
        except Exception as e:
            logger.error(f"Failed to create sandbox for user {user_id}: {str(e)}")
            raise SandboxCreationError(
                f"Failed to create sandbox: {str(e)}",
                user_id=user_id,
                details={"config": config.to_e2b_kwargs()}
            )
    
    async def get_sandbox_info(self, sandbox_id: str) -> SandboxInfo:
        """获取沙箱信息"""
        if sandbox_id not in self._sandbox_info:
            raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found")
        return self._sandbox_info[sandbox_id]
    
    async def destroy_sandbox(self, sandbox_id: str) -> None:
        """销毁沙箱"""
        if sandbox_id not in self._active_sandboxes:
            raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found")
        
        try:
            # 关闭E2B沙箱
            e2b_sandbox = self._active_sandboxes[sandbox_id]
            # E2B Desktop沙箱通常会自动管理生命周期
            # 如果有close方法则调用，否则依靠垃圾回收
            if hasattr(e2b_sandbox, 'close'):
                e2b_sandbox.close()
            elif hasattr(e2b_sandbox, 'kill'):
                e2b_sandbox.kill()
            # E2B Desktop可能使用上下文管理或自动清理
            
            # 清理内部状态
            del self._active_sandboxes[sandbox_id]
            
            if sandbox_id in self._sandbox_info:
                sandbox_info = self._sandbox_info[sandbox_id]
                user_id = sandbox_info.user_id
                
                # 从用户沙箱列表中移除
                if user_id in self._user_sandboxes:
                    self._user_sandboxes[user_id].remove(sandbox_id)
                    if not self._user_sandboxes[user_id]:
                        del self._user_sandboxes[user_id]
                
                del self._sandbox_info[sandbox_id]
            
            # 清理连接信息
            if sandbox_id in self._connections:
                del self._connections[sandbox_id]
            
            logger.info(f"Sandbox {sandbox_id} destroyed successfully")
            
        except Exception as e:
            logger.error(f"Error destroying sandbox {sandbox_id}: {str(e)}")
            raise VMServiceError(f"Failed to destroy sandbox: {str(e)}", sandbox_id=sandbox_id)
    
    async def list_user_sandboxes(self, user_id: str) -> List[SandboxInfo]:
        """列出用户的所有沙箱"""
        sandbox_ids = self._user_sandboxes.get(user_id, [])
        return [self._sandbox_info[sid] for sid in sandbox_ids if sid in self._sandbox_info]
    
    # ==================== 桌面交互操作 ====================
    
    async def click(
        self,
        sandbox_id: str,
        x: int,
        y: int,
        button: str = "left",
        double_click: bool = False
    ) -> None:
        """
        鼠标点击
        
        Args:
            sandbox_id: 沙箱ID
            x: X坐标
            y: Y坐标  
            button: 鼠标按钮 ("left", "right", "middle")
            double_click: 是否双击
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        
        try:
            if double_click:
                e2b_sandbox.double_click()
            elif button == "left":
                e2b_sandbox.left_click(x=x, y=y)
            elif button == "right":
                e2b_sandbox.right_click()  # E2B right_click不需要坐标
            else:
                # 先移动到位置，再点击
                e2b_sandbox.move_mouse(x, y)
                e2b_sandbox.left_click(x=x, y=y)  # 通用点击
                
        except Exception as e:
            raise VMServiceError(f"Click operation failed: {str(e)}", sandbox_id=sandbox_id)
    
    async def move_mouse(self, sandbox_id: str, x: int, y: int) -> None:
        """移动鼠标"""
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            e2b_sandbox.move_mouse(x, y)
        except Exception as e:
            raise VMServiceError(f"Mouse move failed: {str(e)}", sandbox_id=sandbox_id)
    
    async def drag(
        self,
        sandbox_id: str,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int
    ) -> None:
        """拖拽操作"""
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            e2b_sandbox.drag((from_x, from_y), (to_x, to_y))
        except Exception as e:
            raise VMServiceError(f"Drag operation failed: {str(e)}", sandbox_id=sandbox_id)
    
    async def scroll(self, sandbox_id: str, direction: int, amount: int = 3) -> None:
        """
        滚动操作
        
        Args:
            sandbox_id: 沙箱ID
            direction: 滚动方向 (正数向上，负数向下)
            amount: 滚动量
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            # E2B Desktop的scroll方法，正数向上滚动
            e2b_sandbox.scroll(direction * amount)
        except Exception as e:
            raise VMServiceError(f"Scroll operation failed: {str(e)}", sandbox_id=sandbox_id)
    
    # ==================== 键盘操作 ====================
    
    async def type_text(
        self,
        sandbox_id: str,
        text: str,
        chunk_size: int = 25,
        delay_ms: int = 75
    ) -> None:
        """
        输入文本
        
        Args:
            sandbox_id: 沙箱ID
            text: 要输入的文本
            chunk_size: 输入块大小
            delay_ms: 延迟毫秒
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            e2b_sandbox.write(text, chunk_size=chunk_size, delay_in_ms=delay_ms)
        except Exception as e:
            raise VMServiceError(f"Text input failed: {str(e)}", sandbox_id=sandbox_id)
    
    async def press_key(self, sandbox_id: str, key: str) -> None:
        """按单个按键"""
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            e2b_sandbox.press(key)
        except Exception as e:
            raise VMServiceError(f"Key press failed: {str(e)}", sandbox_id=sandbox_id)
    
    async def press_key_combination(
        self,
        sandbox_id: str,
        keys: List[str]
    ) -> None:
        """
        按键组合
        
        Args:
            sandbox_id: 沙箱ID  
            keys: 按键列表，如 ["ctrl", "c"]
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            e2b_sandbox.press(keys)
        except Exception as e:
            raise VMServiceError(f"Key combination failed: {str(e)}", sandbox_id=sandbox_id)
    
    # ==================== 截图和流媒体 ====================
    
    async def screenshot(self, sandbox_id: str) -> bytes:
        """获取截图"""
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            return e2b_sandbox.screenshot()
        except Exception as e:
            raise VMServiceError(f"Screenshot failed: {str(e)}", sandbox_id=sandbox_id)
    
    async def start_stream(
        self,
        sandbox_id: str,
        config: Optional[StreamConfig] = None
    ) -> tuple[str, str]:
        """
        启动流媒体
        
        Args:
            sandbox_id: 沙箱ID
            config: 流媒体配置
            
        Returns:
            tuple[str, str]: (stream_url, auth_key)
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        config = config or StreamConfig()
        
        try:
            # 启动流媒体
            e2b_sandbox.stream.start(
                window_id=config.window_id,
                require_auth=config.require_auth
            )
            
            # 获取认证密钥和URL
            auth_key = e2b_sandbox.stream.get_auth_key()
            stream_url = e2b_sandbox.stream.get_url(auth_key=auth_key)
            
            # 更新沙箱信息
            if sandbox_id in self._sandbox_info:
                self._sandbox_info[sandbox_id].stream_url = stream_url
                self._sandbox_info[sandbox_id].auth_key = auth_key
            
            return stream_url, auth_key
            
        except Exception as e:
            raise StreamError(f"Failed to start stream: {str(e)}", sandbox_id=sandbox_id)
    
    async def stop_stream(self, sandbox_id: str) -> None:
        """
        停止流媒体
        
        Args:
            sandbox_id: 沙箱ID
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            # E2B Desktop的流媒体停止方法
            if hasattr(e2b_sandbox.stream, 'stop'):
                e2b_sandbox.stream.stop()
            else:
                # 如果没有直接的停止方法，可以通过重新启动流来实现
                logger.warning(f"Stream stop method not available for sandbox {sandbox_id}")
            
            # 清理沙箱信息中的流媒体URL
            if sandbox_id in self._sandbox_info:
                self._sandbox_info[sandbox_id].stream_url = None
                self._sandbox_info[sandbox_id].auth_key = None
                
        except Exception as e:
            raise StreamError(f"Failed to stop stream: {str(e)}", sandbox_id=sandbox_id)
    
    async def get_stream_status(self, sandbox_id: str) -> Dict[str, Any]:
        """
        获取流媒体状态
        
        Args:
            sandbox_id: 沙箱ID
            
        Returns:
            Dict[str, Any]: 流媒体状态信息
        """
        try:
            sandbox_info = self._sandbox_info.get(sandbox_id)
            if not sandbox_info:
                raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found")
            
            is_streaming = bool(sandbox_info.stream_url)
            
            return {
                "is_streaming": is_streaming,
                "stream_url": sandbox_info.stream_url,
                "has_auth_key": bool(sandbox_info.auth_key),
                "sandbox_status": sandbox_info.status.value
            }
            
        except Exception as e:
            raise StreamError(f"Failed to get stream status: {str(e)}", sandbox_id=sandbox_id)
    
    # ==================== 文件操作 ====================
    
    async def write_file(
        self,
        sandbox_id: str,
        file_path: str,
        content: str,
        encoding: str = "utf-8"
    ) -> None:
        """写文件"""
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            e2b_sandbox.files.write(file_path, content)
        except Exception as e:
            raise FileOperationError(
                f"Write file failed: {str(e)}",
                file_path=file_path,
                operation="write",
                sandbox_id=sandbox_id
            )
    
    async def read_file(
        self,
        sandbox_id: str,
        file_path: str,
        encoding: str = "utf-8"
    ) -> str:
        """读文件"""
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            return e2b_sandbox.files.read(file_path)
        except Exception as e:
            raise FileOperationError(
                f"Read file failed: {str(e)}",
                file_path=file_path,
                operation="read", 
                sandbox_id=sandbox_id
            )
    
    async def open_file(self, sandbox_id: str, file_path: str) -> None:
        """打开文件（使用默认程序）"""
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            e2b_sandbox.open(file_path)
        except Exception as e:
            raise FileOperationError(
                f"Open file failed: {str(e)}",
                file_path=file_path,
                operation="open",
                sandbox_id=sandbox_id
            )
    
    async def list_files(self, sandbox_id: str, path: str = "/home/user") -> List[Dict[str, Any]]:
        """
        列出目录内容
        
        Args:
            sandbox_id: 沙箱ID
            path: 目录路径
            
        Returns:
            List[Dict[str, Any]]: 文件列表，每个文件包含 name, type, size 等信息
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            # 使用 ls 命令获取详细文件信息
            result = e2b_sandbox.commands.run(f"ls -la '{path}'")
            if result.exit_code != 0:
                raise Exception(f"Directory listing failed: {result.stderr}")
            
            files = []
            lines = result.stdout.strip().split('\n')[1:]  # 跳过第一行总计信息
            
            for line in lines:
                if not line.strip():
                    continue
                    
                parts = line.split(None, 8)  # 最多分割为9部分
                if len(parts) >= 9:
                    permissions = parts[0]
                    size = parts[4]
                    name = parts[8]
                    
                    # 跳过 . 和 .. 目录
                    if name in ['.', '..']:
                        continue
                    
                    file_info = {
                        "name": name,
                        "type": "directory" if permissions.startswith('d') else "file",
                        "size": int(size) if size.isdigit() else 0,
                        "permissions": permissions,
                        "full_path": f"{path.rstrip('/')}/{name}"
                    }
                    files.append(file_info)
            
            return files
            
        except Exception as e:
            raise FileOperationError(
                f"List files failed: {str(e)}",
                file_path=path,
                operation="list",
                sandbox_id=sandbox_id
            )
    
    async def delete_file(self, sandbox_id: str, path: str) -> None:
        """
        删除文件或目录
        
        Args:
            sandbox_id: 沙箱ID
            path: 要删除的文件或目录路径
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            # 使用 rm 命令删除，-rf 参数用于递归删除目录
            result = e2b_sandbox.commands.run(f"rm -rf '{path}'")
            if result.exit_code != 0:
                raise Exception(f"Delete failed: {result.stderr}")
                
        except Exception as e:
            raise FileOperationError(
                f"Delete file failed: {str(e)}",
                file_path=path,
                operation="delete",
                sandbox_id=sandbox_id
            )
    
    async def file_exists(self, sandbox_id: str, path: str) -> bool:
        """
        检查文件或目录是否存在
        
        Args:
            sandbox_id: 沙箱ID
            path: 文件或目录路径
            
        Returns:
            bool: 文件是否存在
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            result = e2b_sandbox.commands.run(f"test -e '{path}'")
            return result.exit_code == 0
            
        except Exception as e:
            logger.warning(f"File exists check failed for {path}: {str(e)}")
            return False
    
    async def upload_file(
        self, 
        sandbox_id: str, 
        local_path: str, 
        remote_path: str
    ) -> None:
        """
        上传文件到沙箱
        
        Args:
            sandbox_id: 沙箱ID
            local_path: 本地文件路径
            remote_path: 远程文件路径
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            # 读取本地文件
            with open(local_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 写入到远程
            e2b_sandbox.files.write(remote_path, content)
            
        except Exception as e:
            raise FileOperationError(
                f"Upload file failed: {str(e)}",
                file_path=f"{local_path} -> {remote_path}",
                operation="upload",
                sandbox_id=sandbox_id
            )
    
    async def download_file(
        self, 
        sandbox_id: str, 
        remote_path: str, 
        local_path: str
    ) -> None:
        """
        从沙箱下载文件
        
        Args:
            sandbox_id: 沙箱ID
            remote_path: 远程文件路径
            local_path: 本地文件路径
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            # 从远程读取
            content = e2b_sandbox.files.read(remote_path)
            
            # 写入到本地
            with open(local_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
        except Exception as e:
            raise FileOperationError(
                f"Download file failed: {str(e)}",
                file_path=f"{remote_path} -> {local_path}",
                operation="download",
                sandbox_id=sandbox_id
            )
    
    async def create_directory(self, sandbox_id: str, path: str) -> None:
        """
        创建目录
        
        Args:
            sandbox_id: 沙箱ID
            path: 目录路径
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            result = e2b_sandbox.commands.run(f"mkdir -p '{path}'")
            if result.exit_code != 0:
                raise Exception(f"Create directory failed: {result.stderr}")
                
        except Exception as e:
            raise FileOperationError(
                f"Create directory failed: {str(e)}",
                file_path=path,
                operation="mkdir",
                sandbox_id=sandbox_id
            )
    
    # ==================== 进程管理 ====================
    
    async def list_processes(self, sandbox_id: str) -> List[ProcessInfo]:
        """
        列出运行中的进程
        
        Args:
            sandbox_id: 沙箱ID
            
        Returns:
            List[ProcessInfo]: 进程信息列表
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            # 使用 ps 命令获取进程信息
            result = e2b_sandbox.commands.run("ps aux")
            if result.exit_code != 0:
                raise Exception(f"Process listing failed: {result.stderr}")
            
            processes = []
            lines = result.stdout.strip().split('\n')[1:]  # 跳过标题行
            
            for line in lines:
                if not line.strip():
                    continue
                    
                parts = line.split(None, 10)  # 最多分割为11部分
                if len(parts) >= 11:
                    process_info = ProcessInfo(
                        pid=int(parts[1]),
                        user=parts[0],
                        cpu_percent=float(parts[2]) if parts[2] != '0.0' else 0.0,
                        memory_percent=float(parts[3]) if parts[3] != '0.0' else 0.0,
                        command=parts[10],
                        status="running"
                    )
                    processes.append(process_info)
            
            return processes
            
        except Exception as e:
            raise VMServiceError(f"List processes failed: {str(e)}", sandbox_id=sandbox_id)
    
    async def kill_process(self, sandbox_id: str, pid: int, signal: str = "TERM") -> None:
        """
        杀死进程
        
        Args:
            sandbox_id: 沙箱ID
            pid: 进程ID
            signal: 信号类型 (TERM, KILL, INT 等)
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            result = e2b_sandbox.commands.run(f"kill -{signal} {pid}")
            if result.exit_code != 0:
                # 进程可能已经不存在，这不算错误
                if "No such process" not in result.stderr:
                    raise Exception(f"Kill process failed: {result.stderr}")
                    
        except Exception as e:
            raise VMServiceError(f"Kill process failed: {str(e)}", sandbox_id=sandbox_id)
    
    async def get_process_info(self, sandbox_id: str, pid: int) -> Optional[ProcessInfo]:
        """
        获取特定进程的信息
        
        Args:
            sandbox_id: 沙箱ID
            pid: 进程ID
            
        Returns:
            Optional[ProcessInfo]: 进程信息，如果进程不存在则返回None
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            result = e2b_sandbox.commands.run(f"ps -p {pid} -o user,pid,%cpu,%mem,comm --no-headers")
            if result.exit_code != 0:
                return None  # 进程不存在
            
            line = result.stdout.strip()
            if not line:
                return None
                
            parts = line.split(None, 4)
            if len(parts) >= 5:
                return ProcessInfo(
                    pid=int(parts[1]),
                    user=parts[0],
                    cpu_percent=float(parts[2]) if parts[2] != '0.0' else 0.0,
                    memory_percent=float(parts[3]) if parts[3] != '0.0' else 0.0,
                    command=parts[4],
                    status="running"
                )
            
            return None
            
        except Exception as e:
            logger.warning(f"Get process info failed for PID {pid}: {str(e)}")
            return None
    
    # ==================== 环境管理 ====================
    
    async def set_environment_variable(
        self, 
        sandbox_id: str, 
        key: str, 
        value: str
    ) -> None:
        """
        设置环境变量
        
        Args:
            sandbox_id: 沙箱ID
            key: 环境变量名
            value: 环境变量值
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            # 设置环境变量到 .bashrc 文件以持久化
            result = e2b_sandbox.commands.run(
                f"echo 'export {key}=\"{value}\"' >> ~/.bashrc"
            )
            if result.exit_code != 0:
                raise Exception(f"Set environment variable failed: {result.stderr}")
            
            # 同时为当前会话设置
            e2b_sandbox.commands.run(f"export {key}=\"{value}\"")
            
        except Exception as e:
            raise VMServiceError(
                f"Set environment variable failed: {str(e)}", 
                sandbox_id=sandbox_id
            )
    
    async def get_environment_variable(
        self, 
        sandbox_id: str, 
        key: str
    ) -> Optional[str]:
        """
        获取环境变量
        
        Args:
            sandbox_id: 沙箱ID
            key: 环境变量名
            
        Returns:
            Optional[str]: 环境变量值，如果不存在则返回None
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            result = e2b_sandbox.commands.run(f"echo ${key}")
            if result.exit_code == 0 and result.stdout.strip():
                return result.stdout.strip()
            return None
            
        except Exception as e:
            logger.warning(f"Get environment variable failed for {key}: {str(e)}")
            return None
    
    async def get_environment(self, sandbox_id: str) -> EnvironmentInfo:
        """
        获取所有环境变量
        
        Args:
            sandbox_id: 沙箱ID
            
        Returns:
            EnvironmentInfo: 环境信息
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            # 获取所有环境变量
            result = e2b_sandbox.commands.run("env")
            if result.exit_code != 0:
                raise Exception(f"Get environment failed: {result.stderr}")
            
            variables = {}
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    variables[key] = value
            
            # 获取系统信息
            os_info_result = e2b_sandbox.commands.run("uname -a")
            os_info = os_info_result.stdout.strip() if os_info_result.exit_code == 0 else "Unknown"
            
            return EnvironmentInfo(
                variables=variables,
                working_directory=variables.get('PWD', '/home/user'),
                home_directory=variables.get('HOME', '/home/user'),
                user=variables.get('USER', 'user'),
                os_info=os_info
            )
            
        except Exception as e:
            raise VMServiceError(f"Get environment failed: {str(e)}", sandbox_id=sandbox_id)
    
    # ==================== 应用程序管理 ====================
    
    async def launch_application(self, sandbox_id: str, app_name: str) -> None:
        """
        启动应用程序
        
        Args:
            sandbox_id: 沙箱ID
            app_name: 应用名称 (如 'google-chrome', 'firefox', 'vscode')
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            e2b_sandbox.launch(app_name)
        except Exception as e:
            raise ApplicationError(
                f"Launch application failed: {str(e)}",
                app_name=app_name,
                sandbox_id=sandbox_id
            )
    
    async def get_current_window_id(self, sandbox_id: str) -> str:
        """获取当前窗口ID"""
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            return e2b_sandbox.get_current_window_id()
        except Exception as e:
            raise VMServiceError(f"Get window ID failed: {str(e)}", sandbox_id=sandbox_id)
    
    async def get_application_windows(self, sandbox_id: str, app_name: str) -> List[str]:
        """获取应用程序的所有窗口ID"""
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            return e2b_sandbox.get_application_windows(app_name)
        except Exception as e:
            raise ApplicationError(
                f"Get application windows failed: {str(e)}",
                app_name=app_name,
                sandbox_id=sandbox_id
            )
    
    # ==================== 命令执行 ====================
    
    async def run_command(
        self,
        sandbox_id: str,
        command: str,
        timeout: Optional[int] = None
    ) -> ExecutionResult:
        """
        执行命令
        
        Args:
            sandbox_id: 沙箱ID
            command: 要执行的命令
            timeout: 超时时间（秒）
            
        Returns:
            ExecutionResult: 执行结果
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        
        start_time = datetime.now()
        try:
            # E2B Desktop的命令执行
            result = e2b_sandbox.commands.run(command)
            end_time = datetime.now()
            
            return ExecutionResult(
                success=result.exit_code == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
                execution_time=(end_time - start_time).total_seconds(),
                timestamp=start_time
            )
            
        except Exception as e:
            end_time = datetime.now()
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                execution_time=(end_time - start_time).total_seconds(),
                timestamp=start_time
            )
    
    # ==================== 内部辅助方法 ====================
    
    def _get_sandbox(self, sandbox_id: str) -> E2BSandbox:
        """获取E2B沙箱实例"""
        if sandbox_id not in self._active_sandboxes:
            raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found or not active")
        
        # 更新连接活动时间
        asyncio.create_task(self.update_connection_activity(sandbox_id))
        
        return self._active_sandboxes[sandbox_id]
    
    def _map_e2b_exception(self, e: Exception, context: str = "") -> VMServiceError:
        """
        将E2B异常映射为VM服务异常
        
        Args:
            e: E2B异常
            context: 上下文信息
            
        Returns:
            VMServiceError: 映射后的VM服务异常
        """
        error_msg = str(e)
        error_type = type(e).__name__
        
        # 根据错误类型和消息内容进行映射
        if "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
            return AuthenticationError(f"E2B authentication failed: {error_msg}")
        elif "quota" in error_msg.lower() or "limit" in error_msg.lower():
            return QuotaExceededError(f"E2B quota exceeded: {error_msg}", quota_type="unknown", current_usage=0, limit=0)
        elif "timeout" in error_msg.lower():
            return SandboxTimeoutError(f"E2B operation timeout: {error_msg}", timeout_seconds=0)
        elif "network" in error_msg.lower() or "connection" in error_msg.lower():
            return NetworkError(f"E2B network error: {error_msg}")
        elif "file" in error_msg.lower() or "directory" in error_msg.lower():
            return FileOperationError(f"E2B file operation failed: {error_msg}", file_path="unknown", operation=context)
        elif "process" in error_msg.lower():
            return ProcessError(f"E2B process operation failed: {error_msg}")
        else:
            return VMServiceError(f"E2B {error_type}: {error_msg} (context: {context})")
    
    async def _execute_with_retry(
        self,
        operation: callable,
        max_retries: int = 3,
        delay_seconds: float = 1.0,
        context: str = ""
    ):
        """
        执行操作并在失败时重试
        
        Args:
            operation: 要执行的操作函数
            max_retries: 最大重试次数
            delay_seconds: 重试延迟
            context: 操作上下文
            
        Returns:
            操作结果
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return await operation() if asyncio.iscoroutinefunction(operation) else operation()
            except Exception as e:
                last_exception = e
                
                if attempt < max_retries:
                    logger.warning(f"Operation failed (attempt {attempt + 1}/{max_retries + 1}): {str(e)}")
                    await asyncio.sleep(delay_seconds * (2 ** attempt))  # 指数退避
                else:
                    logger.error(f"Operation failed after {max_retries + 1} attempts: {str(e)}")
        
        # 所有重试都失败，抛出最后一个异常
        raise self._map_e2b_exception(last_exception, context)
    
    async def _check_user_quota(self, user_id: str) -> None:
        """检查用户配额"""
        user_sandboxes = self._user_sandboxes.get(user_id, [])
        if len(user_sandboxes) >= self.max_concurrent_sandboxes:
            raise QuotaExceededError(
                f"User {user_id} has reached maximum concurrent sandboxes limit",
                quota_type="concurrent_sandboxes",
                current_usage=len(user_sandboxes),
                limit=self.max_concurrent_sandboxes,
                user_id=user_id
            )
    
    async def cleanup_all_sandboxes(self) -> None:
        """清理所有沙箱"""
        sandbox_ids = list(self._active_sandboxes.keys())
        for sandbox_id in sandbox_ids:
            try:
                await self.destroy_sandbox(sandbox_id)
            except Exception as e:
                logger.error(f"Error cleaning up sandbox {sandbox_id}: {str(e)}")
    
    # ==================== 批量操作 ====================
    
    async def cleanup_user_sandboxes(self, user_id: str) -> None:
        """清理用户的所有沙箱"""
        user_sandboxes = self._user_sandboxes.get(user_id, []).copy()
        for sandbox_id in user_sandboxes:
            try:
                await self.destroy_sandbox(sandbox_id)
            except Exception as e:
                logger.error(f"Error cleaning up user sandbox {sandbox_id}: {str(e)}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        return {
            "total_active_sandboxes": len(self._active_sandboxes),
            "total_users": len(self._user_sandboxes),
            "sandboxes_by_user": {
                user_id: len(sandbox_ids) 
                for user_id, sandbox_ids in self._user_sandboxes.items()
            },
            "api_key_configured": bool(self.api_key),
            "default_template": self.default_template,
            "max_concurrent_sandboxes": self.max_concurrent_sandboxes,
            "active_connections": len([c for c in self._connections.values() if c.is_active])
        }
    
    # ==================== 健康监控 ====================
    
    async def get_system_health(self, sandbox_id: str) -> SystemHealth:
        """
        获取系统健康状态
        
        Args:
            sandbox_id: 沙箱ID
            
        Returns:
            SystemHealth: 系统健康信息
        """
        e2b_sandbox = self._get_sandbox(sandbox_id)
        try:
            # 获取CPU使用率
            cpu_result = e2b_sandbox.commands.run("top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'")
            cpu_usage = float(cpu_result.stdout.strip()) if cpu_result.exit_code == 0 and cpu_result.stdout.strip() else 0.0
            
            # 获取内存使用情况
            memory_result = e2b_sandbox.commands.run("free | grep Mem | awk '{printf \"%.1f %.1f %.1f\", ($3/$2)*100, $2/1024, $7/1024}'")
            memory_info = memory_result.stdout.strip().split() if memory_result.exit_code == 0 else ["0", "0", "0"]
            memory_usage = float(memory_info[0]) if len(memory_info) > 0 else 0.0
            total_memory = int(float(memory_info[1])) if len(memory_info) > 1 else 0
            available_memory = int(float(memory_info[2])) if len(memory_info) > 2 else 0
            
            # 获取磁盘使用率
            disk_result = e2b_sandbox.commands.run("df / | tail -1 | awk '{print $5}' | sed 's/%//'")
            disk_usage = float(disk_result.stdout.strip()) if disk_result.exit_code == 0 and disk_result.stdout.strip() else 0.0
            
            # 获取系统负载
            load_result = e2b_sandbox.commands.run("uptime | awk -F'load average:' '{print $2}'")
            load_str = load_result.stdout.strip() if load_result.exit_code == 0 else "0, 0, 0"
            load_average = [float(x.strip()) for x in load_str.split(',')[:3]]
            
            # 获取系统运行时间
            uptime_result = e2b_sandbox.commands.run("cat /proc/uptime | awk '{print $1}'")
            uptime_seconds = int(float(uptime_result.stdout.strip())) if uptime_result.exit_code == 0 and uptime_result.stdout.strip() else 0
            
            # 获取活跃进程数
            ps_result = e2b_sandbox.commands.run("ps aux | wc -l")
            active_processes = int(ps_result.stdout.strip()) - 1 if ps_result.exit_code == 0 and ps_result.stdout.strip() else 0
            
            # 检查网络连通性
            network_result = e2b_sandbox.commands.run("ping -c 1 8.8.8.8 >/dev/null 2>&1 && echo 'active' || echo 'inactive'")
            network_active = network_result.stdout.strip() == 'active' if network_result.exit_code == 0 else False
            
            return SystemHealth(
                cpu_usage_percent=cpu_usage,
                memory_usage_percent=memory_usage,
                disk_usage_percent=disk_usage,
                network_active=network_active,
                uptime_seconds=uptime_seconds,
                load_average=load_average,
                active_processes=active_processes,
                total_memory_mb=total_memory,
                available_memory_mb=available_memory
            )
            
        except Exception as e:
            raise HealthCheckError(f"System health check failed: {str(e)}", check_type="system", sandbox_id=sandbox_id)
    
    async def check_sandbox_health(self, sandbox_id: str) -> Dict[str, Any]:
        """
        检查沙箱健康状态
        
        Args:
            sandbox_id: 沙箱ID
            
        Returns:
            Dict[str, Any]: 健康检查结果
        """
        try:
            health_status = {
                "sandbox_id": sandbox_id,
                "is_active": sandbox_id in self._active_sandboxes,
                "connection_active": False,
                "last_activity": None,
                "system_health": None,
                "issues": []
            }
            
            # 检查连接状态
            if sandbox_id in self._connections:
                connection = self._connections[sandbox_id]
                health_status["connection_active"] = connection.is_active
                health_status["last_activity"] = connection.last_activity.isoformat()
                
                # 检查连接是否超时（5分钟无活动）
                inactive_duration = (datetime.now() - connection.last_activity).total_seconds()
                if inactive_duration > 300:  # 5分钟
                    health_status["issues"].append(f"Connection inactive for {inactive_duration:.0f} seconds")
            
            # 如果沙箱是活跃的，获取系统健康信息
            if health_status["is_active"]:
                try:
                    system_health = await self.get_system_health(sandbox_id)
                    health_status["system_health"] = {
                        "cpu_usage": system_health.cpu_usage_percent,
                        "memory_usage": system_health.memory_usage_percent,
                        "disk_usage": system_health.disk_usage_percent,
                        "network_active": system_health.network_active,
                        "uptime": system_health.uptime_seconds
                    }
                    
                    # 检查资源使用是否过高
                    if system_health.cpu_usage_percent > 90:
                        health_status["issues"].append(f"High CPU usage: {system_health.cpu_usage_percent:.1f}%")
                    if system_health.memory_usage_percent > 90:
                        health_status["issues"].append(f"High memory usage: {system_health.memory_usage_percent:.1f}%")
                    if system_health.disk_usage_percent > 90:
                        health_status["issues"].append(f"High disk usage: {system_health.disk_usage_percent:.1f}%")
                        
                except Exception as e:
                    health_status["issues"].append(f"Failed to get system health: {str(e)}")
            else:
                health_status["issues"].append("Sandbox is not active")
            
            health_status["healthy"] = len(health_status["issues"]) == 0
            return health_status
            
        except Exception as e:
            raise HealthCheckError(f"Sandbox health check failed: {str(e)}", check_type="sandbox", sandbox_id=sandbox_id)
    
    # ==================== 连接管理 ====================
    
    async def update_connection_activity(self, sandbox_id: str) -> None:
        """
        更新连接活动时间
        
        Args:
            sandbox_id: 沙箱ID
        """
        if sandbox_id in self._connections:
            self._connections[sandbox_id].last_activity = datetime.now()
    
    async def get_connection_info(self, sandbox_id: str) -> Optional[ConnectionInfo]:
        """
        获取连接信息
        
        Args:
            sandbox_id: 沙箱ID
            
        Returns:
            Optional[ConnectionInfo]: 连接信息
        """
        return self._connections.get(sandbox_id)
    
    async def close_connection(self, sandbox_id: str) -> None:
        """
        关闭连接
        
        Args:
            sandbox_id: 沙箱ID
        """
        if sandbox_id in self._connections:
            self._connections[sandbox_id].is_active = False
            logger.info(f"Connection closed for sandbox {sandbox_id}")
    
    async def cleanup_inactive_connections(self, timeout_minutes: int = 30) -> List[str]:
        """
        清理非活跃连接
        
        Args:
            timeout_minutes: 超时时间（分钟）
            
        Returns:
            List[str]: 被清理的沙箱ID列表
        """
        cleaned_sandboxes = []
        current_time = datetime.now()
        
        for sandbox_id, connection in list(self._connections.items()):
            if not connection.is_active:
                continue
                
            inactive_duration = (current_time - connection.last_activity).total_seconds()
            if inactive_duration > timeout_minutes * 60:
                try:
                    await self.destroy_sandbox(sandbox_id)
                    cleaned_sandboxes.append(sandbox_id)
                    logger.info(f"Cleaned up inactive sandbox {sandbox_id} after {inactive_duration:.0f}s")
                except Exception as e:
                    logger.error(f"Failed to cleanup sandbox {sandbox_id}: {str(e)}")
        
        return cleaned_sandboxes