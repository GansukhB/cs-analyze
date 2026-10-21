"""The Assistant: a chat over the analysis data, typed or spoken (CONTEXT.md).

Ported from cstat's ``assistant_chat`` view. Stateless on the server: the browser
resends the trimmed transcript every turn, and this router only validates it,
hands it to :mod:`app.services.assistant`, and turns each yielded event into one
Server-Sent Events frame. A spoken question is recorded in the browser and
relayed through :func:`transcribe`, so the ElevenLabs key stays here.
"""

import hashlib
import json
import logging
from collections.abc import Iterator
from datetime import timedelta

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import db as database
from app.config import get_settings
from app.deps import DbSession, StaffUser
from app.models import AssistantUsage, User
from app.models.base import utcnow
from app.schemas import (
    AssistantChat,
    AssistantConfig,
    AssistantTranscript,
    AssistantUsageReport,
    AssistantUserUsage,
)
from app.services import alerts, assistant, mn, voice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

# A spoken question is seconds long; a minute of Opus is well under this.
MAX_AUDIO_BYTES = 10 * 1024 * 1024


@router.get("/config")
def config(_: StaffUser) -> AssistantConfig:
    """Which halves are set up, so the page can hide what wouldn't work."""
    return AssistantConfig(configured=assistant.is_configured(), voice=voice.is_configured())


def _event(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _user_ref(user: User) -> str:
    """An opaque per-User id for Anthropic's abuse detection: no name, no email."""
    secret = get_settings().jwt_secret.get_secret_value()
    return hashlib.sha256(f"{secret}:{user.id}".encode()).hexdigest()[:32]


def spent_today(db: Session, user: User) -> tuple[float, int]:
    """(USD, spoken characters) this User's Assistant turns cost since midnight UTC."""
    since = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    cost, chars = db.execute(
        select(
            func.coalesce(func.sum(AssistantUsage.cost_usd), 0.0),
            func.coalesce(func.sum(AssistantUsage.tts_chars), 0),
        ).where(AssistantUsage.user_id == user.id, AssistantUsage.created_at >= since)
    ).one()
    return float(cost or 0.0), int(chars or 0)


def _record(user_id: int, workspace_id: int, usage: assistant.Usage) -> None:
    """One row for the turn, on its own session: the chat's may be mid-rollback."""
    try:
        with database.SessionLocal() as db:
            db.add(
                AssistantUsage(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    model=usage.model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_write_tokens=usage.cache_write_tokens,
                    tool_rounds=usage.tool_rounds,
                    tts_chars=usage.tts_chars,
                    cost_usd=round(usage.cost_usd(), 6),
                )
            )
            db.commit()
    except Exception:  # the bill must never break the answer
        logger.exception("could not record the Assistant's usage")


def _frames(db: Session, body: AssistantChat, context, user: User, voice_on: bool) -> Iterator[str]:
    page = body.context.page if body.context else ""
    history = assistant.clean_history([t.model_dump() for t in body.history], page=page)
    usage = assistant.Usage()
    user_id, workspace_id, ref = user.id, user.workspace_id, _user_ref(user)
    try:
        for event in assistant.chat_events(
            db,
            history,
            body.message.strip(),
            context=context,
            voice_on=voice_on,
            usage=usage,
            user_ref=ref,
        ):
            yield _event(event)
    except Exception:
        logger.exception("assistant chat failed")
        yield _event({"type": "error", "text": mn.ASSISTANT_FAILED})
    finally:
        # The stream may outlive the request's dependency; give the connection back.
        db.close()
        if usage.input_tokens or usage.output_tokens or usage.tts_chars:
            _record(user_id, workspace_id, usage)


@router.post(
    "/chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-Sent Events: `status`, `paragraph` (`id`, `text`), `audio` "
            "(`id`, base64 MP3), `check` (`id`, the numbers no tool returned), `error`, "
            "then `done`.",
            "content": {"text/event-stream": {}},
        }
    },
)
def chat(body: AssistantChat, db: DbSession, user: StaffUser) -> StreamingResponse:
    """One question, answered paragraph by paragraph as Claude writes it."""
    if not body.message.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Empty message")
    settings = get_settings()
    cost, chars = spent_today(db, user)
    if cost >= settings.assistant_daily_usd:
        alerts.send(
            f"assistant-limit:{user.id}",
            f"{user.username} reached the Assistant's daily limit (${cost:.2f})",
            every=24 * 3600,
        )
        frames = iter(
            [
                _event({"type": "paragraph", "id": 0, "text": mn.ASSISTANT_LIMIT}),
                _event({"type": "done"}),
            ]
        )
        return StreamingResponse(frames, media_type="text/event-stream")
    raw = body.context.model_dump() if body.context else None
    context = assistant.clean_context(db, raw, user)
    # Past the day's speech allowance the answer still comes, in text.
    voice_on = body.voice and chars < settings.assistant_daily_tts_chars
    return StreamingResponse(
        _frames(db, body, context, user, voice_on),
        media_type="text/event-stream",
        # nginx must not buffer it, or every paragraph arrives at the end.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/usage")
def usage(db: DbSession, _: StaffUser) -> AssistantUsageReport:
    """What the Assistant cost today and over the last 30 days, per User (list prices)."""
    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = now - timedelta(days=30)
    rows = db.execute(
        select(
            User.username,
            func.sum(
                case((AssistantUsage.created_at >= today, AssistantUsage.cost_usd), else_=0.0)
            ),
            func.sum(AssistantUsage.cost_usd),
            func.count(AssistantUsage.id),
            func.sum(AssistantUsage.tts_chars),
        )
        .join(User, User.id == AssistantUsage.user_id)
        .where(AssistantUsage.created_at >= month)
        .group_by(User.username)
        .order_by(func.sum(AssistantUsage.cost_usd).desc())
    ).all()
    users = [
        AssistantUserUsage(
            username=name,
            today_usd=round(float(t or 0), 4),
            month_usd=round(float(m or 0), 4),
            turns=int(n or 0),
            tts_chars=int(c or 0),
        )
        for name, t, m, n, c in rows
    ]
    return AssistantUsageReport(
        today_usd=round(sum(u.today_usd for u in users), 4),
        month_usd=round(sum(u.month_usd for u in users), 4),
        daily_cap_usd=get_settings().assistant_daily_usd,
        users=users,
    )


@router.post("/transcribe")
def transcribe(audio: UploadFile, db: DbSession, _: StaffUser) -> AssistantTranscript:
    """A recorded question as text (ElevenLabs Scribe, Mongolian, primed with team names)."""
    if not voice.is_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Voice is not configured")
    data = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Recording is too long")
    text = voice.transcribe(
        data, audio.filename or "", audio.content_type or "", assistant.keyterms(db)
    )
    if text is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not transcribe the recording")
    return AssistantTranscript(text=text)
