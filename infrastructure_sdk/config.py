"""
Configuration management for Infrastructure SDK.

This module provides configuration classes with validation for the Infrastructure SDK,
handling Kubernetes cluster configuration, AWS credentials, VM template management,
and cost optimization settings.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import yaml
from .exceptions import ConfigurationError

try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
except ImportError:
    _DOTENV_AVAILABLE = False


@dataclass
class KubernetesConfig:
    """
    Kubernetes cluster configuration settings.
    
    Manages connection settings for Kubernetes API, namespace configurations,
    and KubeVirt integration parameters.
    """
    
    config_path: Optional[str] = None
    context: Optional[str] = None
    namespace: str = "default"
    kubevirt_namespace: str = "kubevirt"
    api_version: str = "v1"
    
    def __post_init__(self) -> None:
        """Validate Kubernetes configuration after initialization."""
        if not self.config_path:
            # Try standard kubeconfig locations
            home = Path.home()
            default_config = home / ".kube" / "config"
            if default_config.exists():
                self.config_path = str(default_config)
            else:
                raise ConfigurationError(
                    "Kubernetes config not found. Please specify config_path or ensure ~/.kube/config exists",
                    config_key="config_path"
                )


@dataclass
class AWSConfig:
    """
    AWS configuration settings for EC2 and EKS integration.
    
    Manages AWS credentials, region settings, and service-specific configurations
    for EC2 instance management and EKS cluster operations.
    """
    
    region: str = "us-west-2"
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    session_token: Optional[str] = None
    profile: Optional[str] = None
    cluster_name: str = ""
    
    # EC2 Configuration
    default_instance_types: List[str] = field(default_factory=lambda: [
        "m5.large", "m5.xlarge", "m5.2xlarge", "c5.large", "c5.xlarge"
    ])
    spot_instance_preferred: bool = True
    max_spot_price: Optional[float] = None
    
    # VPC and Networking
    vpc_id: Optional[str] = None
    subnet_ids: List[str] = field(default_factory=list)
    security_group_ids: List[str] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """Validate AWS configuration after initialization."""
        if not self.cluster_name:
            raise ConfigurationError(
                "AWS EKS cluster_name is required",
                config_key="cluster_name"
            )
        
        # Validate credentials are available (either explicit or from environment/profile)
        if not any([
            self.access_key_id and self.secret_access_key,
            self.profile,
            os.getenv('AWS_ACCESS_KEY_ID'),
            os.getenv('AWS_PROFILE')
        ]):
            raise ConfigurationError(
                "AWS credentials must be provided via access_key_id/secret_access_key, profile, or environment variables",
                config_key="credentials"
            )


@dataclass 
class VMConfig:
    """
    Virtual Machine configuration settings.
    
    Defines VM templates, resource specifications, and KubeVirt-specific
    configuration for Windows and Linux VM deployments.
    """
    
    # Default VM Specifications
    default_cpu: str = "2"
    default_memory: str = "4Gi"
    default_disk_size: str = "50Gi"
    
    # Windows VM Configuration
    windows_base_image: str = "registry.k8s.io/sig-windows/windows-server-2022:latest"
    windows_startup_timeout: int = 300  # 5 minutes
    windows_fast_launch_enabled: bool = True
    
    # Linux VM Configuration  
    linux_base_image: str = "ubuntu:22.04"
    linux_startup_timeout: int = 120  # 2 minutes
    
    # Storage Configuration
    storage_class: str = "gp3"
    storage_encrypted: bool = True
    storage_iops: int = 3000
    
    # Network Configuration
    network_type: str = "pod"  # pod, multus, or bridge
    dns_policy: str = "ClusterFirst"
    
    def __post_init__(self) -> None:
        """Validate VM configuration after initialization."""
        if self.windows_startup_timeout < 60:
            raise ConfigurationError(
                "Windows VM startup timeout must be at least 60 seconds",
                config_key="windows_startup_timeout",
                config_value=self.windows_startup_timeout
            )
        
        if self.storage_iops < 100:
            raise ConfigurationError(
                "Storage IOPS must be at least 100",
                config_key="storage_iops", 
                config_value=self.storage_iops
            )


@dataclass
class IsolationConfig:
    """
    User isolation configuration settings.
    
    Defines multi-layer isolation policies for compute, network, storage,
    and runtime isolation between user sessions.
    """
    
    # Compute Isolation
    dedicated_nodes: bool = True
    node_affinity_required: bool = True
    cpu_isolation: bool = True
    memory_isolation: bool = True
    
    # Network Isolation  
    network_policies_enabled: bool = True
    dedicated_security_groups: bool = True
    subnet_isolation: bool = False  # Optional for enhanced isolation
    
    # Storage Isolation
    encrypted_storage: bool = True
    user_specific_keys: bool = True
    ephemeral_storage_only: bool = False
    
    # Runtime Isolation
    process_isolation: bool = True
    filesystem_isolation: bool = True
    
    # Validation Settings
    isolation_validation_enabled: bool = True
    validation_frequency: int = 30  # seconds
    
    def __post_init__(self) -> None:
        """Validate isolation configuration after initialization."""
        if self.validation_frequency < 10:
            raise ConfigurationError(
                "Isolation validation frequency must be at least 10 seconds",
                config_key="validation_frequency",
                config_value=self.validation_frequency
            )


@dataclass
class CostOptimizationConfig:
    """
    Cost optimization configuration settings.
    
    Defines strategies for cost reduction through spot instances,
    resource right-sizing, and intelligent scheduling.
    """
    
    # Spot Instance Configuration
    spot_instance_preference: float = 0.7  # 70% preference for spot instances
    spot_interruption_handling: bool = True
    spot_price_threshold: float = 0.5  # Max 50% of on-demand price
    
    # Resource Optimization
    right_sizing_enabled: bool = True
    consolidation_enabled: bool = True
    idle_timeout: int = 7200  # 2 hours in seconds
    
    # Cost Tracking
    cost_tracking_enabled: bool = True
    budget_alerts_enabled: bool = True
    daily_budget_limit: Optional[float] = None
    monthly_budget_limit: Optional[float] = None
    
    # Optimization Targets
    target_cost_reduction: float = 0.65  # Target 65% cost reduction
    target_utilization: float = 0.85     # Target 85% resource utilization
    
    def __post_init__(self) -> None:
        """Validate cost optimization configuration after initialization."""
        if not 0.0 <= self.spot_instance_preference <= 1.0:
            raise ConfigurationError(
                "Spot instance preference must be between 0.0 and 1.0",
                config_key="spot_instance_preference",
                config_value=self.spot_instance_preference
            )
        
        if self.idle_timeout < 300:  # Minimum 5 minutes
            raise ConfigurationError(
                "Idle timeout must be at least 300 seconds (5 minutes)",
                config_key="idle_timeout",
                config_value=self.idle_timeout
            )


@dataclass
class LoggingConfig:
    """
    Logging configuration settings.
    
    Defines log levels, output destinations, and structured logging
    configuration for comprehensive observability.
    """
    
    level: str = "INFO"
    format: str = "json"  # json or text
    output: str = "console"  # console, file, or both
    file_path: Optional[str] = None
    max_file_size: str = "100MB"
    backup_count: int = 5
    
    # Structured logging
    include_timestamps: bool = True
    include_caller_info: bool = True
    include_correlation_id: bool = True
    
    # Component-specific log levels
    kubernetes_log_level: str = "WARNING"
    aws_log_level: str = "WARNING"
    vm_log_level: str = "INFO"
    
    def __post_init__(self) -> None:
        """Validate logging configuration after initialization."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.level not in valid_levels:
            raise ConfigurationError(
                f"Log level must be one of {valid_levels}",
                config_key="level",
                config_value=self.level
            )
        
        if self.output == "file" and not self.file_path:
            raise ConfigurationError(
                "file_path is required when output is set to 'file'",
                config_key="file_path"
            )


