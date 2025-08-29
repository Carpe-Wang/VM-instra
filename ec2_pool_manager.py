"""
EC2 Instance Pool Manager

This module provides advanced EC2 instance pool management with:
- Multi-user VM pools with intelligent allocation
- Dynamic scaling based on demand
- Cost optimization through spot instances
- User isolation and security groups
- Automated cleanup and resource management

Target Architecture: Dynamic EC2 Pool → User Assignment → Automatic Scaling
"""

import asyncio
import boto3
import time
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Tuple
from enum import Enum
import logging
from collections import defaultdict

from windows_infrastructure_sdk import (
    EC2WindowsManager, WindowsInstance, EC2ResourceSpec, 
    UserIsolationPolicy, VMState
)


class PoolState(Enum):
    """Pool scaling states."""
    STABLE = "stable"
    SCALING_UP = "scaling_up"
    SCALING_DOWN = "scaling_down"
    MAINTENANCE = "maintenance"


@dataclass
class PoolMetrics:
    """Pool performance and cost metrics."""
    total_instances: int = 0
    active_instances: int = 0
    pending_instances: int = 0
    spot_instances: int = 0
    on_demand_instances: int = 0
    
    # Utilization metrics
    cpu_utilization_avg: float = 0.0
    memory_utilization_avg: float = 0.0
    
    # Cost metrics
    hourly_cost: float = 0.0
    spot_savings: float = 0.0
    
    # Performance metrics
    avg_startup_time: float = 0.0
    success_rate: float = 100.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_instances": self.total_instances,
            "active_instances": self.active_instances, 
            "pending_instances": self.pending_instances,
            "spot_instances": self.spot_instances,
            "on_demand_instances": self.on_demand_instances,
            "cpu_utilization_avg": self.cpu_utilization_avg,
            "memory_utilization_avg": self.memory_utilization_avg,
            "hourly_cost": self.hourly_cost,
            "spot_savings": self.spot_savings,
            "avg_startup_time": self.avg_startup_time,
            "success_rate": self.success_rate
        }


@dataclass
class ScalingPolicy:
    """Dynamic scaling configuration."""
    # Target utilization thresholds
    target_utilization: float = 75.0  # Target 75% utilization
    scale_up_threshold: float = 85.0   # Scale up at 85%
    scale_down_threshold: float = 50.0  # Scale down below 50%
    
    # Scaling parameters
    min_instances: int = 2
    max_instances: int = 50
    scale_up_increment: int = 2       # Add 2 instances at a time
    scale_down_increment: int = 1     # Remove 1 instance at a time
    
    # Timing controls
    scale_up_cooldown_minutes: int = 5   # Wait 5 minutes before scaling up again
    scale_down_cooldown_minutes: int = 15 # Wait 15 minutes before scaling down
    
    # Buffer configuration
    warm_pool_size: int = 2          # Keep 2 warm instances ready
    preemptive_scaling: bool = True   # Scale before hitting limits


@dataclass
class UserSession:
    """User session tracking for pool management."""
    user_id: str
    session_id: str
    instance_id: str
    allocated_at: datetime
    last_activity: datetime
    session_timeout_minutes: int = 480  # 8 hours default
    
    def is_expired(self) -> bool:
        """Check if session has expired."""
        timeout = timedelta(minutes=self.session_timeout_minutes)
        return datetime.utcnow() - self.last_activity > timeout
    
    def is_idle(self, idle_threshold_minutes: int = 30) -> bool:
        """Check if session is idle."""
        idle_time = timedelta(minutes=idle_threshold_minutes)
        return datetime.utcnow() - self.last_activity > idle_time


