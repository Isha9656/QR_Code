from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.config import get_settings
from app.database import init_db, SessionLocal
from app.auth import create_default_admin
from app.routers import auth, qr, assignment, scanning, printing, analytics

settings = get_settings()

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(qr.router)
app.include_router(assignment.router)
app.include_router(scanning.router)
app.include_router(printing.router)
app.include_router(analytics.router)


@app.on_event("startup")
async def startup():
    """Initialize database and create default admin."""
    init_db()
    db = SessionLocal()
    try:
        create_default_admin(db)
    finally:
        db.close()
    print(f"[+] {settings.APP_NAME} v{settings.APP_VERSION} started")
    print(f"[+] Base URL: {settings.BASE_URL}")
    print(f"[+] API docs: {settings.BASE_URL}/api/docs")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
