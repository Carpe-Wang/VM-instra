#!/usr/bin/env python3
"""
AI Agent Example - Using VMAgentAdapter for Windows VM Control

This example demonstrates how AI agents can use the standardized VMAgentAdapter
interface to control Windows VMs in a simple, intuitive way.

Usage:
    python ai_agent_example.py
"""

import asyncio
import logging
import sys
import os
from typing import Optional

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def simple_ai_agent_demo():
    """
    Simple AI agent demonstration using VMAgentAdapter.
    
    This shows how an AI agent can:
    1. Create a Windows VM
    2. Take screenshots
    3. Perform mouse/keyboard operations
    4. Monitor VM state
    5. Handle errors gracefully
    6. Clean up resources
    """
    
    print("🤖 Simple AI Agent Demo - Windows VM Control")
    print("=" * 60)
    
    # Import the AI-friendly interface
    try:
        from vm_agent_adapter import VMAgentAdapter, ActionBuilder, ActionType
        from windows_infrastructure_sdk import create_ai_friendly_vm
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all required modules are available.")
        return False
    
    vm_adapter: Optional[VMAgentAdapter] = None
    
    try:
        # Step 1: Create VM session for AI agent
        print("\n🚀 Step 1: Creating Windows VM for AI agent...")
        vm_adapter = await create_ai_friendly_vm("ai_agent_demo")
        
        if not vm_adapter:
            print("❌ Failed to create VM session")
            return False
        
        print("✅ VM session created successfully!")
        
        # Step 2: Get VM state
        print("\n📊 Step 2: Checking VM state...")
        state = await vm_adapter.get_vm_state()
        print(f"   VM State: {state.state.value}")
        print(f"   Connection Quality: {state.connection_quality}")
        
        if state.performance_metrics:
            print(f"   Performance Metrics: {state.performance_metrics}")
        
        # Step 3: Take initial screenshot
        print("\n📸 Step 3: Taking screenshot...")
        screenshot_action = ActionBuilder.screenshot()
        screenshot_result = await vm_adapter.execute_action(screenshot_action)
        
        if screenshot_result.success:
            print(f"✅ Screenshot captured ({len(screenshot_result.return_data)} bytes)")
            print(f"   Execution time: {screenshot_result.execution_time_ms}ms")
        else:
            print(f"❌ Screenshot failed: {screenshot_result.error_message}")
        
        # Step 4: Demonstrate mouse operations
        print("\n🖱️  Step 4: Demonstrating mouse operations...")
        
        # Click on desktop center
        click_action = ActionBuilder.click(500, 400)
        click_result = await vm_adapter.execute_action(click_action)
        
        if click_result.success:
            print("✅ Mouse click executed successfully")
        else:
            print(f"❌ Mouse click failed: {click_result.error_message}")
        
        # Wait a moment
        await asyncio.sleep(1)
        
        # Double-click to test
        double_click_action = ActionBuilder.double_click(300, 300)
        double_click_result = await vm_adapter.execute_action(double_click_action)
        
        if double_click_result.success:
            print("✅ Mouse double-click executed successfully")
        else:
            print(f"❌ Mouse double-click failed: {double_click_result.error_message}")
        
        # Step 5: Demonstrate keyboard operations
        print("\n⌨️  Step 5: Demonstrating keyboard operations...")
        
        # Open Run dialog with Win+R
        hotkey_action = ActionBuilder.hotkey("win", "r")
        hotkey_result = await vm_adapter.execute_action(hotkey_action)
        
        if hotkey_result.success:
            print("✅ Hotkey (Win+R) executed successfully")
            
            # Wait for dialog to open
            await asyncio.sleep(2)
            
            # Type notepad command
            type_action = ActionBuilder.type_text("notepad")
            type_result = await vm_adapter.execute_action(type_action)
            
            if type_result.success:
                print("✅ Text typing executed successfully")
                
                # Press Enter to execute
                enter_action = ActionBuilder.hotkey("enter")
                enter_result = await vm_adapter.execute_action(enter_action)
                
                if enter_result.success:
                    print("✅ Enter key executed successfully")
                    
                    # Wait for notepad to open
                    await asyncio.sleep(3)
                    
                    # Type some content in notepad
                    content_action = ActionBuilder.type_text("Hello from AI Agent!\nThis is automated text entry.")
                    content_result = await vm_adapter.execute_action(content_action)
                    
                    if content_result.success:
                        print("✅ Content typing executed successfully")
                    else:
                        print(f"❌ Content typing failed: {content_result.error_message}")
                        
                else:
                    print(f"❌ Enter key failed: {enter_result.error_message}")
            else:
                print(f"❌ Text typing failed: {type_result.error_message}")
        else:
            print(f"❌ Hotkey failed: {hotkey_result.error_message}")
        
        # Step 6: Monitor performance
        print("\n📈 Step 6: Monitoring performance...")
        final_state = await vm_adapter.get_vm_state()
        
        print(f"   Final VM State: {final_state.state.value}")
        print(f"   Connection Quality: {final_state.connection_quality}")
        
        if final_state.performance_metrics:
            metrics = final_state.performance_metrics
            print(f"   Average Response Time: {metrics.get('average_response_time_ms', 'N/A')}ms")
            print(f"   Success Rate: {metrics.get('success_rate_percent', 'N/A')}%")
            print(f"   Total Actions: {metrics.get('total_actions_executed', 'N/A')}")
        
        # Step 7: Final screenshot
        print("\n📸 Step 7: Taking final screenshot...")
        final_screenshot = await vm_adapter.execute_action(ActionBuilder.screenshot())
        
        if final_screenshot.success:
            print(f"✅ Final screenshot captured ({len(final_screenshot.return_data)} bytes)")
        
        print("\n🎉 AI Agent demo completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Demo failed with error: {e}")
        print(f"❌ Demo failed: {e}")
        return False
        
    finally:
        # Step 8: Cleanup (always do this)
        if vm_adapter:
            print("\n🧹 Step 8: Cleaning up VM session...")
            cleanup_success = await vm_adapter.cleanup_session()
            
            if cleanup_success:
                print("✅ VM session cleaned up successfully")
            else:
                print("⚠️  VM cleanup had issues (check logs)")


