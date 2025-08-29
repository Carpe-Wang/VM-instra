#!/usr/bin/env python3
"""
Infrastructure SDK Example Usage

This script demonstrates the basic usage of the Infrastructure SDK
for VM-based user isolation and lifecycle management.
"""

import asyncio
import logging
from infrastructure_sdk import (
    UserSessionManager,
    VMLifecycleController,
    IsolationEngine,
    SessionRequest,
    ResourceSpec
)
from infrastructure_sdk.config import (
    InfraSDKConfig,
    KubernetesConfig,
    AWSConfig,
    LoggingConfig
)
from infrastructure_sdk.logging import setup_logging, get_logger


async def main():
    """Main example demonstrating Infrastructure SDK usage."""
    
    # Option 1: Load configuration from .env file
    print("Loading configuration from .env file...")
    try:
        config = InfraSDKConfig.from_dotenv()
        print("✅ Configuration loaded from .env successfully")
    except Exception as e:
        print(f"❌ Failed to load .env config: {e}")
        print("📝 Creating demo configuration instead...")
        
        # Fallback: Set up mock configuration for demo
        # Create components individually to bypass validation
        k8s_config = KubernetesConfig.__new__(KubernetesConfig)
        k8s_config.config_path = "/dev/null"
        k8s_config.namespace = "default"
        k8s_config.kubevirt_namespace = "kubevirt"
        
        aws_config = AWSConfig.__new__(AWSConfig)
        aws_config.cluster_name = "demo-cluster"
        aws_config.region = "us-west-2"
        aws_config.access_key_id = "demo-key"
        aws_config.secret_access_key = "demo-secret"
        aws_config.default_instance_types = ["m5.large"]
        aws_config.spot_instance_preferred = True
        
        logging_config = LoggingConfig()
        logging_config.level = "INFO"
        logging_config.format = "text"
        
        # Create main config
        config = InfraSDKConfig.__new__(InfraSDKConfig)
        config.kubernetes = k8s_config
        config.aws = aws_config
        config.logging = logging_config
        
        # Set defaults for other components
        from infrastructure_sdk.config import VMConfig, IsolationConfig, CostOptimizationConfig
        config.vm = VMConfig()
        config.isolation = IsolationConfig()
        config.cost_optimization = CostOptimizationConfig()
    
    setup_logging(config.logging)
    
    logger = get_logger(__name__)
    logger.info("Starting Infrastructure SDK example")
    
    try:
        
        # Initialize SDK components
        logger.info("Initializing SDK components...")
        session_manager = UserSessionManager(config)
        vm_controller = VMLifecycleController(config)
        isolation_engine = IsolationEngine(config)
        
        # Create a session request
        logger.info("Creating session request...")
        session_request = SessionRequest(
            user_id="demo-user-123",
            session_type="desktop",
            vm_os="windows",
            resources=ResourceSpec(
                cpu="4",
                memory="8Gi", 
                disk_size="100Gi"
            ),
            ttl="2h",
            allow_spot=True,
            tags={
                "environment": "demo",
                "project": "infrastructure-sdk-demo"
            }
        )
        
        # Create user session
        logger.info(f"Creating session for user: {session_request.user_id}")
        session = await session_manager.create_session(None, session_request)
        logger.info(f"Session created successfully: {session.session_id}")
        
        # Wait a moment for provisioning to start
        await asyncio.sleep(2)
        
        # Get session details
        retrieved_session = await session_manager.get_session(None, session.session_id)
        logger.info(f"Session state: {retrieved_session.state.value}")
        
        # List user sessions
        user_sessions = await session_manager.list_user_sessions(None, session_request.user_id)
        logger.info(f"User has {len(user_sessions)} sessions")
        
        # Validate isolation (this would run actual checks in production)
        logger.info("Validating session isolation...")
        isolation_report = await isolation_engine.validate_isolation(
            ctx={"demo": True},
            session_id=session.session_id,
            user_id=session.user_id
        )
        logger.info(f"Isolation score: {isolation_report.isolation_score:.2f}")
        logger.info(f"Overall status: {isolation_report.overall_status.value}")
        
        # Wait for session to transition (simulated)
        logger.info("Waiting for session provisioning...")
        await asyncio.sleep(5)
        
        # Check session state again
        updated_session = await session_manager.get_session(None, session.session_id)
        logger.info(f"Updated session state: {updated_session.state.value}")
        
        # Demonstrate session operations
        if updated_session.state.value == "active":
            # Suspend session
            logger.info("Suspending session...")
            await session_manager.suspend_session(None, session.session_id)
            suspended_session = await session_manager.get_session(None, session.session_id)
            logger.info(f"Session suspended: {suspended_session.state.value}")
            
            # Resume session
            logger.info("Resuming session...")
            await session_manager.resume_session(None, session.session_id)
            resumed_session = await session_manager.get_session(None, session.session_id)
            logger.info(f"Session resumed: {resumed_session.state.value}")
        
        # Clean up - terminate session
        logger.info("Terminating session...")
        await session_manager.terminate_session(None, session.session_id)
        
        # Wait for cleanup
        await asyncio.sleep(2)
        
        final_session = await session_manager.get_session(None, session.session_id)
        logger.info(f"Final session state: {final_session.state.value}")
        
        logger.info("Infrastructure SDK example completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during example execution: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())