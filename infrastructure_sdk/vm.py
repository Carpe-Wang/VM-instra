"""
VM Lifecycle Controller for Infrastructure SDK.

This module manages complete VM lifecycle from provisioning to decommissioning,
including dynamic EC2 VM provisioning, state management, automated recycling,
health monitoring, and automatic recovery using direct EC2 APIs.

Simplified architecture: Direct EC2 instance management without Kubernetes complexity.
"""

import asyncio
import boto3
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from enum import Enum
import logging

from .config import InfraSDKConfig
from .session import ResourceSpec
from .exceptions import (
    VMProvisioningError,
    ResourceNotFoundError,
    ConfigurationError
)


class VMState(Enum):
    """Enumeration of possible VM states."""
    PENDING = "pending"
    PROVISIONING = "provisioning"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    SUSPENDED = "suspended"
    FAILED = "failed"
    TERMINATING = "terminating"
    TERMINATED = "terminated"


@dataclass
class VMSpec:
    """
    VM specification for EC2 virtual machine creation.
    
    Simplified from KubeVirt to direct EC2 instance configuration.
    """
    
    # Basic VM Information
    vm_name: str
    user_id: str
    session_id: str
    
    # Resource Requirements  
    resources: ResourceSpec
    
    # OS Configuration
    os_type: str = "windows"  # windows, linux
    os_version: str = "2022"  # 2022, 2019 for Windows
    ami_id: Optional[str] = None
    
    # EC2 Configuration
    instance_type: str = "m5.large"
    spot_instance: bool = True
    
    # Networking
    security_group_ids: List[str] = field(default_factory=list)
    subnet_id: Optional[str] = None
    
    # Storage
    disk_size_gb: int = 100
    
    # Labels and Tags
    tags: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Set up default VM specification values."""
        # Set default tags
        self.tags.update({
            'infra-sdk.io/managed': 'true',
            'infra-sdk.io/user-id': self.user_id,
            'infra-sdk.io/session-id': self.session_id,
            'infra-sdk.io/os-type': self.os_type,
            'ManagedBy': 'InfrastructureSDK'
        })


@dataclass
class VM:
    """
    Represents a virtual machine instance (EC2).
    
    Simplified from KubeVirt to direct EC2 instance management.
    """
    
    vm_id: str  # EC2 Instance ID
    vm_name: str
    user_id: str
    session_id: str
    state: VMState = VMState.PENDING
    
    # VM Specification
    spec: VMSpec = None
    
    # EC2 Instance Information
    instance_id: Optional[str] = None
    instance_type: Optional[str] = None
    availability_zone: Optional[str] = None
    
    # Network Information
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None
    rdp_port: int = 3389
    
    # RDP Access
    rdp_username: str = "Administrator"
    rdp_password: Optional[str] = None
    
    # Lifecycle Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    terminated_at: Optional[datetime] = None
    
    # Health Information
    health_status: str = "unknown"
    startup_duration: Optional[float] = None  # seconds
    error_message: Optional[str] = None
    
    # Cost Information
    spot_instance: bool = False
    hourly_cost: Optional[float] = None
    
    def is_healthy(self) -> bool:
        """Check if VM is in a healthy state."""
        return (
            self.state == VMState.RUNNING and 
            self.health_status in ["healthy", "ready"] and
            self.last_heartbeat is not None and
            (datetime.utcnow() - self.last_heartbeat).total_seconds() < 120
        )
    
    def is_ready_for_rdp(self) -> bool:
        """Check if VM is ready for RDP connection."""
        return (
            self.is_healthy() and
            self.public_ip is not None and
            self.rdp_password is not None
        )
    
    def get_rdp_connection_info(self) -> Dict[str, Any]:
        """Get RDP connection information."""
        if not self.is_ready_for_rdp():
            return {"error": "VM not ready for RDP connection"}
        
        return {
            "host": self.public_ip,
            "port": self.rdp_port,
            "username": self.rdp_username,
            "password": self.rdp_password,
            "connection_url": f"rdp://{self.rdp_username}@{self.public_ip}:{self.rdp_port}"
        }
    
    def update_heartbeat(self) -> None:
        """Update VM heartbeat timestamp."""
        self.last_heartbeat = datetime.utcnow()
    
    def calculate_cost(self) -> float:
        """Calculate current session cost."""
        if not self.hourly_cost or not self.started_at:
            return 0.0
        
        duration_hours = (datetime.utcnow() - self.started_at).total_seconds() / 3600
        return round(duration_hours * self.hourly_cost, 4)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert VM to dictionary for serialization."""
        return {
            'vm_id': self.vm_id,
            'vm_name': self.vm_name, 
            'user_id': self.user_id,
            'session_id': self.session_id,
            'state': self.state.value,
            'instance_id': self.instance_id,
            'instance_type': self.instance_type,
            'availability_zone': self.availability_zone,
            'public_ip': self.public_ip,
            'private_ip': self.private_ip,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'health_status': self.health_status,
            'startup_duration': self.startup_duration,
            'spot_instance': self.spot_instance,
            'hourly_cost': self.hourly_cost,
            'current_cost': self.calculate_cost(),
            'error_message': self.error_message,
            'rdp_connection': self.get_rdp_connection_info() if self.is_ready_for_rdp() else None
        }


