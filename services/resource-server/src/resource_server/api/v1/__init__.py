from fastapi import APIRouter

from resource_server.api.reading_speed import router as reading_speed_router

router = APIRouter(prefix="/v1")
router.include_router(reading_speed_router)
