#!/usr/bin/env python3
"""
Simplified RDP Pool Test Script
Tests the RDP-based Windows VM pool management system without complex dependencies
"""

import asyncio
import logging
import sys
import os
import time
import argparse
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import boto3
from dotenv import load_dotenv
import subprocess
import platform
import base64
import tempfile

# Load environment variables from .env file
load_dotenv()

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

class SimpleRDPPoolTest:
    """Simplified test for RDP pool management"""
    
    def __init__(self, region: str = 'us-west-2', instance_type: str = 't3.micro'):
        self.region = region
        self.instance_type = instance_type
        
        # Debug: Check if AWS credentials are loaded
        logger.info(f"AWS_ACCESS_KEY_ID present: {bool(os.getenv('AWS_ACCESS_KEY_ID'))}")
        logger.info(f"AWS_SECRET_ACCESS_KEY present: {bool(os.getenv('AWS_SECRET_ACCESS_KEY'))}")
        
        # Create EC2 client with explicit credential check
        try:
            self.ec2_client = boto3.client('ec2', region_name=region)
            # Test credentials by making a simple API call
            self.ec2_client.describe_regions()
            logger.info("✓ AWS credentials configured successfully")
        except Exception as e:
            logger.error(f"AWS credential error: {e}")
            raise
        
        self.instances = []
        self.test_results = {}
        
        logger.info(f"Initializing Simple RDP Pool Test in region {region}")
    
    async def create_windows_instances(self, count: int = 2) -> bool:
        """Create Windows EC2 instances with RDP enabled"""
        try:
            logger.info(f"=== Creating {count} Windows instances ===")
            
            # Find latest Windows Server 2022 AMI
            response = self.ec2_client.describe_images(
                Owners=['amazon'],
                Filters=[
                    {'Name': 'name', 'Values': ['Windows_Server-2022-English-Full-Base-*']},
                    {'Name': 'architecture', 'Values': ['x86_64']},
                    {'Name': 'state', 'Values': ['available']}
                ]
            )
            
            if not response['Images']:
                logger.error("No Windows AMI found")
                return False
            
            # Sort by creation date and get the latest
            images = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)
            ami_id = images[0]['ImageId']
            logger.info(f"Using AMI: {ami_id}")
            
            # Create security group for RDP
            sg_name = f'rdp-test-{datetime.now().strftime("%Y%m%d%H%M%S")}'
            try:
                sg_response = self.ec2_client.create_security_group(
                    GroupName=sg_name,
                    Description='Security group for RDP test'
                )
                security_group_id = sg_response['GroupId']
                
                # Add RDP rule
                self.ec2_client.authorize_security_group_ingress(
                    GroupId=security_group_id,
                    IpPermissions=[
                        {
                            'IpProtocol': 'tcp',
                            'FromPort': 3389,
                            'ToPort': 3389,
                            'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                        }
                    ]
                )
                logger.info(f"Created security group: {security_group_id}")
            except Exception as e:
                logger.warning(f"Security group creation failed, using default: {e}")
                security_group_id = None
            
            # Launch instances
            launch_params = {
                'ImageId': ami_id,
                'InstanceType': self.instance_type,
                'MinCount': count,
                'MaxCount': count,
                'TagSpecifications': [
                    {
                        'ResourceType': 'instance',
                        'Tags': [
                            {'Key': 'Name', 'Value': 'RDP-Test-Instance'},
                            {'Key': 'Test', 'Value': 'RDPPool'}
                        ]
                    }
                ]
            }
            
            if security_group_id:
                launch_params['SecurityGroupIds'] = [security_group_id]
            
            response = self.ec2_client.run_instances(**launch_params)
            
            for instance in response['Instances']:
                self.instances.append({
                    'instance_id': instance['InstanceId'],
                    'state': 'pending',
                    'public_ip': None,
                    'rdp_password': None
                })
                logger.info(f"Launched instance: {instance['InstanceId']}")
            
            self.test_results['instance_launch'] = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to create instances: {e}")
            self.test_results['instance_launch'] = False
            return False
    
    async def wait_for_instances(self) -> bool:
        """Wait for instances to be running and get public IPs"""
        try:
            logger.info("=== Waiting for instances to be ready ===")
            
            instance_ids = [inst['instance_id'] for inst in self.instances]
            
            # Wait for instances to be running
            logger.info("Waiting for instances to enter 'running' state...")
            waiter = self.ec2_client.get_waiter('instance_running')
            waiter.wait(InstanceIds=instance_ids)
            
            # Get instance details
            response = self.ec2_client.describe_instances(InstanceIds=instance_ids)
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    for inst_data in self.instances:
                        if inst_data['instance_id'] == instance['InstanceId']:
                            inst_data['state'] = instance['State']['Name']
                            inst_data['public_ip'] = instance.get('PublicIpAddress')
                            logger.info(f"Instance {instance['InstanceId']}: {inst_data['state']}, IP: {inst_data['public_ip']}")
            
            # Wait for Windows to initialize (usually takes 4-5 minutes)
            logger.info("Waiting for Windows to initialize (this may take 4-5 minutes)...")
            await asyncio.sleep(240)  # Wait 4 minutes
            
            # Get Windows passwords
            for inst_data in self.instances:
                try:
                    logger.info(f"Attempting to get password for {inst_data['instance_id']}")
                    response = self.ec2_client.get_password_data(InstanceId=inst_data['instance_id'])
                    
                    # Password might not be available immediately
                    if response.get('PasswordData'):
                        inst_data['rdp_password'] = response['PasswordData']
                        logger.info(f"Got password for {inst_data['instance_id']}")
                    else:
                        logger.warning(f"Password not yet available for {inst_data['instance_id']}")
                        
                except Exception as e:
                    logger.error(f"Failed to get password for {inst_data['instance_id']}: {e}")
            
            self.test_results['instance_ready'] = True
            return True
            
        except Exception as e:
            logger.error(f"Failed waiting for instances: {e}")
            self.test_results['instance_ready'] = False
            return False
    
    def launch_rdp_client(self, host: str, username: str = 'Administrator', password: str = None):
        """Launch RDP client to connect to Windows instance"""
        system = platform.system().lower()
        
        logger.info(f"\n{'='*60}")
        logger.info(f"RDP CONNECTION INFORMATION")
        logger.info(f"{'='*60}")
        logger.info(f"Host: {host}")
        logger.info(f"Username: {username}")
        if password:
            logger.info(f"Password: {password}")
        else:
            logger.info(f"Password: (not available - need .pem key to decrypt)")
        logger.info(f"{'='*60}")
        
        if system == 'darwin':  # macOS
            # Check if xfreerdp is installed
            if subprocess.run(['which', 'xfreerdp'], capture_output=True).returncode == 0:
                logger.info("\n✓ FreeRDP found. Launching RDP connection...")
                cmd = [
                    'xfreerdp',
                    f'/v:{host}',
                    f'/u:{username}',
                    '/w:1920',
                    '/h:1080',
                    '/cert:ignore',
                    '+clipboard',
                    '/network:auto'
                ]
                if password:
                    cmd.append(f'/p:{password}')
                
                logger.info(f"Command: {' '.join(cmd[:3])}...")
                subprocess.Popen(cmd)
                logger.info("✓ RDP client launched. Check your desktop for the remote window.")
            else:
                logger.info("\n⚠️  FreeRDP not found.")
                logger.info("To install: brew install freerdp")
                logger.info("\nAlternatively, use Microsoft Remote Desktop from App Store")
                logger.info("Manual connection using the details above.")
        
        elif system == 'windows':
            # Create RDP file for Windows
            rdp_content = f"""full address:s:{host}
username:s:{username}
authentication level:i:0
screen mode id:i:2
desktopwidth:i:1920
desktopheight:i:1080"""
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.rdp', delete=False) as f:
                f.write(rdp_content)
                rdp_file = f.name
            
            logger.info("\n✓ Launching Windows Remote Desktop...")
            subprocess.Popen(['mstsc', rdp_file])
            logger.info("✓ RDP client launched. Enter the password when prompted.")
            
        elif system == 'linux':
            # Try xfreerdp or rdesktop
            if subprocess.run(['which', 'xfreerdp'], capture_output=True).returncode == 0:
                logger.info("\n✓ FreeRDP found. Launching RDP connection...")
                cmd = [
                    'xfreerdp',
                    f'/v:{host}',
                    f'/u:{username}',
                    '/w:1920',
                    '/h:1080',
                    '/cert:ignore'
                ]
                if password:
                    cmd.append(f'/p:{password}')
                subprocess.Popen(cmd)
                logger.info("✓ RDP client launched.")
            elif subprocess.run(['which', 'rdesktop'], capture_output=True).returncode == 0:
                cmd = ['rdesktop', '-u', username, '-g', '1920x1080', host]
                if password:
                    cmd.extend(['-p', password])
                subprocess.Popen(cmd)
                logger.info("✓ RDP client launched.")
            else:
                logger.info("\n⚠️  No RDP client found.")
                logger.info("Install with: sudo apt-get install freerdp2-x11")
                logger.info("Or: sudo apt-get install rdesktop")
    
    async def test_rdp_connectivity(self) -> bool:
        """Test RDP port connectivity and optionally launch RDP client"""
        try:
            logger.info("=== Testing RDP connectivity ===")
            
            import socket
            
            for i, inst_data in enumerate(self.instances):
                if not inst_data.get('public_ip'):
                    logger.warning(f"No public IP for {inst_data['instance_id']}")
                    continue
                
                logger.info(f"Testing RDP port on {inst_data['public_ip']}:3389")
                
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)
                
                try:
                    result = sock.connect_ex((inst_data['public_ip'], 3389))
                    if result == 0:
                        logger.info(f"✓ RDP port open on {inst_data['public_ip']}")
                        inst_data['rdp_available'] = True
                        
                        # Launch RDP client for first available instance
                        if i == 0:  # Only launch for first instance to avoid multiple windows
                            logger.info(f"\nLaunching RDP client for instance {inst_data['instance_id']}...")
                            self.launch_rdp_client(
                                inst_data['public_ip'],
                                username='Administrator',
                                password=inst_data.get('rdp_password')
                            )
                    else:
                        logger.warning(f"✗ RDP port closed on {inst_data['public_ip']}")
                        inst_data['rdp_available'] = False
                finally:
                    sock.close()
            
            self.test_results['rdp_connectivity'] = any(inst.get('rdp_available', False) for inst in self.instances)
            return self.test_results['rdp_connectivity']
            
        except Exception as e:
            logger.error(f"RDP connectivity test failed: {e}")
            self.test_results['rdp_connectivity'] = False
            return False
    
    async def simulate_pool_operations(self) -> bool:
        """Simulate pool management operations"""
        try:
            logger.info("=== Simulating pool operations ===")
            
            if len(self.instances) < 2:
                logger.warning("Not enough instances for pool simulation")
                return False
            
            # Simulate allocating instances to users
            logger.info("Allocating instance 1 to user-1")
            self.instances[0]['allocated_to'] = 'user-1'
            self.instances[0]['allocated_at'] = datetime.now()
            
            logger.info("Allocating instance 2 to user-2")
            self.instances[1]['allocated_to'] = 'user-2'
            self.instances[1]['allocated_at'] = datetime.now()
            
            # Simulate some work
            await asyncio.sleep(5)
            
            # Simulate releasing and reallocating
            logger.info("Releasing instance 1 from user-1")
            self.instances[0]['allocated_to'] = None
            self.instances[0]['released_at'] = datetime.now()
            
            await asyncio.sleep(2)
            
            logger.info("Reallocating instance 1 to user-3")
            self.instances[0]['allocated_to'] = 'user-3'
            self.instances[0]['allocated_at'] = datetime.now()
            
            self.test_results['pool_operations'] = True
            logger.info("✓ Pool operations simulation completed")
            return True
            
        except Exception as e:
            logger.error(f"Pool operations failed: {e}")
            self.test_results['pool_operations'] = False
            return False
    
    async def cleanup(self) -> bool:
        """Terminate all instances and clean up resources"""
        try:
            logger.info("=== Cleaning up resources ===")
            
            instance_ids = [inst['instance_id'] for inst in self.instances]
            
            if instance_ids:
                logger.info(f"Terminating {len(instance_ids)} instances...")
                self.ec2_client.terminate_instances(InstanceIds=instance_ids)
                
                # Wait for termination
                logger.info("Waiting for instances to terminate...")
                waiter = self.ec2_client.get_waiter('instance_terminated')
                waiter.wait(InstanceIds=instance_ids)
                
                logger.info(f"✓ Terminated {len(instance_ids)} instances")
            
            self.test_results['cleanup'] = True
            return True
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            self.test_results['cleanup'] = False
            return False
    
    def print_results(self):
        """Print test results summary"""
        logger.info("\n" + "="*60)
        logger.info("TEST RESULTS SUMMARY")
        logger.info("="*60)
        
        for test_name, passed in self.test_results.items():
            status = "✓ PASSED" if passed else "✗ FAILED"
            logger.info(f"{test_name:.<30} {status}")
        
        logger.info("="*60)
        
        # Print instance details
        logger.info("\nINSTANCE DETAILS:")
        for inst in self.instances:
            logger.info(f"  Instance: {inst['instance_id']}")
            logger.info(f"    State: {inst.get('state', 'unknown')}")
            logger.info(f"    Public IP: {inst.get('public_ip', 'none')}")
            logger.info(f"    RDP Available: {inst.get('rdp_available', False)}")
            logger.info(f"    Last allocated to: {inst.get('allocated_to', 'none')}")
    
    async def run_all_tests(self, pool_size: int = 2):
        """Run all tests"""
        try:
            logger.info("Starting Simple RDP Pool Tests")
            logger.info("="*60)
            
            # Create instances
            if not await self.create_windows_instances(count=pool_size):
                logger.error("Failed to create instances")
                return
            
            # Wait for instances
            if not await self.wait_for_instances():
                logger.error("Instances not ready")
                # Continue to cleanup
            else:
                # Test connectivity
                await self.test_rdp_connectivity()
                
                # Simulate pool operations
                await self.simulate_pool_operations()
            
        except Exception as e:
            logger.error(f"Test error: {e}")
        finally:
            # Always cleanup
            await self.cleanup()
            
            # Print results
            self.print_results()


async def main():
    """Main execution"""
    parser = argparse.ArgumentParser(description='Simple RDP Pool Test')
    parser.add_argument('--region', default='us-west-2', help='AWS region')
    parser.add_argument('--pool-size', type=int, default=2, help='Number of instances')
    parser.add_argument('--instance-type', default='t3.micro', help='EC2 instance type')
    parser.add_argument('--skip-cleanup', action='store_true', help='Skip cleanup for debugging')
    
    args = parser.parse_args()
    
    # Create and run tests
    tester = SimpleRDPPoolTest(region=args.region, instance_type=args.instance_type)
    
    try:
        await tester.run_all_tests(pool_size=args.pool_size)
    except KeyboardInterrupt:
        logger.info("\n⚠️  Test interrupted by user")
        if not args.skip_cleanup:
            await tester.cleanup()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if not args.skip_cleanup:
            await tester.cleanup()


if __name__ == "__main__":
    asyncio.run(main())