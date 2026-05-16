from fastapi import APIRouter

from bff.api.books import router as books_router

router = APIRouter(prefix="/v1")
router.include_router(books_router)
