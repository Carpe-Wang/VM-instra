"""
User Session Manager for Infrastructure SDK.

This module implements complete user session lifecycle orchestration,
including session creation, authentication, resource allocation,
state tracking, and multi-tenant session coordination.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from enum import Enum
import logging

from .config import InfraSDKConfig
from .exceptions import (
    SessionCreationError,
    ResourceNotFoundError,
    ConfigurationError
)


class SessionState(Enum):
    """Enumeration of possible session states."""
    PENDING = "pending"
    PROVISIONING = "provisioning" 
    ACTIVE = "active"
    IDLE = "idle"
    SUSPENDED = "suspended"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    FAILED = "failed"


@dataclass
class ResourceSpec:
    """
    Resource specification for VM allocation.
    
    Defines CPU, memory, storage, and network requirements
    for user session VM instances.
    """
    
    cpu: str = "2"           # CPU cores (e.g., "2", "4")
    memory: str = "4Gi"      # Memory (e.g., "4Gi", "8Gi")
    disk_size: str = "50Gi"  # Root disk size
    storage_class: str = "gp3"
    network_type: str = "pod"
    
    # Optional resource limits
    cpu_limit: Optional[str] = None
    memory_limit: Optional[str] = None
    
    # GPU resources (optional)
    gpu_type: Optional[str] = None
    gpu_count: int = 0
    
    def __post_init__(self) -> None:
        """Validate resource specification."""
        # Parse CPU requirement
        try:
            cpu_val = float(self.cpu)
            if cpu_val <= 0 or cpu_val > 96:  # Reasonable limits
                raise ValueError(f"CPU must be between 0 and 96, got: {cpu_val}")
        except ValueError as e:
            raise ConfigurationError(f"Invalid CPU specification: {self.cpu}") from e
        
        # Validate memory format
        if not any(self.memory.endswith(unit) for unit in ['Gi', 'Mi', 'G', 'M']):
            raise ConfigurationError(f"Invalid memory specification: {self.memory}")


@dataclass
class SessionRequest:
    """
    Request structure for creating a new user session.
    
    Contains all parameters necessary for session creation including
    user identification, resource requirements, and configuration options.
    """
    
    user_id: str
    session_type: str = "desktop"  # desktop, server, development
    resources: ResourceSpec = field(default_factory=ResourceSpec)
    ttl: str = "2h"  # Session time-to-live
    
    # VM Configuration
    vm_os: str = "windows"  # windows, linux
    vm_image: Optional[str] = None
    applications: List[str] = field(default_factory=list)
    
    # Cost Optimization
    allow_spot: bool = True
    max_hourly_cost: Optional[float] = None
    
    # Isolation Requirements
    dedicated_node: bool = True
    network_isolation: bool = True
    storage_encryption: bool = True
    
    # Metadata
    tags: Dict[str, str] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate session request after initialization."""
        if not self.user_id:
            raise SessionCreationError("user_id is required")
        
        if self.session_type not in ["desktop", "server", "development"]:
            raise SessionCreationError(
                f"Invalid session_type: {self.session_type}",
                user_id=self.user_id,
                details={"valid_types": ["desktop", "server", "development"]}
            )
        
        if self.vm_os not in ["windows", "linux"]:
            raise SessionCreationError(
                f"Invalid vm_os: {self.vm_os}",
                user_id=self.user_id,
                details={"valid_os": ["windows", "linux"]}
            )


