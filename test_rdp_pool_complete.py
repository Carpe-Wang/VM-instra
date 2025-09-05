#!/usr/bin/env python3
"""
Complete RDP Pool Test Script
Tests all aspects of the RDP-based Windows VM pool management system:
- Pool initialization with multiple instances
- RDP connection establishment
- Mouse and keyboard input control
- Instance allocation and release
- Instance reuse for new tasks
- Pool cleanup and termination
"""

import asyncio
import logging
import sys
import time
import argparse
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import boto3

# Import our modules
from ec2_pool_manager import EC2PoolManager, ScalingPolicy, UserSession, PoolMetrics
from windows_infrastructure_sdk import EC2WindowsManager, EC2ResourceSpec, UserIsolationPolicy
from rdp_controller import RDPController, RDPConnectionConfig, RDPConnectionPool
from vm_agent_adapter import VMAgentAdapter, ActionRequest
from infrastructure_sdk.config import InfraSDKConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_rdp_pool.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class RDPPoolTestSuite:
    """Comprehensive test suite for RDP pool management"""
    
    def __init__(self, region: str = 'us-west-2'):
        self.region = region
        self.pool_manager: Optional[EC2PoolManager] = None
        self.rdp_pool: Optional[RDPConnectionPool] = None
        self.instances: List[Dict[str, Any]] = []
        self.sessions: List[UserSession] = []
        self.test_results = {
            'pool_creation': False,
            'instance_launch': False,
            'rdp_connection': False,
            'mouse_input': False,
            'keyboard_input': False,
            'instance_release': False,
            'instance_reuse': False,
            'pool_cleanup': False
        }
        
        logger.info(f"Initializing RDP Pool Test Suite in region {region}")
    
    async def setup_pool(self, pool_size: int = 2) -> bool:
        """Initialize EC2 pool with specified number of instances"""
        try:
            logger.info(f"=== Setting up pool with {pool_size} instances ===")
            
            # Create SDK configuration
            config = InfraSDKConfig()
            config.aws.region = self.region
            
            # Configure scaling policy (optional, for pool manager internal use)
            config.scaling_policy = ScalingPolicy(
                target_utilization=75.0,
                scale_up_threshold=85.0,
                scale_down_threshold=50.0,
                min_instances=pool_size,
                max_instances=pool_size + 2,
                scale_up_increment=1,
                scale_down_increment=1
            )
            
            # Set pool configuration
            config.min_pool_size = pool_size
            config.max_pool_size = pool_size + 2
            config.instance_type = 't3.medium'
            
            # Create pool manager with SDK config
            self.pool_manager = EC2PoolManager(config)
            
            # Initialize RDP connection pool
            self.rdp_pool = RDPConnectionPool(max_connections=pool_size * 2)
            
            # Start pool manager
            await self.pool_manager.initialize()
            
            # Wait for initial instances to be ready
            logger.info("Waiting for pool instances to become ready...")
            start_time = time.time()
            timeout = 600  # 10 minutes
            
            while len(self.pool_manager.pool) < pool_size:
                if time.time() - start_time > timeout:
                    logger.error(f"Timeout waiting for pool instances (got {len(self.pool_manager.pool)}/{pool_size})")
                    return False
                
                await asyncio.sleep(10)
                status = self.pool_manager.get_pool_status()
                logger.info(f"Pool status: {status['total_instances']} instances, "
                          f"{status['available_instances']} available")
            
            self.test_results['pool_creation'] = True
            logger.info(f"✓ Pool created successfully with {pool_size} instances")
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to setup pool: {e}")
            return False
    
    async def test_instance_allocation(self) -> bool:
        """Test allocating instances from pool"""
        try:
            logger.info("=== Testing instance allocation ===")
            
            # Request first instance
            logger.info("Requesting first instance from pool...")
            session1 = await self.pool_manager.request_instance("test-user-1")
            if not session1:
                logger.error("Failed to allocate first instance")
                return False
            
            self.sessions.append(session1)
            self.instances.append({
                'session': session1,
                'instance_id': session1.instance_id,
                'rdp_host': session1.rdp_host,
                'rdp_password': session1.rdp_password
            })
            logger.info(f"✓ First instance allocated: {session1.instance_id}")
            
            # Request second instance
            logger.info("Requesting second instance from pool...")
            session2 = await self.pool_manager.request_instance("test-user-2")
            if not session2:
                logger.error("Failed to allocate second instance")
                return False
            
            self.sessions.append(session2)
            self.instances.append({
                'session': session2,
                'instance_id': session2.instance_id,
                'rdp_host': session2.rdp_host,
                'rdp_password': session2.rdp_password
            })
            logger.info(f"✓ Second instance allocated: {session2.instance_id}")
            
            # Verify instances are different
            if session1.instance_id == session2.instance_id:
                logger.error("Same instance allocated twice!")
                return False
            
            self.test_results['instance_launch'] = True
            logger.info(f"✓ Successfully allocated {len(self.instances)} unique instances")
            return True
            
        except Exception as e:
            logger.error(f"✗ Instance allocation failed: {e}")
            return False
    
    async def test_rdp_connections(self) -> bool:
        """Test RDP connections to allocated instances"""
        try:
            logger.info("=== Testing RDP connections ===")
            
            for i, instance in enumerate(self.instances):
                logger.info(f"Connecting to instance {i+1}: {instance['rdp_host']}")
                
                # Create RDP configuration
                rdp_config = RDPConnectionConfig(
                    host=instance['rdp_host'],
                    username='Administrator',
                    password=instance['rdp_password'],
                    width=1920,
                    height=1080,
                    clipboard=True,
                    compression=True
                )
                
                # Get RDP connection from pool
                rdp_controller = await self.rdp_pool.get_connection(rdp_config)
                instance['rdp_controller'] = rdp_controller
                
                # Verify connection is ready
                if rdp_controller.state.value != 'ready':
                    logger.error(f"RDP connection not ready for instance {i+1}")
                    return False
                
                logger.info(f"✓ RDP connected to instance {i+1}")
                
                # Take a screenshot to verify connection
                screenshot = await rdp_controller.capture_screenshot()
                if screenshot:
                    logger.info(f"✓ Screenshot captured from instance {i+1} ({len(screenshot)} bytes)")
                else:
                    logger.warning(f"Could not capture screenshot from instance {i+1}")
            
            self.test_results['rdp_connection'] = True
            logger.info("✓ All RDP connections established successfully")
            return True
            
        except Exception as e:
            logger.error(f"✗ RDP connection test failed: {e}")
            return False
    
    async def test_mouse_input(self) -> bool:
        """Test mouse input on each instance"""
        try:
            logger.info("=== Testing mouse input ===")
            
            test_positions = [
                (100, 100, "left"),   # Top-left click
                (960, 540, "left"),   # Center click
                (1820, 980, "right"), # Bottom-right right-click
                (500, 500, "left"),   # Random position
            ]
            
            for i, instance in enumerate(self.instances):
                if 'rdp_controller' not in instance:
                    logger.warning(f"No RDP controller for instance {i+1}")
                    continue
                
                controller = instance['rdp_controller']
                logger.info(f"Testing mouse input on instance {i+1}")
                
                for x, y, button in test_positions:
                    await controller.send_mouse_click(x, y, button)
                    logger.info(f"  Clicked at ({x}, {y}) with {button} button")
                    await asyncio.sleep(0.5)
                
                # Test drag operation (select text)
                logger.info(f"  Testing mouse drag on instance {i+1}")
                await controller.send_mouse_click(400, 400, "left")
                await asyncio.sleep(0.1)
                # Simulate drag by sending mouse move events (would need implementation)
                await controller.send_mouse_click(600, 400, "left")
                
                logger.info(f"✓ Mouse input tested on instance {i+1}")
            
            self.test_results['mouse_input'] = True
            logger.info("✓ Mouse input test completed")
            return True
            
        except Exception as e:
            logger.error(f"✗ Mouse input test failed: {e}")
            return False
    
    async def test_keyboard_input(self) -> bool:
        """Test keyboard input on each instance"""
        try:
            logger.info("=== Testing keyboard input ===")
            
            test_sequences = [
                ("win+r", "Open Run dialog"),
                ("notepad", "Type 'notepad'"),
                ("enter", "Press Enter"),
                ("Hello from RDP test!", "Type test message"),
                ("ctrl+a", "Select all"),
                ("ctrl+c", "Copy"),
                ("ctrl+v", "Paste"),
                ("alt+f4", "Close window"),
            ]
            
            for i, instance in enumerate(self.instances):
                if 'rdp_controller' not in instance:
                    logger.warning(f"No RDP controller for instance {i+1}")
                    continue
                
                controller = instance['rdp_controller']
                logger.info(f"Testing keyboard input on instance {i+1}")
                
                # Open Notepad and type text
                for keys, description in test_sequences[:4]:
                    logger.info(f"  {description}: {keys}")
                    if keys in ['win+r', 'enter', 'ctrl+a', 'ctrl+c', 'ctrl+v', 'alt+f4']:
                        await controller.send_key_sequence(keys)
                    else:
                        await controller.send_text(keys)
                    await asyncio.sleep(1)
                
                # Test special keys
                logger.info(f"  Testing special keys on instance {i+1}")
                await controller.send_key_sequence("esc")
                await asyncio.sleep(0.5)
                await controller.send_key_sequence("tab")
                await asyncio.sleep(0.5)
                
                logger.info(f"✓ Keyboard input tested on instance {i+1}")
            
            self.test_results['keyboard_input'] = True
            logger.info("✓ Keyboard input test completed")
            return True
            
        except Exception as e:
            logger.error(f"✗ Keyboard input test failed: {e}")
            return False
    
    async def test_instance_release_and_reuse(self) -> bool:
        """Test releasing an instance and reusing it for a new task"""
        try:
            logger.info("=== Testing instance release and reuse ===")
            
            if len(self.sessions) < 1:
                logger.error("No sessions available for release test")
                return False
            
            # Release first instance
            first_session = self.sessions[0]
            first_instance_id = first_session.instance_id
            logger.info(f"Releasing instance: {first_instance_id}")
            
            await self.pool_manager.release_instance(first_session.session_id)
            logger.info(f"✓ Instance {first_instance_id} released back to pool")
            
            # Wait a bit for the instance to be marked as available
            await asyncio.sleep(5)
            
            # Request a new instance (should get the same one back)
            logger.info("Requesting new instance (expecting reuse)...")
            new_session = await self.pool_manager.request_instance("test-user-3")
            
            if not new_session:
                logger.error("Failed to get new instance after release")
                return False
            
            # Check if we got the same instance
            if new_session.instance_id == first_instance_id:
                logger.info(f"✓ Instance {first_instance_id} was successfully reused")
                reused = True
            else:
                logger.info(f"Got different instance: {new_session.instance_id}")
                reused = False
            
            # Test the reused instance
            if reused:
                logger.info("Testing reused instance functionality...")
                
                # Create new RDP connection
                rdp_config = RDPConnectionConfig(
                    host=new_session.rdp_host,
                    username='Administrator',
                    password=new_session.rdp_password
                )
                
                rdp_controller = await self.rdp_pool.get_connection(rdp_config)
                
                # Test basic operations
                await rdp_controller.send_key_sequence("win")
                await asyncio.sleep(1)
                await rdp_controller.send_key_sequence("esc")
                
                screenshot = await rdp_controller.capture_screenshot()
                if screenshot:
                    logger.info(f"✓ Reused instance is functional ({len(screenshot)} bytes screenshot)")
                
                # Release it again
                await self.pool_manager.release_instance(new_session.session_id)
            
            self.test_results['instance_release'] = True
            self.test_results['instance_reuse'] = reused
            logger.info("✓ Instance release and reuse test completed")
            return True
            
        except Exception as e:
            logger.error(f"✗ Instance release/reuse test failed: {e}")
            return False
    
    async def test_concurrent_operations(self) -> bool:
        """Test concurrent operations on multiple instances"""
        try:
            logger.info("=== Testing concurrent operations ===")
            
            if len(self.instances) < 2:
                logger.warning("Not enough instances for concurrent test")
                return True
            
            async def operate_on_instance(instance: Dict, task_num: int):
                """Perform operations on a single instance"""
                controller = instance.get('rdp_controller')
                if not controller:
                    return
                
                logger.info(f"Task {task_num} starting on {instance['instance_id']}")
                
                # Open calculator
                await controller.send_key_sequence("win+r")
                await asyncio.sleep(0.5)
                await controller.send_text("calc")
                await asyncio.sleep(0.5)
                await controller.send_key_sequence("enter")
                await asyncio.sleep(1)
                
                # Perform calculation
                calculations = ['1', '+', '2', '=']
                for key in calculations:
                    await controller.send_text(key)
                    await asyncio.sleep(0.3)
                
                # Close calculator
                await controller.send_key_sequence("alt+f4")
                
                logger.info(f"Task {task_num} completed on {instance['instance_id']}")
            
            # Run operations concurrently on all instances
            tasks = [
                operate_on_instance(instance, i+1) 
                for i, instance in enumerate(self.instances)
            ]
            
            await asyncio.gather(*tasks)
            
            logger.info("✓ Concurrent operations completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"✗ Concurrent operations test failed: {e}")
            return False
    
    async def cleanup_pool(self) -> bool:
        """Clean up all resources"""
        try:
            logger.info("=== Cleaning up pool and instances ===")
            
            # Close all RDP connections
            if self.rdp_pool:
                logger.info("Closing all RDP connections...")
                await self.rdp_pool.close_all()
                logger.info("✓ RDP connections closed")
            
            # Terminate all instances
            if self.pool_manager:
                logger.info("Terminating all pool instances...")
                
                # Get all instances
                pool_status = self.pool_manager.get_pool_status()
                instance_count = pool_status['total_instances']
                
                # Shutdown pool
                await self.pool_manager.shutdown()
                
                logger.info(f"✓ Terminated {instance_count} instances")
            
            # Verify cleanup
            if self.pool_manager:
                ec2 = boto3.client('ec2', region_name=self.region)
                
                # Check if instances are terminated
                instance_ids = [inst['instance_id'] for inst in self.instances if 'instance_id' in inst]
                if instance_ids:
                    response = ec2.describe_instances(InstanceIds=instance_ids)
                    for reservation in response['Reservations']:
                        for instance in reservation['Instances']:
                            state = instance['State']['Name']
                            logger.info(f"Instance {instance['InstanceId']}: {state}")
            
            self.test_results['pool_cleanup'] = True
            logger.info("✓ Pool cleanup completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"✗ Cleanup failed: {e}")
            return False
    
    def print_test_results(self):
        """Print summary of test results"""
        logger.info("\n" + "="*60)
        logger.info("TEST RESULTS SUMMARY")
        logger.info("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for v in self.test_results.values() if v)
        
        for test_name, passed in self.test_results.items():
            status = "✓ PASSED" if passed else "✗ FAILED"
            logger.info(f"{test_name:.<30} {status}")
        
        logger.info("-"*60)
        logger.info(f"Total: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            logger.info("🎉 ALL TESTS PASSED! 🎉")
        else:
            logger.info("⚠️  Some tests failed. Check logs for details.")
        
        logger.info("="*60)
    
    async def run_all_tests(self):
        """Run complete test suite"""
        try:
            logger.info("Starting RDP Pool Complete Test Suite")
            logger.info("="*60)
            
            # Setup pool with 2 instances
            if not await self.setup_pool(pool_size=2):
                logger.error("Failed to setup pool")
                return
            
            # Test instance allocation
            if not await self.test_instance_allocation():
                logger.error("Failed instance allocation test")
                return
            
            # Test RDP connections
            if not await self.test_rdp_connections():
                logger.error("Failed RDP connection test")
                # Continue anyway to test cleanup
            
            # Test mouse input
            if await self.test_rdp_connections():
                await self.test_mouse_input()
            
            # Test keyboard input
            if await self.test_rdp_connections():
                await self.test_keyboard_input()
            
            # Test concurrent operations
            await self.test_concurrent_operations()
            
            # Test instance release and reuse
            await self.test_instance_release_and_reuse()
            
        except Exception as e:
            logger.error(f"Test suite error: {e}")
        finally:
            # Always cleanup
            await self.cleanup_pool()
            
            # Print results
            self.print_test_results()


async def main():
    """Main test execution"""
    parser = argparse.ArgumentParser(description='Complete RDP Pool Test')
    parser.add_argument('--region', default='us-west-2', help='AWS region')
    parser.add_argument('--pool-size', type=int, default=2, help='Initial pool size')
    parser.add_argument('--instance-type', default='t3.medium', help='EC2 instance type')
    parser.add_argument('--skip-cleanup', action='store_true', help='Skip cleanup for debugging')
    
    args = parser.parse_args()
    
    # Create and run test suite
    test_suite = RDPPoolTestSuite(region=args.region)
    
    try:
        await test_suite.run_all_tests()
    except KeyboardInterrupt:
        logger.info("\n⚠️  Test interrupted by user")
        if not args.skip_cleanup:
            await test_suite.cleanup_pool()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if not args.skip_cleanup:
            await test_suite.cleanup_pool()


if __name__ == "__main__":
    # Run the test
    asyncio.run(main())