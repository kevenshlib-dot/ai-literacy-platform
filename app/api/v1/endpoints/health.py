from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "AI素养评测平台",
        "version": "0.1.0",
    }


@router.get("/health/ready")
async def readiness_check():
    return {"status": "ready"}
