"""
Infrastructure SDK - VM-Based User Isolation and Lifecycle Management System

This SDK provides user-isolated VM environments with efficient lifecycle management
and resource cleanup capabilities, leveraging Kubernetes-native approaches combined
with VM orchestration for secure, scalable, and cost-effective infrastructure management.

Key Components:
- User Session Manager: Complete session lifecycle orchestration
- VM Lifecycle Controller: Automated VM provisioning, recycling, and cleanup
- Isolation Engine: Multi-layer user isolation architecture
- Resource Optimizer: Cost optimization and intelligent resource management
- Cleanup Orchestrator: Comprehensive resource cleanup and data sanitization

Author: Infrastructure SDK Team
Version: 1.0.0
License: MIT
"""

from typing import Dict, Any

from .session import UserSessionManager, Session, SessionRequest, ResourceSpec
from .vm import VMLifecycleController, VM, VMSpec
from .isolation import IsolationEngine, IsolationReport
from .config import InfraSDKConfig
from .exceptions import (
    InfraSDKException,
    SessionCreationError,
    VMProvisioningError,
    IsolationValidationError,
    CleanupError,
    ResourceNotFoundError
)

__version__ = "1.0.0"
__author__ = "Infrastructure SDK Team"

__all__ = [
    # Core Components
    "UserSessionManager",
    "VMLifecycleController", 
    "IsolationEngine",
    "InfraSDKConfig",
    
    # Data Models
    "Session",
    "SessionRequest",
    "ResourceSpec",
    "VM",
    "VMSpec",
    "IsolationReport",
    
    # Exceptions
    "InfraSDKException",
    "SessionCreationError",
    "VMProvisioningError",
    "IsolationValidationError",
    "CleanupError",
    "ResourceNotFoundError",
]

# SDK Metadata
SDK_INFO: Dict[str, Any] = {
    "name": "infrastructure-sdk",
    "version": __version__,
    "description": "VM-Based User Isolation and Lifecycle Management System",
    "author": __author__,
    "kubernetes_native": True,
    "vm_orchestration": "KubeVirt",
    "cost_optimization": True,
    "security_isolation": "multi-layer",
}