from fastapi import APIRouter

from resource_server.api.estimate import router as estimate_router
from resource_server.api.reading_speed import router as reading_speed_router

router = APIRouter(prefix="/v1")
router.include_router(estimate_router)
router.include_router(reading_speed_router)
