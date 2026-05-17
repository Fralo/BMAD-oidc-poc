from fastapi import APIRouter

from bff.api.books import router as books_router
from bff.api.reading_speed import router as reading_speed_router

router = APIRouter(prefix="/v1")
router.include_router(books_router)
router.include_router(reading_speed_router)
