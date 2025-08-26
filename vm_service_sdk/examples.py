"""
VM服务SDK使用示例
展示如何使用VMServiceClient为其他微服务提供VM和Sandbox操作
"""

import asyncio
import os
from typing import Optional

from vm_service_sdk import VMServiceClient, SandboxConfig, StreamConfig
from vm_service_sdk.exceptions import VMServiceError


async def basic_usage_example():
    """基础使用示例"""
    print("=== VM Service SDK 基础使用示例 ===")
    
    # 初始化客户端
    async with VMServiceClient(
        api_key=os.environ.get("E2B_API_KEY"),
        default_template="desktop",
        max_concurrent_sandboxes=5
    ) as client:
        
        try:
            # 1. 为用户创建沙箱
            print("创建用户沙箱...")
            sandbox_info = await client.create_sandbox(
                user_id="demo_user_123",
                config=SandboxConfig(
                    template="desktop",
                    cpu_count=2,
                    memory_mb=2048,
                    timeout_seconds=1800  # 30分钟
                )
            )
            print(f"沙箱创建成功: {sandbox_info.sandbox_id}")
            
            # 2. 基础桌面操作
            print("执行桌面操作...")
            
            # 截图
            screenshot_data = await client.screenshot(sandbox_info.sandbox_id)
            print(f"截图完成，大小: {len(screenshot_data)} bytes")
            
            # 鼠标点击
            await client.click(sandbox_info.sandbox_id, 400, 300)
            print("鼠标点击完成")
            
            # 输入文本
            await client.type_text(sandbox_info.sandbox_id, "Hello from VM Service SDK!")
            print("文本输入完成")
            
            # 按键操作
            await client.press_key_combination(sandbox_info.sandbox_id, ["ctrl", "a"])
            await client.press_key_combination(sandbox_info.sandbox_id, ["ctrl", "c"])
            print("复制操作完成")
            
            # 3. 应用程序管理
            print("管理应用程序...")
            
            # 启动浏览器
            await client.launch_application(sandbox_info.sandbox_id, "firefox")
            print("Firefox启动完成")
            
            # 等待应用启动
            await asyncio.sleep(3)
            
            # 获取窗口信息
            current_window = await client.get_current_window_id(sandbox_info.sandbox_id)
            print(f"当前窗口ID: {current_window}")
            
            # 4. 文件操作
            print("执行文件操作...")
            
            # 写文件
            test_content = "This is a test file created by VM Service SDK"
            await client.write_file(
                sandbox_info.sandbox_id,
                "/home/user/test.txt",
                test_content
            )
            print("文件写入完成")
            
            # 读文件
            read_content = await client.read_file(
                sandbox_info.sandbox_id,
                "/home/user/test.txt"
            )
            print(f"文件读取完成: {read_content[:50]}...")
            
            # 5. 命令执行
            print("执行系统命令...")
            
            result = await client.run_command(
                sandbox_info.sandbox_id,
                "ls -la /home/user"
            )
            print(f"命令执行结果 (exit_code: {result.exit_code}):")
            print(result.stdout[:200] + "..." if len(result.stdout) > 200 else result.stdout)
            
            # 6. 启动流媒体
            print("启动VNC流媒体...")
            
            stream_url, auth_key = await client.start_stream(
                sandbox_info.sandbox_id,
                config=StreamConfig(require_auth=True)
            )
            print(f"流媒体URL: {stream_url}")
            print(f"认证密钥: {auth_key[:20]}...")
            
            # 7. 查看统计信息
            stats = await client.get_stats()
            print(f"服务统计: {stats}")
            
        except VMServiceError as e:
            print(f"VM服务错误: {e.message}")
            print(f"错误详情: {e.to_dict()}")
        
        except Exception as e:
            print(f"未预期错误: {str(e)}")


