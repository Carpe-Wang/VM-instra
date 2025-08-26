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

# E2B Desktop 导入
from e2b_desktop import Sandbox as E2BSandbox

from .models import (
    SandboxConfig, SandboxInfo, SandboxStatus, ExecutionResult,
    StreamConfig, MouseAction, KeyboardAction, FileOperation, ApplicationInfo
)
from .exceptions import (
    VMServiceError, SandboxCreationError, SandboxNotFoundError,
    AuthenticationError, QuotaExceededError, FileOperationError,
    ApplicationError, StreamError
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
        return self._active_sandboxes[sandbox_id]
    
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
            "max_concurrent_sandboxes": self.max_concurrent_sandboxes
        }