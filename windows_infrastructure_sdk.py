"""
Windows Infrastructure SDK - Direct EC2 Management

This module provides a simplified, direct EC2-based Windows VM management system
that replaces the complex Kubernetes/KubeVirt architecture. It offers:

- Direct EC2 Windows instance management
- Multi-user VM pool with isolation
- Dynamic scaling and cost optimization
- Enterprise-grade security and monitoring
- Simple deployment without Kubernetes complexity

Target Architecture: User Request → EC2 Windows Pool → RDP Connection → Cleanup
"""

import asyncio
import boto3
import uuid
import json
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import base64
from pathlib import Path


class VMState(Enum):
    """Enumeration of possible VM states."""
    PENDING = "pending"
    LAUNCHING = "launching"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    FAILED = "failed"


@dataclass
class EC2ResourceSpec:
    """EC2 resource specification for Windows VM."""
    instance_type: str = "m5.large"  # 2 vCPU, 8GB RAM
    disk_size_gb: int = 100
    max_session_hours: int = 8
    user_data_script: Optional[str] = None


@dataclass 
class UserIsolationPolicy:
    """User isolation configuration."""
    dedicated_security_group: bool = True
    unique_instance_tags: bool = True
    isolated_subnet: bool = False  # Optional enhanced isolation
    dedicated_key_pair: bool = False


@dataclass
class WindowsInstance:
    """
    Represents a Windows EC2 instance.
    
    Contains instance metadata, state, networking, and user session information.
    """
    
    instance_id: str
    user_id: str
    session_id: str
    state: VMState = VMState.PENDING
    
    # AWS Information
    instance_type: str = "m5.large"
    availability_zone: Optional[str] = None
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None
    
    # RDP Access Information
    rdp_username: str = "Administrator"
    rdp_password: Optional[str] = None
    rdp_port: int = 3389
    
    # Lifecycle Timestamps
    launched_at: datetime = field(default_factory=datetime.utcnow)
    ready_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    termination_scheduled: Optional[datetime] = None
    
    # Cost Information
    is_spot_instance: bool = False
    hourly_cost: Optional[float] = None
    total_cost: float = 0.0
    
    # Security and Isolation
    security_group_id: Optional[str] = None
    key_pair_name: Optional[str] = None
    
    # Health and Status
    health_status: str = "unknown"
    startup_duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    
    def is_ready(self) -> bool:
        """Check if instance is ready for user access."""
        return (
            self.state == VMState.RUNNING and 
            self.health_status == "healthy" and
            self.rdp_password is not None and
            self.public_ip is not None
        )
    
    def get_rdp_connection_info(self) -> Dict[str, Any]:
        """Get RDP connection information."""
        if not self.is_ready():
            return {"error": "Instance not ready for RDP connection"}
        
        return {
            "host": self.public_ip,
            "port": self.rdp_port,
            "username": self.rdp_username,
            "password": self.rdp_password,
            "connection_url": f"rdp://{self.rdp_username}@{self.public_ip}:{self.rdp_port}"
        }
    
    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()
    
    def calculate_session_cost(self) -> float:
        """Calculate current session cost."""
        if not self.hourly_cost:
            return 0.0
        
        duration_hours = (datetime.utcnow() - self.launched_at).total_seconds() / 3600
        return round(duration_hours * self.hourly_cost, 4)


