"""
VM Lifecycle Controller for Infrastructure SDK.

This module manages complete VM lifecycle from provisioning to decommissioning,
including dynamic VM provisioning, state management, automated recycling,
health monitoring, and automatic recovery using KubeVirt and Karpenter.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from enum import Enum
import logging
import yaml

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
    VM specification for KubeVirt virtual machine creation.
    
    Defines all parameters necessary for VM provisioning including
    resources, OS configuration, networking, and storage.
    """
    
    # Basic VM Information
    vm_name: str
    user_id: str
    session_id: str
    
    # Resource Requirements  
    resources: ResourceSpec
    
    # OS Configuration
    os_type: str = "windows"  # windows, linux
    os_version: str = "2022"  # 2022, 2019 for Windows; 22.04, 20.04 for Ubuntu
    base_image: Optional[str] = None
    
    # VM Configuration
    boot_order: List[str] = field(default_factory=lambda: ["hd", "cdrom"])
    machine_type: str = "q35"
    firmware: str = "uefi"  # uefi, bios
    
    # Networking
    network_interfaces: List[Dict[str, Any]] = field(default_factory=list)
    
    # Storage
    disks: List[Dict[str, Any]] = field(default_factory=list)
    
    # Node Placement
    node_selector: Dict[str, str] = field(default_factory=dict)
    tolerations: List[Dict[str, Any]] = field(default_factory=list)
    affinity: Dict[str, Any] = field(default_factory=dict)
    
    # Labels and Annotations
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Set up default VM specification values."""
        # Set default labels
        self.labels.update({
            'infra-sdk.io/managed': 'true',
            'infra-sdk.io/user-id': self.user_id,
            'infra-sdk.io/session-id': self.session_id,
            'infra-sdk.io/os-type': self.os_type,
        })
        
        # Set default node selector for user isolation
        self.node_selector.update({
            'dedicated-user': self.user_id,
            'infra-sdk.io/user-isolation': 'enabled'
        })
        
        # Set default tolerations for dedicated nodes
        self.tolerations.extend([
            {
                'key': 'dedicated-user',
                'operator': 'Equal',
                'value': self.user_id,
                'effect': 'NoSchedule'
            },
            {
                'key': 'os-type', 
                'operator': 'Equal',
                'value': self.os_type,
                'effect': 'NoSchedule'
            }
        ])
        
        # Set default affinity for user isolation
        self.affinity = {
            'nodeAffinity': {
                'requiredDuringSchedulingIgnoredDuringExecution': {
                    'nodeSelectorTerms': [{
                        'matchExpressions': [{
                            'key': 'dedicated-user',
                            'operator': 'In', 
                            'values': [self.user_id]
                        }]
                    }]
                }
            }
        }
        
        # Set up default network interface
        if not self.network_interfaces:
            self.network_interfaces.append({
                'name': 'default',
                'masquerade': {},
                'ports': [
                    {'port': 3389, 'name': 'rdp'},  # RDP for Windows
                    {'port': 5900, 'name': 'vnc'},  # VNC
                ]
            })
        
        # Set up default disk
        if not self.disks:
            self.disks.append({
                'name': 'rootdisk',
                'disk': {'bus': 'virtio'},
                'size': self.resources.disk_size
            })


@dataclass
class VM:
    """
    Represents a virtual machine instance.
    
    Contains VM state, metadata, resource allocation, networking information,
    and lifecycle management data.
    """
    
    vm_id: str
    vm_name: str
    user_id: str
    session_id: str
    state: VMState = VMState.PENDING
    
    # VM Specification
    spec: VMSpec = None
    
    # Resource Information
    allocated_resources: Optional[ResourceSpec] = None
    node_name: Optional[str] = None
    
    # Network Information
    ip_address: Optional[str] = None
    access_ports: Dict[str, int] = field(default_factory=dict)
    
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
    instance_type: Optional[str] = None
    spot_instance: bool = False
    hourly_cost: Optional[float] = None
    
    # Kubernetes Information
    namespace: str = "default"
    kubevirt_vm_manifest: Optional[Dict[str, Any]] = None
    
    def is_healthy(self) -> bool:
        """Check if VM is in a healthy state."""
        return (
            self.state == VMState.RUNNING and 
            self.health_status in ["healthy", "ready"] and
            self.last_heartbeat is not None and
            (datetime.utcnow() - self.last_heartbeat).total_seconds() < 120
        )
    
    def update_heartbeat(self) -> None:
        """Update VM heartbeat timestamp."""
        self.last_heartbeat = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert VM to dictionary for serialization."""
        return {
            'vm_id': self.vm_id,
            'vm_name': self.vm_name, 
            'user_id': self.user_id,
            'session_id': self.session_id,
            'state': self.state.value,
            'node_name': self.node_name,
            'ip_address': self.ip_address,
            'access_ports': self.access_ports,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'health_status': self.health_status,
            'startup_duration': self.startup_duration,
            'instance_type': self.instance_type,
            'spot_instance': self.spot_instance,
            'hourly_cost': self.hourly_cost,
            'error_message': self.error_message
        }


