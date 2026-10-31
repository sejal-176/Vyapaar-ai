"""FastAPI main application for VyapaarAI."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db import Base, engine
from backend.api.dashboard import router as dashboard_router
from backend.api.verify import router as verify_router
from backend.api.agent import router as agent_router
from backend.api.cases import router as cases_router
from backend.api.report import router as report_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup if missing
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="VyapaarAI API",
    description="AI business partner for small Paytm merchants",
    lifespan=lifespan,
)

# CORS: allow ONLY http://localhost:5173 per PLAN.md
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(dashboard_router)
app.include_router(verify_router)
app.include_router(agent_router)
app.include_router(cases_router)
app.include_router(report_router)


@app.get("/")
def root():
    return {"app": "VyapaarAI", "status": "running"}