class EC2PoolManager:
    """
    Advanced EC2 instance pool manager with intelligent scaling.
    
    Provides enterprise-grade features:
    - Dynamic pool sizing based on demand
    - Intelligent instance allocation
    - Cost optimization with spot/on-demand mix
    - User isolation and security
    - Predictive scaling
    - Automated resource cleanup
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize EC2 Pool Manager."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Core managers
        self.ec2_manager = EC2WindowsManager(config)
        
        # AWS clients
        self.ec2_client = boto3.client(
            'ec2',
            region_name=config.get('aws_region', 'us-west-2'),
            aws_access_key_id=config.get('aws_access_key_id'),
            aws_secret_access_key=config.get('aws_secret_access_key')
        )
        self.cloudwatch = boto3.client(
            'cloudwatch',
            region_name=config.get('aws_region', 'us-west-2'),
            aws_access_key_id=config.get('aws_access_key_id'),
            aws_secret_access_key=config.get('aws_secret_access_key')
        )
        
        # Pool state management
        self.pool_state = PoolState.STABLE
        self.last_scale_action = datetime.utcnow()
        
        # Instance tracking
        self.warm_instances: Set[str] = set()  # Ready instances not assigned
        self.assigned_instances: Dict[str, str] = {}  # instance_id -> user_id
        self.user_sessions: Dict[str, UserSession] = {}  # session_id -> UserSession
        
        # Scaling configuration
        self.scaling_policy = ScalingPolicy(
            min_instances=config.get('min_pool_size', 2),
            max_instances=config.get('max_pool_size', 50),
            target_utilization=config.get('target_utilization', 75.0)
        )
        
        # Background tasks
        self._scaling_task: Optional[asyncio.Task] = None
        self._monitoring_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        self.logger.info("EC2 Pool Manager initialized")
    
    async def start_pool_management(self) -> None:
        """Start background pool management tasks."""
        self.logger.info("Starting pool management tasks")
        
        # Start background tasks
        self._scaling_task = asyncio.create_task(self._scaling_loop())
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        # Initialize warm pool
        await self._ensure_warm_pool()
    
    async def stop_pool_management(self) -> None:
        """Stop background pool management tasks."""
        self.logger.info("Stopping pool management tasks")
        
        tasks = [self._scaling_task, self._monitoring_task, self._cleanup_task]
        for task in tasks:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    async def request_instance(self, user_id: str, resource_spec: EC2ResourceSpec,
                             isolation_policy: UserIsolationPolicy,
                             session_timeout_minutes: int = 480) -> WindowsInstance:
        """
        Request a Windows instance from the pool.
        
        Uses intelligent allocation:
        1. Try to allocate from warm pool (fastest)
        2. Scale up if needed
        3. Create new instance if necessary
        
        Args:
            user_id: User identifier
            resource_spec: Resource requirements
            isolation_policy: User isolation settings
            session_timeout_minutes: Session timeout
            
        Returns:
            WindowsInstance ready for use
        """
        session_id = f"pool-session-{int(time.time())}"
        
        self.logger.info(f"Processing instance request for user {user_id}")
        
        try:
            # 1. Try to allocate from warm pool
            instance = await self._allocate_from_warm_pool(user_id, session_id, session_timeout_minutes)
            if instance:
                self.logger.info(f"Allocated warm instance {instance.instance_id} to user {user_id}")
                return instance
            
            # 2. Check if we need to scale up
            await self._trigger_scale_up_if_needed()
            
            # 3. Create new instance directly
            instance = await self.ec2_manager.create_user_session(
                user_id=user_id,
                resource_spec=resource_spec,
                isolation_policy=isolation_policy
            )
            
            # Track the session
            user_session = UserSession(
                user_id=user_id,
                session_id=session_id,
                instance_id=instance.instance_id,
                allocated_at=datetime.utcnow(),
                last_activity=datetime.utcnow(),
                session_timeout_minutes=session_timeout_minutes
            )
            
            self.user_sessions[session_id] = user_session
            self.assigned_instances[instance.instance_id] = user_id
            
            self.logger.info(f"Created new instance {instance.instance_id} for user {user_id}")
            return instance
            
        except Exception as e:
            self.logger.error(f"Failed to allocate instance for user {user_id}: {e}")
            raise
    
    async def release_instance(self, instance_id: str, cleanup_user_data: bool = True) -> None:
        """
        Release an instance back to the pool or terminate it.
        
        Args:
            instance_id: Instance to release
            cleanup_user_data: Whether to clean user data before reuse
        """
        self.logger.info(f"Releasing instance {instance_id}")
        
        try:
            # Find and remove user session
            session_to_remove = None
            for session_id, session in self.user_sessions.items():
                if session.instance_id == instance_id:
                    session_to_remove = session_id
                    break
            
            if session_to_remove:
                del self.user_sessions[session_to_remove]
            
            # Remove from assigned instances
            if instance_id in self.assigned_instances:
                del self.assigned_instances[instance_id]
            
            # Decide whether to return to warm pool or terminate
            if cleanup_user_data and len(self.warm_instances) < self.scaling_policy.warm_pool_size:
                # Clean and return to warm pool
                await self._prepare_instance_for_reuse(instance_id)
                self.warm_instances.add(instance_id)
                self.logger.info(f"Instance {instance_id} returned to warm pool")
            else:
                # Terminate the instance
                await self.ec2_manager.terminate_instance(instance_id)
                self.logger.info(f"Instance {instance_id} terminated")
                
        except Exception as e:
            self.logger.error(f"Failed to release instance {instance_id}: {e}")
    
    async def get_pool_metrics(self) -> PoolMetrics:
        """Get current pool metrics and performance data."""
        try:
            # Get instance counts
            all_instances = await self._get_all_pool_instances()
            active_instances = [i for i in all_instances if i.state == VMState.RUNNING]
            pending_instances = [i for i in all_instances if i.state in [VMState.PENDING, VMState.LAUNCHING]]
            spot_instances = [i for i in active_instances if i.is_spot_instance]
            
            # Calculate costs
            hourly_cost = sum(i.hourly_cost or 0.0 for i in active_instances)
            spot_savings = self._calculate_spot_savings(active_instances)
            
            # Calculate performance metrics
            startup_times = [i.startup_duration_seconds for i in active_instances 
                           if i.startup_duration_seconds is not None]
            avg_startup_time = sum(startup_times) / len(startup_times) if startup_times else 0.0
            
            # Calculate success rate
            failed_instances = [i for i in all_instances if i.state == VMState.FAILED]
            total_attempts = len(all_instances)
            success_rate = ((total_attempts - len(failed_instances)) / total_attempts * 100) if total_attempts > 0 else 100.0
            
            metrics = PoolMetrics(
                total_instances=len(all_instances),
                active_instances=len(active_instances),
                pending_instances=len(pending_instances),
                spot_instances=len(spot_instances),
                on_demand_instances=len(active_instances) - len(spot_instances),
                hourly_cost=hourly_cost,
                spot_savings=spot_savings,
                avg_startup_time=avg_startup_time,
                success_rate=success_rate
            )
            
            # Get CloudWatch metrics if available
            await self._enrich_metrics_with_cloudwatch(metrics)
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Failed to get pool metrics: {e}")
            return PoolMetrics()
    
    async def _allocate_from_warm_pool(self, user_id: str, session_id: str,
                                     session_timeout_minutes: int) -> Optional[WindowsInstance]:
        """Allocate an instance from the warm pool."""
        if not self.warm_instances:
            return None
        
        # Get a warm instance
        instance_id = self.warm_instances.pop()
        
        # Get instance details
        instance = await self.ec2_manager.get_instance(instance_id)
        if not instance or not instance.is_ready():
            # Instance not ready, try another or return None
            if self.warm_instances:
                return await self._allocate_from_warm_pool(user_id, session_id, session_timeout_minutes)
            return None
        
        # Update instance for new user
        instance.user_id = user_id
        instance.session_id = session_id
        
        # Create user session tracking
        user_session = UserSession(
            user_id=user_id,
            session_id=session_id,
            instance_id=instance_id,
            allocated_at=datetime.utcnow(),
            last_activity=datetime.utcnow(),
            session_timeout_minutes=session_timeout_minutes
        )
        
        self.user_sessions[session_id] = user_session
        self.assigned_instances[instance_id] = user_id
        
        return instance
    
    async def _ensure_warm_pool(self) -> None:
        """Ensure minimum warm pool size is maintained."""
        current_warm = len(self.warm_instances)
        target_warm = self.scaling_policy.warm_pool_size
        
        if current_warm < target_warm:
            needed = target_warm - current_warm
            self.logger.info(f"Creating {needed} warm instances for pool")
            
            # Create warm instances
            tasks = []
            for _ in range(needed):
                task = asyncio.create_task(self._create_warm_instance())
                tasks.append(task)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _create_warm_instance(self) -> None:
        """Create a warm instance for the pool."""
        try:
            # Use default resource spec for warm instances
            resource_spec = EC2ResourceSpec(
                instance_type=self.config.get('default_instance_type', 'm5.large')
            )
            
            isolation_policy = UserIsolationPolicy(
                dedicated_security_group=False  # Use shared security group for warm instances
            )
            
            instance = await self.ec2_manager.create_user_session(
                user_id="warm-pool",
                resource_spec=resource_spec,
                isolation_policy=isolation_policy
            )
            
            # Wait for instance to be ready
            await self._wait_for_instance_ready(instance.instance_id, timeout_seconds=600)
            
            # Add to warm pool
            self.warm_instances.add(instance.instance_id)
            
            self.logger.info(f"Created warm instance {instance.instance_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to create warm instance: {e}")
    
    async def _wait_for_instance_ready(self, instance_id: str, timeout_seconds: int = 600) -> bool:
        """Wait for instance to be ready."""
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            try:
                instance = await self.ec2_manager.get_instance(instance_id)
                if instance and instance.is_ready():
                    return True
                await asyncio.sleep(30)
            except Exception:
                await asyncio.sleep(30)
        
        return False
    
    async def _scaling_loop(self) -> None:
        """Background scaling management loop."""
        while True:
            try:
                await self._check_and_scale()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in scaling loop: {e}")
                await asyncio.sleep(60)
    
    async def _check_and_scale(self) -> None:
        """Check pool utilization and scale if needed."""
        metrics = await self.get_pool_metrics()
        
        # Calculate utilization
        if metrics.total_instances > 0:
            utilization = (metrics.active_instances - len(self.warm_instances)) / metrics.total_instances * 100
        else:
            utilization = 0.0
        
        # Check scaling conditions
        if utilization > self.scaling_policy.scale_up_threshold:
            await self._scale_up()
        elif utilization < self.scaling_policy.scale_down_threshold:
            await self._scale_down()
    
    async def _scale_up(self) -> None:
        """Scale up the pool."""
        if self.pool_state == PoolState.SCALING_UP:
            return  # Already scaling
        
        # Check cooldown
        cooldown = timedelta(minutes=self.scaling_policy.scale_up_cooldown_minutes)
        if datetime.utcnow() - self.last_scale_action < cooldown:
            return
        
        # Check max instances
        metrics = await self.get_pool_metrics()
        if metrics.total_instances >= self.scaling_policy.max_instances:
            return
        
        self.pool_state = PoolState.SCALING_UP
        self.last_scale_action = datetime.utcnow()
        
        # Calculate instances to add
        instances_to_add = min(
            self.scaling_policy.scale_up_increment,
            self.scaling_policy.max_instances - metrics.total_instances
        )
        
        self.logger.info(f"Scaling up: adding {instances_to_add} instances")
        
        # Create new instances
        tasks = []
        for _ in range(instances_to_add):
            task = asyncio.create_task(self._create_warm_instance())
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        self.pool_state = PoolState.STABLE
    
    async def _scale_down(self) -> None:
        """Scale down the pool."""
        if self.pool_state == PoolState.SCALING_DOWN:
            return  # Already scaling
        
        # Check cooldown
        cooldown = timedelta(minutes=self.scaling_policy.scale_down_cooldown_minutes)
        if datetime.utcnow() - self.last_scale_action < cooldown:
            return
        
        # Don't scale below minimum
        metrics = await self.get_pool_metrics()
        if metrics.total_instances <= self.scaling_policy.min_instances:
            return
        
        self.pool_state = PoolState.SCALING_DOWN
        self.last_scale_action = datetime.utcnow()
        
        # Calculate instances to remove
        instances_to_remove = min(
            self.scaling_policy.scale_down_increment,
            metrics.total_instances - self.scaling_policy.min_instances
        )
        
        self.logger.info(f"Scaling down: removing {instances_to_remove} instances")
        
        # Remove warm instances first
        removed = 0
        warm_instances_copy = list(self.warm_instances)
        for instance_id in warm_instances_copy:
            if removed >= instances_to_remove:
                break
            
            await self.ec2_manager.terminate_instance(instance_id)
            self.warm_instances.discard(instance_id)
            removed += 1
        
        self.pool_state = PoolState.STABLE
    
    async def _monitoring_loop(self) -> None:
        """Background monitoring and metrics collection."""
        while True:
            try:
                await self._collect_metrics()
                await asyncio.sleep(300)  # Collect every 5 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(300)
    
    async def _cleanup_loop(self) -> None:
        """Background cleanup of expired sessions and instances."""
        while True:
            try:
                await self._cleanup_expired_sessions()
                await asyncio.sleep(900)  # Check every 15 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(900)
    
    async def _cleanup_expired_sessions(self) -> None:
        """Clean up expired user sessions."""
        expired_sessions = []
        
        for session_id, session in self.user_sessions.items():
            if session.is_expired():
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            session = self.user_sessions[session_id]
            self.logger.info(f"Cleaning up expired session {session_id} for user {session.user_id}")
            await self.release_instance(session.instance_id)
    
    async def _get_all_pool_instances(self) -> List[WindowsInstance]:
        """Get all instances managed by the pool."""
        # This would query all instances with pool management tags
        # For now, return instances from the manager
        return list(self.ec2_manager._instances.values())
    
    def _calculate_spot_savings(self, instances: List[WindowsInstance]) -> float:
        """Calculate cost savings from spot instances."""
        spot_cost = sum(i.hourly_cost or 0.0 for i in instances if i.is_spot_instance)
        on_demand_cost = sum((i.hourly_cost or 0.0) * 1.5 for i in instances if i.is_spot_instance)  # Estimate on-demand cost
        
        return max(0.0, on_demand_cost - spot_cost)
    
    async def _prepare_instance_for_reuse(self, instance_id: str) -> None:
        """Prepare an instance for reuse by cleaning user data."""
        # This would run cleanup scripts on the instance
        # For now, just log the action
        self.logger.info(f"Preparing instance {instance_id} for reuse (cleanup user data)")
    
    async def _collect_metrics(self) -> None:
        """Collect and publish metrics to CloudWatch."""
        try:
            metrics = await self.get_pool_metrics()
            
            # Publish to CloudWatch
            await self._publish_cloudwatch_metrics(metrics)
            
        except Exception as e:
            self.logger.error(f"Failed to collect metrics: {e}")
    
    async def _publish_cloudwatch_metrics(self, metrics: PoolMetrics) -> None:
        """Publish metrics to AWS CloudWatch."""
        try:
            timestamp = datetime.utcnow()
            
            metric_data = [
                {
                    'MetricName': 'TotalInstances',
                    'Value': metrics.total_instances,
                    'Unit': 'Count',
                    'Timestamp': timestamp
                },
                {
                    'MetricName': 'ActiveInstances', 
                    'Value': metrics.active_instances,
                    'Unit': 'Count',
                    'Timestamp': timestamp
                },
                {
                    'MetricName': 'HourlyCost',
                    'Value': metrics.hourly_cost,
                    'Unit': 'None',
                    'Timestamp': timestamp
                },
                {
                    'MetricName': 'SpotSavings',
                    'Value': metrics.spot_savings,
                    'Unit': 'None',
                    'Timestamp': timestamp
                }
            ]
            
            self.cloudwatch.put_metric_data(
                Namespace='EC2Pool',
                MetricData=metric_data
            )
            
        except Exception as e:
            self.logger.error(f"Failed to publish CloudWatch metrics: {e}")
    
    async def _enrich_metrics_with_cloudwatch(self, metrics: PoolMetrics) -> None:
        """Enrich metrics with CloudWatch data."""
        try:
            # Get CPU utilization data
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)
            
            # This would fetch actual CloudWatch metrics
            # For now, use placeholder values
            metrics.cpu_utilization_avg = 65.0
            metrics.memory_utilization_avg = 70.0
            
        except Exception as e:
            self.logger.error(f"Failed to enrich metrics with CloudWatch: {e}")
    
    async def _trigger_scale_up_if_needed(self) -> None:
        """Trigger scale up if pool is at capacity."""
        if len(self.warm_instances) == 0:
            # No warm instances available, trigger scale up
            await self._scale_up()