@dataclass 
class InfraSDKConfig:
    """
    Main configuration class for Infrastructure SDK.
    
    Combines all configuration sections and provides methods for loading
    configuration from files, environment variables, and validation.
    """
    
    kubernetes: KubernetesConfig = field(default_factory=KubernetesConfig)
    aws: AWSConfig = field(default_factory=AWSConfig)
    vm: VMConfig = field(default_factory=VMConfig)
    isolation: IsolationConfig = field(default_factory=IsolationConfig)
    cost_optimization: CostOptimizationConfig = field(default_factory=CostOptimizationConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    @classmethod
    def from_file(cls, config_path: Union[str, Path]) -> 'InfraSDKConfig':
        """
        Load configuration from YAML file.
        
        Args:
            config_path: Path to YAML configuration file
            
        Returns:
            InfraSDKConfig instance with loaded configuration
            
        Raises:
            ConfigurationError: If file cannot be read or parsed
        """
        try:
            path = Path(config_path)
            if not path.exists():
                raise ConfigurationError(
                    f"Configuration file not found: {config_path}",
                    config_key="config_path",
                    config_value=str(config_path)
                )
            
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
            
            return cls.from_dict(data)
        
        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Failed to parse YAML configuration: {e}",
                config_key="yaml_parsing"
            )
        except Exception as e:
            raise ConfigurationError(
                f"Failed to load configuration file: {e}",
                config_key="file_loading"
            )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'InfraSDKConfig':
        """
        Create configuration from dictionary.
        
        Args:
            data: Configuration dictionary
            
        Returns:
            InfraSDKConfig instance
        """
        config = cls()
        
        if 'kubernetes' in data:
            config.kubernetes = KubernetesConfig(**data['kubernetes'])
        
        if 'aws' in data:
            config.aws = AWSConfig(**data['aws'])
        
        if 'vm' in data:
            config.vm = VMConfig(**data['vm'])
        
        if 'isolation' in data:
            config.isolation = IsolationConfig(**data['isolation'])
        
        if 'cost_optimization' in data:
            config.cost_optimization = CostOptimizationConfig(**data['cost_optimization'])
        
        if 'logging' in data:
            config.logging = LoggingConfig(**data['logging'])
        
        return config
    
    @classmethod
    def from_dotenv(cls, dotenv_path: Optional[Union[str, Path]] = None) -> 'InfraSDKConfig':
        """
        Load configuration from .env file.
        
        Args:
            dotenv_path: Path to .env file. If None, looks for .env in current directory
            
        Returns:
            InfraSDKConfig instance with .env-based configuration
            
        Raises:
            ConfigurationError: If dotenv is not available or file cannot be loaded
        """
        if not _DOTENV_AVAILABLE:
            raise ConfigurationError(
                "python-dotenv is required for .env file support. Install with: pip install python-dotenv",
                config_key="dotenv_dependency"
            )
        
        if dotenv_path is None:
            dotenv_path = Path.cwd() / '.env'
        else:
            dotenv_path = Path(dotenv_path)
        
        if not dotenv_path.exists():
            raise ConfigurationError(
                f".env file not found: {dotenv_path}",
                config_key="dotenv_path",
                config_value=str(dotenv_path)
            )
        
        # Load .env file
        load_dotenv(dotenv_path)
        
        # Use environment method to parse loaded variables
        return cls.from_environment()
    
    @classmethod
    def from_environment(cls) -> 'InfraSDKConfig':
        """
        Create configuration from environment variables.
        
        Environment variables should be prefixed with 'INFRA_SDK_'
        and use double underscores for nested configuration.
        
        Examples:
            INFRA_SDK_AWS__REGION=us-east-1
            INFRA_SDK_VM__DEFAULT_CPU=4
            INFRA_SDK_LOGGING__LEVEL=DEBUG
        
        Returns:
            InfraSDKConfig instance with environment-based configuration
        """
        config = cls()
        
        # Kubernetes Configuration
        if config_path := os.getenv('INFRA_SDK_KUBERNETES__CONFIG_PATH'):
            config.kubernetes.config_path = config_path
        if context := os.getenv('INFRA_SDK_KUBERNETES__CONTEXT'):
            config.kubernetes.context = context
        if namespace := os.getenv('INFRA_SDK_KUBERNETES__NAMESPACE'):
            config.kubernetes.namespace = namespace
        
        # AWS Configuration
        if region := os.getenv('INFRA_SDK_AWS__REGION'):
            config.aws.region = region
        if access_key := os.getenv('INFRA_SDK_AWS__ACCESS_KEY_ID'):
            config.aws.access_key_id = access_key
        if secret_key := os.getenv('INFRA_SDK_AWS__SECRET_ACCESS_KEY'):
            config.aws.secret_access_key = secret_key
        if session_token := os.getenv('INFRA_SDK_AWS__SESSION_TOKEN'):
            config.aws.session_token = session_token
        if profile := os.getenv('INFRA_SDK_AWS__PROFILE'):
            config.aws.profile = profile
        if cluster_name := os.getenv('INFRA_SDK_AWS__CLUSTER_NAME'):
            config.aws.cluster_name = cluster_name
        if spot_pref := os.getenv('INFRA_SDK_AWS__SPOT_INSTANCE_PREFERRED'):
            config.aws.spot_instance_preferred = spot_pref.lower() == 'true'
        if vpc_id := os.getenv('INFRA_SDK_AWS__VPC_ID'):
            config.aws.vpc_id = vpc_id
        
        # VM Configuration
        if cpu := os.getenv('INFRA_SDK_VM__DEFAULT_CPU'):
            config.vm.default_cpu = cpu
        if memory := os.getenv('INFRA_SDK_VM__DEFAULT_MEMORY'):
            config.vm.default_memory = memory
        if disk_size := os.getenv('INFRA_SDK_VM__DEFAULT_DISK_SIZE'):
            config.vm.default_disk_size = disk_size
        if windows_image := os.getenv('INFRA_SDK_VM__WINDOWS_BASE_IMAGE'):
            config.vm.windows_base_image = windows_image
        if linux_image := os.getenv('INFRA_SDK_VM__LINUX_BASE_IMAGE'):
            config.vm.linux_base_image = linux_image
        
        # Isolation Configuration
        if dedicated_nodes := os.getenv('INFRA_SDK_ISOLATION__DEDICATED_NODES'):
            config.isolation.dedicated_nodes = dedicated_nodes.lower() == 'true'
        if network_policies := os.getenv('INFRA_SDK_ISOLATION__NETWORK_POLICIES_ENABLED'):
            config.isolation.network_policies_enabled = network_policies.lower() == 'true'
        if encrypted_storage := os.getenv('INFRA_SDK_ISOLATION__ENCRYPTED_STORAGE'):
            config.isolation.encrypted_storage = encrypted_storage.lower() == 'true'
        
        # Cost Optimization Configuration
        if spot_preference := os.getenv('INFRA_SDK_COST__SPOT_INSTANCE_PREFERENCE'):
            config.cost_optimization.spot_instance_preference = float(spot_preference)
        if idle_timeout := os.getenv('INFRA_SDK_COST__IDLE_TIMEOUT'):
            config.cost_optimization.idle_timeout = int(idle_timeout)
        if daily_budget := os.getenv('INFRA_SDK_COST__DAILY_BUDGET_LIMIT'):
            config.cost_optimization.daily_budget_limit = float(daily_budget)
        if monthly_budget := os.getenv('INFRA_SDK_COST__MONTHLY_BUDGET_LIMIT'):
            config.cost_optimization.monthly_budget_limit = float(monthly_budget)
        
        # Logging Configuration
        if log_level := os.getenv('INFRA_SDK_LOGGING__LEVEL'):
            config.logging.level = log_level.upper()
        if log_format := os.getenv('INFRA_SDK_LOGGING__FORMAT'):
            config.logging.format = log_format
        if log_output := os.getenv('INFRA_SDK_LOGGING__OUTPUT'):
            config.logging.output = log_output
        if log_file := os.getenv('INFRA_SDK_LOGGING__FILE_PATH'):
            config.logging.file_path = log_file
        
        return config
    
    def validate(self) -> None:
        """
        Validate entire configuration.
        
        Raises:
            ConfigurationError: If any configuration is invalid
        """
        # Individual dataclass __post_init__ methods handle validation
        # This method can be extended for cross-section validation
        
        # Example cross-validation
        if self.cost_optimization.budget_alerts_enabled:
            if not (self.cost_optimization.daily_budget_limit or 
                   self.cost_optimization.monthly_budget_limit):
                raise ConfigurationError(
                    "Budget limits must be set when budget alerts are enabled",
                    config_key="budget_configuration"
                )
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of configuration
        """
        return {
            'kubernetes': self.kubernetes.__dict__,
            'aws': self.aws.__dict__,
            'vm': self.vm.__dict__,
            'isolation': self.isolation.__dict__,
            'cost_optimization': self.cost_optimization.__dict__,
            'logging': self.logging.__dict__
        }