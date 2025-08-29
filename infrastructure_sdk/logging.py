"""
Logging configuration for Infrastructure SDK.

This module provides comprehensive logging setup with structured logging,
correlation IDs, and configurable output destinations for observability
across all SDK components.
"""

import logging
import logging.handlers
import json
import sys
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import contextvars

from .config import LoggingConfig
from .exceptions import ConfigurationError


# Context variable for correlation ID tracking
correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'correlation_id', default=None
)


class CorrelationFilter(logging.Filter):
    """
    Logging filter that adds correlation ID to log records.
    
    Enables request tracing across the entire SDK by injecting
    correlation IDs into all log records.
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation ID to log record."""
        correlation_id = correlation_id_var.get()
        record.correlation_id = correlation_id or "unknown"
        return True


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    
    Formats log records as JSON for better parsing and analysis
    in log aggregation systems like ELK stack or CloudWatch.
    """
    
    def __init__(self, include_caller_info: bool = True):
        super().__init__()
        self.include_caller_info = include_caller_info
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Build log entry
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'correlation_id': getattr(record, 'correlation_id', 'unknown')
        }
        
        # Add caller information if enabled
        if self.include_caller_info:
            log_entry.update({
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno,
                'pathname': record.pathname
            })
        
        # Add exception information if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields from LoggerAdapter
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
        
        # Add any extra attributes
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                'thread', 'threadName', 'processName', 'process', 'getMessage',
                'correlation_id', 'extra_fields'
            } and not key.startswith('_'):
                log_entry[key] = value
        
        return json.dumps(log_entry, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """
    Human-readable text formatter for console output.
    
    Provides readable log output for development and debugging
    with consistent formatting and correlation ID tracking.
    """
    
    def __init__(self, include_caller_info: bool = True):
        format_string = '%(asctime)s [%(levelname)s] %(name)s'
        
        if include_caller_info:
            format_string += ' [%(module)s:%(funcName)s:%(lineno)d]'
        
        format_string += ' [%(correlation_id)s] %(message)s'
        
        super().__init__(fmt=format_string, datefmt='%Y-%m-%d %H:%M:%S')


class InfraSDKLoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter for Infrastructure SDK.
    
    Adds SDK-specific context and formatting to log records,
    including component identification and structured extra fields.
    """
    
    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        super().__init__(logger, extra or {})
    
    def process(self, msg: Any, kwargs: Dict[str, Any]) -> tuple:
        """Process log record with extra context."""
        if 'extra' in kwargs:
            # Merge adapter extra with call-specific extra
            merged_extra = {**self.extra, **kwargs['extra']}
            kwargs['extra'] = merged_extra
        else:
            kwargs['extra'] = self.extra.copy()
        
        return msg, kwargs


