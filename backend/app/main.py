from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.google_drive import router as google_drive_router
from app.api.gmail import router as gmail_router
from app.api.ingestion import router as ingestion_router
from app.core.settings import settings

# Create the FastAPI application
app = FastAPI(
    title=settings.APP_NAME, # example usage of settings 
    description="Backend API for the Company Brain knowledge transfer platform.",
    version="1.0.0",
)

# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to the Company Brain API!"
    }

# Register API routers
app.include_router(health_router)
app.include_router(google_drive_router)
app.include_router(gmail_router)
app.include_router(ingestion_router)
