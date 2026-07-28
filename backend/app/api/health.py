from fastapi import APIRouter

# Create a router instance
router = APIRouter()

# Health check endpoint
@router.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "company-brain-backend"
    }