class EC2TemplateManager:
    """
    Manages EC2 instance templates for different OS types.
    
    Simplified from KubeVirt to direct EC2 AMI and user data management.
    """
    
    def __init__(self, config: InfraSDKConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize EC2 client
        self.ec2_client = boto3.client(
            'ec2',
            region_name=config.aws.region,
            aws_access_key_id=config.aws.access_key_id,
            aws_secret_access_key=config.aws.secret_access_key
        )
    
    async def get_windows_ami_id(self, os_version: str = "2022") -> str:
        """Get the latest Windows AMI ID."""
        try:
            ami_filter = f"Windows_Server-{os_version}-English-Full-Base-*"
            
            response = self.ec2_client.describe_images(
                Filters=[
                    {'Name': 'name', 'Values': [ami_filter]},
                    {'Name': 'state', 'Values': ['available']},
                    {'Name': 'owner-id', 'Values': ['801119661308']}  # Amazon
                ],
                Owners=['amazon']
            )
            
            if not response['Images']:
                raise ConfigurationError(f"No Windows AMI found for version {os_version}")
            
            # Sort by creation date and get latest
            images = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)
            latest_ami = images[0]['ImageId']
            
            self.logger.info(f"Found Windows {os_version} AMI: {latest_ami}")
            return latest_ami
            
        except Exception as e:
            self.logger.error(f"Failed to find Windows AMI: {e}")
            raise ConfigurationError(f"Windows AMI lookup failed: {e}")
    
    def generate_windows_user_data(self, spec: VMSpec) -> str:
        """Generate Windows PowerShell user data script."""
        script = f"""<powershell>
# Windows VM Initialization for Infrastructure SDK
Write-Host "Initializing Windows VM for user {spec.user_id}"

# Enable RDP
Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -name "fDenyTSConnections" -Value 0
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

# Set Administrator password  
$Password = "InfraSDK" + (Get-Random -Maximum 9999) + "!"
$SecurePassword = ConvertTo-SecureString -String $Password -AsPlainText -Force
Set-LocalUser -Name "Administrator" -Password $SecurePassword

# Store password for SDK retrieval
$Password | Out-File -FilePath C:\\temp\\rdp_password.txt -Encoding ASCII

# Create user session directory
New-Item -ItemType Directory -Path "C:\\UserSessions\\{spec.user_id}\\{spec.session_id}" -Force

# Install Chocolatey for software management
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))

# Install common software
choco install -y googlechrome firefox notepadplusplus 7zip

# Configure desktop
# Additional desktop customization can be added here

# Signal VM is ready
New-Item -ItemType File -Path "C:\\temp\\vm_ready.txt" -Force

Write-Host "Windows VM initialization completed"
</powershell>"""
        return script


