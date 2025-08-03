# Admin routes package
from .activity import activity_router
from .apps import apps_router
from .auth import auth_router
from .dashboard import dashboard_router
from .llm import llm_router
from .referrals import referrals_router
from .system import system_router
from .users import users_router

__all__ = [
    "activity_router",
    "auth_router",
    "dashboard_router",
    "users_router",
    "apps_router",
    "llm_router",
    "referrals_router",
    "system_router",
]