async def multi_user_example():
    """多用户隔离示例"""
    print("\n=== 多用户隔离示例 ===")
    
    async with VMServiceClient(
        api_key=os.environ.get("E2B_API_KEY"),
        max_concurrent_sandboxes=10
    ) as client:
        
        users = ["user_alice", "user_bob", "user_charlie"]
        sandbox_infos = []
        
        try:
            # 为每个用户创建沙箱
            for user_id in users:
                print(f"为用户 {user_id} 创建沙箱...")
                sandbox_info = await client.create_sandbox(
                    user_id=user_id,
                    config=SandboxConfig(template="desktop")
                )
                sandbox_infos.append(sandbox_info)
                print(f"用户 {user_id} 的沙箱: {sandbox_info.sandbox_id}")
            
            # 每个用户执行不同的操作
            tasks = []
            for i, sandbox_info in enumerate(sandbox_infos):
                task = asyncio.create_task(
                    user_specific_operations(client, sandbox_info, f"User_{i+1}")
                )
                tasks.append(task)
            
            # 并发执行所有用户操作
            await asyncio.gather(*tasks)
            
            # 查看每个用户的沙箱
            for user_id in users:
                user_sandboxes = await client.list_user_sandboxes(user_id)
                print(f"用户 {user_id} 的沙箱数量: {len(user_sandboxes)}")
            
        except Exception as e:
            print(f"多用户示例错误: {str(e)}")


async def user_specific_operations(client: VMServiceClient, sandbox_info, user_label: str):
    """用户专属操作"""
    try:
        print(f"[{user_label}] 开始执行专属操作...")
        
        # 每个用户创建不同的文件
        await client.write_file(
            sandbox_info.sandbox_id,
            f"/home/user/{user_label.lower()}_file.txt",
            f"This is {user_label}'s private file"
        )
        
        # 执行不同的命令
        result = await client.run_command(
            sandbox_info.sandbox_id,
            f"echo 'Hello from {user_label}' > /home/user/greeting.txt"
        )
        
        # 截图（每个用户的桌面是隔离的）
        screenshot = await client.screenshot(sandbox_info.sandbox_id)
        
        print(f"[{user_label}] 操作完成，截图大小: {len(screenshot)} bytes")
        
    except Exception as e:
        print(f"[{user_label}] 操作失败: {str(e)}")


async def web_service_integration_example():
    """Web服务集成示例 - FastAPI风格"""
    print("\n=== Web服务集成示例 ===")
    
    # 模拟FastAPI endpoint的处理逻辑
    class VMWebService:
        def __init__(self):
            self.client = None
        
        async def startup(self):
            """服务启动初始化"""
            self.client = VMServiceClient(
                api_key=os.environ.get("E2B_API_KEY"),
                default_template="desktop",
                max_concurrent_sandboxes=20
            )
            print("VM Web Service 启动完成")
        
        async def shutdown(self):
            """服务关闭清理"""
            if self.client:
                await self.client.cleanup_all_sandboxes()
                print("VM Web Service 关闭完成")
        
        async def create_user_session(self, user_id: str, session_type: str = "desktop"):
            """创建用户会话 - 对应 POST /api/sessions"""
            try:
                config = SandboxConfig(
                    template=session_type,
                    cpu_count=2 if session_type == "desktop" else 1,
                    memory_mb=2048 if session_type == "desktop" else 1024
                )
                
                sandbox_info = await self.client.create_sandbox(
                    user_id=user_id,
                    config=config
                )
                
                return {
                    "success": True,
                    "session_id": sandbox_info.session_id,
                    "sandbox_id": sandbox_info.sandbox_id,
                    "created_at": sandbox_info.created_at.isoformat()
                }
                
            except VMServiceError as e:
                return {
                    "success": False,
                    "error": e.to_dict()
                }
        
        async def execute_user_action(self, sandbox_id: str, action_type: str, params: dict):
            """执行用户操作 - 对应 POST /api/sessions/{session_id}/actions"""
            try:
                if action_type == "click":
                    await self.client.click(
                        sandbox_id, 
                        params["x"], 
                        params["y"],
                        params.get("button", "left")
                    )
                    
                elif action_type == "type":
                    await self.client.type_text(
                        sandbox_id,
                        params["text"]
                    )
                    
                elif action_type == "screenshot":
                    screenshot_data = await self.client.screenshot(sandbox_id)
                    return {
                        "success": True,
                        "data": screenshot_data.hex(),  # 转为hex字符串传输
                        "size": len(screenshot_data)
                    }
                    
                elif action_type == "launch_app":
                    await self.client.launch_application(
                        sandbox_id,
                        params["app_name"]
                    )
                    
                elif action_type == "run_command":
                    result = await self.client.run_command(
                        sandbox_id,
                        params["command"]
                    )
                    return {
                        "success": True,
                        "result": {
                            "exit_code": result.exit_code,
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                            "execution_time": result.execution_time
                        }
                    }
                
                return {"success": True}
                
            except VMServiceError as e:
                return {
                    "success": False,
                    "error": e.to_dict()
                }
        
        async def start_user_stream(self, sandbox_id: str):
            """启动用户流媒体 - 对应 POST /api/sessions/{session_id}/stream"""
            try:
                stream_url, auth_key = await self.client.start_stream(sandbox_id)
                return {
                    "success": True,
                    "stream_url": stream_url,
                    "auth_key": auth_key
                }
            except VMServiceError as e:
                return {
                    "success": False,
                    "error": e.to_dict()
                }
    
    # 模拟Web服务运行
    service = VMWebService()
    await service.startup()
    
    try:
        # 模拟API调用
        print("模拟用户会话创建...")
        session_response = await service.create_user_session("web_user_123", "desktop")
        print(f"会话创建响应: {session_response}")
        
        if session_response["success"]:
            sandbox_id = session_response["sandbox_id"]
            
            # 模拟用户操作
            print("模拟用户点击...")
            click_response = await service.execute_user_action(
                sandbox_id, 
                "click", 
                {"x": 200, "y": 300, "button": "left"}
            )
            print(f"点击响应: {click_response}")
            
            # 模拟截图
            print("模拟截图...")
            screenshot_response = await service.execute_user_action(
                sandbox_id,
                "screenshot",
                {}
            )
            print(f"截图响应: 成功={screenshot_response['success']}, 大小={screenshot_response.get('size', 0)}")
            
            # 模拟启动流媒体
            print("模拟启动流媒体...")
            stream_response = await service.start_user_stream(sandbox_id)
            print(f"流媒体响应: {stream_response}")
    
    finally:
        await service.shutdown()


