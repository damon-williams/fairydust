# Legacy routes.py file for backward compatibility
# This file re-exports the modular routers from the routes/ package

from .routes import (
    auth_router,
    dashboard_router,
    users_router,
    apps_router,
    questions_router,
    llm_router
)

# For backward compatibility, create a combined admin_router
# Though this is no longer recommended - use individual routers instead
from fastapi import APIRouter

admin_router = APIRouter()

# Include all routers under the admin router for legacy support
admin_router.include_router(auth_router)
admin_router.include_router(dashboard_router)
admin_router.include_router(users_router, prefix="/users")
admin_router.include_router(apps_router, prefix="/apps")
admin_router.include_router(questions_router, prefix="/questions")
admin_router.include_router(llm_router, prefix="/llm")

__all__ = [
    "admin_router",
    "auth_router",
    "dashboard_router",
    "users_router",
    "apps_router",
    "questions_router",
    "llm_router"
]