class VMTemplateManager:
    """
    Manages VM templates for different OS types and configurations.
    
    Provides base templates for Windows and Linux VMs with optimization
    for startup time and resource efficiency.
    """
    
    def __init__(self, config: InfraSDKConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def get_windows_template(self, spec: VMSpec) -> Dict[str, Any]:
        """
        Get KubeVirt template for Windows VM.
        
        Creates optimized Windows VM template with fast startup configuration.
        """
        return {
            'apiVersion': 'kubevirt.io/v1',
            'kind': 'VirtualMachine',
            'metadata': {
                'name': spec.vm_name,
                'namespace': self.config.kubernetes.namespace,
                'labels': spec.labels,
                'annotations': spec.annotations
            },
            'spec': {
                'running': True,
                'template': {
                    'metadata': {
                        'labels': spec.labels
                    },
                    'spec': {
                        'domain': {
                            'devices': {
                                'disks': [
                                    {
                                        'name': 'rootdisk',
                                        'disk': {'bus': 'virtio'},
                                        'bootOrder': 1
                                    },
                                    {
                                        'name': 'cloudinitdisk',
                                        'disk': {'bus': 'virtio'}
                                    }
                                ],
                                'interfaces': [{
                                    'name': 'default',
                                    'masquerade': {},
                                    'ports': [
                                        {'port': 3389, 'name': 'rdp'},
                                        {'port': 5900, 'name': 'vnc'}
                                    ]
                                }],
                                'rng': {}  # Hardware random number generator
                            },
                            'machine': {
                                'type': spec.machine_type or 'q35'
                            },
                            'resources': {
                                'requests': {
                                    'memory': spec.resources.memory,
                                    'cpu': spec.resources.cpu
                                }
                            },
                            'features': {
                                'acpi': {'enabled': True},
                                'apic': {'enabled': True},
                                'hyperv': {
                                    'relaxed': {'enabled': True},
                                    'spinlocks': {'enabled': True, 'spinlocks': 8191},
                                    'vapic': {'enabled': True},
                                    'vpindex': {'enabled': True},
                                    'runtime': {'enabled': True},
                                    'synic': {'enabled': True},
                                    'stimer': {'enabled': True},
                                    'frequencies': {'enabled': True},
                                    'reenlightenment': {'enabled': True},
                                    'tlbflush': {'enabled': True},
                                    'ipi': {'enabled': True}
                                }
                            },
                            'clock': {
                                'utc': {},
                                'timer': {
                                    'hpet': {'present': False},
                                    'pit': {'tickPolicy': 'delay'},
                                    'rtc': {'tickPolicy': 'catchup'},
                                    'hyperv': {'present': True}
                                }
                            }
                        },
                        'networks': [{
                            'name': 'default',
                            'pod': {}
                        }],
                        'volumes': [
                            {
                                'name': 'rootdisk',
                                'containerDisk': {
                                    'image': spec.base_image or self.config.vm.windows_base_image
                                }
                            },
                            {
                                'name': 'cloudinitdisk',
                                'cloudInitNoCloud': {
                                    'userData': self._get_windows_userdata(spec)
                                }
                            }
                        ],
                        'nodeSelector': spec.node_selector,
                        'tolerations': spec.tolerations,
                        'affinity': spec.affinity
                    }
                }
            }
        }
    
    def get_linux_template(self, spec: VMSpec) -> Dict[str, Any]:
        """
        Get KubeVirt template for Linux VM.
        
        Creates optimized Linux VM template for development/server workloads.
        """
        return {
            'apiVersion': 'kubevirt.io/v1',
            'kind': 'VirtualMachine',
            'metadata': {
                'name': spec.vm_name,
                'namespace': self.config.kubernetes.namespace,
                'labels': spec.labels,
                'annotations': spec.annotations
            },
            'spec': {
                'running': True,
                'template': {
                    'metadata': {
                        'labels': spec.labels
                    },
                    'spec': {
                        'domain': {
                            'devices': {
                                'disks': [
                                    {
                                        'name': 'rootdisk',
                                        'disk': {'bus': 'virtio'},
                                        'bootOrder': 1
                                    },
                                    {
                                        'name': 'cloudinitdisk',
                                        'disk': {'bus': 'virtio'}
                                    }
                                ],
                                'interfaces': [{
                                    'name': 'default',
                                    'masquerade': {}
                                }],
                                'rng': {}
                            },
                            'machine': {
                                'type': 'q35'
                            },
                            'resources': {
                                'requests': {
                                    'memory': spec.resources.memory,
                                    'cpu': spec.resources.cpu
                                }
                            }
                        },
                        'networks': [{
                            'name': 'default',
                            'pod': {}
                        }],
                        'volumes': [
                            {
                                'name': 'rootdisk',
                                'containerDisk': {
                                    'image': spec.base_image or self.config.vm.linux_base_image
                                }
                            },
                            {
                                'name': 'cloudinitdisk',
                                'cloudInitNoCloud': {
                                    'userData': self._get_linux_userdata(spec)
                                }
                            }
                        ],
                        'nodeSelector': spec.node_selector,
                        'tolerations': spec.tolerations,
                        'affinity': spec.affinity
                    }
                }
            }
        }
    
    def _get_windows_userdata(self, spec: VMSpec) -> str:
        """Generate cloud-init userdata for Windows VM."""
        return """#ps1
# Windows VM initialization script
Write-Host "Starting Infrastructure SDK VM initialization..."

# Enable RDP
Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -name "fDenyTSConnections" -Value 0
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

# Create user account
$username = "vmuser"
$password = ConvertTo-SecureString -String "TempPassword123!" -AsPlainText -Force
New-LocalUser -Name $username -Password $password -FullName "VM User" -Description "Infrastructure SDK VM User"
Add-LocalGroupMember -Group "Remote Desktop Users" -Member $username
Add-LocalGroupMember -Group "Administrators" -Member $username

Write-Host "VM initialization completed successfully"
"""
    
    def _get_linux_userdata(self, spec: VMSpec) -> str:
        """Generate cloud-init userdata for Linux VM."""
        return """#cloud-config
users:
  - name: vmuser
    sudo: ALL=(ALL) NOPASSWD:ALL
    groups: users, admin
    shell: /bin/bash
    lock_passwd: false
    passwd: $6$rounds=4096$salt$hashed_password_here

packages:
  - curl
  - wget
  - git
  - htop
  - vim

runcmd:
  - systemctl enable ssh
  - systemctl start ssh
  - echo "VM initialization completed" >> /var/log/vm-init.log
"""


class VMStateTracker:
    """
    Tracks VM state changes and health monitoring.
    
    Provides real-time state tracking with event-driven updates
    and health monitoring capabilities.
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
    Manages complete VM lifecycle operations.
    
    Orchestrates VM provisioning, state management, health monitoring,
    and cleanup using KubeVirt and Karpenter integration.
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
        self.template_manager = VMTemplateManager(config)
        self.state_tracker = VMStateTracker()
        
        # VM storage (in production, use persistent storage)
        self._vms: Dict[str, VM] = {}
        
        # Background monitoring
        self._monitoring_task: Optional[asyncio.Task] = None
        
        self.logger.info("VM Lifecycle Controller initialized")
    
    async def provision_vm(self, ctx: Optional[Dict[str, Any]], spec: VMSpec) -> VM:
        """
        Provision a new virtual machine.
        
        Orchestrates complete VM provisioning including resource validation,
        KubeVirt VM creation, and initial health checks.
        
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
                f"Provisioning VM {vm_id} for user {spec.user_id}",
                extra={
                    'vm_id': vm_id,
                    'user_id': spec.user_id,
                    'session_id': spec.session_id,
                    'os_type': spec.os_type
                }
            )
            
            # Validate resource requirements
            await self._validate_resource_requirements(spec)
            
            # Create VM object
            vm = VM(
                vm_id=vm_id,
                vm_name=spec.vm_name,
                user_id=spec.user_id,
                session_id=spec.session_id,
                spec=spec,
                state=VMState.PROVISIONING,
                namespace=self.config.kubernetes.namespace
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
    
    async def _validate_resource_requirements(self, spec: VMSpec) -> None:
        """Validate VM resource requirements against cluster capacity."""
        # TODO: Implement actual resource validation
        # This would check:
        # 1. Cluster has sufficient resources
        # 2. User quotas are not exceeded
        # 3. Node affinity requirements can be satisfied
        pass
    
    async def _provision_vm_async(self, vm: VM) -> None:
        """
        Async VM provisioning workflow.
        
        Orchestrates the complete VM provisioning process including
        KubeVirt VM creation, networking setup, and health validation.
        """
        try:
            vm_id = vm.vm_id
            self.logger.info(f"Starting async provisioning for VM {vm_id}")
            
            # Update state to starting
            await self.state_tracker.update_vm_state(vm, VMState.STARTING)
            
            # 1. Generate KubeVirt VM manifest
            if vm.spec.os_type == "windows":
                manifest = self.template_manager.get_windows_template(vm.spec)
                startup_timeout = self.config.vm.windows_startup_timeout
            else:
                manifest = self.template_manager.get_linux_template(vm.spec)
                startup_timeout = self.config.vm.linux_startup_timeout
            
            vm.kubevirt_vm_manifest = manifest
            
            # 2. Create KubeVirt VM (simulated)
            self.logger.info(f"Creating KubeVirt VM {vm.spec.vm_name}")
            # TODO: Implement actual Kubernetes API call
            # kubectl_client.create_namespaced_custom_object(...)
            
            # 3. Wait for VM startup (simulated)
            startup_start = datetime.utcnow()
            await asyncio.sleep(45)  # Simulate optimized startup time
            startup_duration = (datetime.utcnow() - startup_start).total_seconds()
            
            # 4. Update VM information
            vm.started_at = datetime.utcnow() 
            vm.startup_duration = startup_duration
            vm.allocated_resources = vm.spec.resources
            vm.node_name = f"karpenter-node-{vm.user_id}"
            vm.ip_address = f"10.244.{hash(vm_id) % 255}.{hash(vm_id) % 255}"
            vm.access_ports = {'rdp': 3389, 'vnc': 5900}
            vm.health_status = "healthy"
            vm.instance_type = "m5.xlarge"
            vm.spot_instance = True
            vm.hourly_cost = 0.15  # Simulated cost
            
            # 5. Update state to running
            await self.state_tracker.update_vm_state(vm, VMState.RUNNING)
            vm.update_heartbeat()
            
            self.logger.info(
                f"VM {vm_id} provisioned successfully in {startup_duration:.1f}s",
                extra={'vm_id': vm_id, 'startup_duration': startup_duration}
            )
            
        except Exception as e:
            self.logger.error(f"Failed to provision VM {vm.vm_id}: {e}")
            await self.state_tracker.update_vm_state(vm, VMState.FAILED)
            vm.error_message = str(e)
    
    async def _cleanup_vm_async(self, vm: VM) -> None:
        """
        Async VM cleanup workflow.
        
        Orchestrates complete VM resource cleanup including KubeVirt VM
        deletion, storage cleanup, and state removal.
        """
        try:
            vm_id = vm.vm_id
            self.logger.info(f"Starting async cleanup for VM {vm_id}")
            
            # TODO: Implement actual cleanup logic:
            # 1. Delete KubeVirt VM
            # 2. Clean up storage volumes 
            # 3. Remove network resources
            # 4. Update monitoring systems
            
            # Simulate cleanup time
            await asyncio.sleep(10)
            
            # Update state
            await self.state_tracker.update_vm_state(vm, VMState.TERMINATED)
            
            # Remove from storage
            del self._vms[vm_id]
            
            self.logger.info(f"VM {vm_id} cleaned up successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup VM {vm.vm_id}: {e}")
            vm.error_message = f"Cleanup failed: {e}"