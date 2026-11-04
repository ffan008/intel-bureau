"""FastAPI 应用：REST + SSE，托管 web/dist。"""

from bureau.api.app import create_app

__all__ = ["create_app"]