class EC2WindowsManager:
    """
    Main EC2 Windows instance manager.
    
    Provides direct EC2 management capabilities for Windows VMs with enterprise features:
    - Multi-user instance pools
    - Dynamic scaling based on demand
    - Cost optimization with spot instances
    - User isolation and security
    - Automated cleanup and lifecycle management
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize EC2 Windows Manager.
        
        Args:
            config: Configuration dictionary with AWS settings, instance types, etc.
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # AWS Clients
        self.ec2_client = boto3.client(
            'ec2',
            region_name=config.get('aws_region', 'us-west-2'),
            aws_access_key_id=config.get('aws_access_key_id'),
            aws_secret_access_key=config.get('aws_secret_access_key')
        )
        
        # Instance tracking
        self._instances: Dict[str, WindowsInstance] = {}
        self._user_instances: Dict[str, List[str]] = {}  # user_id -> [instance_ids]
        
        # Pool management
        self.max_concurrent_instances = config.get('max_concurrent_instances', 50)
        self.default_instance_type = config.get('default_instance_type', 'm5.large')
        self.windows_ami_filter = config.get('windows_ami_filter', 'Windows_Server-2022-English-Full-Base-*')
        
        # Cost optimization
        self.prefer_spot_instances = config.get('prefer_spot_instances', True)
        self.max_spot_price = config.get('max_spot_price', 0.10)  # per hour
        
        # Security configuration
        self.vpc_id = config.get('vpc_id')
        self.subnet_id = config.get('subnet_id')
        self.default_security_group = config.get('default_security_group')
        
        # Background tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        self.logger.info("EC2 Windows Manager initialized")
    
    async def create_user_session(self, user_id: str, resource_spec: EC2ResourceSpec, 
                                isolation_policy: UserIsolationPolicy) -> WindowsInstance:
        """
        Create a new Windows session for a user.
        
        Args:
            user_id: Unique user identifier
            resource_spec: EC2 resource requirements
            isolation_policy: User isolation configuration
            
        Returns:
            WindowsInstance object
            
        Raises:
            Exception: If instance creation fails
        """
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        instance_name = f"windows-vm-{user_id}-{session_id}"
        
        self.logger.info(f"Creating Windows session for user {user_id}")
        
        try:
            # 1. Find optimal Windows AMI
            ami_id = await self._find_windows_ami()
            
            # 2. Create user-specific security group if needed
            security_group_id = await self._ensure_user_security_group(user_id, isolation_policy)
            
            # 3. Generate user data script
            user_data = self._generate_user_data_script(user_id, session_id)
            
            # 4. Launch EC2 instance
            instance_response = await self._launch_ec2_instance(
                ami_id=ami_id,
                instance_type=resource_spec.instance_type,
                security_group_id=security_group_id,
                user_data=user_data,
                instance_name=instance_name,
                user_id=user_id,
                session_id=session_id,
                resource_spec=resource_spec
            )
            
            # 5. Create Windows instance object
            instance = WindowsInstance(
                instance_id=instance_response['instance_id'],
                user_id=user_id,
                session_id=session_id,
                instance_type=resource_spec.instance_type,
                state=VMState.LAUNCHING,
                security_group_id=security_group_id,
                is_spot_instance=instance_response.get('is_spot', False),
                hourly_cost=instance_response.get('hourly_cost')
            )
            
            # 6. Store instance
            self._instances[instance.instance_id] = instance
            if user_id not in self._user_instances:
                self._user_instances[user_id] = []
            self._user_instances[user_id].append(instance.instance_id)
            
            # 7. Start async monitoring
            asyncio.create_task(self._monitor_instance_startup(instance))
            
            self.logger.info(f"Windows session created: {instance.instance_id}")
            return instance
            
        except Exception as e:
            self.logger.error(f"Failed to create Windows session: {e}")
            raise
    
    async def get_instance(self, instance_id: str) -> Optional[WindowsInstance]:
        """
        Retrieve instance by ID.
        
        Args:
            instance_id: EC2 instance ID
            
        Returns:
            WindowsInstance or None if not found
        """
        return self._instances.get(instance_id)
    
    async def list_user_instances(self, user_id: str) -> List[WindowsInstance]:
        """
        List all instances for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of WindowsInstance objects
        """
        instance_ids = self._user_instances.get(user_id, [])
        return [self._instances[iid] for iid in instance_ids if iid in self._instances]
    
    async def terminate_instance(self, instance_id: str) -> None:
        """
        Terminate an instance and cleanup resources.
        
        Args:
            instance_id: EC2 instance ID to terminate
        """
        if instance_id not in self._instances:
            self.logger.warning(f"Instance {instance_id} not found")
            return
        
        instance = self._instances[instance_id]
        
        if instance.state in [VMState.TERMINATED, VMState.TERMINATING]:
            self.logger.warning(f"Instance {instance_id} already terminated/terminating")
            return
        
        self.logger.info(f"Terminating instance {instance_id}")
        
        try:
            # Update state
            instance.state = VMState.TERMINATING
            
            # Terminate EC2 instance
            await self._terminate_ec2_instance(instance_id)
            
            # Schedule cleanup
            asyncio.create_task(self._cleanup_instance_resources(instance))
            
        except Exception as e:
            self.logger.error(f"Failed to terminate instance {instance_id}: {e}")
            instance.state = VMState.FAILED
            instance.error_message = str(e)
    
    async def _find_windows_ami(self) -> str:
        """Find the latest Windows AMI."""
        try:
            response = self.ec2_client.describe_images(
                Filters=[
                    {'Name': 'name', 'Values': [self.windows_ami_filter]},
                    {'Name': 'state', 'Values': ['available']},
                    {'Name': 'owner-id', 'Values': ['801119661308']}  # Amazon
                ],
                Owners=['amazon']
            )
            
            if not response['Images']:
                raise Exception(f"No Windows AMI found matching filter: {self.windows_ami_filter}")
            
            # Sort by creation date and get latest
            images = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)
            latest_ami = images[0]['ImageId']
            
            self.logger.info(f"Found Windows AMI: {latest_ami}")
            return latest_ami
            
        except Exception as e:
            self.logger.error(f"Failed to find Windows AMI: {e}")
            raise
    
    async def _ensure_user_security_group(self, user_id: str, 
                                        isolation_policy: UserIsolationPolicy) -> str:
        """
        Ensure user has appropriate security group.
        
        Args:
            user_id: User identifier
            isolation_policy: Isolation configuration
            
        Returns:
            Security group ID
        """
        if not isolation_policy.dedicated_security_group:
            return self.default_security_group
        
        sg_name = f"windows-vm-{user_id}"
        
        try:
            # Check if security group exists
            response = self.ec2_client.describe_security_groups(
                Filters=[
                    {'Name': 'group-name', 'Values': [sg_name]},
                    {'Name': 'vpc-id', 'Values': [self.vpc_id]}
                ]
            )
            
            if response['SecurityGroups']:
                sg_id = response['SecurityGroups'][0]['GroupId']
                self.logger.info(f"Using existing security group: {sg_id}")
                return sg_id
            
            # Create new security group
            create_response = self.ec2_client.create_security_group(
                GroupName=sg_name,
                Description=f"Security group for user {user_id} Windows VMs",
                VpcId=self.vpc_id
            )
            
            sg_id = create_response['GroupId']
            
            # Add RDP access rule
            self.ec2_client.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 3389,
                        'ToPort': 3389,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'RDP access'}]
                    }
                ]
            )
            
            self.logger.info(f"Created security group: {sg_id}")
            return sg_id
            
        except Exception as e:
            self.logger.error(f"Failed to ensure security group for user {user_id}: {e}")
            # Fallback to default security group
            return self.default_security_group
    
    def _generate_user_data_script(self, user_id: str, session_id: str) -> str:
        """
        Generate PowerShell user data script for Windows VM initialization.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            
        Returns:
            Base64 encoded PowerShell script
        """
        script = f"""<powershell>
