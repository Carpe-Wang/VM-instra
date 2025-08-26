"""
VM Service SDK
基于E2B Desktop封装的VM和Sandbox服务SDK，为其他微服务提供统一的VM操作接口
"""

from .client import VMServiceClient
from .models import (
    SandboxStatus,
    SandboxConfig, 
    SandboxInfo, 
    ExecutionResult,
    StreamConfig,
    ProcessInfo,
    EnvironmentInfo,
    SystemHealth,
    ConnectionInfo,
    FileInfo
)
from .exceptions import (
    VMServiceError,
    SandboxCreationError,
    SandboxNotFoundError,
    AuthenticationError,
    QuotaExceededError,
    FileOperationError,
    ApplicationError,
    StreamError,
    ProcessError,
    EnvironmentError,
    ConnectionError,
    ResourceLimitError,
    HealthCheckError
)

__version__ = "1.0.0"
__all__ = [
    "VMServiceClient",
    # Models
    "SandboxStatus",
    "SandboxConfig", 
    "SandboxInfo",
    "ExecutionResult",
    "StreamConfig",
    "ProcessInfo",
    "EnvironmentInfo",
    "SystemHealth",
    "ConnectionInfo",
    "FileInfo",
    # Exceptions
    "VMServiceError",
    "SandboxCreationError", 
    "SandboxNotFoundError",
    "AuthenticationError",
    "QuotaExceededError",
    "FileOperationError",
    "ApplicationError",
    "StreamError",
    "ProcessError",
    "EnvironmentError",
    "ConnectionError",
    "ResourceLimitError",
    "HealthCheckError"
]