"""本地可视化工作台（Web UI）。

对外接口：
- serve_forever(project_root, host, port, use_token)：阻塞式启动服务
- create_server(project_root, host, port, use_token)：创建服务对象（测试用）
"""
from .server import STATIC_DIR, WorkbenchServer, create_server, serve_forever

__all__ = ["STATIC_DIR", "WorkbenchServer", "create_server", "serve_forever"]