async def error_handling_example():
    """错误处理示例"""
    print("\n=== 错误处理示例 ===")
    
    async with VMServiceClient(
        api_key="invalid_key",  # 故意使用无效密钥
        max_concurrent_sandboxes=1  # 设置低配额用于测试
    ) as client:
        
        try:
            # 尝试创建沙箱（会因为无效密钥失败）
            await client.create_sandbox("test_user")
        except VMServiceError as e:
            print(f"预期的认证错误: {e.error_code} - {e.message}")
    
    # 使用有效密钥但测试配额限制
    if os.environ.get("E2B_API_KEY"):
        async with VMServiceClient(
            api_key=os.environ.get("E2B_API_KEY"),
            max_concurrent_sandboxes=1
        ) as client:
            
            try:
                # 创建第一个沙箱（应该成功）
                sandbox1 = await client.create_sandbox("quota_test_user")
                print(f"第一个沙箱创建成功: {sandbox1.sandbox_id}")
                
                # 尝试创建第二个沙箱（应该失败 - 配额限制）
                sandbox2 = await client.create_sandbox("quota_test_user")
                print(f"第二个沙箱创建成功: {sandbox2.sandbox_id}")
                
            except VMServiceError as e:
                print(f"预期的配额错误: {e.error_code} - {e.message}")
                if hasattr(e, 'current_usage') and hasattr(e, 'limit'):
                    print(f"当前使用: {e.current_usage}, 限制: {e.limit}")


async def main():
    """主函数 - 运行所有示例"""
    print("VM Service SDK 示例程序启动")
    print("=" * 50)
    
    # 检查环境变量
    if not os.environ.get("E2B_API_KEY"):
        print("警告: 未设置 E2B_API_KEY 环境变量")
        print("部分示例可能无法正常运行")
        print()
    
    try:
        # 运行所有示例
        await basic_usage_example()
        await multi_user_example()
        await web_service_integration_example()
        await error_handling_example()
        
    except Exception as e:
        print(f"示例程序异常: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 50)
    print("VM Service SDK 示例程序完成")


if __name__ == "__main__":
    asyncio.run(main())