class VMStateTracker:
    """
    Tracks VM state changes and health monitoring.
    
    Simplified from KubeVirt events to direct EC2 instance monitoring.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._state_callbacks: Dict[VMState, List[callable]] = {}
    
    def register_state_callback(self, state: VMState, callback: callable) -> None:
        """Register callback for specific state transitions."""
        if state not in self._state_callbacks:
            self._state_callbacks[state] = []
        self._state_callbacks[state].append(callback)
    
    async def update_vm_state(self, vm: VM, new_state: VMState) -> None:
        """Update VM state and trigger callbacks."""
        old_state = vm.state
        vm.state = new_state
        
        self.logger.info(
            f"VM {vm.vm_name} state changed: {old_state.value} -> {new_state.value}",
            extra={
                'vm_id': vm.vm_id,
                'instance_id': vm.instance_id,
                'old_state': old_state.value,
                'new_state': new_state.value
            }
        )
        
        # Trigger state-specific callbacks
        if new_state in self._state_callbacks:
            for callback in self._state_callbacks[new_state]:
                try:
                    await callback(vm, old_state, new_state)
                except Exception as e:
                    self.logger.error(f"State callback failed: {e}")


class VMLifecycleController:
    """
    Manages complete VM lifecycle operations using direct EC2.
    
    Simplified from KubeVirt/Karpenter to direct EC2 instance management
    for reduced complexity and faster deployment.
    """
    
    def __init__(self, config: InfraSDKConfig):
        """
        Initialize VM Lifecycle Controller.
        
        Args:
            config: Infrastructure SDK configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Component managers
        self.template_manager = EC2TemplateManager(config)
        self.state_tracker = VMStateTracker()
        
        # EC2 Client
        self.ec2_client = boto3.client(
            'ec2',
            region_name=config.aws.region,
            aws_access_key_id=config.aws.access_key_id,
            aws_secret_access_key=config.aws.secret_access_key
        )
        
        # VM storage (in production, use persistent storage)
        self._vms: Dict[str, VM] = {}
        
        # Background monitoring
        self._monitoring_task: Optional[asyncio.Task] = None
        
        self.logger.info("VM Lifecycle Controller initialized (EC2 Direct)")
    
    async def provision_vm(self, ctx: Optional[Dict[str, Any]], spec: VMSpec) -> VM:
        """
        Provision a new virtual machine using EC2.
        
        Args:
            ctx: Request context
            spec: VM specification
            
        Returns:
            Created VM object
            
        Raises:
            VMProvisioningError: If VM provisioning fails
        """
        try:
            # Generate unique VM ID
            vm_id = f"vm-{uuid.uuid4().hex[:8]}"
            
            self.logger.info(
                f"Provisioning EC2 VM {vm_id} for user {spec.user_id}",
                extra={
                    'vm_id': vm_id,
                    'user_id': spec.user_id,
                    'session_id': spec.session_id,
                    'os_type': spec.os_type,
                    'instance_type': spec.instance_type
                }
            )
            
            # Get Windows AMI
            ami_id = await self.template_manager.get_windows_ami_id(spec.os_version)
            spec.ami_id = ami_id
            
            # Create VM object
            vm = VM(
                vm_id=vm_id,
                vm_name=spec.vm_name,
                user_id=spec.user_id,
                session_id=spec.session_id,
                spec=spec,
                state=VMState.PROVISIONING
            )
            
            # Store VM
            self._vms[vm_id] = vm
            
            # Start async provisioning
            asyncio.create_task(self._provision_vm_async(vm))
            
            return vm
            
        except Exception as e:
            self.logger.error(f"Failed to provision VM: {e}")
            raise VMProvisioningError(
                f"VM provisioning failed: {e}",
                vm_spec=spec.__dict__,
                session_id=spec.session_id
            ) from e
    
    async def get_vm(self, ctx: Optional[Dict[str, Any]], vm_id: str) -> VM:
        """
        Retrieve VM by ID.
        
        Args:
            ctx: Request context
            vm_id: VM identifier
            
        Returns:
            VM object
            
        Raises:
            ResourceNotFoundError: If VM not found
        """
        if vm_id not in self._vms:
            raise ResourceNotFoundError(
                f"VM not found: {vm_id}",
                resource_type="vm",
                resource_id=vm_id
            )
        
        return self._vms[vm_id]
    
    async def terminate_vm(self, ctx: Optional[Dict[str, Any]], vm_id: str) -> None:
        """
        Terminate VM and cleanup resources.
        
        Args:
            ctx: Request context
            vm_id: VM identifier
        """
        vm = await self.get_vm(ctx, vm_id)
        
        if vm.state in [VMState.TERMINATED, VMState.TERMINATING]:
            self.logger.warning(f"VM {vm_id} already terminated/terminating")
            return
        
        self.logger.info(f"Terminating VM {vm_id}")
        
        await self.state_tracker.update_vm_state(vm, VMState.TERMINATING)
        vm.terminated_at = datetime.utcnow()
        
        # Start async cleanup
        asyncio.create_task(self._cleanup_vm_async(vm))
    
    async def _provision_vm_async(self, vm: VM) -> None:
        """
        Async VM provisioning workflow using EC2.
        
        Simplified from KubeVirt to direct EC2 instance launch.
        """
        try:
            vm_id = vm.vm_id
            self.logger.info(f"Starting EC2 provisioning for VM {vm_id}")
            
            # Update state to starting
            await self.state_tracker.update_vm_state(vm, VMState.STARTING)
            
            # 1. Generate user data script
            user_data = self.template_manager.generate_windows_user_data(vm.spec)
            
            # 2. Launch EC2 instance
            run_config = {
                'ImageId': vm.spec.ami_id,
                'InstanceType': vm.spec.instance_type,
                'MaxCount': 1,
                'MinCount': 1,
                'UserData': user_data,
                'TagSpecifications': [
                    {
                        'ResourceType': 'instance',
                        'Tags': [{'Key': k, 'Value': v} for k, v in vm.spec.tags.items()]
                    }
                ],
                'BlockDeviceMappings': [
                    {
                        'DeviceName': '/dev/sda1',
                        'Ebs': {
                            'VolumeSize': vm.spec.disk_size_gb,
                            'VolumeType': 'gp3',
                            'DeleteOnTermination': True
                        }
                    }
                ]
            }
            
            # Add security group and subnet if specified
            if vm.spec.security_group_ids:
                run_config['SecurityGroupIds'] = vm.spec.security_group_ids
            if vm.spec.subnet_id:
                run_config['SubnetId'] = vm.spec.subnet_id
            
            # Try spot instance if enabled
            if vm.spec.spot_instance:
                run_config['InstanceMarketOptions'] = {
                    'MarketType': 'spot',
                    'SpotOptions': {
                        'MaxPrice': '0.10',  # Max price per hour
                        'SpotInstanceType': 'one-time'
                    }
                }
            
            response = self.ec2_client.run_instances(**run_config)
            instance = response['Instances'][0]
            
            # 3. Update VM with EC2 instance information
            vm.instance_id = instance['InstanceId']
            vm.instance_type = instance['InstanceType']
            vm.availability_zone = instance['Placement']['AvailabilityZone']
            vm.spot_instance = vm.spec.spot_instance
            vm.hourly_cost = 0.08 if vm.spot_instance else 0.12  # Estimate
            
            self.logger.info(f"EC2 instance launched: {vm.instance_id}")
            
            # 4. Monitor instance startup
            await self._monitor_instance_startup(vm)
            
        except Exception as e:
            self.logger.error(f"Failed to provision VM {vm.vm_id}: {e}")
            await self.state_tracker.update_vm_state(vm, VMState.FAILED)
            vm.error_message = str(e)
    
    async def _monitor_instance_startup(self, vm: VM) -> None:
        """Monitor EC2 instance startup and update VM status."""
        startup_start = datetime.utcnow()
        max_startup_time = 600  # 10 minutes
        
        while True:
            try:
                elapsed = (datetime.utcnow() - startup_start).total_seconds()
                
                if elapsed > max_startup_time:
                    await self.state_tracker.update_vm_state(vm, VMState.FAILED)
                    vm.error_message = "Instance startup timeout"
                    break
                
                # Check instance state
                response = self.ec2_client.describe_instances(
                    InstanceIds=[vm.instance_id]
                )
                
                if not response['Reservations']:
                    await asyncio.sleep(30)
                    continue
                
                instance = response['Reservations'][0]['Instances'][0]
                instance_state = instance['State']['Name']
                
                # Update network information
                if 'PublicIpAddress' in instance:
                    vm.public_ip = instance['PublicIpAddress']
                if 'PrivateIpAddress' in instance:
                    vm.private_ip = instance['PrivateIpAddress']
                
                if instance_state == 'running':
                    await self.state_tracker.update_vm_state(vm, VMState.RUNNING)
                    vm.started_at = datetime.utcnow()
                    
                    # Wait for Windows to initialize and generate RDP password
                    await asyncio.sleep(60)
                    
                    # Set RDP password (simplified for demo)
                    vm.rdp_password = f"InfraSDK{hash(vm.instance_id) % 9999}!"
                    vm.health_status = "healthy"
                    vm.startup_duration = elapsed
                    vm.update_heartbeat()
                    
                    self.logger.info(f"VM {vm.vm_id} is ready for RDP access")
                    break
                
                elif instance_state in ['stopped', 'stopping', 'terminated', 'terminating']:
                    await self.state_tracker.update_vm_state(vm, VMState.FAILED)
                    vm.error_message = f"Instance unexpectedly entered state: {instance_state}"
                    break
                
                await asyncio.sleep(30)
                
            except Exception as e:
                self.logger.error(f"Error monitoring VM startup {vm.vm_id}: {e}")
                await self.state_tracker.update_vm_state(vm, VMState.FAILED)
                vm.error_message = str(e)
                break
    
    async def _cleanup_vm_async(self, vm: VM) -> None:
        """
        Async VM cleanup workflow.
        
        Simplified from KubeVirt to direct EC2 instance termination.
        """
        try:
            vm_id = vm.vm_id
            self.logger.info(f"Starting cleanup for VM {vm_id}")
            
            # Terminate EC2 instance
            if vm.instance_id:
                self.ec2_client.terminate_instances(InstanceIds=[vm.instance_id])
                self.logger.info(f"Terminated EC2 instance: {vm.instance_id}")
            
            # Wait for termination to complete
            await asyncio.sleep(30)
            
            # Update state
            await self.state_tracker.update_vm_state(vm, VMState.TERMINATED)
            
            # Calculate final cost
            final_cost = vm.calculate_cost()
            
            self.logger.info(f"VM {vm_id} cleaned up successfully. Cost: ${final_cost:.4f}")
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup VM {vm.vm_id}: {e}")
            vm.error_message = f"Cleanup failed: {e}"
    
    def get_pool_status(self) -> Dict[str, Any]:
        """Get current VM pool status."""
        active_vms = [vm for vm in self._vms.values() if vm.state == VMState.RUNNING]
        total_cost = sum(vm.calculate_cost() for vm in active_vms)
        
        return {
            "total_vms": len(self._vms),
            "active_vms": len(active_vms),
            "states": {state.value: sum(1 for vm in self._vms.values() if vm.state == state) 
                      for state in VMState},
            "total_active_cost": round(total_cost, 4),
            "spot_instances": sum(1 for vm in active_vms if vm.spot_instance)
        }