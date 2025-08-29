#!/usr/bin/env python3
"""
VM Agent Adapter - Standardized Interface for AI Agents

This module provides a standardized interface for AI agents to interact with Windows VMs
without needing to understand the underlying VNC/EC2 implementation details.

The adapter focuses on:
- Standard action execution
- VM state monitoring  
- Error handling and recovery
- Event-driven responses

It does NOT include:
- AI-specific logic (NLP, computer vision, etc.)
- Complex workflow orchestration
- Machine learning components

Those features should be implemented in separate AI agent libraries that use this adapter.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Union, Callable
from datetime import datetime, timedelta

from vnc_controller import TightVNCController
from ec2_pool_manager import EC2PoolManager, UserSession


class ActionType(Enum):
    """Standard VM action types for AI agents."""
    MOUSE_CLICK = "mouse_click"
    MOUSE_DOUBLE_CLICK = "mouse_double_click"
    MOUSE_RIGHT_CLICK = "mouse_right_click"
    MOUSE_DRAG = "mouse_drag"
    KEYBOARD_TYPE = "keyboard_type"
    KEYBOARD_HOTKEY = "keyboard_hotkey"
    SCREEN_CAPTURE = "screen_capture"
    WAIT = "wait"
    WAIT_FOR_ELEMENT = "wait_for_element"
    GET_STATE = "get_state"


class VMState(Enum):
    """VM operational states."""
    UNKNOWN = "unknown"
    BOOTING = "booting"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    DISCONNECTED = "disconnected"


@dataclass
class ActionRequest:
    """Standardized action request for VM operations."""
    action_type: ActionType
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 30
    retry_count: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    """Result of VM action execution."""
    success: bool
    action_type: ActionType
    execution_time_ms: int
    error_message: Optional[str] = None
    return_data: Optional[Any] = None
    vm_state_after: Optional[VMState] = None
    screenshot_data: Optional[bytes] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VMStateInfo:
    """Current VM state information for AI agents."""
    state: VMState
    last_action_time: Optional[datetime]
    last_screenshot_time: Optional[datetime]
    active_window_title: Optional[str]
    mouse_position: Optional[tuple]
    screen_resolution: Optional[tuple]
    connection_quality: str  # "excellent", "good", "poor", "disconnected"
    performance_metrics: Dict[str, float] = field(default_factory=dict)


class VMAgentAdapter:
    """
    Standardized adapter interface for AI agents to control Windows VMs.
    
    This class provides a clean, standardized interface that AI agents can use
    without needing to understand VNC protocols or EC2 management details.
    """
    
    def __init__(self, pool_manager: Optional[EC2PoolManager] = None):
        """Initialize VM Agent Adapter."""
        self.pool_manager = pool_manager
        self.logger = logging.getLogger(__name__)
        
        # Current session state
        self.current_session: Optional[UserSession] = None
        self.vnc_controller: Optional[TightVNCController] = None
        self.vm_state = VMState.UNKNOWN
        
        # Performance tracking
        self.action_history: List[ActionResult] = []
        self.last_screenshot: Optional[bytes] = None
        self.last_screenshot_time: Optional[datetime] = None
        
        # State monitoring
        self.state_change_callbacks: List[Callable[[VMState, VMState], None]] = []
        self.action_callbacks: List[Callable[[ActionRequest, ActionResult], None]] = []
        
        # Configuration
        self.default_timeout = 30
        self.screenshot_cache_duration = timedelta(seconds=5)
        self.max_history_items = 100
    
    async def create_vm_session(self, user_id: str, vm_requirements: Optional[Dict[str, Any]] = None) -> bool:
        """
        Create a new VM session for the AI agent.
        
        Args:
            user_id: Unique identifier for the session
            vm_requirements: Optional VM specifications (instance type, etc.)
            
        Returns:
            True if session created successfully, False otherwise
        """
        try:
            self.logger.info(f"Creating VM session for user: {user_id}")
            
            if not self.pool_manager:
                raise ValueError("Pool manager not configured")
            
            # Create VM session
            self.current_session = await self.pool_manager.allocate_instance(user_id)
            
            if not self.current_session:
                self.logger.error(f"Failed to allocate VM instance for user {user_id}")
                return False
            
            # Initialize VNC controller
            self.vnc_controller = TightVNCController(
                host=self.current_session.public_ip,
                port=5900,  # Default VNC port
                password=self.current_session.vnc_password if hasattr(self.current_session, 'vnc_password') else None
            )
            await self.vnc_controller.connect()
            
            # Update state
            await self._update_vm_state(VMState.READY)
            
            self.logger.info(f"VM session created successfully: {self.current_session.instance_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create VM session: {e}")
            await self._update_vm_state(VMState.ERROR)
            return False
    
    async def execute_action(self, action: ActionRequest) -> ActionResult:
        """
        Execute a standardized action on the VM.
        
        Args:
            action: The action request to execute
            
        Returns:
            ActionResult with execution details
        """
        start_time = time.time()
        
        try:
            self.logger.debug(f"Executing action: {action.action_type.value}")
            
            # Validate session
            if not self._is_session_valid():
                return ActionResult(
                    success=False,
                    action_type=action.action_type,
                    execution_time_ms=0,
                    error_message="No valid VM session available"
                )
            
            # Execute action based on type
            result_data = None
            
            if action.action_type == ActionType.MOUSE_CLICK:
                result_data = await self._execute_mouse_click(action.parameters)
            elif action.action_type == ActionType.MOUSE_DOUBLE_CLICK:
                result_data = await self._execute_mouse_double_click(action.parameters)
            elif action.action_type == ActionType.MOUSE_RIGHT_CLICK:
                result_data = await self._execute_mouse_right_click(action.parameters)
            elif action.action_type == ActionType.MOUSE_DRAG:
                result_data = await self._execute_mouse_drag(action.parameters)
            elif action.action_type == ActionType.KEYBOARD_TYPE:
                result_data = await self._execute_keyboard_type(action.parameters)
            elif action.action_type == ActionType.KEYBOARD_HOTKEY:
                result_data = await self._execute_keyboard_hotkey(action.parameters)
            elif action.action_type == ActionType.SCREEN_CAPTURE:
                result_data = await self._execute_screen_capture(action.parameters)
            elif action.action_type == ActionType.WAIT:
                result_data = await self._execute_wait(action.parameters)
            elif action.action_type == ActionType.WAIT_FOR_ELEMENT:
                result_data = await self._execute_wait_for_element(action.parameters)
            elif action.action_type == ActionType.GET_STATE:
                result_data = await self._execute_get_state(action.parameters)
            else:
                raise ValueError(f"Unsupported action type: {action.action_type}")
            
            # Create successful result
            execution_time = int((time.time() - start_time) * 1000)
            result = ActionResult(
                success=True,
                action_type=action.action_type,
                execution_time_ms=execution_time,
                return_data=result_data,
                vm_state_after=self.vm_state
            )
            
            # Add to history
            self._add_to_history(result)
            
            # Trigger callbacks
            for callback in self.action_callbacks:
                try:
                    callback(action, result)
                except Exception as e:
                    self.logger.warning(f"Action callback error: {e}")
            
            return result
            
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            self.logger.error(f"Action execution failed: {e}")
            
            result = ActionResult(
                success=False,
                action_type=action.action_type,
                execution_time_ms=execution_time,
                error_message=str(e),
                vm_state_after=self.vm_state
            )
            
            self._add_to_history(result)
            return result
    
    async def get_vm_state(self) -> VMStateInfo:
        """
        Get comprehensive VM state information.
        
        Returns:
            VMStateInfo with current state details
        """
        try:
            # Get basic state info
            state_info = VMStateInfo(
                state=self.vm_state,
                last_action_time=self._get_last_action_time(),
                last_screenshot_time=self.last_screenshot_time,
                active_window_title=None,  # Could be enhanced with OCR
                mouse_position=None,  # Could be tracked
                screen_resolution=None,  # Could be detected
                connection_quality=self._assess_connection_quality()
            )
            
            # Add performance metrics
            if self.action_history:
                recent_actions = self.action_history[-10:]  # Last 10 actions
                avg_response_time = sum(a.execution_time_ms for a in recent_actions) / len(recent_actions)
                success_rate = sum(1 for a in recent_actions if a.success) / len(recent_actions) * 100
                
                state_info.performance_metrics = {
                    "average_response_time_ms": avg_response_time,
                    "success_rate_percent": success_rate,
                    "total_actions_executed": len(self.action_history)
                }
            
            return state_info
            
        except Exception as e:
            self.logger.error(f"Failed to get VM state: {e}")
            return VMStateInfo(
                state=VMState.ERROR,
                last_action_time=None,
                last_screenshot_time=None,
                connection_quality="disconnected"
            )
    
    async def wait_for_condition(self, condition_check: Callable[[], bool], 
                                timeout_seconds: int = 30, 
                                check_interval: float = 1.0) -> bool:
        """
        Wait for a specific condition to be met.
        
        Args:
            condition_check: Function that returns True when condition is met
            timeout_seconds: Maximum time to wait
            check_interval: Time between checks in seconds
            
        Returns:
            True if condition was met, False if timeout
        """
        start_time = time.time()
        
        while (time.time() - start_time) < timeout_seconds:
            try:
                if condition_check():
                    return True
            except Exception as e:
                self.logger.warning(f"Condition check error: {e}")
            
            await asyncio.sleep(check_interval)
        
        return False
    
    def add_state_change_callback(self, callback: Callable[[VMState, VMState], None]):
        """Add callback for VM state changes."""
        self.state_change_callbacks.append(callback)
    
    def add_action_callback(self, callback: Callable[[ActionRequest, ActionResult], None]):
        """Add callback for action execution."""
        self.action_callbacks.append(callback)
    
    async def cleanup_session(self) -> bool:
        """
        Clean up the current VM session.
        
        Returns:
            True if cleanup successful, False otherwise
        """
        try:
            self.logger.info("Cleaning up VM session")
            
            # Disconnect VNC
            if self.vnc_controller:
                await self.vnc_controller.disconnect()
                self.vnc_controller = None
            
            # Release VM instance
            if self.pool_manager and self.current_session:
                await self.pool_manager.release_instance(self.current_session.instance_id)
            
            # Reset state
            self.current_session = None
            await self._update_vm_state(VMState.UNKNOWN)
            
            self.logger.info("VM session cleaned up successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup session: {e}")
            return False
    
    # Private helper methods
    
    def _is_session_valid(self) -> bool:
        """Check if current session is valid and connected."""
        return (self.current_session is not None and 
                self.vnc_controller is not None and
                self.vm_state not in [VMState.ERROR, VMState.DISCONNECTED])
    
    async def _update_vm_state(self, new_state: VMState):
        """Update VM state and trigger callbacks."""
        if new_state != self.vm_state:
            old_state = self.vm_state
            self.vm_state = new_state
            
            self.logger.info(f"VM state changed: {old_state.value} -> {new_state.value}")
            
            # Trigger callbacks
            for callback in self.state_change_callbacks:
                try:
                    callback(old_state, new_state)
                except Exception as e:
                    self.logger.warning(f"State change callback error: {e}")
    
    def _add_to_history(self, result: ActionResult):
        """Add action result to history."""
        self.action_history.append(result)
        
        # Keep only recent history
        if len(self.action_history) > self.max_history_items:
            self.action_history = self.action_history[-self.max_history_items:]
    
    def _get_last_action_time(self) -> Optional[datetime]:
        """Get timestamp of last action."""
        if self.action_history:
            # This would need to be added to ActionResult if we track timestamps
            return datetime.utcnow()
        return None
    
    def _assess_connection_quality(self) -> str:
        """Assess current connection quality."""
        if not self._is_session_valid():
            return "disconnected"
        
        # Simple quality assessment based on recent performance
        if self.action_history:
            recent_actions = self.action_history[-5:]
            avg_response_time = sum(a.execution_time_ms for a in recent_actions) / len(recent_actions)
            success_rate = sum(1 for a in recent_actions if a.success) / len(recent_actions)
            
            if avg_response_time < 500 and success_rate > 0.9:
                return "excellent"
            elif avg_response_time < 1000 and success_rate > 0.8:
                return "good"
            else:
                return "poor"
        
        return "unknown"
    
    # Action execution methods
    
    async def _execute_mouse_click(self, params: Dict[str, Any]) -> bool:
        """Execute mouse click action."""
        x = params.get('x')
        y = params.get('y')
        button = params.get('button', 'left')
        
        if x is None or y is None:
            raise ValueError("Mouse click requires x and y coordinates")
        
        return await self.vnc_controller.send_mouse_click(x, y, button)
    
    async def _execute_mouse_double_click(self, params: Dict[str, Any]) -> bool:
        """Execute mouse double click action."""
        x = params.get('x')
        y = params.get('y')
        
        if x is None or y is None:
            raise ValueError("Mouse double click requires x and y coordinates")
        
        # Double click by sending two rapid clicks
        await self.vnc_controller.send_mouse_click(x, y, 'left')
        await asyncio.sleep(0.1)
        return await self.vnc_controller.send_mouse_click(x, y, 'left')
    
    async def _execute_mouse_right_click(self, params: Dict[str, Any]) -> bool:
        """Execute mouse right click action."""
        x = params.get('x')
        y = params.get('y')
        
        if x is None or y is None:
            raise ValueError("Mouse right click requires x and y coordinates")
        
        return await self.vnc_controller.send_mouse_click(x, y, 'right')
    
    async def _execute_mouse_drag(self, params: Dict[str, Any]) -> bool:
        """Execute mouse drag action."""
        start_x = params.get('start_x')
        start_y = params.get('start_y')
        end_x = params.get('end_x')
        end_y = params.get('end_y')
        
        if None in [start_x, start_y, end_x, end_y]:
            raise ValueError("Mouse drag requires start_x, start_y, end_x, end_y coordinates")
        
        # Implement drag as move + click + move + release
        await self.vnc_controller.send_mouse_move(start_x, start_y)
        await self.vnc_controller.send_mouse_click(start_x, start_y, 'left')
        await self.vnc_controller.send_mouse_move(end_x, end_y)
        # Note: TightVNCController may need mouse release method
        return True
    
    async def _execute_keyboard_type(self, params: Dict[str, Any]) -> bool:
        """Execute keyboard typing action."""
        text = params.get('text')
        if not text:
            raise ValueError("Keyboard type requires text parameter")
        
        return await self.vnc_controller.send_key_sequence(text)
    
    async def _execute_keyboard_hotkey(self, params: Dict[str, Any]) -> bool:
        """Execute keyboard hotkey combination."""
        keys = params.get('keys')
        if not keys:
            raise ValueError("Keyboard hotkey requires keys parameter")
        
        # Convert key combination to string
        key_combo = "+".join(keys)
        return await self.vnc_controller.send_key_sequence(key_combo)
    
    async def _execute_screen_capture(self, params: Dict[str, Any]) -> bytes:
        """Execute screen capture action."""
        # Check cache first
        if (self.last_screenshot and self.last_screenshot_time and 
            datetime.utcnow() - self.last_screenshot_time < self.screenshot_cache_duration):
            return self.last_screenshot
        
        # Capture new screenshot
        screenshot_data = await self.vnc_controller.capture_screenshot()
        
        # Update cache
        self.last_screenshot = screenshot_data
        self.last_screenshot_time = datetime.utcnow()
        
        return screenshot_data
    
    async def _execute_wait(self, params: Dict[str, Any]) -> bool:
        """Execute wait action."""
        duration = params.get('duration_seconds', 1.0)
        await asyncio.sleep(duration)
        return True
    
    async def _execute_wait_for_element(self, params: Dict[str, Any]) -> bool:
        """Execute wait for element action."""
        # This would require computer vision capabilities
        # For now, just wait for specified duration
        timeout = params.get('timeout_seconds', 30)
        await asyncio.sleep(min(timeout, 5))  # Simplified implementation
        return True
    
    async def _execute_get_state(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute get state action."""
        state_info = await self.get_vm_state()
        return {
            'state': state_info.state.value,
            'connection_quality': state_info.connection_quality,
            'performance_metrics': state_info.performance_metrics
        }


