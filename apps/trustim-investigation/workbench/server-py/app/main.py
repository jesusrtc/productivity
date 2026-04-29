from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import alerts, automations, health, investigations, misc, playbooks, sessions, skills


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.sessions_dir.mkdir(parents=True, exist_ok=True)
    settings.alerts_dir.mkdir(parents=True, exist_ok=True)
    settings.automations_dir.mkdir(parents=True, exist_ok=True)
    settings.playbooks_dir.mkdir(parents=True, exist_ok=True)
    settings.templates_dir.mkdir(parents=True, exist_ok=True)
    settings.notebooks_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Juniper Server", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(skills.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(automations.router, prefix="/api")
app.include_router(playbooks.router, prefix="/api")
app.include_router(investigations.router, prefix="/api")
app.include_router(misc.router, prefix="/api")
