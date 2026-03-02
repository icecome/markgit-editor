# MarkGit Editor - 本地开发环境启动脚本
# 适用于 Windows 本地开发测试

import os
import sys
import uvicorn
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

if __name__ == "__main__":
    port = int(os.getenv('PORT', '13131'))
    
    print(f"启动 MarkGit Editor 开发服务器...")
    print(f"监听地址：http://127.0.0.1:{port}")
    print(f"生产环境模式：{os.getenv('PRODUCTION', 'false')}")
    
    # 开发环境配置
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=port,
        reload=True,  # 开发环境启用热重载
        log_level="info"
    )
