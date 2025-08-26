"""
数据模型定义
基于E2B Desktop API的数据结构
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SandboxStatus(str, Enum):
    """沙箱状态"""
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class SandboxConfig:
    """沙箱配置 - 基于E2B Desktop Sandbox构造参数"""
    
    # E2B Desktop原生参数
    template: str = "desktop"  # E2B模板名称
    cpu_count: Optional[int] = None  # CPU核心数 (1-8)
    memory_mb: Optional[int] = None  # 内存大小MB (512-8192)
    timeout_seconds: Optional[int] = None  # 超时时间秒
    
    # 网络和安全配置
    allow_internet_access: bool = True  # 是否允许互联网访问
    
    # 用户隔离配置
    user_id: Optional[str] = None  # 用户ID，用于多租户隔离
    session_id: Optional[str] = None  # 会话ID
    
    # 环境变量和工作目录
    environment: Dict[str, str] = field(default_factory=dict)
    working_directory: str = "/home/user"
    
    def to_e2b_kwargs(self) -> Dict[str, Any]:
        """转换为E2B Desktop Sandbox的构造参数"""
        # 根据E2B.md文档，基础的Sandbox()不需要参数
        # 但支持以下可选参数
        kwargs = {}
        
        # 模板参数（如果不是默认desktop）
        if self.template != "desktop":
            kwargs["template"] = self.template
        
        # CPU配置：1-8个vCPU
        if self.cpu_count is not None:
            kwargs["cpu_count"] = self.cpu_count
            
        # 内存配置：512MB-8GB
        if self.memory_mb is not None:
            kwargs["memory_mb"] = self.memory_mb
            
        # 超时设置：几秒到24小时
        if self.timeout_seconds is not None:
            kwargs["timeout_seconds"] = self.timeout_seconds
            
        # 返回非空参数字典，如果为空则返回None表示使用默认配置
        return kwargs if kwargs else None


@dataclass
class SandboxInfo:
    """沙箱信息"""
    sandbox_id: str
    status: SandboxStatus
    config: SandboxConfig
    created_at: datetime
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    stream_url: Optional[str] = None
    auth_key: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """命令执行结果"""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class StreamConfig:
    """流媒体配置"""
    window_id: Optional[str] = None  # 特定窗口ID，None表示全桌面
    require_auth: bool = True  # 是否需要认证
    quality: str = "medium"  # 流媒体质量: low, medium, high
    frame_rate: int = 30  # 帧率


@dataclass
class MouseAction:
    """鼠标动作"""
    action_type: str  # click, move, drag, scroll
    x: int
    y: int
    button: Optional[str] = "left"  # left, right, middle
    target_x: Optional[int] = None  # 拖拽目标x（仅拖拽时使用）
    target_y: Optional[int] = None  # 拖拽目标y（仅拖拽时使用）
    scroll_direction: Optional[int] = None  # 滚动方向（仅滚动时使用）


@dataclass
class KeyboardAction:
    """键盘动作"""
    action_type: str  # type, press, press_combination
    text: Optional[str] = None  # 输入的文本
    key: Optional[str] = None  # 单个按键
    key_combination: Optional[List[str]] = None  # 按键组合 ["ctrl", "c"]
    chunk_size: int = 25  # 文本输入块大小
    delay_ms: int = 75  # 输入延迟毫秒


@dataclass
class FileOperation:
    """文件操作"""
    operation: str  # read, write, delete, list, exists
    path: str
    content: Optional[str] = None  # 写入内容
    encoding: str = "utf-8"  # 文件编码


@dataclass
class ApplicationInfo:
    """应用程序信息"""
    name: str  # 应用名称
    process_id: Optional[int] = None  # 进程ID
    window_ids: List[str] = field(default_factory=list)  # 窗口ID列表
    status: str = "unknown"  # running, stopped, error