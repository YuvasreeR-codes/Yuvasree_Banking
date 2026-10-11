
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.db.connection import get_engine


# ---------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    message: str


class DatabaseHealthResponse(BaseModel):
    status: str
    database: str
    message: str


# ---------------------------------------------------------
# Initialize FastAPI application
# ---------------------------------------------------------

app = FastAPI(
    title="Banking Loan Risk Analysis API",
    description=(
        "REST API for banking portfolio analytics, "
        "customer risk assessment, financial trends, "
        "and customer-level analysis."
    ),
    version="1.0.0"
)

from src.api.routers.dashboard import router as dashboard_router

app.include_router(dashboard_router)

from src.api.routers.customers import router as customers_router

app.include_router(customers_router)

from src.api.routers.exports import router as exports_router

app.include_router(exports_router)

from src.api.routers.reviews import router as reviews_router

app.include_router(reviews_router)

from src.api.routers.auth import router as auth_router

app.include_router(auth_router)
# ---------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "Banking Loan Risk Analysis API",
        "docs": "/docs"
    }


# ---------------------------------------------------------
# Application health check
# ---------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health_check():

    logger.info("Application health check requested")

    return HealthResponse(
        status="healthy",
        message="Banking Loan Risk Analysis API is running"
    )


# ---------------------------------------------------------
# Database health check
# ---------------------------------------------------------

@app.get(
    "/health/db",
    response_model=DatabaseHealthResponse
)
def database_health_check():

    logger.info("Database health check requested")

    try:
        engine = get_engine()

        with engine.connect() as connection:

            result = connection.execute(
                text("SELECT DATABASE()")
            )

            database_name = result.scalar()

        if not database_name:
            logger.error("No MySQL database is selected")

            raise HTTPException(
                status_code=503,
                detail="Database is not configured correctly"
            )

        logger.info("Database connectivity verified")

        return DatabaseHealthResponse(
            status="healthy",
            database=database_name,
            message="MySQL database connection successful"
        )

    except SQLAlchemyError:

        logger.exception("Database connectivity failed")

        raise HTTPException(
            status_code=503,
            detail="Database service unavailable"
        )
