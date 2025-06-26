# Modular admin routes - imports from individual route modules
from .routes.apps import apps_router
from .routes.auth import auth_router
from .routes.dashboard import dashboard_router
from .routes.llm import llm_router
from .routes.questions import questions_router
from .routes.users import users_router

# Re-export all routers for backward compatibility
__all__ = [
    "auth_router",
    "dashboard_router",
    "users_router",
    "apps_router",
    "questions_router",
    "llm_router",
]