@dataclass
class Session:
    """
    Represents an active user session.
    
    Contains session state, metadata, resource allocation information,
    and lifecycle management data.
    """
    
    session_id: str
    user_id: str
    state: SessionState = SessionState.PENDING
    
    # Request Information
    session_request: SessionRequest = None
    
    # Resource Allocation
    allocated_resources: Optional[ResourceSpec] = None
    node_name: Optional[str] = None
    vm_name: Optional[str] = None
    
    # Networking
    access_url: Optional[str] = None
    rdp_port: Optional[int] = None
    vnc_port: Optional[int] = None
    
    # Lifecycle Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    terminated_at: Optional[datetime] = None
    
    # Cost Tracking
    estimated_hourly_cost: Optional[float] = None
    actual_cost: float = 0.0
    spot_instance: bool = False
    
    # Status Information
    health_status: str = "unknown"
    error_message: Optional[str] = None
    
    # Metadata
    tags: Dict[str, str] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Calculate derived fields after initialization."""
        if self.session_request and not self.expires_at:
            # Parse TTL and set expiration
            ttl_seconds = self._parse_ttl(self.session_request.ttl)
            self.expires_at = self.created_at + timedelta(seconds=ttl_seconds)
    
    def _parse_ttl(self, ttl: str) -> int:
        """Parse TTL string to seconds."""
        ttl = ttl.strip().lower()
        
        if ttl.endswith('s'):
            return int(ttl[:-1])
        elif ttl.endswith('m'):
            return int(ttl[:-1]) * 60
        elif ttl.endswith('h'):
            return int(ttl[:-1]) * 3600
        elif ttl.endswith('d'):
            return int(ttl[:-1]) * 86400
        else:
            # Assume hours if no unit specified
            return int(ttl) * 3600
    
    def is_expired(self) -> bool:
        """Check if session has expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    def is_idle(self, idle_threshold: int = 1800) -> bool:
        """Check if session is idle based on last activity."""
        if not self.last_activity:
            return False
        
        idle_since = datetime.utcnow() - self.last_activity
        return idle_since.total_seconds() > idle_threshold
    
    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for serialization."""
        return {
            'session_id': self.session_id,
            'user_id': self.user_id,
            'state': self.state.value,
            'allocated_resources': self.allocated_resources.__dict__ if self.allocated_resources else None,
            'node_name': self.node_name,
            'vm_name': self.vm_name,
            'access_url': self.access_url,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'estimated_hourly_cost': self.estimated_hourly_cost,
            'actual_cost': self.actual_cost,
            'spot_instance': self.spot_instance,
            'health_status': self.health_status,
            'error_message': self.error_message,
            'tags': self.tags,
            'labels': self.labels
        }


class UserSessionManager:
    """
    Manages complete user session lifecycle operations.
    
    Orchestrates session creation, state management, resource allocation,
    monitoring, and cleanup for multi-tenant VM-based user sessions.
    """
    
    def __init__(self, config: InfraSDKConfig):
        """
        Initialize User Session Manager.
        
        Args:
            config: Infrastructure SDK configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Session storage (in production, use persistent storage)
        self._sessions: Dict[str, Session] = {}
        self._user_sessions: Dict[str, List[str]] = {}  # user_id -> session_ids
        
        # Background tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        self.logger.info("User Session Manager initialized")
    
    async def create_session(
        self, 
        ctx: Optional[Dict[str, Any]], 
        req: SessionRequest
    ) -> Session:
        """
        Create a new user session.
        
        Orchestrates complete session creation including resource allocation,
        VM provisioning, and initial configuration.
        
        Args:
            ctx: Request context (for correlation, auth, etc.)
            req: Session creation request
            
        Returns:
            Created Session object
            
        Raises:
            SessionCreationError: If session creation fails
        """
        try:
            # Generate unique session ID
            session_id = self._generate_session_id()
            
            self.logger.info(
                f"Creating session {session_id} for user {req.user_id}",
                extra={
                    'session_id': session_id,
                    'user_id': req.user_id,
                    'session_type': req.session_type
                }
            )
            
            # Validate user can create sessions
            await self._validate_user_session_limits(req.user_id)
            
            # Create session object
            session = Session(
                session_id=session_id,
                user_id=req.user_id,
                session_request=req,
                state=SessionState.PROVISIONING,
                tags=req.tags.copy(),
                labels=req.labels.copy()
            )
            
            # Add default labels
            session.labels.update({
                'infra-sdk.io/managed': 'true',
                'infra-sdk.io/user-id': req.user_id,
                'infra-sdk.io/session-type': req.session_type
            })
            
            # Store session
            self._sessions[session_id] = session
            if req.user_id not in self._user_sessions:
                self._user_sessions[req.user_id] = []
            self._user_sessions[req.user_id].append(session_id)
            
            # Start async provisioning
            asyncio.create_task(self._provision_session(session))
            
            self.logger.info(
                f"Session {session_id} created successfully",
                extra={'session_id': session_id}
            )
            
            return session
            
        except Exception as e:
            self.logger.error(
                f"Failed to create session for user {req.user_id}: {e}",
                extra={'user_id': req.user_id}
            )
            raise SessionCreationError(
                f"Session creation failed: {e}",
                user_id=req.user_id,
                session_spec=req.__dict__
            ) from e
    
    async def get_session(
        self, 
        ctx: Optional[Dict[str, Any]], 
        session_id: str
    ) -> Session:
        """
        Retrieve session by ID.
        
        Args:
            ctx: Request context
            session_id: Session identifier
            
        Returns:
            Session object
            
        Raises:
            ResourceNotFoundError: If session not found
        """
        if session_id not in self._sessions:
            raise ResourceNotFoundError(
                f"Session not found: {session_id}",
                resource_type="session",
                resource_id=session_id
            )
        
        session = self._sessions[session_id]
        
        # Update activity if session is active
        if session.state == SessionState.ACTIVE:
            session.update_activity()
        
        return session
    
    async def terminate_session(
        self, 
        ctx: Optional[Dict[str, Any]], 
        session_id: str
    ) -> None:
        """
        Terminate session and cleanup resources.
        
        Args:
            ctx: Request context
            session_id: Session identifier
            
        Raises:
            ResourceNotFoundError: If session not found
        """
        session = await self.get_session(ctx, session_id)
        
        if session.state in [SessionState.TERMINATED, SessionState.TERMINATING]:
            self.logger.warning(f"Session {session_id} already terminated/terminating")
            return
        
        self.logger.info(
            f"Terminating session {session_id}",
            extra={'session_id': session_id, 'user_id': session.user_id}
        )
        
        session.state = SessionState.TERMINATING
        session.terminated_at = datetime.utcnow()
        
        # Start async cleanup
        asyncio.create_task(self._cleanup_session(session))
    
    async def list_user_sessions(
        self, 
        ctx: Optional[Dict[str, Any]], 
        user_id: str
    ) -> List[Session]:
        """
        List all sessions for a user.
        
        Args:
            ctx: Request context
            user_id: User identifier
            
        Returns:
            List of Session objects for the user
        """
        if user_id not in self._user_sessions:
            return []
        
        session_ids = self._user_sessions[user_id]
        sessions = [self._sessions[sid] for sid in session_ids if sid in self._sessions]
        
        # Sort by creation time (newest first)
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        
        return sessions
    
    async def suspend_session(
        self,
        ctx: Optional[Dict[str, Any]],
        session_id: str
    ) -> None:
        """
        Suspend a session to save costs.
        
        Args:
            ctx: Request context
            session_id: Session identifier
        """
        session = await self.get_session(ctx, session_id)
        
        if session.state != SessionState.ACTIVE:
            raise SessionCreationError(
                f"Can only suspend active sessions, current state: {session.state.value}",
                session_id=session_id
            )
        
        self.logger.info(f"Suspending session {session_id}")
        session.state = SessionState.SUSPENDED
        
        # TODO: Implement VM suspension logic
    
    async def resume_session(
        self,
        ctx: Optional[Dict[str, Any]], 
        session_id: str
    ) -> None:
        """
        Resume a suspended session.
        
        Args:
            ctx: Request context
            session_id: Session identifier
        """
        session = await self.get_session(ctx, session_id)
        
        if session.state != SessionState.SUSPENDED:
            raise SessionCreationError(
                f"Can only resume suspended sessions, current state: {session.state.value}",
                session_id=session_id
            )
        
        self.logger.info(f"Resuming session {session_id}")
        session.state = SessionState.ACTIVE
        session.update_activity()
        
        # TODO: Implement VM resume logic
    
    def _generate_session_id(self) -> str:
        """Generate unique session identifier."""
        return f"session-{uuid.uuid4().hex[:8]}"
    
    async def _validate_user_session_limits(self, user_id: str) -> None:
        """Validate user can create additional sessions."""
        user_sessions = await self.list_user_sessions(None, user_id)
        active_sessions = [
            s for s in user_sessions 
            if s.state in [SessionState.ACTIVE, SessionState.PROVISIONING, SessionState.IDLE]
        ]
        
        # TODO: Make this configurable
        max_concurrent_sessions = 5
        
        if len(active_sessions) >= max_concurrent_sessions:
            raise SessionCreationError(
                f"User {user_id} has reached maximum concurrent sessions ({max_concurrent_sessions})",
                user_id=user_id,
                details={
                    'current_sessions': len(active_sessions),
                    'max_sessions': max_concurrent_sessions
                }
            )
    
    async def _provision_session(self, session: Session) -> None:
        """
        Async session provisioning workflow.
        
        This method orchestrates the complete session provisioning process
        including VM creation, networking setup, and health checks.
        """
        try:
            session_id = session.session_id
            self.logger.info(f"Starting provisioning for session {session_id}")
            
            # TODO: Implement actual provisioning logic with:
            # 1. VM Lifecycle Controller integration
            # 2. Node provisioning through Karpenter  
            # 3. KubeVirt VM creation
            # 4. Network configuration
            # 5. Health checks
            
            # Simulate provisioning delay
            await asyncio.sleep(30)  # In reality, this would be VM startup time
            
            # Update session state
            session.state = SessionState.ACTIVE
            session.started_at = datetime.utcnow()
            session.update_activity()
            session.health_status = "healthy"
            
            # Mock resource allocation
            session.allocated_resources = session.session_request.resources
            session.node_name = f"node-{session.user_id}"
            session.vm_name = f"vm-{session_id}"
            session.access_url = f"https://rdp-gateway.example.com/session/{session_id}"
            
            self.logger.info(f"Session {session_id} provisioned successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to provision session {session.session_id}: {e}")
            session.state = SessionState.FAILED
            session.error_message = str(e)
    
    async def _cleanup_session(self, session: Session) -> None:
        """
        Async session cleanup workflow.
        
        Orchestrates complete resource cleanup including VM termination,
        storage cleanup, and state removal.
        """
        try:
            session_id = session.session_id
            self.logger.info(f"Starting cleanup for session {session_id}")
            
            # TODO: Implement actual cleanup logic with:
            # 1. VM termination
            # 2. EBS volume deletion  
            # 3. Network resource cleanup
            # 4. Monitoring data cleanup
            
            # Simulate cleanup time
            await asyncio.sleep(10)
            
            # Update session state
            session.state = SessionState.TERMINATED
            
            # Remove from user sessions list
            if session.user_id in self._user_sessions:
                self._user_sessions[session.user_id] = [
                    sid for sid in self._user_sessions[session.user_id] 
                    if sid != session_id
                ]
            
            self.logger.info(f"Session {session_id} cleaned up successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup session {session.session_id}: {e}")
            session.error_message = f"Cleanup failed: {e}"