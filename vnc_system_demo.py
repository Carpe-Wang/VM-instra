#!/usr/bin/env python3
"""
TightVNC Windows VM Control System - Complete Demo

This demo script demonstrates the complete TightVNC Windows VM control system:
1. VM Pool Manager with TightVNC integration
2. Web VNC Gateway for browser-based remote desktop
3. HTML5 VNC viewer with real-time interaction
4. Comprehensive automation and monitoring

Usage:
    python vnc_system_demo.py [--config config.yaml] [--demo-mode]
"""

import asyncio
import argparse
import logging
import yaml
import sys
import os
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from ec2_pool_manager import EC2PoolManager
from web_vnc_gateway import create_vnc_web_gateway
from infrastructure_sdk.config import InfraSDKConfig
# Note: logging setup will be handled directly


class VNCSystemDemo:
    """Complete TightVNC System Demonstration."""
    
    def __init__(self, config_path: str = None, demo_mode: bool = False):
        """Initialize VNC System Demo."""
        self.config_path = config_path or "enterprise_config.yaml"
        self.demo_mode = demo_mode
        self.logger = None
        self.config = None
        self.pool_manager = None
        self.vnc_gateway = None
        
    async def setup_system(self):
        """Set up the complete VNC system."""
        print("🚀 Starting TightVNC Windows VM Control System Demo")
        print("=" * 60)
        
        try:
            # Load configuration
            print("📁 Loading configuration...")
            self.config = await self._load_configuration()
            
            # Setup logging
            print("📝 Setting up logging...")
            logging.basicConfig(
                level=getattr(logging, self.config.logging.level),
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            self.logger = logging.getLogger(__name__)
            self.logger.info("VNC System Demo starting up")
            
            # Initialize EC2 Pool Manager with VNC support
            print("🖥️  Initializing EC2 Pool Manager with VNC integration...")
            self.pool_manager = EC2PoolManager(self.config)
            
            # Initialize VNC Web Gateway
            print("🌐 Setting up VNC Web Gateway...")
            # Use default gateway config since it's not in the config class yet
            self.vnc_gateway = create_vnc_web_gateway(
                pool_manager=self.pool_manager,
                host="localhost",
                websocket_port=8081,
                http_port=8080
            )
            
            # Start pool management
            print("⚡ Starting pool management services...")
            await self.pool_manager.start_pool_management()
            
            # Start VNC gateway
            print("🔗 Starting VNC Web Gateway servers...")
            await self.vnc_gateway.start_server()
            
            print("✅ TightVNC System initialized successfully!")
            self._print_system_info()
            
        except Exception as e:
            print(f"❌ Failed to setup VNC system: {e}")
            self.logger.error(f"System setup failed: {e}") if self.logger else None
            raise
    
    async def run_demo_scenarios(self):
        """Run demonstration scenarios."""
        if not self.demo_mode:
            print("💡 Use --demo-mode to run automated demo scenarios")
            return
            
        print("\n🎭 Running Demo Scenarios")
        print("=" * 40)
        
        scenarios = [
            self._demo_vm_creation,
            self._demo_vnc_connection,
            self._demo_automation_commands,
            self._demo_pool_scaling,
            self._demo_monitoring_metrics
        ]
        
        for i, scenario in enumerate(scenarios, 1):
            try:
                print(f"\n📋 Demo {i}/{len(scenarios)}: {scenario.__name__}")
                await scenario()
                await asyncio.sleep(2)  # Brief pause between demos
            except Exception as e:
                print(f"❌ Demo scenario failed: {e}")
                self.logger.error(f"Demo scenario {scenario.__name__} failed: {e}")
    
    async def _demo_vm_creation(self):
        """Demo: Create Windows VM with TightVNC."""
        print("Creating Windows VM with TightVNC auto-installation...")
        
        from windows_infrastructure_sdk import EC2ResourceSpec, UserIsolationPolicy
        
        # Configure VM specification
        resource_spec = EC2ResourceSpec(
            instance_type="t3.medium",  # Smaller instance for demo
            disk_size_gb=50,
            max_session_hours=2
        )
        
        isolation_policy = UserIsolationPolicy(
            dedicated_security_group=True,
            unique_instance_tags=True
        )
        
        # Request instance from pool
        try:
            instance = await self.pool_manager.request_instance(
                user_id="demo_user",
                resource_spec=resource_spec,
                isolation_policy=isolation_policy,
                session_timeout_minutes=120
            )
            
            print(f"✅ VM created successfully: {instance.instance_id}")
            print(f"   Instance Type: {instance.instance_type}")
            print(f"   Public IP: {instance.public_ip}")
            print(f"   VNC will be available on port 5900 after initialization")
            
            return instance
            
        except Exception as e:
            print(f"❌ VM creation failed: {e}")
            raise
    
    async def _demo_vnc_connection(self):
        """Demo: Test VNC connectivity."""
        print("Testing VNC connectivity to active instances...")
        
        # Get pool metrics to find active instances
        metrics = await self.pool_manager.get_pool_metrics()
        print(f"Active instances: {metrics.active_instances}")
        
        if metrics.active_instances > 0:
            # Test VNC connectivity on the first available instance
            for session_id, user_session in self.pool_manager.user_sessions.items():
                if user_session.vnc_ready:
                    print(f"Testing VNC connection for instance: {user_session.instance_id}")
                    
                    try:
                        vnc_test = await self.pool_manager.test_instance_vnc(user_session.instance_id)
                        print(f"VNC Test Results: {vnc_test}")
                        
                        if vnc_test.get('vnc_ready'):
                            print("✅ VNC connection is ready and working!")
                        else:
                            print("⚠️ VNC connection not ready yet")
                        
                    except Exception as e:
                        print(f"❌ VNC test failed: {e}")
                    
                    break
            else:
                print("ℹ️ No VNC-ready instances found")
        else:
            print("ℹ️ No active instances to test")
    
    async def _demo_automation_commands(self):
        """Demo: Automation commands via VNC."""
        print("Demonstrating Windows automation via VNC...")
        
        # Find a VNC-ready session
        for session_id, user_session in self.pool_manager.user_sessions.items():
            if user_session.vnc_ready and user_session.vnc_controller:
                print(f"Executing automation commands on instance: {user_session.instance_id}")
                
                controller = user_session.vnc_controller
                
                # Demo commands
                demo_commands = [
                    ("desktop", "Show Desktop"),
                    ("notepad", "Open Notepad"),
                    ("run_dialog", "Open Run Dialog"),
                    ("chrome", "Launch Chrome Browser")
                ]
                
                for command, description in demo_commands:
                    try:
                        print(f"  🎯 {description}...")
                        success = await controller.execute_automation_command(command)
                        print(f"     {'✅' if success else '❌'} {description} {'completed' if success else 'failed'}")
                        await asyncio.sleep(1)  # Brief delay between commands
                        
                    except Exception as e:
                        print(f"     ❌ Command failed: {e}")
                
                # Demo screenshot capture
                try:
                    print("  📷 Capturing screenshot...")
                    screenshot = await controller.capture_screenshot()
                    if screenshot:
                        print(f"     ✅ Screenshot captured: {len(screenshot)} bytes")
                    else:
                        print("     ❌ Screenshot capture failed")
                        
                except Exception as e:
                    print(f"     ❌ Screenshot failed: {e}")
                
                break
        else:
            print("ℹ️ No VNC-ready instances available for automation demo")
    
    async def _demo_pool_scaling(self):
        """Demo: Pool scaling operations."""
        print("Demonstrating dynamic pool scaling...")
        
        # Get current pool status
        initial_metrics = await self.pool_manager.get_pool_metrics()
        print(f"Initial pool size: {initial_metrics.total_instances} instances")
        print(f"Warm instances: {len(self.pool_manager.warm_instances)}")
        print(f"Assigned instances: {len(self.pool_manager.assigned_instances)}")
        
        # Trigger scaling events (in a real scenario, this would be based on demand)
        print("Simulating high demand scenario...")
        
        # Force create additional warm instances
        try:
            print("Adding warm instances to pool...")
            await self.pool_manager._ensure_warm_pool()
            
            # Wait a moment and check metrics again
            await asyncio.sleep(5)
            final_metrics = await self.pool_manager.get_pool_metrics()
            
            print(f"Final pool size: {final_metrics.total_instances} instances")
            print(f"Scaling demonstration completed")
            
        except Exception as e:
            print(f"❌ Pool scaling demo failed: {e}")
    
    async def _demo_monitoring_metrics(self):
        """Demo: System monitoring and metrics."""
        print("Displaying system monitoring metrics...")
        
        # Pool metrics
        pool_metrics = await self.pool_manager.get_pool_metrics()
        print(f"\n📊 Pool Metrics:")
        print(f"   Total Instances: {pool_metrics.total_instances}")
        print(f"   Active Instances: {pool_metrics.active_instances}")
        print(f"   Spot Instances: {pool_metrics.spot_instances}")
        print(f"   Hourly Cost: ${pool_metrics.hourly_cost:.2f}")
        print(f"   Spot Savings: ${pool_metrics.spot_savings:.2f}")
        print(f"   Average Startup Time: {pool_metrics.avg_startup_time:.1f}s")
        print(f"   Success Rate: {pool_metrics.success_rate:.1f}%")
        
        # VNC Pool status
        vnc_status = self.pool_manager.get_vnc_pool_status()
        print(f"\n🔗 VNC Pool Status:")
        print(f"   Total Connections: {vnc_status.get('total_connections', 0)}")
        print(f"   Active Connections: {vnc_status.get('active_connections', 0)}")
        print(f"   Max Connections: {vnc_status.get('max_connections', 0)}")
        
        # Gateway status
        gateway_sessions = self.vnc_gateway.get_session_count()
        active_sessions = len(self.vnc_gateway.get_active_sessions())
        print(f"\n🌐 Web Gateway Status:")
        print(f"   Total Sessions: {gateway_sessions}")
        print(f"   Active Sessions: {active_sessions}")
        print(f"   Max Sessions: {self.vnc_gateway.max_concurrent_sessions}")
    
    async def _load_configuration(self):
        """Load system configuration."""
        if not os.path.exists(self.config_path):
            print(f"⚠️  Configuration file {self.config_path} not found, using defaults...")
            config = InfraSDKConfig()
        else:
            try:
                config = InfraSDKConfig.from_yaml(self.config_path)
            except Exception as e:
                print(f"⚠️  Failed to load {self.config_path}: {e}")
                print("🔄 Using default configuration for demo...")
                config = InfraSDKConfig()
        
        # Add demo-specific overrides  
        if self.demo_mode:
            print("🎮 Demo mode enabled - using mock credentials")
            # Set testing environment to bypass AWS credential validation
            os.environ['TESTING'] = '1'
            # Create a fresh config to avoid credential validation
            config = InfraSDKConfig.from_dotenv()
            config.aws.spot_instance_preferred = False  # Use on-demand for demos
            config.cost_optimization.max_concurrent_instances = 5  # Limit for demo
            
        return config
    
    def _print_system_info(self):
        """Print system access information."""
        # Use default gateway config since it's not in the config class yet
        
        print("\n🎯 System Access Information")
        print("=" * 40)
        print(f"VNC Web Gateway:")
        print(f"  Web Interface: http://localhost:8080")
        print(f"  VNC Viewer: http://localhost:8080/vnc")
        print(f"  WebSocket: ws://localhost:8081")
        print(f"  API Status: http://localhost:8080/api/status")
        print(f"  API Sessions: http://localhost:8080/api/sessions")
        
        print(f"\nConfiguration:")
        print(f"  Max Sessions: 50")
        print(f"  Frame Rate: 18 FPS")
        print(f"  Session Timeout: 60 minutes")
    
    async def wait_for_shutdown(self):
        """Wait for shutdown signal."""
        print("\n🏃 TightVNC System is now running!")
        print("Press Ctrl+C to stop the system gracefully...")
        
        try:
            # Keep running until interrupted
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            print("\n🛑 Shutdown signal received...")
    
    async def cleanup_system(self):
        """Clean up system resources."""
        print("🧹 Cleaning up system resources...")
        
        try:
            if self.vnc_gateway:
                await self.vnc_gateway.stop_server()
                print("✅ VNC Web Gateway stopped")
            
            if self.pool_manager:
                await self.pool_manager.stop_pool_management()
                print("✅ Pool Manager stopped")
                
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")
            if self.logger:
                self.logger.error(f"Cleanup failed: {e}")
        
        print("✅ System cleanup completed")


async def main():
    """Main demo function."""
    parser = argparse.ArgumentParser(description="TightVNC Windows VM Control System Demo")
    parser.add_argument("--config", default="enterprise_config.yaml", help="Configuration file path")
    parser.add_argument("--demo-mode", action="store_true", help="Run automated demo scenarios")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    
    args = parser.parse_args()
    
    # Set up basic logging for the demo script
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    demo = VNCSystemDemo(config_path=args.config, demo_mode=args.demo_mode)
    
    try:
        # Initialize system
        await demo.setup_system()
        
        # Run demo scenarios if requested
        if args.demo_mode:
            await demo.run_demo_scenarios()
        
        # Keep system running
        await demo.wait_for_shutdown()
        
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        print(f"❌ System error: {e}")
        logging.error(f"System error: {e}")
        return 1
    finally:
        await demo.cleanup_system()
    
    print("👋 TightVNC System Demo completed!")
    return 0


if __name__ == "__main__":
    # Run the demo
    exit_code = asyncio.run(main())
    sys.exit(exit_code)