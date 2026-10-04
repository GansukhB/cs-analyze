from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.cache import get_cache
from app.config import get_settings
from app.deps import DbSession
from app.routers import assistant, auth, gameplan, jobs, matches, teams

app = FastAPI(title="cs-analyze API", version="0.1.0")

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
app.include_router(gameplan.router)
app.include_router(assistant.router)


@app.get("/health", tags=["health"])
def health(db: DbSession) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    get_cache().ping()
    return {"status": "ok"}
