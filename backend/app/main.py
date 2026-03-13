from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.routers import grounds, bookings, auth, owner, admin
from app.utils.tasks import start_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
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
app.include_router(grounds.router, prefix="/api")
app.include_router(bookings.router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to GetGround API"}