async def advanced_ai_agent_demo():
    """
    Advanced AI agent demonstration with error handling and state monitoring.
    
    This shows more sophisticated AI agent patterns:
    - State change monitoring
    - Action callbacks
    - Error recovery
    - Condition waiting
    """
    
    print("\n🧠 Advanced AI Agent Demo - Sophisticated Patterns")
    print("=" * 60)
    
    try:
        from vm_agent_adapter import VMAgentAdapter, ActionBuilder, VMState
        from windows_infrastructure_sdk import create_ai_friendly_vm
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    
    vm_adapter = None
    
    try:
        # Create VM with monitoring
        print("\n🚀 Creating monitored VM session...")
        vm_adapter = await create_ai_friendly_vm("advanced_ai_agent")
        
        if not vm_adapter:
            print("❌ Failed to create VM session")
            return False
        
        # Add state change callback
        def on_state_change(old_state: VMState, new_state: VMState):
            print(f"   🔄 State changed: {old_state.value} → {new_state.value}")
        
        vm_adapter.add_state_change_callback(on_state_change)
        
        # Add action callback for monitoring
        def on_action_completed(action, result):
            status = "✅" if result.success else "❌"
            print(f"   {status} Action {action.action_type.value}: {result.execution_time_ms}ms")
        
        vm_adapter.add_action_callback(on_action_completed)
        
        # Demonstrate smart waiting
        print("\n⏳ Demonstrating condition waiting...")
        
        # Define a condition checker
        screenshot_count = 0
        
        def screenshot_condition():
            nonlocal screenshot_count
            screenshot_count += 1
            print(f"   Checking condition (attempt {screenshot_count})...")
            return screenshot_count >= 3  # Simple condition: after 3 attempts
        
        # Wait for condition with timeout
        condition_met = await vm_adapter.wait_for_condition(
            screenshot_condition,
            timeout_seconds=10,
            check_interval=2.0
        )
        
        if condition_met:
            print("✅ Condition met successfully")
        else:
            print("❌ Condition timed out")
        
        # Demonstrate error handling and recovery
        print("\n🛠️  Demonstrating error handling...")
        
        # Try an operation that might fail (invalid coordinates)
        invalid_click = ActionBuilder.click(-1, -1)  # Invalid coordinates
        result = await vm_adapter.execute_action(invalid_click)
        
        if not result.success:
            print(f"✅ Error handling working: {result.error_message}")
            
            # Try recovery action
            recovery_click = ActionBuilder.click(100, 100)
            recovery_result = await vm_adapter.execute_action(recovery_click)
            
            if recovery_result.success:
                print("✅ Recovery action successful")
        
        print("\n🎉 Advanced demo completed!")
        return True
        
    except Exception as e:
        print(f"❌ Advanced demo failed: {e}")
        return False
        
    finally:
        if vm_adapter:
            print("\n🧹 Cleaning up advanced demo...")
            await vm_adapter.cleanup_session()


async def show_code_examples():
    """Display code examples for AI agent developers."""
    
    print("\n💡 AI Agent Code Examples")
    print("=" * 60)
    
    try:
        from windows_infrastructure_sdk import get_ai_action_examples
        examples = get_ai_action_examples()
        
        for example_name, code in examples.items():
            print(f"\n📝 {example_name.replace('_', ' ').title()}:")
            print("-" * 30)
            print(code.strip())
            
    except ImportError:
        print("❌ Code examples not available (missing windows_infrastructure_sdk)")


async def main():
    """Main demonstration function."""
    
    print("🤖 AI Agent VM Control Demonstration")
    print("=" * 60)
    print("This demo shows how AI agents can control Windows VMs")
    print("using the standardized VMAgentAdapter interface.")
    print()
    
    # Check if we're in demo mode (no real AWS)
    if os.getenv('TESTING') or '--demo' in sys.argv:
        print("🎮 Running in demo mode (no real VMs will be created)")
        print()
        
        # Just show code examples in demo mode
        await show_code_examples()
        return
    
    # Ask user what demo to run
    print("Choose a demo:")
    print("1. Simple AI Agent Demo (basic operations)")
    print("2. Advanced AI Agent Demo (sophisticated patterns)")
    print("3. Show Code Examples")
    print("4. All of the above")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    if choice in ['1', '4']:
        success = await simple_ai_agent_demo()
        if not success:
            print("❌ Simple demo failed")
    
    if choice in ['2', '4']:
        success = await advanced_ai_agent_demo()
        if not success:
            print("❌ Advanced demo failed")
    
    if choice in ['3', '4']:
        await show_code_examples()
    
    if choice not in ['1', '2', '3', '4']:
        print("Invalid choice")
        return
    
    print("\n🎯 Demo Summary:")
    print("The VMAgentAdapter provides a clean, standardized interface")
    print("that allows AI agents to control Windows VMs without needing")
    print("to understand VNC protocols or EC2 management details.")
    print()
    print("Key benefits for AI agents:")
    print("✅ Simple action-based interface")
    print("✅ Standardized error handling")
    print("✅ Performance monitoring")
    print("✅ State management")
    print("✅ Event callbacks")
    print("✅ Automatic cleanup")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo error: {e}")
        sys.exit(1)