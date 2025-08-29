#!/usr/bin/env python3
"""
Configuration Demo Script

This script demonstrates different ways to load configuration
in the Infrastructure SDK, including .env file support.
"""

import os
from pathlib import Path
from infrastructure_sdk.config import InfraSDKConfig

def demo_env_config():
    """Demonstrate .env configuration loading."""
    print("=" * 60)
    print("🔧 Infrastructure SDK Configuration Demo")
    print("=" * 60)
    
    # Method 1: Load from .env file
    print("\n1️⃣ Loading from .env file:")
    print("   Copy .env.example to .env and fill in your values")
    
    try:
        config = InfraSDKConfig.from_dotenv()
        print("   ✅ Configuration loaded successfully from .env")
        print(f"   📍 AWS Region: {config.aws.region}")
        print(f"   📍 K8s Namespace: {config.kubernetes.namespace}")
        print(f"   📍 VM CPU: {config.vm.default_cpu}")
        print(f"   📍 Log Level: {config.logging.level}")
        return config
    except Exception as e:
        print(f"   ❌ Error loading .env: {e}")
        print("   💡 Try copying .env.example to .env first")
    
    # Method 2: Load from environment variables
    print("\n2️⃣ Loading from environment variables:")
    print("   Setting some example environment variables...")
    
    os.environ['INFRA_SDK_AWS__REGION'] = 'us-east-1'
    os.environ['INFRA_SDK_AWS__CLUSTER_NAME'] = 'my-test-cluster'
    os.environ['INFRA_SDK_VM__DEFAULT_CPU'] = '8'
    os.environ['INFRA_SDK_LOGGING__LEVEL'] = 'DEBUG'
    
    try:
        config = InfraSDKConfig.from_environment()
        print("   ✅ Configuration loaded from environment")
        print(f"   📍 AWS Region: {config.aws.region}")
        print(f"   📍 Cluster: {config.aws.cluster_name}")
        print(f"   📍 VM CPU: {config.vm.default_cpu}")
        print(f"   📍 Log Level: {config.logging.level}")
        return config
    except Exception as e:
        print(f"   ❌ Error loading environment config: {e}")
    
    # Method 3: Default configuration
    print("\n3️⃣ Using default configuration:")
    try:
        config = InfraSDKConfig()
        # Override required fields to bypass validation
        config.aws.cluster_name = "default-cluster"
        config.kubernetes.config_path = str(Path.home() / ".kube" / "config")
        
        print("   ✅ Default configuration created")
        print(f"   📍 AWS Region: {config.aws.region}")
        print(f"   📍 VM Memory: {config.vm.default_memory}")
        print(f"   📍 Isolation: {'Enabled' if config.isolation.dedicated_nodes else 'Disabled'}")
        return config
    except Exception as e:
        print(f"   ❌ Error creating default config: {e}")
    
    return None

def show_config_details(config: InfraSDKConfig):
    """Show detailed configuration information."""
    print("\n" + "=" * 60)
    print("📋 Configuration Details")
    print("=" * 60)
    
    print("\n🔧 Kubernetes Configuration:")
    print(f"   Config Path: {config.kubernetes.config_path}")
    print(f"   Namespace: {config.kubernetes.namespace}")
    print(f"   KubeVirt Namespace: {config.kubernetes.kubevirt_namespace}")
    
    print("\n☁️  AWS Configuration:")
    print(f"   Region: {config.aws.region}")
    print(f"   Cluster: {config.aws.cluster_name}")
    print(f"   Spot Preferred: {config.aws.spot_instance_preferred}")
    print(f"   Default Instance Types: {', '.join(config.aws.default_instance_types[:3])}...")
    
    print("\n💻 VM Configuration:")
    print(f"   Default CPU: {config.vm.default_cpu}")
    print(f"   Default Memory: {config.vm.default_memory}")
    print(f"   Default Disk: {config.vm.default_disk_size}")
    print(f"   Windows Timeout: {config.vm.windows_startup_timeout}s")
    
    print("\n🛡️  Isolation Configuration:")
    print(f"   Dedicated Nodes: {config.isolation.dedicated_nodes}")
    print(f"   Network Policies: {config.isolation.network_policies_enabled}")
    print(f"   Encrypted Storage: {config.isolation.encrypted_storage}")
    
    print("\n💰 Cost Optimization:")
    print(f"   Spot Preference: {config.cost_optimization.spot_instance_preference:.1%}")
    print(f"   Idle Timeout: {config.cost_optimization.idle_timeout}s")
    print(f"   Target Cost Reduction: {config.cost_optimization.target_cost_reduction:.1%}")
    
    print("\n📝 Logging Configuration:")
    print(f"   Level: {config.logging.level}")
    print(f"   Format: {config.logging.format}")
    print(f"   Output: {config.logging.output}")

def create_sample_env():
    """Create a sample .env file for testing."""
    env_path = Path(".env.demo")
    
    print(f"\n📝 Creating sample .env file at: {env_path}")
    
    sample_content = """# Sample Infrastructure SDK Configuration
INFRA_SDK_AWS__REGION=us-west-2
INFRA_SDK_AWS__CLUSTER_NAME=demo-cluster
INFRA_SDK_AWS__SPOT_INSTANCE_PREFERRED=true

INFRA_SDK_VM__DEFAULT_CPU=4
INFRA_SDK_VM__DEFAULT_MEMORY=8Gi
INFRA_SDK_VM__DEFAULT_DISK_SIZE=50Gi

INFRA_SDK_ISOLATION__DEDICATED_NODES=true
INFRA_SDK_ISOLATION__ENCRYPTED_STORAGE=true

INFRA_SDK_LOGGING__LEVEL=INFO
INFRA_SDK_LOGGING__FORMAT=json
"""
    
    with open(env_path, 'w') as f:
        f.write(sample_content)
    
    print(f"   ✅ Sample .env created: {env_path}")
    print(f"   💡 Test with: config = InfraSDKConfig.from_dotenv('{env_path}')")
    
    # Test loading the sample
    try:
        config = InfraSDKConfig.from_dotenv(env_path)
        print(f"   ✅ Sample .env loads successfully!")
        print(f"   📍 Sample config - Region: {config.aws.region}, CPU: {config.vm.default_cpu}")
    except Exception as e:
        print(f"   ❌ Error loading sample .env: {e}")

def main():
    """Main demo function."""
    config = demo_env_config()
    
    if config:
        show_config_details(config)
    
    print("\n" + "=" * 60)
    create_sample_env()
    
    print("\n" + "=" * 60)
    print("🎯 Summary:")
    print("   • Use .env files for local development")
    print("   • Use environment variables in production")
    print("   • All config keys follow INFRA_SDK_SECTION__KEY pattern")
    print("   • Boolean values: 'true'/'false' (case insensitive)")
    print("   • Copy .env.example to .env and customize")
    print("=" * 60)

if __name__ == "__main__":
    main()