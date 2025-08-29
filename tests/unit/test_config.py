"""
Unit tests for Configuration Management.

This module contains comprehensive unit tests for the configuration
classes, validation logic, and configuration loading mechanisms.
"""

import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, mock_open

from infrastructure_sdk.config import (
    InfraSDKConfig,
    KubernetesConfig,
    AWSConfig,
    VMConfig,
    IsolationConfig,
    CostOptimizationConfig,
    LoggingConfig
)
from infrastructure_sdk.exceptions import ConfigurationError


class TestKubernetesConfig:
    """Test cases for KubernetesConfig class."""
    
    def test_kubernetes_config_defaults(self):
        """Test KubernetesConfig with default values."""
        with patch('pathlib.Path.exists', return_value=True):
            config = KubernetesConfig()
            
            assert config.namespace == "default"
            assert config.kubevirt_namespace == "kubevirt"
            assert config.api_version == "v1"
            assert config.config_path is not None
    
    def test_kubernetes_config_custom_path(self):
        """Test KubernetesConfig with custom config path."""
        config = KubernetesConfig(config_path="/custom/path/kubeconfig")
        
        assert config.config_path == "/custom/path/kubeconfig"
        assert config.namespace == "default"
    
    def test_kubernetes_config_missing_config_file(self):
        """Test KubernetesConfig with missing config file."""
        with patch('pathlib.Path.exists', return_value=False):
            with pytest.raises(ConfigurationError) as exc_info:
                KubernetesConfig()
            
            assert "Kubernetes config not found" in str(exc_info.value)
            assert exc_info.value.config_key == "config_path"


