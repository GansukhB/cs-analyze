from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.cache import get_cache
from app.config import get_settings
from app.deps import DbSession
from app.routers import (
    assistant,
    auth,
    briefings,
    development,
    forecasts,
    gameplan,
    jobs,
    matches,
    me,
    players,
    system,
    teams,
    uploads,
    workspace,
)

_docs = get_settings().api_docs
app = FastAPI(
    title="cs-analyze API",
    version="0.1.0",
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(teams.router)
app.include_router(matches.router)
app.include_router(players.router)
app.include_router(me.router)
app.include_router(gameplan.router)
app.include_router(forecasts.router)
app.include_router(briefings.router)
app.include_router(development.router)
app.include_router(uploads.router)
app.include_router(workspace.router)
app.include_router(assistant.router)
app.include_router(system.router)


@app.get("/health", tags=["health"])
def health(db: DbSession) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    get_cache().ping()
    return {"status": "ok"}
