"""
ResQVision 2.0 — FastAPI Application

SIH Problem Statement ID: 26191
Team: OffGrid
"""

import time
import uuid

from fastapi import (
    FastAPI,
    Request,
)

from fastapi.middleware.cors import (
    CORSMiddleware,
)

from fastapi.responses import (
    JSONResponse,
)

from app.api.v1.simulation import (
    router as simulation_router,
)

from app.api.v1.dashboard import (
    router as dashboard_router,
)

from app.api.v1.priority import (
    router as priority_router,
)

from app.api.v1.hazards import (
    router as hazards_router,
)

from app.api.v1.sites import (
    router as sites_router,
)

from app.api.v1.capacity import (
    router as capacity_router,
)

from app.api.v1.analytics import (
    router as analytics_router,
)

from app.api.v1.reports import (
    router as reports_router,
)

from app.api.v1.settings import (
    router as settings_router,
)


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="ResQVision 2.0 API",
    description="""
ResQVision 2.0 — Intelligent Disaster Management
& Relocation Planning

SIH Problem Statement ID: 26191
Team: OffGrid
""",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Request-ID",
    ],
)


# ============================================================
# REQUEST LOGGING
# ============================================================

@app.middleware("http")
async def request_logging_middleware(
    request: Request,
    call_next,
):
    request_id = str(
        uuid.uuid4()
    )

    request.state.request_id = (
        request_id
    )

    start = time.perf_counter()

    try:
        response = await call_next(
            request
        )

    except Exception as exc:

        print(
            f"[ERROR] "
            f"{request.method} "
            f"{request.url.path} "
            f"-> {exc}"
        )

        raise

    duration_ms = round(
        (
            time.perf_counter()
            - start
        )
        * 1000,
        2,
    )

    response.headers[
        "X-Request-ID"
    ] = request_id

    print(
        f"[REQUEST] "
        f"{request.method} "
        f"{request.url.path} "
        f"{response.status_code} "
        f"{duration_ms}ms"
    )

    return response


# ============================================================
# ROOT
# ============================================================

@app.get(
    "/",
    tags=["Health"],
)
def root():
    return {
        "service": "ResQVision 2.0",
        "version": "2.0.0",
        "status": "operational",
        "docs": "/docs",
        "health": "/health",
    }


# ============================================================
# HEALTH
# ============================================================

@app.get(
    "/health",
    tags=["Health"],
)
def health():
    return {
        "status": "healthy",
        "service": "ResQVision 2.0",
        "version": "2.0.0",
        "checks": {
            "api": "ok",
        },
    }


# ============================================================
# API ROUTERS
# ============================================================

# ------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------

app.include_router(
    dashboard_router,
    prefix="/api/v1",
)


# ------------------------------------------------------------
# Priority
# ------------------------------------------------------------

app.include_router(
    priority_router,
    prefix="/api/v1",
)


# ------------------------------------------------------------
# Hazards
# ------------------------------------------------------------

app.include_router(
    hazards_router,
    prefix="/api/v1",
)


# ------------------------------------------------------------
# Sites
# ------------------------------------------------------------

app.include_router(
    sites_router,
    prefix="/api/v1",
)


# ------------------------------------------------------------
# Carrying Capacity
# ------------------------------------------------------------

app.include_router(
    capacity_router,
    prefix="/api/v1",
)


# ------------------------------------------------------------
# Simulation
# ------------------------------------------------------------

app.include_router(
    simulation_router,
    prefix="/api/v1",
)


# ------------------------------------------------------------
# Analytics
# ------------------------------------------------------------

app.include_router(
    analytics_router,
    prefix="/api/v1",
)


# ------------------------------------------------------------
# Reports
# ------------------------------------------------------------

app.include_router(
    reports_router,
    prefix="/api/v1",
)


# ------------------------------------------------------------
# Settings
# ------------------------------------------------------------

app.include_router(
    settings_router,
    prefix="/api/v1",
)


# ============================================================
# GENERIC API STATUS
# ============================================================

@app.get(
    "/api/v1",
    tags=["Health"],
)
def api_status():
    return {
        "success": True,
        "service": "ResQVision 2.0 API",
        "version": "2.0.0",
        "status": "operational",
    }


# ============================================================
# GLOBAL EXCEPTION HANDLER
# ============================================================

@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception,
):
    request_id = getattr(
        request.state,
        "request_id",
        None,
    )

    print(
        f"[ERROR] Unhandled exception: "
        f"{exc}"
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": (
                    "INTERNAL_SERVER_ERROR"
                ),
                "message": (
                    "An unexpected error occurred."
                ),
                "details": {},
                "request_id": request_id,
            },
        },
    )


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )