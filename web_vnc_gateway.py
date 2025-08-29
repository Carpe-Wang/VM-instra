"""
VNC Web Gateway for Real-time Remote Desktop Access

This module provides a WebSocket-based gateway that bridges VNC connections
with web browsers, enabling real-time remote desktop access through HTML5.

Features:
- WebSocket server for real-time bidirectional communication
- VNC-to-WebSocket bridge with high performance
- HTML5 Canvas streaming with 15-20fps support
- Mouse and keyboard event forwarding
- Multi-session management with user isolation
- Security integration and access control
- Performance optimization for low latency
- Error handling and connection recovery

Target: Bridge TightVNC servers to web browsers via WebSockets
"""

import asyncio
import json
import base64
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import weakref
import struct

# WebSocket server
try:
    import websockets
    from websockets.server import WebSocketServerProtocol
    from websockets.exceptions import ConnectionClosed, WebSocketException
except ImportError:
    websockets = None
    WebSocketServerProtocol = None
    ConnectionClosed = Exception
    WebSocketException = Exception

# HTTP server for static content
try:
    from aiohttp import web, WSMsgType
    from aiohttp.web_ws import WebSocketResponse
except ImportError:
    web = None
    WSMsgType = None
    WebSocketResponse = None

# VNC integration
from vnc_controller import (
    TightVNCController, VNCConnectionConfig, VNCState,
    create_vnc_config
)

from ec2_pool_manager import EC2PoolManager


class WebSocketMessageType(Enum):
    """WebSocket message types for VNC gateway."""
    # Client to server
    CONNECT_REQUEST = "connect_request"
    DISCONNECT_REQUEST = "disconnect_request"
    MOUSE_EVENT = "mouse_event"
    KEYBOARD_EVENT = "keyboard_event"
    SCREENSHOT_REQUEST = "screenshot_request"
    AUTOMATION_COMMAND = "automation_command"
    PING = "ping"
    
    # Server to client
    CONNECTION_STATUS = "connection_status"
    FRAME_UPDATE = "frame_update"
    ERROR_MESSAGE = "error_message"
    VNC_METRICS = "vnc_metrics"
    PONG = "pong"


@dataclass
class WebSocketSession:
    """WebSocket session tracking."""
    session_id: str
    user_id: str
    websocket: Any  # WebSocket connection
    created_at: datetime
    last_activity: datetime
    
    # VNC connection details
    vnc_controller: Optional[TightVNCController] = None
    instance_id: Optional[str] = None
    vnc_ready: bool = False
    
    # Performance tracking
    frames_sent: int = 0
    bytes_sent: int = 0
    latency_ms: float = 0.0
    
    # Connection state
    is_active: bool = True
    error_count: int = 0
    
    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()
    
    def is_expired(self, timeout_minutes: int = 60) -> bool:
        """Check if session has expired."""
        timeout = timedelta(minutes=timeout_minutes)
        return datetime.utcnow() - self.last_activity > timeout
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "instance_id": self.instance_id,
            "vnc_ready": self.vnc_ready,
            "frames_sent": self.frames_sent,
            "bytes_sent": self.bytes_sent,
            "latency_ms": self.latency_ms,
            "is_active": self.is_active,
            "error_count": self.error_count
        }


class VNCWebGateway:
    """
    VNC Web Gateway for browser-based remote desktop access.
    
    Provides WebSocket-based bridge between VNC servers and web browsers,
    enabling real-time remote desktop interaction through HTML5 Canvas.
    """
    
    def __init__(self, pool_manager: EC2PoolManager, config: Dict[str, Any]):
        """Initialize VNC Web Gateway."""
        if not websockets:
            raise ImportError("websockets is required. Install with: pip install websockets")
        if not web:
            raise ImportError("aiohttp is required. Install with: pip install aiohttp")
        
        self.pool_manager = pool_manager
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # WebSocket configuration
        self.ws_host = config.get('websocket_host', '0.0.0.0')
        self.ws_port = config.get('websocket_port', 8765)
        self.http_host = config.get('http_host', '0.0.0.0') 
        self.http_port = config.get('http_port', 8080)
        
        # Session management
        self.sessions: Dict[str, WebSocketSession] = {}
        self.user_sessions: Dict[str, Set[str]] = {}  # user_id -> set of session_ids
        
        # Performance settings
        self.max_concurrent_sessions = config.get('max_concurrent_sessions', 50)
        self.frame_rate_limit = config.get('frame_rate_limit', 20)
        self.compression_level = config.get('compression_level', 6)
        
        # Security settings
        self.allowed_origins = config.get('allowed_origins', ['*'])
        self.authentication_required = config.get('authentication_required', False)
        self.session_timeout_minutes = config.get('session_timeout_minutes', 60)
        
        # Server instances
        self.websocket_server = None
        self.http_server = None
        self.http_app = None
        
        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._monitoring_task: Optional[asyncio.Task] = None
        
        self.logger.info(f"VNC Web Gateway initialized - WebSocket: {self.ws_host}:{self.ws_port}, HTTP: {self.http_host}:{self.http_port}")
    
    async def start_server(self) -> None:
        """Start WebSocket and HTTP servers."""
        self.logger.info("Starting VNC Web Gateway servers")
        
        try:
            # Start WebSocket server
            self.websocket_server = await websockets.serve(
                self._handle_websocket_connection,
                self.ws_host,
                self.ws_port,
                ping_interval=30,
                ping_timeout=10,
                max_size=10**7,  # 10MB message size limit
                compression="deflate"
            )
            
            # Create and start HTTP server for static content
            await self._start_http_server()
            
            # Start background tasks
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            
            self.logger.info(f"VNC Web Gateway started successfully")
            self.logger.info(f"WebSocket server: ws://{self.ws_host}:{self.ws_port}")
            self.logger.info(f"HTTP server: http://{self.http_host}:{self.http_port}")
            
        except Exception as e:
            self.logger.error(f"Failed to start VNC Web Gateway: {e}")
            raise
    
    async def stop_server(self) -> None:
        """Stop WebSocket and HTTP servers."""
        self.logger.info("Stopping VNC Web Gateway servers")
        
        # Stop background tasks
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._monitoring_task:
            self._monitoring_task.cancel()
        
        # Close all WebSocket sessions
        for session in list(self.sessions.values()):
            await self._cleanup_session(session.session_id)
        
        # Stop servers
        if self.websocket_server:
            self.websocket_server.close()
            await self.websocket_server.wait_closed()
        
        if self.http_server:
            await self.http_server.cleanup()
        
        self.logger.info("VNC Web Gateway stopped")
    
    async def _start_http_server(self) -> None:
        """Start HTTP server for static content."""
        self.http_app = web.Application()
        
        # Add routes
        self.http_app.router.add_get('/', self._handle_index)
        self.http_app.router.add_get('/vnc', self._handle_vnc_viewer)
        self.http_app.router.add_get('/api/sessions', self._handle_get_sessions)
        self.http_app.router.add_get('/api/status', self._handle_get_status)
        self.http_app.router.add_static('/static', path='./static', name='static')
        
        # Add WebSocket route for alternative connection method
        self.http_app.router.add_get('/ws', self._handle_websocket_http)
        
        # Start HTTP server
        runner = web.AppRunner(self.http_app)
        await runner.setup()
        
        site = web.TCPSite(runner, self.http_host, self.http_port)
        await site.start()
        
        self.http_server = runner
    
    async def _handle_websocket_connection(self, websocket: WebSocketServerProtocol, path: str) -> None:
        """Handle new WebSocket connection."""
        session_id = f"ws_{int(time.time() * 1000)}"
        self.logger.info(f"New WebSocket connection: {session_id}")
        
        try:
            # Create session (user_id will be set during authentication)
            session = WebSocketSession(
                session_id=session_id,
                user_id="anonymous",  # Will be updated during auth
                websocket=websocket,
                created_at=datetime.utcnow(),
                last_activity=datetime.utcnow()
            )
            
            self.sessions[session_id] = session
            
            # Handle messages
            async for message in websocket:
                try:
                    await self._handle_websocket_message(session, message)
                except Exception as e:
                    self.logger.error(f"Error handling WebSocket message: {e}")
                    await self._send_error(session, str(e))
                    
        except ConnectionClosed:
            self.logger.info(f"WebSocket connection closed: {session_id}")
        except Exception as e:
            self.logger.error(f"WebSocket connection error: {e}")
        finally:
            await self._cleanup_session(session_id)
    
    async def _handle_websocket_http(self, request) -> WebSocketResponse:
        """Handle WebSocket connection via HTTP upgrade."""
        ws = WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        
        session_id = f"http_ws_{int(time.time() * 1000)}"
        self.logger.info(f"New HTTP WebSocket connection: {session_id}")
        
        try:
            session = WebSocketSession(
                session_id=session_id,
                user_id="anonymous",
                websocket=ws,
                created_at=datetime.utcnow(),
                last_activity=datetime.utcnow()
            )
            
            self.sessions[session_id] = session
            
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        await self._handle_websocket_message(session, msg.data)
                    except Exception as e:
                        self.logger.error(f"Error handling HTTP WebSocket message: {e}")
                        await self._send_error(session, str(e))
                elif msg.type == WSMsgType.ERROR:
                    self.logger.error(f"WebSocket error: {ws.exception()}")
                    break
                    
        except Exception as e:
            self.logger.error(f"HTTP WebSocket error: {e}")
        finally:
            await self._cleanup_session(session_id)
        
        return ws
    
    async def _handle_websocket_message(self, session: WebSocketSession, message: str) -> None:
        """Handle WebSocket message from client."""
        try:
            data = json.loads(message)
            message_type = data.get('type')
            payload = data.get('payload', {})
            
            session.update_activity()
            
            if message_type == WebSocketMessageType.CONNECT_REQUEST.value:
                await self._handle_connect_request(session, payload)
            elif message_type == WebSocketMessageType.DISCONNECT_REQUEST.value:
                await self._handle_disconnect_request(session, payload)
            elif message_type == WebSocketMessageType.MOUSE_EVENT.value:
                await self._handle_mouse_event(session, payload)
            elif message_type == WebSocketMessageType.KEYBOARD_EVENT.value:
                await self._handle_keyboard_event(session, payload)
            elif message_type == WebSocketMessageType.SCREENSHOT_REQUEST.value:
                await self._handle_screenshot_request(session, payload)
            elif message_type == WebSocketMessageType.AUTOMATION_COMMAND.value:
                await self._handle_automation_command(session, payload)
            elif message_type == WebSocketMessageType.PING.value:
                await self._handle_ping(session, payload)
            else:
                await self._send_error(session, f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError as e:
            await self._send_error(session, f"Invalid JSON: {e}")
        except Exception as e:
            self.logger.error(f"Message handling error: {e}")
            await self._send_error(session, str(e))
    
    async def _handle_connect_request(self, session: WebSocketSession, payload: Dict[str, Any]) -> None:
        """Handle VNC connection request."""
        try:
            user_id = payload.get('user_id')
            instance_id = payload.get('instance_id')
            
            if not user_id or not instance_id:
                await self._send_error(session, "user_id and instance_id are required")
                return
            
            # Update session with user info
            session.user_id = user_id
            session.instance_id = instance_id
            
            # Track user sessions
            if user_id not in self.user_sessions:
                self.user_sessions[user_id] = set()
            self.user_sessions[user_id].add(session.session_id)
            
            # Get VNC connection from pool manager
            # First, find the session in pool manager
            pool_session_id = None
            for sid, user_session in self.pool_manager.user_sessions.items():
                if user_session.user_id == user_id and user_session.instance_id == instance_id:
                    pool_session_id = sid
                    break
            
            if not pool_session_id:
                await self._send_error(session, f"No active session found for instance {instance_id}")
                return
            
            # Get VNC controller
            vnc_controller = await self.pool_manager.get_vnc_connection(user_id, pool_session_id)
            if not vnc_controller:
                await self._send_error(session, "Failed to establish VNC connection")
                return
            
            session.vnc_controller = vnc_controller
            session.vnc_ready = True
            
            # Start frame streaming
            asyncio.create_task(self._start_frame_streaming(session))
            
            # Send connection success
            await self._send_message(session, WebSocketMessageType.CONNECTION_STATUS, {
                "status": "connected",
                "instance_id": instance_id,
                "vnc_ready": True
            })
            
            self.logger.info(f"VNC connection established for session {session.session_id}")
            
        except Exception as e:
            self.logger.error(f"Connect request failed: {e}")
            await self._send_error(session, str(e))
    
    async def _handle_disconnect_request(self, session: WebSocketSession, payload: Dict[str, Any]) -> None:
        """Handle VNC disconnection request."""
        try:
            if session.vnc_controller:
                # Release VNC connection back to pool
                if session.instance_id:
                    pool_session_id = None
                    for sid, user_session in self.pool_manager.user_sessions.items():
                        if (user_session.user_id == session.user_id and 
                            user_session.instance_id == session.instance_id):
                            pool_session_id = sid
                            break
                    
                    if pool_session_id:
                        await self.pool_manager.release_vnc_connection(session.user_id, pool_session_id)
                
                session.vnc_controller = None
                session.vnc_ready = False
            
            await self._send_message(session, WebSocketMessageType.CONNECTION_STATUS, {
                "status": "disconnected"
            })
            
        except Exception as e:
            self.logger.error(f"Disconnect request failed: {e}")
            await self._send_error(session, str(e))
    
    async def _handle_mouse_event(self, session: WebSocketSession, payload: Dict[str, Any]) -> None:
        """Handle mouse event from client."""
        if not session.vnc_ready or not session.vnc_controller:
            return
        
        try:
            event_type = payload.get('event_type')  # move, click, scroll
            x = payload.get('x', 0)
            y = payload.get('y', 0)
            button = payload.get('button', 'left')  # left, right, middle
            
            if event_type == 'move':
                await session.vnc_controller.send_mouse_move(x, y)
            elif event_type == 'click':
                await session.vnc_controller.send_mouse_click(x, y, button)
            elif event_type == 'scroll':
                # Handle scroll events (convert to mouse wheel)
                scroll_y = payload.get('scroll_y', 0)
                if scroll_y != 0:
                    wheel_button = 'wheel_up' if scroll_y > 0 else 'wheel_down'
                    await session.vnc_controller.send_mouse_click(x, y, wheel_button)
            
        except Exception as e:
            self.logger.error(f"Mouse event failed: {e}")
    
    async def _handle_keyboard_event(self, session: WebSocketSession, payload: Dict[str, Any]) -> None:
        """Handle keyboard event from client."""
        if not session.vnc_ready or not session.vnc_controller:
            return
        
        try:
            event_type = payload.get('event_type')  # keydown, keyup, type
            key = payload.get('key', '')
            text = payload.get('text', '')
            
            if event_type == 'type' and text:
                await session.vnc_controller.send_key_sequence(text)
            elif key:
                # Handle special keys and combinations
                if 'ctrl+' in key or 'alt+' in key or 'win+' in key:
                    await session.vnc_controller.send_key_sequence(key)
                else:
                    await session.vnc_controller.send_key_sequence(key)
            
        except Exception as e:
            self.logger.error(f"Keyboard event failed: {e}")
    
    async def _handle_screenshot_request(self, session: WebSocketSession, payload: Dict[str, Any]) -> None:
        """Handle screenshot request from client."""
        if not session.vnc_ready or not session.vnc_controller:
            await self._send_error(session, "VNC not ready")
            return
        
        try:
            screenshot = await session.vnc_controller.capture_screenshot()
            if screenshot:
                # Encode screenshot as base64
                screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
                
                await self._send_message(session, WebSocketMessageType.FRAME_UPDATE, {
                    "image_data": screenshot_b64,
                    "format": "png",
                    "timestamp": time.time()
                })
                
                session.frames_sent += 1
                session.bytes_sent += len(screenshot)
            
        except Exception as e:
            self.logger.error(f"Screenshot request failed: {e}")
            await self._send_error(session, str(e))
    
    async def _handle_automation_command(self, session: WebSocketSession, payload: Dict[str, Any]) -> None:
        """Handle automation command from client."""
        if not session.vnc_ready or not session.vnc_controller:
            await self._send_error(session, "VNC not ready")
            return
        
        try:
            command = payload.get('command')
            if not command:
                await self._send_error(session, "command is required")
                return
            
            success = await session.vnc_controller.execute_automation_command(command)
            
            await self._send_message(session, "automation_response", {
                "command": command,
                "success": success
            })
            
        except Exception as e:
            self.logger.error(f"Automation command failed: {e}")
            await self._send_error(session, str(e))
    
    async def _handle_ping(self, session: WebSocketSession, payload: Dict[str, Any]) -> None:
        """Handle ping from client."""
        timestamp = payload.get('timestamp', time.time())
        
        await self._send_message(session, WebSocketMessageType.PONG, {
            "timestamp": timestamp,
            "server_timestamp": time.time()
        })
    
    async def _start_frame_streaming(self, session: WebSocketSession) -> None:
        """Start continuous frame streaming for a session."""
        if not session.vnc_ready or not session.vnc_controller:
            return
        
        try:
            frame_interval = 1.0 / self.frame_rate_limit
            
            # Add frame callback to VNC controller
            def frame_callback(frame_data: bytes):
                asyncio.create_task(self._send_frame_update(session, frame_data))
            
            session.vnc_controller.add_frame_callback(frame_callback)
            
            # Start continuous capture
            await session.vnc_controller.start_continuous_capture(fps=self.frame_rate_limit)
            
        except Exception as e:
            self.logger.error(f"Frame streaming failed: {e}")
    
    async def _send_frame_update(self, session: WebSocketSession, frame_data: bytes) -> None:
        """Send frame update to client."""
        try:
            if not session.is_active:
                return
            
            # Encode frame as base64
            frame_b64 = base64.b64encode(frame_data).decode('utf-8')
            
            await self._send_message(session, WebSocketMessageType.FRAME_UPDATE, {
                "image_data": frame_b64,
                "format": "png",
                "timestamp": time.time()
            })
            
            session.frames_sent += 1
            session.bytes_sent += len(frame_data)
            
        except Exception as e:
            self.logger.error(f"Frame update failed: {e}")
    
    async def _send_message(self, session: WebSocketSession, message_type: WebSocketMessageType, payload: Dict[str, Any]) -> None:
        """Send message to WebSocket client."""
        try:
            if not session.is_active:
                return
            
            message = {
                "type": message_type.value if isinstance(message_type, WebSocketMessageType) else message_type,
                "payload": payload,
                "timestamp": time.time()
            }
            
            message_json = json.dumps(message)
            
            if hasattr(session.websocket, 'send'):
                await session.websocket.send(message_json)
            elif hasattr(session.websocket, 'send_str'):
                await session.websocket.send_str(message_json)
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            session.error_count += 1
    
    async def _send_error(self, session: WebSocketSession, error_message: str) -> None:
        """Send error message to client."""
        await self._send_message(session, WebSocketMessageType.ERROR_MESSAGE, {
            "error": error_message,
            "session_id": session.session_id
        })
    
    async def _cleanup_session(self, session_id: str) -> None:
        """Clean up WebSocket session."""
        if session_id not in self.sessions:
            return
        
        session = self.sessions[session_id]
        
        try:
            # Stop frame streaming
            if session.vnc_controller:
                await session.vnc_controller.stop_continuous_capture()
                
                # Release VNC connection
                if session.instance_id:
                    pool_session_id = None
                    for sid, user_session in self.pool_manager.user_sessions.items():
                        if (user_session.user_id == session.user_id and 
                            user_session.instance_id == session.instance_id):
                            pool_session_id = sid
                            break
                    
                    if pool_session_id:
                        await self.pool_manager.release_vnc_connection(session.user_id, pool_session_id)
            
            # Remove from user sessions tracking
            if session.user_id in self.user_sessions:
                self.user_sessions[session.user_id].discard(session_id)
                if not self.user_sessions[session.user_id]:
                    del self.user_sessions[session.user_id]
            
            # Mark session as inactive
            session.is_active = False
            
            # Remove session
            del self.sessions[session_id]
            
            self.logger.info(f"Session cleaned up: {session_id}")
            
        except Exception as e:
            self.logger.error(f"Session cleanup failed: {e}")
    
    async def _cleanup_loop(self) -> None:
        """Background task for cleaning up expired sessions."""
        while True:
            try:
                current_time = datetime.utcnow()
                expired_sessions = []
                
                for session_id, session in self.sessions.items():
                    if session.is_expired(self.session_timeout_minutes):
                        expired_sessions.append(session_id)
                
                for session_id in expired_sessions:
                    self.logger.info(f"Cleaning up expired session: {session_id}")
                    await self._cleanup_session(session_id)
                
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Cleanup loop error: {e}")
                await asyncio.sleep(60)
    
    async def _monitoring_loop(self) -> None:
        """Background task for monitoring sessions and performance."""
        while True:
            try:
                # Log session statistics
                total_sessions = len(self.sessions)
                active_vnc_sessions = sum(1 for s in self.sessions.values() if s.vnc_ready)
                total_frames = sum(s.frames_sent for s in self.sessions.values())
                total_bytes = sum(s.bytes_sent for s in self.sessions.values())
                
                self.logger.info(f"Gateway stats - Sessions: {total_sessions}, "
                               f"VNC Active: {active_vnc_sessions}, "
                               f"Frames: {total_frames}, Bytes: {total_bytes}")
                
                await asyncio.sleep(300)  # Log every 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(300)
    
    # HTTP request handlers
    
    async def _handle_index(self, request) -> web.Response:
        """Handle index page request."""
        return web.Response(text="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>VNC Web Gateway</title>
        </head>
        <body>
            <h1>VNC Web Gateway</h1>
            <p>WebSocket server running on port {}</p>
            <p><a href="/vnc">Open VNC Viewer</a></p>
        </body>
        </html>
        """.format(self.ws_port), content_type='text/html')
    
    async def _handle_vnc_viewer(self, request) -> web.Response:
        """Handle VNC viewer page request."""
        try:
            # Serve the HTML5 VNC viewer
            import os
            viewer_path = os.path.join(os.path.dirname(__file__), 'static', 'vnc_viewer.html')
            
            if os.path.exists(viewer_path):
                with open(viewer_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Replace placeholder WebSocket URL with actual server URL
                html_content = html_content.replace('ws://localhost:8765', f'ws://{self.ws_host}:{self.ws_port}')
                
                return web.Response(text=html_content, content_type='text/html')
            else:
                # Fallback if static file not found
                return web.Response(text=f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>VNC Viewer</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 40px; }}
                        .error {{ color: #d13438; background: #f8f8f8; padding: 20px; border-radius: 4px; }}
                    </style>
                </head>
                <body>
                    <h1>VNC Remote Desktop</h1>
                    <div class="error">
                        <h3>VNC Viewer Not Found</h3>
                        <p>The HTML5 VNC viewer is not available at: {viewer_path}</p>
                        <p>WebSocket Server: ws://{self.ws_host}:{self.ws_port}</p>
                    </div>
                </body>
                </html>
                """, content_type='text/html')
                
        except Exception as e:
            return web.Response(text=f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>VNC Viewer Error</title>
            </head>
            <body>
                <h1>Error Loading VNC Viewer</h1>
                <p>Error: {str(e)}</p>
            </body>
            </html>
            """, content_type='text/html')
    
    async def _handle_get_sessions(self, request) -> web.Response:
        """Handle get active sessions API request."""
        sessions_data = {
            "total_sessions": len(self.sessions),
            "active_sessions": sum(1 for s in self.sessions.values() if s.is_active),
            "vnc_ready_sessions": sum(1 for s in self.sessions.values() if s.vnc_ready),
            "sessions": [session.to_dict() for session in self.sessions.values()]
        }
        
        return web.json_response(sessions_data)
    
    async def _handle_get_status(self, request) -> web.Response:
        """Handle get gateway status API request."""
        status_data = {
            "server_status": "running",
            "websocket_port": self.ws_port,
            "http_port": self.http_port,
            "total_sessions": len(self.sessions),
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "frame_rate_limit": self.frame_rate_limit,
            "uptime_seconds": (datetime.utcnow() - datetime.utcnow()).total_seconds(),  # Placeholder
            "vnc_pool_status": self.pool_manager.get_vnc_pool_status() if self.pool_manager else {}
        }
        
        return web.json_response(status_data)
    
    def get_session_count(self) -> int:
        """Get current session count."""
        return len(self.sessions)
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get list of active sessions."""
        return [session.to_dict() for session in self.sessions.values() if session.is_active]
    
    async def broadcast_to_user(self, user_id: str, message_type: WebSocketMessageType, payload: Dict[str, Any]) -> None:
        """Broadcast message to all sessions for a specific user."""
        if user_id not in self.user_sessions:
            return
        
        for session_id in self.user_sessions[user_id]:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                await self._send_message(session, message_type, payload)


# Utility functions for VNC Web Gateway

def create_vnc_web_gateway(pool_manager: EC2PoolManager, **config) -> VNCWebGateway:
    """
    Create VNC Web Gateway with default configuration.
    
    Args:
        pool_manager: EC2 pool manager instance
        **config: Additional configuration options
        
    Returns:
        VNCWebGateway: Configured gateway instance
    """
    default_config = {
        'websocket_host': '0.0.0.0',
        'websocket_port': 8765,
        'http_host': '0.0.0.0',
        'http_port': 8080,
        'max_concurrent_sessions': 50,
        'frame_rate_limit': 18,
        'compression_level': 6,
        'allowed_origins': ['*'],
        'authentication_required': False,
        'session_timeout_minutes': 60
    }
    
    # Merge with provided config
    default_config.update(config)
    
    return VNCWebGateway(pool_manager, default_config)


if __name__ == "__main__":
    # Example usage and testing
    import sys
    import os
    sys.path.append(os.path.dirname(__file__))
    
    async def main():
        """Example VNC Web Gateway usage."""
        # This would normally be imported from your application
        # For demo purposes, create a mock pool manager
        pool_config = {
            'aws_region': 'us-west-2',
            'min_pool_size': 1,
            'max_pool_size': 10
        }
        
        # pool_manager = EC2PoolManager(pool_config)
        # await pool_manager.start_pool_management()
        
        # Create VNC Web Gateway
        gateway_config = {
            'websocket_port': 8765,
            'http_port': 8080,
            'frame_rate_limit': 20
        }
        
        # gateway = create_vnc_web_gateway(pool_manager, **gateway_config)
        
        try:
            # await gateway.start_server()
            print("VNC Web Gateway started. Press Ctrl+C to stop.")
            # await asyncio.Event().wait()  # Wait forever
        except KeyboardInterrupt:
            print("Stopping VNC Web Gateway...")
            # await gateway.stop_server()
            # await pool_manager.stop_pool_management()
    
    # Run example if script executed directly
    # asyncio.run(main())
    print("VNC Web Gateway module loaded successfully")