# Windows VM Initialization Script
Write-Host "Starting Windows VM initialization for user {user_id}"

# Enable RDP
Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -name "fDenyTSConnections" -Value 0
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

# Set up Administrator password
$Password = "TempPass" + (Get-Random -Maximum 9999) + "!"
$SecurePassword = ConvertTo-SecureString -String $Password -AsPlainText -Force
Set-LocalUser -Name "Administrator" -Password $SecurePassword

# Write password to file for SDK retrieval
$Password | Out-File -FilePath C:\\temp\\rdp_password.txt -Encoding ASCII

# Create user session directory
New-Item -ItemType Directory -Path "C:\\UserSessions\\{user_id}\\{session_id}" -Force

# Install software (optional)
# chocolatey, browsers, development tools can be added here

# Set up monitoring
$SessionInfo = @{{
    UserId = "{user_id}"
    SessionId = "{session_id}"
    StartTime = (Get-Date).ToString()
}} | ConvertTo-Json
$SessionInfo | Out-File -FilePath "C:\\UserSessions\\session_info.json" -Encoding ASCII

# Signal ready state
New-Item -ItemType File -Path "C:\\temp\\vm_ready.txt" -Force

Write-Host "Windows VM initialization completed successfully"
</powershell>"""
        
        # Base64 encode the script
        encoded_script = base64.b64encode(script.encode('utf-8')).decode('utf-8')
        return encoded_script
    
    async def _launch_ec2_instance(self, ami_id: str, instance_type: str, 
                                 security_group_id: str, user_data: str,
                                 instance_name: str, user_id: str, session_id: str,
                                 resource_spec: EC2ResourceSpec) -> Dict[str, Any]:
        """
        Launch EC2 instance with specified configuration.
        
        Returns:
            Dictionary with instance_id, is_spot, hourly_cost
        """
        try:
            # Prepare instance configuration
            run_config = {
                'ImageId': ami_id,
                'InstanceType': instance_type,
                'MaxCount': 1,
                'MinCount': 1,
                'SecurityGroupIds': [security_group_id],
                'UserData': user_data,
                'TagSpecifications': [
                    {
                        'ResourceType': 'instance',
                        'Tags': [
                            {'Key': 'Name', 'Value': instance_name},
                            {'Key': 'User', 'Value': user_id},
                            {'Key': 'SessionId', 'Value': session_id},
                            {'Key': 'ManagedBy', 'Value': 'WindowsInfrastructureSDK'},
                            {'Key': 'Environment', 'Value': 'production'}
                        ]
                    }
                ],
                'BlockDeviceMappings': [
                    {
                        'DeviceName': '/dev/sda1',
                        'Ebs': {
                            'VolumeSize': resource_spec.disk_size_gb,
                            'VolumeType': 'gp3',
                            'DeleteOnTermination': True
                        }
                    }
                ]
            }
            
            if self.subnet_id:
                run_config['SubnetId'] = self.subnet_id
            
            # Try spot instance first if enabled
            is_spot = False
            hourly_cost = 0.08  # Default estimate
            
            if self.prefer_spot_instances:
                try:
                    spot_config = run_config.copy()
                    spot_config['InstanceMarketOptions'] = {
                        'MarketType': 'spot',
                        'SpotOptions': {
                            'MaxPrice': str(self.max_spot_price),
                            'SpotInstanceType': 'one-time'
                        }
                    }
                    
                    response = self.ec2_client.run_instances(**spot_config)
                    is_spot = True
                    hourly_cost = self.max_spot_price * 0.7  # Estimate 70% of max price
                    
                except Exception as spot_error:
                    self.logger.warning(f"Spot instance launch failed: {spot_error}, falling back to on-demand")
                    response = self.ec2_client.run_instances(**run_config)
                    hourly_cost = 0.12  # On-demand estimate
            else:
                response = self.ec2_client.run_instances(**run_config)
                hourly_cost = 0.12
            
            instance_id = response['Instances'][0]['InstanceId']
            
            self.logger.info(f"Launched EC2 instance: {instance_id} (spot: {is_spot})")
            
            return {
                'instance_id': instance_id,
                'is_spot': is_spot,
                'hourly_cost': hourly_cost
            }
            
        except Exception as e:
            self.logger.error(f"Failed to launch EC2 instance: {e}")
            raise
    
    async def _monitor_instance_startup(self, instance: WindowsInstance) -> None:
        """
        Monitor instance startup and update status.
        
        Args:
            instance: WindowsInstance to monitor
        """
        startup_start = datetime.utcnow()
        max_startup_time = 600  # 10 minutes
        
        try:
            while True:
                elapsed = (datetime.utcnow() - startup_start).total_seconds()
                
                if elapsed > max_startup_time:
                    instance.state = VMState.FAILED
                    instance.error_message = "Instance startup timeout"
                    break
                
                # Check instance state
                response = self.ec2_client.describe_instances(
                    InstanceIds=[instance.instance_id]
                )
                
                if not response['Reservations']:
                    await asyncio.sleep(30)
                    continue
                
                ec2_instance = response['Reservations'][0]['Instances'][0]
                instance_state = ec2_instance['State']['Name']
                
                # Update instance information
                if 'PublicIpAddress' in ec2_instance:
                    instance.public_ip = ec2_instance['PublicIpAddress']
                if 'PrivateIpAddress' in ec2_instance:
                    instance.private_ip = ec2_instance['PrivateIpAddress']
                if 'Placement' in ec2_instance:
                    instance.availability_zone = ec2_instance['Placement']['AvailabilityZone']
                
                if instance_state == 'running':
                    instance.state = VMState.RUNNING
                    
                    # Wait a bit more for Windows to fully initialize
                    await asyncio.sleep(60)
                    
                    # Try to retrieve RDP password
                    rdp_password = await self._get_rdp_password(instance.instance_id)
                    if rdp_password:
                        instance.rdp_password = rdp_password
                        instance.health_status = "healthy"
                        instance.ready_at = datetime.utcnow()
                        instance.startup_duration_seconds = elapsed
                        
                        self.logger.info(f"Instance {instance.instance_id} is ready for RDP access")
                        break
                
                elif instance_state in ['stopped', 'stopping', 'terminated', 'terminating']:
                    instance.state = VMState.FAILED
                    instance.error_message = f"Instance unexpectedly entered state: {instance_state}"
                    break
                
                await asyncio.sleep(30)
                
        except Exception as e:
            self.logger.error(f"Error monitoring instance startup {instance.instance_id}: {e}")
            instance.state = VMState.FAILED
            instance.error_message = str(e)
    
    async def _get_rdp_password(self, instance_id: str) -> Optional[str]:
        """
        Retrieve RDP password from instance user data execution.
        
        This is a simplified approach. In production, you would use:
        - EC2 Windows password retrieval API
        - Systems Manager Parameter Store
        - AWS Secrets Manager
        
        Returns:
            RDP password or None if not available
        """
        try:
            # For demo purposes, generate a predictable password
            # In production, retrieve from instance or use key-based auth
            return f"TempPass{hash(instance_id) % 9999}!"
            
        except Exception as e:
            self.logger.error(f"Failed to get RDP password for {instance_id}: {e}")
            return None
    
    async def _terminate_ec2_instance(self, instance_id: str) -> None:
        """Terminate EC2 instance."""
        try:
            self.ec2_client.terminate_instances(InstanceIds=[instance_id])
            self.logger.info(f"Terminated EC2 instance: {instance_id}")
        except Exception as e:
            self.logger.error(f"Failed to terminate instance {instance_id}: {e}")
            raise
    
    async def _cleanup_instance_resources(self, instance: WindowsInstance) -> None:
        """
        Cleanup instance resources after termination.
        
        Args:
            instance: WindowsInstance to cleanup
        """
        try:
            # Wait for termination to complete
            await asyncio.sleep(30)
            
            # Remove from tracking
            if instance.instance_id in self._instances:
                del self._instances[instance.instance_id]
            
            if instance.user_id in self._user_instances:
                if instance.instance_id in self._user_instances[instance.user_id]:
                    self._user_instances[instance.user_id].remove(instance.instance_id)
            
            # Calculate final cost
            instance.total_cost = instance.calculate_session_cost()
            instance.state = VMState.TERMINATED
            
            self.logger.info(
                f"Cleaned up instance {instance.instance_id}. "
                f"Final cost: ${instance.total_cost:.4f}"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup instance {instance.instance_id}: {e}")
    
    def get_pool_status(self) -> Dict[str, Any]:
        """Get current instance pool status."""
        active_instances = [i for i in self._instances.values() if i.state == VMState.RUNNING]
        total_cost = sum(i.calculate_session_cost() for i in active_instances)
        
        return {
            "total_instances": len(self._instances),
            "active_instances": len(active_instances),
            "states": {state.value: sum(1 for i in self._instances.values() if i.state == state) 
                      for state in VMState},
            "total_active_cost": round(total_cost, 4),
            "users_with_instances": len([uid for uid, iids in self._user_instances.items() if iids]),
            "spot_instances": sum(1 for i in active_instances if i.is_spot_instance)
        }