class TestAWSConfig:
    """Test cases for AWSConfig class."""
    
    def test_aws_config_defaults(self):
        """Test AWSConfig with default values."""
        config = AWSConfig(cluster_name="test-cluster")
        
        assert config.region == "us-west-2"
        assert config.cluster_name == "test-cluster"
        assert config.spot_instance_preferred is True
        assert len(config.default_instance_types) > 0
    
    def test_aws_config_with_credentials(self):
        """Test AWSConfig with explicit credentials."""
        config = AWSConfig(
            cluster_name="test-cluster",
            access_key_id="test-key",
            secret_access_key="test-secret",
            region="us-east-1"
        )
        
        assert config.access_key_id == "test-key"
        assert config.secret_access_key == "test-secret"
        assert config.region == "us-east-1"
    
    def test_aws_config_missing_cluster_name(self):
        """Test AWSConfig validation with missing cluster name."""
        with pytest.raises(ConfigurationError) as exc_info:
            AWSConfig()
        
        assert "cluster_name is required" in str(exc_info.value)
        assert exc_info.value.config_key == "cluster_name"
    
    @patch.dict('os.environ', {'AWS_ACCESS_KEY_ID': 'env-key'})
    def test_aws_config_env_credentials(self):
        """Test AWSConfig with environment credentials."""
        config = AWSConfig(cluster_name="test-cluster")
        # Should not raise exception when env vars are set
        assert config.cluster_name == "test-cluster"
    
    def test_aws_config_no_credentials(self):
        """Test AWSConfig with no credentials available."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ConfigurationError) as exc_info:
                AWSConfig(cluster_name="test-cluster")
            
            assert "AWS credentials must be provided" in str(exc_info.value)
            assert exc_info.value.config_key == "credentials"


class TestVMConfig:
    """Test cases for VMConfig class."""
    
    def test_vm_config_defaults(self):
        """Test VMConfig with default values."""
        config = VMConfig()
        
        assert config.default_cpu == "2"
        assert config.default_memory == "4Gi"
        assert config.default_disk_size == "50Gi"
        assert config.windows_fast_launch_enabled is True
        assert config.storage_encrypted is True
    
    def test_vm_config_custom_values(self):
        """Test VMConfig with custom values."""
        config = VMConfig(
            default_cpu="8",
            default_memory="16Gi",
            windows_startup_timeout=180,
            storage_iops=5000
        )
        
        assert config.default_cpu == "8"
        assert config.default_memory == "16Gi"
        assert config.windows_startup_timeout == 180
        assert config.storage_iops == 5000
    
    def test_vm_config_invalid_startup_timeout(self):
        """Test VMConfig validation with invalid startup timeout."""
        with pytest.raises(ConfigurationError) as exc_info:
            VMConfig(windows_startup_timeout=30)
        
        assert "startup timeout must be at least 60 seconds" in str(exc_info.value)
        assert exc_info.value.config_key == "windows_startup_timeout"
    
    def test_vm_config_invalid_storage_iops(self):
        """Test VMConfig validation with invalid storage IOPS."""
        with pytest.raises(ConfigurationError) as exc_info:
            VMConfig(storage_iops=50)
        
        assert "Storage IOPS must be at least 100" in str(exc_info.value)
        assert exc_info.value.config_key == "storage_iops"


class TestIsolationConfig:
    """Test cases for IsolationConfig class."""
    
    def test_isolation_config_defaults(self):
        """Test IsolationConfig with default values."""
        config = IsolationConfig()
        
        assert config.dedicated_nodes is True
        assert config.network_policies_enabled is True
        assert config.encrypted_storage is True
        assert config.isolation_validation_enabled is True
        assert config.validation_frequency == 30
    
    def test_isolation_config_custom_values(self):
        """Test IsolationConfig with custom values."""
        config = IsolationConfig(
            subnet_isolation=True,
            ephemeral_storage_only=True,
            validation_frequency=60
        )
        
        assert config.subnet_isolation is True
        assert config.ephemeral_storage_only is True
        assert config.validation_frequency == 60
    
    def test_isolation_config_invalid_validation_frequency(self):
        """Test IsolationConfig validation with invalid frequency."""
        with pytest.raises(ConfigurationError) as exc_info:
            IsolationConfig(validation_frequency=5)
        
        assert "validation frequency must be at least 10 seconds" in str(exc_info.value)
        assert exc_info.value.config_key == "validation_frequency"


class TestCostOptimizationConfig:
    """Test cases for CostOptimizationConfig class."""
    
    def test_cost_config_defaults(self):
        """Test CostOptimizationConfig with default values."""
        config = CostOptimizationConfig()
        
        assert config.spot_instance_preference == 0.7
        assert config.right_sizing_enabled is True
        assert config.idle_timeout == 7200  # 2 hours
        assert config.target_cost_reduction == 0.65
    
    def test_cost_config_custom_values(self):
        """Test CostOptimizationConfig with custom values."""
        config = CostOptimizationConfig(
            spot_instance_preference=0.9,
            idle_timeout=3600,
            daily_budget_limit=100.0
        )
        
        assert config.spot_instance_preference == 0.9
        assert config.idle_timeout == 3600
        assert config.daily_budget_limit == 100.0
    
    def test_cost_config_invalid_spot_preference(self):
        """Test CostOptimizationConfig with invalid spot preference."""
        with pytest.raises(ConfigurationError) as exc_info:
            CostOptimizationConfig(spot_instance_preference=1.5)
        
        assert "Spot instance preference must be between 0.0 and 1.0" in str(exc_info.value)
        assert exc_info.value.config_key == "spot_instance_preference"
    
    def test_cost_config_invalid_idle_timeout(self):
        """Test CostOptimizationConfig with invalid idle timeout."""
        with pytest.raises(ConfigurationError) as exc_info:
            CostOptimizationConfig(idle_timeout=100)
        
        assert "Idle timeout must be at least 300 seconds" in str(exc_info.value)
        assert exc_info.value.config_key == "idle_timeout"


class TestLoggingConfig:
    """Test cases for LoggingConfig class."""
    
    def test_logging_config_defaults(self):
        """Test LoggingConfig with default values."""
        config = LoggingConfig()
        
        assert config.level == "INFO"
        assert config.format == "json"
        assert config.output == "console"
        assert config.include_timestamps is True
        assert config.kubernetes_log_level == "WARNING"
    
    def test_logging_config_custom_values(self):
        """Test LoggingConfig with custom values."""
        config = LoggingConfig(
            level="DEBUG",
            format="text",
            output="file",
            file_path="/var/log/infra-sdk.log"
        )
        
        assert config.level == "DEBUG"
        assert config.format == "text"
        assert config.output == "file"
        assert config.file_path == "/var/log/infra-sdk.log"
    
    def test_logging_config_invalid_level(self):
        """Test LoggingConfig with invalid log level."""
        with pytest.raises(ConfigurationError) as exc_info:
            LoggingConfig(level="INVALID")
        
        assert "Log level must be one of" in str(exc_info.value)
        assert exc_info.value.config_key == "level"
    
    def test_logging_config_file_without_path(self):
        """Test LoggingConfig with file output but no path."""
        with pytest.raises(ConfigurationError) as exc_info:
            LoggingConfig(output="file")
        
        assert "file_path is required when output is set to 'file'" in str(exc_info.value)
        assert exc_info.value.config_key == "file_path"


class TestInfraSDKConfig:
    """Test cases for InfraSDKConfig class."""
    
    def test_infra_config_creation(self):
        """Test InfraSDKConfig creation with defaults."""
        with patch('pathlib.Path.exists', return_value=True):
            with patch.dict('os.environ', {'AWS_ACCESS_KEY_ID': 'test', 'INFRA_SDK_AWS__CLUSTER_NAME': 'test'}):
                config = InfraSDKConfig()
                
                assert isinstance(config.kubernetes, KubernetesConfig)
                assert isinstance(config.aws, AWSConfig)
                assert isinstance(config.vm, VMConfig)
                assert isinstance(config.isolation, IsolationConfig)
                assert isinstance(config.cost_optimization, CostOptimizationConfig)
                assert isinstance(config.logging, LoggingConfig)
    
    def test_from_dict_creation(self):
        """Test InfraSDKConfig creation from dictionary."""
        config_dict = {
            'aws': {
                'cluster_name': 'test-cluster',
                'region': 'us-east-1',
                'access_key_id': 'test-key',
                'secret_access_key': 'test-secret'
            },
            'vm': {
                'default_cpu': '4',
                'default_memory': '8Gi'
            },
            'logging': {
                'level': 'DEBUG',
                'format': 'text'
            }
        }
        
        with patch('pathlib.Path.exists', return_value=True):
            config = InfraSDKConfig.from_dict(config_dict)
            
            assert config.aws.cluster_name == 'test-cluster'
            assert config.aws.region == 'us-east-1'
            assert config.vm.default_cpu == '4'
            assert config.vm.default_memory == '8Gi'
            assert config.logging.level == 'DEBUG'
            assert config.logging.format == 'text'
    
    def test_from_file_creation(self):
        """Test InfraSDKConfig creation from YAML file."""
        config_data = {
            'aws': {
                'cluster_name': 'test-cluster',
                'region': 'us-west-1',
                'access_key_id': 'test-key',
                'secret_access_key': 'test-secret'
            },
            'vm': {
                'default_cpu': '8',
                'windows_startup_timeout': 240
            }
        }
        
        yaml_content = yaml.dump(config_data)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            with patch('pathlib.Path.exists', return_value=True):
                config = InfraSDKConfig.from_file(temp_path)
                
                assert config.aws.cluster_name == 'test-cluster'
                assert config.aws.region == 'us-west-1'
                assert config.vm.default_cpu == '8'
                assert config.vm.windows_startup_timeout == 240
        finally:
            Path(temp_path).unlink()
    
    def test_from_file_not_found(self):
        """Test InfraSDKConfig from non-existent file."""
        with pytest.raises(ConfigurationError) as exc_info:
            InfraSDKConfig.from_file("/non/existent/file.yaml")
        
        assert "Configuration file not found" in str(exc_info.value)
        assert exc_info.value.config_key == "config_path"
    
    def test_from_file_invalid_yaml(self):
        """Test InfraSDKConfig from invalid YAML file."""
        invalid_yaml = "invalid: yaml: content: ["
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(invalid_yaml)
            temp_path = f.name
        
        try:
            with pytest.raises(ConfigurationError) as exc_info:
                InfraSDKConfig.from_file(temp_path)
            
            assert "Failed to parse YAML configuration" in str(exc_info.value)
            assert exc_info.value.config_key == "yaml_parsing"
        finally:
            Path(temp_path).unlink()
    
    @patch.dict('os.environ', {
        'INFRA_SDK_AWS__REGION': 'us-east-2',
        'INFRA_SDK_AWS__CLUSTER_NAME': 'env-cluster',
        'INFRA_SDK_VM__DEFAULT_CPU': '8',
        'INFRA_SDK_LOGGING__LEVEL': 'DEBUG'
    })
    def test_from_environment(self):
        """Test InfraSDKConfig creation from environment variables."""
        with patch('pathlib.Path.exists', return_value=True):
            with patch.dict('os.environ', {'AWS_ACCESS_KEY_ID': 'test'}, clear=False):
                config = InfraSDKConfig.from_environment()
                
                assert config.aws.region == 'us-east-2'
                assert config.aws.cluster_name == 'env-cluster'
                assert config.vm.default_cpu == '8'
                assert config.logging.level == 'DEBUG'
    
    def test_validate_cross_section(self):
        """Test configuration cross-section validation."""
        with patch('pathlib.Path.exists', return_value=True):
            with patch.dict('os.environ', {'AWS_ACCESS_KEY_ID': 'test', 'INFRA_SDK_AWS__CLUSTER_NAME': 'test'}):
                config = InfraSDKConfig()
                
                # Enable budget alerts without setting limits
                config.cost_optimization.budget_alerts_enabled = True
                config.cost_optimization.daily_budget_limit = None
                config.cost_optimization.monthly_budget_limit = None
                
                with pytest.raises(ConfigurationError) as exc_info:
                    config.validate()
                
                assert "Budget limits must be set when budget alerts are enabled" in str(exc_info.value)
                assert exc_info.value.config_key == "budget_configuration"
    
    def test_to_dict_conversion(self):
        """Test configuration conversion to dictionary."""
        with patch('pathlib.Path.exists', return_value=True):
            with patch.dict('os.environ', {'AWS_ACCESS_KEY_ID': 'test', 'INFRA_SDK_AWS__CLUSTER_NAME': 'test'}):
                config = InfraSDKConfig()
                config_dict = config.to_dict()
                
                assert 'kubernetes' in config_dict
                assert 'aws' in config_dict
                assert 'vm' in config_dict
                assert 'isolation' in config_dict
                assert 'cost_optimization' in config_dict
                assert 'logging' in config_dict
                
                # Check nested structure
                assert 'cluster_name' in config_dict['aws']
                assert 'default_cpu' in config_dict['vm']
                assert 'level' in config_dict['logging']