def setup_logging(config: LoggingConfig) -> None:
    """
    Set up logging configuration for the Infrastructure SDK.
    
    Configures log levels, formatters, handlers, and filters
    according to the provided configuration.
    
    Args:
        config: Logging configuration
        
    Raises:
        ConfigurationError: If logging configuration is invalid
    """
    try:
        # Clear any existing handlers
        logging.getLogger().handlers.clear()
        
        # Set root logger level
        logging.getLogger().setLevel(getattr(logging, config.level))
        
        # Create formatter based on configuration
        if config.format == "json":
            formatter = JSONFormatter(
                include_caller_info=config.include_caller_info
            )
        else:
            formatter = TextFormatter(
                include_caller_info=config.include_caller_info
            )
        
        # Set up handlers based on output configuration
        handlers = []
        
        if config.output in ["console", "both"]:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            console_handler.addFilter(CorrelationFilter())
            handlers.append(console_handler)
        
        if config.output in ["file", "both"]:
            if not config.file_path:
                raise ConfigurationError(
                    "file_path is required when output includes 'file'",
                    config_key="file_path"
                )
            
            # Ensure log directory exists
            log_path = Path(config.file_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Parse max file size
            max_bytes = _parse_size(config.max_file_size)
            
            file_handler = logging.handlers.RotatingFileHandler(
                filename=config.file_path,
                maxBytes=max_bytes,
                backupCount=config.backup_count,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            file_handler.addFilter(CorrelationFilter())
            handlers.append(file_handler)
        
        # Add handlers to root logger
        root_logger = logging.getLogger()
        for handler in handlers:
            root_logger.addHandler(handler)
        
        # Configure component-specific log levels
        logging.getLogger('kubernetes').setLevel(
            getattr(logging, config.kubernetes_log_level)
        )
        logging.getLogger('urllib3').setLevel(
            getattr(logging, config.aws_log_level)
        )
        logging.getLogger('botocore').setLevel(
            getattr(logging, config.aws_log_level)
        )
        logging.getLogger('infrastructure_sdk.vm').setLevel(
            getattr(logging, config.vm_log_level)
        )
        
        # Log successful configuration
        logger = logging.getLogger(__name__)
        logger.info(
            f"Logging configured successfully",
            extra={
                'level': config.level,
                'format': config.format,
                'output': config.output,
                'correlation_tracking': config.include_correlation_id
            }
        )
        
    except Exception as e:
        raise ConfigurationError(
            f"Failed to setup logging: {e}",
            config_key="logging_setup"
        ) from e


def get_logger(name: str, **extra: Any) -> InfraSDKLoggerAdapter:
    """
    Get a configured logger for Infrastructure SDK components.
    
    Args:
        name: Logger name (typically __name__)
        **extra: Extra fields to include in all log records
        
    Returns:
        Configured logger adapter with SDK context
    """
    base_logger = logging.getLogger(name)
    
    # Add SDK context to extra fields
    sdk_extra = {
        'sdk_version': '1.0.0',
        'component': name.replace('infrastructure_sdk.', ''),
        **extra
    }
    
    return InfraSDKLoggerAdapter(base_logger, sdk_extra)


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """
    Set correlation ID for request tracing.
    
    Args:
        correlation_id: Correlation ID to set (generates UUID if None)
        
    Returns:
        The correlation ID that was set
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())
    
    correlation_id_var.set(correlation_id)
    return correlation_id


def get_correlation_id() -> Optional[str]:
    """
    Get current correlation ID.
    
    Returns:
        Current correlation ID or None if not set
    """
    return correlation_id_var.get()


def clear_correlation_id() -> None:
    """Clear current correlation ID."""
    correlation_id_var.set(None)


def log_function_entry(logger: logging.Logger, func_name: str, **kwargs: Any) -> None:
    """
    Log function entry with parameters.
    
    Args:
        logger: Logger instance
        func_name: Function name
        **kwargs: Function parameters to log
    """
    logger.debug(
        f"Entering {func_name}",
        extra={
            'function': func_name,
            'parameters': {k: str(v) for k, v in kwargs.items()}
        }
    )


def log_function_exit(
    logger: logging.Logger, 
    func_name: str, 
    result: Any = None,
    duration: Optional[float] = None
) -> None:
    """
    Log function exit with result and duration.
    
    Args:
        logger: Logger instance
        func_name: Function name
        result: Function return value
        duration: Execution duration in seconds
    """
    extra = {
        'function': func_name,
        'has_result': result is not None
    }
    
    if duration is not None:
        extra['duration_seconds'] = duration
    
    logger.debug(f"Exiting {func_name}", extra=extra)


def _parse_size(size_str: str) -> int:
    """
    Parse size string to bytes.
    
    Args:
        size_str: Size string (e.g., "100MB", "1GB")
        
    Returns:
        Size in bytes
        
    Raises:
        ConfigurationError: If size format is invalid
    """
    size_str = size_str.upper().strip()
    
    size_units = {
        'B': 1,
        'KB': 1024,
        'MB': 1024 * 1024,
        'GB': 1024 * 1024 * 1024,
        'TB': 1024 * 1024 * 1024 * 1024
    }
    
    for unit, multiplier in size_units.items():
        if size_str.endswith(unit):
            try:
                value = float(size_str[:-len(unit)])
                return int(value * multiplier)
            except ValueError:
                pass
    
    # Try parsing as plain number (assume bytes)
    try:
        return int(size_str)
    except ValueError:
        raise ConfigurationError(
            f"Invalid size format: {size_str}. Expected formats: 100MB, 1GB, etc.",
            config_key="file_size",
            config_value=size_str
        )


class LoggingContextManager:
    """
    Context manager for managing logging context and correlation IDs.
    
    Automatically sets up correlation IDs and cleans up logging context
    for request processing and component operations.
    """
    
    def __init__(
        self, 
        correlation_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        operation: Optional[str] = None
    ):
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.logger = logger
        self.operation = operation
        self.start_time: Optional[datetime] = None
        self.previous_correlation_id: Optional[str] = None
    
    def __enter__(self) -> str:
        """Enter logging context."""
        self.previous_correlation_id = get_correlation_id()
        set_correlation_id(self.correlation_id)
        self.start_time = datetime.utcnow()
        
        if self.logger and self.operation:
            self.logger.info(
                f"Starting {self.operation}",
                extra={'operation': self.operation}
            )
        
        return self.correlation_id
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit logging context."""
        if self.logger and self.operation and self.start_time:
            duration = (datetime.utcnow() - self.start_time).total_seconds()
            
            if exc_type is None:
                self.logger.info(
                    f"Completed {self.operation}",
                    extra={
                        'operation': self.operation,
                        'duration_seconds': duration,
                        'success': True
                    }
                )
            else:
                self.logger.error(
                    f"Failed {self.operation}: {exc_val}",
                    extra={
                        'operation': self.operation,
                        'duration_seconds': duration,
                        'success': False,
                        'error_type': exc_type.__name__ if exc_type else None
                    },
                    exc_info=True
                )
        
        # Restore previous correlation ID
        if self.previous_correlation_id:
            set_correlation_id(self.previous_correlation_id)
        else:
            clear_correlation_id()


# Convenience function for creating logging context
def logging_context(
    correlation_id: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    operation: Optional[str] = None
) -> LoggingContextManager:
    """
    Create a logging context manager.
    
    Args:
        correlation_id: Optional correlation ID (generates UUID if None)
        logger: Optional logger for operation logging
        operation: Optional operation name for logging
        
    Returns:
        LoggingContextManager instance
    """
    return LoggingContextManager(correlation_id, logger, operation)


# Module-level logger for this module
_logger = get_logger(__name__)