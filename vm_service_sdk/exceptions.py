"""
异常定义
VM服务SDK的异常体系
"""

from typing import Optional, Dict, Any


class VMServiceError(Exception):
    """VM服务基础异常"""
    
    def __init__(
        self, 
        message: str, 
        error_code: Optional[str] = None,
        sandbox_id: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.sandbox_id = sandbox_id
        self.user_id = user_id
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "sandbox_id": self.sandbox_id,
            "user_id": self.user_id,
            "details": self.details
        }


class SandboxCreationError(VMServiceError):
    """沙箱创建失败"""
    pass


class SandboxNotFoundError(VMServiceError):
    """沙箱未找到"""
    pass


class SandboxTimeoutError(VMServiceError):
    """沙箱操作超时"""
    
    def __init__(self, message: str, timeout_seconds: int, **kwargs):
        super().__init__(message, **kwargs)
        self.timeout_seconds = timeout_seconds


class AuthenticationError(VMServiceError):
    """认证失败"""
    pass


class QuotaExceededError(VMServiceError):
    """配额超限"""
    
    def __init__(self, message: str, quota_type: str, current_usage: int, limit: int, **kwargs):
        super().__init__(message, **kwargs)
        self.quota_type = quota_type
        self.current_usage = current_usage
        self.limit = limit


class NetworkError(VMServiceError):
    """网络错误"""
    pass


class FileOperationError(VMServiceError):
    """文件操作错误"""
    
    def __init__(self, message: str, file_path: str, operation: str, **kwargs):
        super().__init__(message, **kwargs)
        self.file_path = file_path
        self.operation = operation


class ApplicationError(VMServiceError):
    """应用程序操作错误"""
    
    def __init__(self, message: str, app_name: str, **kwargs):
        super().__init__(message, **kwargs)
        self.app_name = app_name


class StreamError(VMServiceError):
    """流媒体错误"""
    pass