"""
VM Service SDK
基于E2B Desktop封装的VM和Sandbox服务SDK，为其他微服务提供统一的VM操作接口
"""

from .client import VMServiceClient
from .models import (
    SandboxConfig, 
    SandboxInfo, 
    ExecutionResult,
    StreamConfig
)
from .exceptions import (
    VMServiceError,
    SandboxCreationError,
    SandboxNotFoundError,
    AuthenticationError
)

__version__ = "1.0.0"
__all__ = [
    "VMServiceClient",
    "SandboxConfig", 
    "SandboxInfo",
    "ExecutionResult",
    "StreamConfig",
    "VMServiceError",
    "SandboxCreationError", 
    "SandboxNotFoundError",
    "AuthenticationError"
]