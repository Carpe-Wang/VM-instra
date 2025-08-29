"""
Unit tests for UserSessionManager.

This module contains comprehensive unit tests for the session management
functionality, including session creation, state management, and cleanup.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from infrastructure_sdk.session import (
    UserSessionManager,
    Session,
    SessionRequest,
    SessionState,
    ResourceSpec
)
from infrastructure_sdk.exceptions import (
    SessionCreationError,
    ResourceNotFoundError
)


class TestResourceSpec:
    """Test cases for ResourceSpec class."""
    
    def test_resource_spec_creation(self):
        """Test ResourceSpec creation with default values."""
        spec = ResourceSpec()
        
        assert spec.cpu == "2"
        assert spec.memory == "4Gi"
        assert spec.disk_size == "50Gi"
        assert spec.storage_class == "gp3"
        assert spec.network_type == "pod"
    
    def test_resource_spec_custom_values(self):
        """Test ResourceSpec creation with custom values."""
        spec = ResourceSpec(
            cpu="8",
            memory="16Gi",
            disk_size="200Gi",
            storage_class="gp2",
            gpu_type="nvidia-t4",
            gpu_count=1
        )
        
        assert spec.cpu == "8"
        assert spec.memory == "16Gi"
        assert spec.disk_size == "200Gi"
        assert spec.storage_class == "gp2"
        assert spec.gpu_type == "nvidia-t4"
        assert spec.gpu_count == 1
    
    def test_resource_spec_validation_invalid_cpu(self):
        """Test ResourceSpec validation with invalid CPU values."""
        with pytest.raises(Exception):  # ConfigurationError
            ResourceSpec(cpu="-1")
        
        with pytest.raises(Exception):  # ConfigurationError
            ResourceSpec(cpu="invalid")
    
    def test_resource_spec_validation_invalid_memory(self):
        """Test ResourceSpec validation with invalid memory values."""
        with pytest.raises(Exception):  # ConfigurationError
            ResourceSpec(memory="invalid")
        
        with pytest.raises(Exception):  # ConfigurationError
            ResourceSpec(memory="8Invalid")


class TestSessionRequest:
    """Test cases for SessionRequest class."""
    
    def test_session_request_creation(self):
        """Test SessionRequest creation with required fields."""
        req = SessionRequest(user_id="test-user")
        
        assert req.user_id == "test-user"
        assert req.session_type == "desktop"
        assert req.vm_os == "windows"
        assert req.ttl == "2h"
        assert req.allow_spot is True
        assert req.dedicated_node is True
    
    def test_session_request_validation_missing_user_id(self):
        """Test SessionRequest validation with missing user_id."""
        with pytest.raises(SessionCreationError) as exc_info:
            SessionRequest(user_id="")
        
        assert "user_id is required" in str(exc_info.value)
    
    def test_session_request_validation_invalid_session_type(self):
        """Test SessionRequest validation with invalid session_type."""
        with pytest.raises(SessionCreationError) as exc_info:
            SessionRequest(user_id="test-user", session_type="invalid")
        
        assert "Invalid session_type" in str(exc_info.value)
    
    def test_session_request_validation_invalid_vm_os(self):
        """Test SessionRequest validation with invalid vm_os."""
        with pytest.raises(SessionCreationError) as exc_info:
            SessionRequest(user_id="test-user", vm_os="invalid")
        
        assert "Invalid vm_os" in str(exc_info.value)


class TestSession:
    """Test cases for Session class."""
    
    def test_session_creation(self):
        """Test Session creation with basic parameters."""
        session = Session(
            session_id="test-session",
            user_id="test-user"
        )
        
        assert session.session_id == "test-session"
        assert session.user_id == "test-user"
        assert session.state == SessionState.PENDING
        assert session.created_at is not None
        assert isinstance(session.created_at, datetime)
    
    def test_session_ttl_parsing(self):
        """Test TTL parsing and expiration calculation."""
        req = SessionRequest(user_id="test-user", ttl="1h")
        session = Session(
            session_id="test-session",
            user_id="test-user",
            session_request=req
        )
        
        expected_expiry = session.created_at + timedelta(hours=1)
        assert abs((session.expires_at - expected_expiry).total_seconds()) < 1
    
    def test_session_is_expired(self):
        """Test session expiration checking."""
        # Create expired session
        past_time = datetime.utcnow() - timedelta(hours=1)
        session = Session(
            session_id="test-session",
            user_id="test-user",
            expires_at=past_time
        )
        
        assert session.is_expired() is True
        
        # Create non-expired session
        future_time = datetime.utcnow() + timedelta(hours=1)
        session.expires_at = future_time
        assert session.is_expired() is False
    
    def test_session_is_idle(self):
        """Test session idle detection."""
        session = Session(
            session_id="test-session",
            user_id="test-user"
        )
        
        # No activity recorded - should not be idle
        assert session.is_idle() is False
        
        # Set old activity
        session.last_activity = datetime.utcnow() - timedelta(minutes=45)
        assert session.is_idle(idle_threshold=1800) is True  # 30 minutes
        
        # Set recent activity
        session.last_activity = datetime.utcnow() - timedelta(minutes=15)
        assert session.is_idle(idle_threshold=1800) is False
    
    def test_session_update_activity(self):
        """Test session activity update."""
        session = Session(
            session_id="test-session",
            user_id="test-user"
        )
        
        initial_activity = session.last_activity
        session.update_activity()
        
        assert session.last_activity != initial_activity
        assert session.last_activity is not None
    
    def test_session_to_dict(self):
        """Test session serialization to dictionary."""
        session = Session(
            session_id="test-session",
            user_id="test-user",
            state=SessionState.ACTIVE,
            node_name="test-node",
            vm_name="test-vm"
        )
        
        session_dict = session.to_dict()
        
        assert session_dict["session_id"] == "test-session"
        assert session_dict["user_id"] == "test-user"
        assert session_dict["state"] == "active"
        assert session_dict["node_name"] == "test-node"
        assert session_dict["vm_name"] == "test-vm"
        assert "created_at" in session_dict


class TestUserSessionManager:
    """Test cases for UserSessionManager class."""
    
    @pytest.fixture
    def session_manager(self, mock_config):
        """Create UserSessionManager instance for testing."""
        return UserSessionManager(mock_config)
    
    @pytest.mark.asyncio
    async def test_create_session_success(self, session_manager):
        """Test successful session creation."""
        req = SessionRequest(user_id="test-user")
        
        with patch.object(session_manager, '_validate_user_session_limits', new_callable=AsyncMock):
            with patch.object(session_manager, '_provision_session', new_callable=AsyncMock):
                session = await session_manager.create_session(None, req)
                
                assert session.user_id == "test-user"
                assert session.state == SessionState.PROVISIONING
                assert session.session_id.startswith("session-")
                assert session.session_id in session_manager._sessions
    
    @pytest.mark.asyncio
    async def test_create_session_user_limit_exceeded(self, session_manager):
        """Test session creation failure due to user limits."""
        req = SessionRequest(user_id="test-user")
        
        # Mock user limit validation to raise exception
        with patch.object(
            session_manager, 
            '_validate_user_session_limits',
            new_callable=AsyncMock,
            side_effect=SessionCreationError("User limit exceeded")
        ):
            with pytest.raises(SessionCreationError) as exc_info:
                await session_manager.create_session(None, req)
            
            assert "Session creation failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_session_success(self, session_manager):
        """Test successful session retrieval."""
        req = SessionRequest(user_id="test-user")
        
        with patch.object(session_manager, '_validate_user_session_limits', new_callable=AsyncMock):
            with patch.object(session_manager, '_provision_session', new_callable=AsyncMock):
                created_session = await session_manager.create_session(None, req)
                retrieved_session = await session_manager.get_session(None, created_session.session_id)
                
                assert retrieved_session.session_id == created_session.session_id
                assert retrieved_session.user_id == "test-user"
    
    @pytest.mark.asyncio
    async def test_get_session_not_found(self, session_manager):
        """Test session retrieval with non-existent session."""
        with pytest.raises(ResourceNotFoundError) as exc_info:
            await session_manager.get_session(None, "non-existent-session")
        
        assert "Session not found" in str(exc_info.value)
        assert exc_info.value.resource_type == "session"
    
    @pytest.mark.asyncio
    async def test_get_session_updates_activity(self, session_manager):
        """Test that getting an active session updates activity."""
        req = SessionRequest(user_id="test-user")
        
        with patch.object(session_manager, '_validate_user_session_limits', new_callable=AsyncMock):
            with patch.object(session_manager, '_provision_session', new_callable=AsyncMock):
                session = await session_manager.create_session(None, req)
                session.state = SessionState.ACTIVE
                
                initial_activity = session.last_activity
                retrieved_session = await session_manager.get_session(None, session.session_id)
                
                assert retrieved_session.last_activity != initial_activity
    
    @pytest.mark.asyncio
    async def test_terminate_session_success(self, session_manager):
        """Test successful session termination."""
        req = SessionRequest(user_id="test-user")
        
        with patch.object(session_manager, '_validate_user_session_limits', new_callable=AsyncMock):
            with patch.object(session_manager, '_provision_session', new_callable=AsyncMock):
                with patch.object(session_manager, '_cleanup_session', new_callable=AsyncMock):
                    session = await session_manager.create_session(None, req)
                    
                    await session_manager.terminate_session(None, session.session_id)
                    
                    assert session.state == SessionState.TERMINATING
                    assert session.terminated_at is not None
    
    @pytest.mark.asyncio
    async def test_terminate_session_already_terminated(self, session_manager):
        """Test terminating an already terminated session."""
        req = SessionRequest(user_id="test-user")
        
        with patch.object(session_manager, '_validate_user_session_limits', new_callable=AsyncMock):
            with patch.object(session_manager, '_provision_session', new_callable=AsyncMock):
                session = await session_manager.create_session(None, req)
                session.state = SessionState.TERMINATED
                
                # Should not raise exception
                await session_manager.terminate_session(None, session.session_id)
                assert session.state == SessionState.TERMINATED
    
    @pytest.mark.asyncio
    async def test_list_user_sessions(self, session_manager):
        """Test listing sessions for a user."""
        req1 = SessionRequest(user_id="test-user")
        req2 = SessionRequest(user_id="test-user")
        req3 = SessionRequest(user_id="other-user")
        
        with patch.object(session_manager, '_validate_user_session_limits', new_callable=AsyncMock):
            with patch.object(session_manager, '_provision_session', new_callable=AsyncMock):
                session1 = await session_manager.create_session(None, req1)
                session2 = await session_manager.create_session(None, req2)
                session3 = await session_manager.create_session(None, req3)
                
                user_sessions = await session_manager.list_user_sessions(None, "test-user")
                
                assert len(user_sessions) == 2
                session_ids = [s.session_id for s in user_sessions]
                assert session1.session_id in session_ids
                assert session2.session_id in session_ids
                assert session3.session_id not in session_ids
    
    @pytest.mark.asyncio
    async def test_list_user_sessions_empty(self, session_manager):
        """Test listing sessions for user with no sessions."""
        sessions = await session_manager.list_user_sessions(None, "non-existent-user")
        assert sessions == []
    
    @pytest.mark.asyncio
    async def test_suspend_session_success(self, session_manager):
        """Test successful session suspension."""
        req = SessionRequest(user_id="test-user")
        
        with patch.object(session_manager, '_validate_user_session_limits', new_callable=AsyncMock):
            with patch.object(session_manager, '_provision_session', new_callable=AsyncMock):
                session = await session_manager.create_session(None, req)
                session.state = SessionState.ACTIVE
                
                await session_manager.suspend_session(None, session.session_id)
                
                assert session.state == SessionState.SUSPENDED
    
    @pytest.mark.asyncio 
    async def test_suspend_session_invalid_state(self, session_manager):
        """Test suspending session in invalid state."""
        req = SessionRequest(user_id="test-user")
        
        with patch.object(session_manager, '_validate_user_session_limits', new_callable=AsyncMock):
            with patch.object(session_manager, '_provision_session', new_callable=AsyncMock):
                session = await session_manager.create_session(None, req)
                session.state = SessionState.TERMINATED
                
                with pytest.raises(SessionCreationError) as exc_info:
                    await session_manager.suspend_session(None, session.session_id)
                
                assert "Can only suspend active sessions" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_resume_session_success(self, session_manager):
        """Test successful session resumption."""
        req = SessionRequest(user_id="test-user")
        
        with patch.object(session_manager, '_validate_user_session_limits', new_callable=AsyncMock):
            with patch.object(session_manager, '_provision_session', new_callable=AsyncMock):
                session = await session_manager.create_session(None, req)
                session.state = SessionState.SUSPENDED
                
                await session_manager.resume_session(None, session.session_id)
                
                assert session.state == SessionState.ACTIVE
                assert session.last_activity is not None
    
    @pytest.mark.asyncio
    async def test_resume_session_invalid_state(self, session_manager):
        """Test resuming session in invalid state."""
        req = SessionRequest(user_id="test-user")
        
        with patch.object(session_manager, '_validate_user_session_limits', new_callable=AsyncMock):
            with patch.object(session_manager, '_provision_session', new_callable=AsyncMock):
                session = await session_manager.create_session(None, req)
                session.state = SessionState.ACTIVE
                
                with pytest.raises(SessionCreationError) as exc_info:
                    await session_manager.resume_session(None, session.session_id)
                
                assert "Can only resume suspended sessions" in str(exc_info.value)
    
    def test_generate_session_id(self, session_manager):
        """Test session ID generation."""
        session_id = session_manager._generate_session_id()
        
        assert session_id.startswith("session-")
        assert len(session_id) > len("session-")
        
        # Generate another to ensure uniqueness
        session_id2 = session_manager._generate_session_id()
        assert session_id != session_id2
    
    @pytest.mark.asyncio
    async def test_validate_user_session_limits(self, session_manager):
        """Test user session limit validation."""
        user_id = "test-user"
        
        # Mock existing sessions for user
        session_manager._user_sessions[user_id] = ["session-1", "session-2", "session-3"]
        for session_id in session_manager._user_sessions[user_id]:
            session = Session(session_id=session_id, user_id=user_id, state=SessionState.ACTIVE)
            session_manager._sessions[session_id] = session
        
        # Should pass with 3 sessions (under limit of 5)
        await session_manager._validate_user_session_limits(user_id)
        
        # Add more sessions to exceed limit
        for i in range(4, 7):  # Add sessions 4, 5, 6
            session_id = f"session-{i}"
            session_manager._user_sessions[user_id].append(session_id)
            session = Session(session_id=session_id, user_id=user_id, state=SessionState.ACTIVE)
            session_manager._sessions[session_id] = session
        
        # Should now fail due to limit
        with pytest.raises(SessionCreationError) as exc_info:
            await session_manager._validate_user_session_limits(user_id)
        
        assert "maximum concurrent sessions" in str(exc_info.value)