# Admin routes package
from .auth import auth_router
from .dashboard import dashboard_router
from .users import users_router
from .apps import apps_router
from .questions import questions_router
from .llm import llm_router

__all__ = [
    "auth_router",
    "dashboard_router", 
    "users_router",
    "apps_router",
    "questions_router",
    "llm_router"
]