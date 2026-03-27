from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from contextlib import asynccontextmanager
from app.routers import grounds, bookings, auth, owner, admin
from app.utils.tasks import start_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure all tables exist (simple migration step for now)
    from app.database import engine, Base
    from app.models import user, ground, booking # Import all models into registry
    Base.metadata.create_all(bind=engine)

    from app.utils.tasks import start_scheduler
    start_scheduler()
    yield
    # Shutdown

app = FastAPI(title="GetGround API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(owner.router, prefix="/api")
app.include_router(admin.router, prefix="/api")

# Configure static file serving for uploads directory in project root
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

from app.routers import upload
app.include_router(upload.router, prefix="/api")
app.include_router(grounds.router, prefix="/api")
app.include_router(bookings.router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to GetGround API"}