# Convenience functions for AI agents
async def create_ai_vm_session(user_id: str, pool_manager: EC2PoolManager) -> Optional[VMAgentAdapter]:
    """
    Convenience function to create a VM session for AI agents.
    
    Args:
        user_id: Unique identifier for the session
        pool_manager: EC2 pool manager instance
        
    Returns:
        VMAgentAdapter instance if successful, None otherwise
    """
    adapter = VMAgentAdapter(pool_manager)
    success = await adapter.create_vm_session(user_id)
    
    if success:
        return adapter
    else:
        await adapter.cleanup_session()
        return None


def create_action(action_type: ActionType, **parameters) -> ActionRequest:
    """
    Convenience function to create standardized action requests.
    
    Args:
        action_type: Type of action to perform
        **parameters: Action-specific parameters
        
    Returns:
        ActionRequest instance
    """
    return ActionRequest(action_type=action_type, parameters=parameters)


# Common action builders for AI agents
class ActionBuilder:
    """Builder class for common VM actions."""
    
    @staticmethod
    def click(x: int, y: int) -> ActionRequest:
        """Create a mouse click action."""
        return create_action(ActionType.MOUSE_CLICK, x=x, y=y)
    
    @staticmethod
    def double_click(x: int, y: int) -> ActionRequest:
        """Create a mouse double click action."""
        return create_action(ActionType.MOUSE_DOUBLE_CLICK, x=x, y=y)
    
    @staticmethod
    def right_click(x: int, y: int) -> ActionRequest:
        """Create a mouse right click action."""
        return create_action(ActionType.MOUSE_RIGHT_CLICK, x=x, y=y)
    
    @staticmethod
    def type_text(text: str) -> ActionRequest:
        """Create a keyboard typing action."""
        return create_action(ActionType.KEYBOARD_TYPE, text=text)
    
    @staticmethod
    def hotkey(*keys: str) -> ActionRequest:
        """Create a keyboard hotkey action."""
        return create_action(ActionType.KEYBOARD_HOTKEY, keys=list(keys))
    
    @staticmethod
    def screenshot() -> ActionRequest:
        """Create a screen capture action."""
        return create_action(ActionType.SCREEN_CAPTURE)
    
    @staticmethod
    def wait(seconds: float) -> ActionRequest:
        """Create a wait action."""
        return create_action(ActionType.WAIT, duration_seconds=seconds)
    
    @staticmethod
    def get_state() -> ActionRequest:
        """Create a get state action."""
        return create_action(ActionType.GET_STATE)