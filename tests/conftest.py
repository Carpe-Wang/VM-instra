"""
Pytest configuration and shared fixtures for Infrastructure SDK tests.

This module provides common test fixtures, configuration, and utilities
that are shared across all test modules in the SDK test suite.
"""

import pytest
import asyncio
from typing import Dict, Any, Generator
from unittest.mock import Mock, AsyncMock

from infrastructure_sdk.config import InfraSDKConfig, KubernetesConfig, AWSConfig, VMConfig
from infrastructure_sdk.session import UserSessionManager
from infrastructure_sdk.vm import VMLifecycleController
from infrastructure_sdk.isolation import IsolationEngine


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Create an instance of the default event loop for the test session.
    
    This fixture ensures that async tests have a consistent event loop
    throughout the test session.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_config() -> InfraSDKConfig:
    """
    Provide a mock Infrastructure SDK configuration for testing.
    
    Returns a configuration object with safe test values that don't
    require actual cloud resources or credentials.
    """
    config = InfraSDKConfig()
    
    # Override with test-safe values
    config.kubernetes.config_path = "/dev/null"  # Don't try to load real kubeconfig
    config.aws.cluster_name = "test-cluster"
    config.aws.region = "us-west-2"
    config.aws.access_key_id = "test-key"
    config.aws.secret_access_key = "test-secret"
    
    return config


@pytest.fixture
def mock_kubernetes_client():
    """
    Mock Kubernetes client for testing.
    
    Provides a mock Kubernetes client that simulates API responses
    without requiring a real Kubernetes cluster.
    """
    client = Mock()
    
    # Mock common Kubernetes operations
    client.create_namespaced_custom_object = AsyncMock(return_value={"status": "success"})
    client.delete_namespaced_custom_object = AsyncMock(return_value={"status": "success"})
    client.get_namespaced_custom_object = AsyncMock(return_value={"status": "running"})
    client.list_namespaced_custom_object = AsyncMock(return_value={"items": []})
    
    return client


@pytest.fixture
def mock_aws_client():
    """
    Mock AWS client for testing.
    
    Provides a mock AWS client that simulates AWS API responses
    without requiring real AWS credentials or resources.
    """
    client = Mock()
    
    # Mock EC2 operations
    client.describe_instances = AsyncMock(return_value={
        "Reservations": [{
            "Instances": [{
                "InstanceId": "i-1234567890abcdef0",
                "State": {"Name": "running"},
                "InstanceType": "m5.large",
                "SpotInstanceRequestId": "sir-1234abcd"
            }]
        }]
    })
    
    client.run_instances = AsyncMock(return_value={
        "Instances": [{
            "InstanceId": "i-1234567890abcdef0",
            "State": {"Name": "pending"}
        }]
    })
    
    client.terminate_instances = AsyncMock(return_value={
        "TerminatingInstances": [{
            "InstanceId": "i-1234567890abcdef0",
            "CurrentState": {"Name": "shutting-down"}
        }]
    })
    
    return client


@pytest.fixture
def user_session_manager(mock_config: InfraSDKConfig) -> UserSessionManager:
    """
    Provide a UserSessionManager instance for testing.
    
    Creates a session manager with mock configuration suitable
    for testing session lifecycle operations.
    """
    return UserSessionManager(mock_config)


@pytest.fixture
def vm_lifecycle_controller(mock_config: InfraSDKConfig) -> VMLifecycleController:
    """
    Provide a VMLifecycleController instance for testing.
    
    Creates a VM controller with mock configuration suitable
    for testing VM lifecycle operations.
    """
    return VMLifecycleController(mock_config)


@pytest.fixture
def isolation_engine(mock_config: InfraSDKConfig) -> IsolationEngine:
    """
    Provide an IsolationEngine instance for testing.
    
    Creates an isolation engine with mock configuration suitable
    for testing isolation validation operations.
    """
    return IsolationEngine(mock_config)


@pytest.fixture
def sample_session_request() -> Dict[str, Any]:
    """
    Provide a sample session request for testing.
    
    Returns a valid session request dictionary that can be used
    to test session creation and management operations.
    """
    return {
        "user_id": "test-user-123",
        "session_type": "desktop",
        "vm_os": "windows",
        "resources": {
            "cpu": "4",
            "memory": "8Gi",
            "disk_size": "100Gi"
        },
        "ttl": "2h",
        "allow_spot": True,
        "dedicated_node": True,
        "tags": {
            "environment": "test",
            "project": "infrastructure-sdk"
        }
    }


@pytest.fixture
def sample_vm_spec() -> Dict[str, Any]:
    """
    Provide a sample VM specification for testing.
    
    Returns a valid VM spec dictionary that can be used
    to test VM provisioning and management operations.
    """
    return {
        "vm_name": "test-vm-123",
        "user_id": "test-user-123", 
        "session_id": "session-123",
        "os_type": "windows",
        "resources": {
            "cpu": "4",
            "memory": "8Gi",
            "disk_size": "100Gi"
        },
        "labels": {
            "test": "true",
            "environment": "test"
        }
    }


@pytest.fixture
def mock_context() -> Dict[str, Any]:
    """
    Provide a mock request context for testing.
    
    Returns a context dictionary that simulates request context
    passed to SDK operations during testing.
    """
    return {
        "correlation_id": "test-correlation-123",
        "user_id": "test-user-123",
        "request_id": "test-request-456",
        "timestamp": "2024-01-01T00:00:00Z"
    }


# Pytest markers for organizing tests
pytestmark = [
    pytest.mark.asyncio,  # Enable async test support
]


# Test configuration
def pytest_configure(config):
    """Configure pytest with custom markers and settings."""
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests (fast, isolated)"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (slower, may require external services)"
    )
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end tests (slowest, requires full environment)"
    )
    config.addinivalue_line(
        "markers", "aws: marks tests that require AWS credentials"
    )
    config.addinivalue_line(
        "markers", "kubernetes: marks tests that require Kubernetes cluster"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location and content."""
    for item in items:
        # Mark tests based on directory structure
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
        
        # Mark tests that interact with AWS
        if "aws" in str(item.fspath).lower() or "boto" in str(item.fspath).lower():
            item.add_marker(pytest.mark.aws)
        
        # Mark tests that interact with Kubernetes
        if "kubernetes" in str(item.fspath).lower() or "k8s" in str(item.fspath).lower():
            item.add_marker(pytest.mark.kubernetes)