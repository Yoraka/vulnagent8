from fastapi import APIRouter

from api.routes.agents import agents_router
from api.routes.status import status_router
from api.routes.workflows import workflows_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(status_router)
v1_router.include_router(agents_router)
v1_router.include_router(workflows_router, prefix="/workflows", tags=["Workflows"])
