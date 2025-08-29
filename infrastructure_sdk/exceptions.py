"""
Custom exceptions for Infrastructure SDK.

This module defines all custom exceptions used throughout the Infrastructure SDK,
providing clear error handling and debugging capabilities for VM lifecycle management,
user isolation, session management, and resource cleanup operations.
"""

from typing import Optional, Dict, Any


class InfraSDKException(Exception):
    """
    Base exception for all Infrastructure SDK errors.
    
    This is the root exception class that all other SDK exceptions inherit from.
    It provides common functionality for error reporting and debugging.
    """
    
    def __init__(
        self, 
        message: str, 
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
    
    def __str__(self) -> str:
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for serialization."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details
        }


class SessionCreationError(InfraSDKException):
    """
    Raised when session creation fails.
    
    This exception is thrown during user session creation when:
    - Resource allocation fails
    - Authentication/authorization errors
    - Invalid session parameters
    - Kubernetes resource creation failures
    """
    
    def __init__(
        self, 
        message: str,
        user_id: Optional[str] = None,
        session_spec: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        details = kwargs.get('details', {})
        if user_id:
            details['user_id'] = user_id
        if session_spec:
            details['session_spec'] = session_spec
        
        super().__init__(
            message=message,
            error_code=kwargs.get('error_code', 'SESSION_CREATE_FAILED'),
            details=details
        )
        self.user_id = user_id
        self.session_spec = session_spec


class VMProvisioningError(InfraSDKException):
    """
    Raised when VM provisioning fails.
    
    This exception is thrown during VM lifecycle operations when:
    - KubeVirt VM creation fails
    - Node provisioning through Karpenter fails
    - Resource constraints prevent VM creation
    - VM health checks fail
    - Network or storage configuration errors
    """
    
    def __init__(
        self,
        message: str,
        vm_spec: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        **kwargs
    ) -> None:
        details = kwargs.get('details', {})
        if vm_spec:
            details['vm_spec'] = vm_spec
        if session_id:
            details['session_id'] = session_id
        
        super().__init__(
            message=message,
            error_code=kwargs.get('error_code', 'VM_PROVISION_FAILED'),
            details=details
        )
        self.vm_spec = vm_spec
        self.session_id = session_id


class IsolationValidationError(InfraSDKException):
    """
    Raised when user isolation validation fails.
    
    This exception is thrown when the isolation validation framework detects:
    - Network isolation breaches
    - Compute resource sharing violations
    - Storage access control failures
    - Memory isolation compromises
    - Security policy violations
    """
    
    def __init__(
        self,
        message: str,
        session_id: Optional[str] = None,
        isolation_type: Optional[str] = None,
        validation_results: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        details = kwargs.get('details', {})
        if session_id:
            details['session_id'] = session_id
        if isolation_type:
            details['isolation_type'] = isolation_type
        if validation_results:
            details['validation_results'] = validation_results
        
        super().__init__(
            message=message,
            error_code=kwargs.get('error_code', 'ISOLATION_VALIDATION_FAILED'),
            details=details
        )
        self.session_id = session_id
        self.isolation_type = isolation_type
        self.validation_results = validation_results


class CleanupError(InfraSDKException):
    """
    Raised when resource cleanup operations fail.
    
    This exception is thrown during cleanup operations when:
    - VM termination fails
    - EBS volume deletion fails
    - Network resource cleanup fails
    - Session state cleanup fails
    - Monitoring data cleanup fails
    """
    
    def __init__(
        self,
        message: str,
        session_id: Optional[str] = None,
        cleanup_phase: Optional[str] = None,
        failed_resources: Optional[list] = None,
        **kwargs
    ) -> None:
        details = kwargs.get('details', {})
        if session_id:
            details['session_id'] = session_id
        if cleanup_phase:
            details['cleanup_phase'] = cleanup_phase
        if failed_resources:
            details['failed_resources'] = failed_resources
        
        super().__init__(
            message=message,
            error_code=kwargs.get('error_code', 'CLEANUP_FAILED'),
            details=details
        )
        self.session_id = session_id
        self.cleanup_phase = cleanup_phase
        self.failed_resources = failed_resources or []


class ResourceNotFoundError(InfraSDKException):
    """
    Raised when requested resources cannot be found.
    
    This exception is thrown when:
    - Session ID does not exist
    - VM instance cannot be located
    - Kubernetes resources are missing
    - Node or namespace not found
    """
    
    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        **kwargs
    ) -> None:
        details = kwargs.get('details', {})
        if resource_type:
            details['resource_type'] = resource_type
        if resource_id:
            details['resource_id'] = resource_id
        
        super().__init__(
            message=message,
            error_code=kwargs.get('error_code', 'RESOURCE_NOT_FOUND'),
            details=details
        )
        self.resource_type = resource_type
        self.resource_id = resource_id


class ConfigurationError(InfraSDKException):
    """
    Raised when configuration validation fails.
    
    This exception is thrown when:
    - Required configuration parameters are missing
    - Configuration values are invalid
    - Kubernetes cluster configuration is incorrect
    - AWS credentials or permissions are insufficient
    """
    
    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        config_value: Optional[Any] = None,
        **kwargs
    ) -> None:
        details = kwargs.get('details', {})
        if config_key:
            details['config_key'] = config_key
        if config_value is not None:
            details['config_value'] = str(config_value)
        
        super().__init__(
            message=message,
            error_code=kwargs.get('error_code', 'CONFIGURATION_ERROR'),
            details=details
        )
        self.config_key = config_key
        self.config_value = config_value


class CostOptimizationError(InfraSDKException):
    """
    Raised when cost optimization operations fail.
    
    This exception is thrown when:
    - Spot instance prediction fails
    - Resource right-sizing calculations fail
    - Cost tracking mechanisms encounter errors
    - Budget limits are exceeded
    """
    
    def __init__(
        self,
        message: str,
        optimization_type: Optional[str] = None,
        cost_impact: Optional[float] = None,
        **kwargs
    ) -> None:
        details = kwargs.get('details', {})
        if optimization_type:
            details['optimization_type'] = optimization_type
        if cost_impact is not None:
            details['cost_impact'] = cost_impact
        
        super().__init__(
            message=message,
            error_code=kwargs.get('error_code', 'COST_OPTIMIZATION_FAILED'),
            details=details
        )
        self.optimization_type = optimization_type
        self.cost_impact = cost_impact