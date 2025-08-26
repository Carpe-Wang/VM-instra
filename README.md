# VM Service SDK

基于E2B Desktop封装的VM和Sandbox服务SDK，为其他微服务提供统一的VM操作接口。

## 项目结构

```
VM-instra/
├── LICENSE                    # 开源许可证
├── README.md                  # 项目说明
└── vm_service_sdk/            # 核心SDK包
    ├── __init__.py           # 包初始化
    ├── client.py             # 主要客户端实现
    ├── models.py             # 数据模型
    ├── exceptions.py         # 异常定义
    ├── examples.py           # 使用示例
    └── README.md             # SDK详细文档
```

## 快速开始

```python
import asyncio
from vm_service_sdk import VMServiceClient, SandboxConfig

async def main():
    async with VMServiceClient(api_key="your_e2b_key") as client:
        # 为用户创建沙箱
        sandbox_info = await client.create_sandbox(
            user_id="user123",
            config=SandboxConfig(template="desktop")
        )
        
        # 桌面操作
        await client.click(sandbox_info.sandbox_id, 100, 200)
        await client.type_text(sandbox_info.sandbox_id, "Hello!")
        
        # 截图
        screenshot = await client.screenshot(sandbox_info.sandbox_id)

if __name__ == "__main__":
    asyncio.run(main())
```

## 安装

```bash
pip install e2b-desktop
export E2B_API_KEY="your_api_key"
```

详细文档请查看 [vm_service_sdk/README.md](vm_service_sdk/README.md)