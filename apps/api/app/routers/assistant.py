"""The Assistant: a chat over the analysis data, typed or spoken (CONTEXT.md).

Ported from cstat's ``assistant_chat`` view. Stateless on the server: the browser
resends the trimmed transcript every turn, and this router only validates it,
hands it to :mod:`app.services.assistant`, and turns each yielded event into one
Server-Sent Events frame. A spoken question is recorded in the browser and
relayed through :func:`transcribe`, so the ElevenLabs key stays here.
"""

import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.deps import DbSession, StaffUser
from app.schemas import AssistantChat, AssistantConfig, AssistantTranscript
from app.services import assistant, mn, voice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

# A spoken question is seconds long; a minute of Opus is well under this.
MAX_AUDIO_BYTES = 10 * 1024 * 1024


@router.get("/config")
def config(_: StaffUser) -> AssistantConfig:
    """Which halves are set up, so the page can hide what wouldn't work."""
    return AssistantConfig(configured=assistant.is_configured(), voice=voice.is_configured())


def _frames(db: Session, body: AssistantChat, context) -> Iterator[str]:
    history = assistant.clean_history([t.model_dump() for t in body.history])
    try:
        for event in assistant.chat_events(
            db, history, body.message.strip(), context=context, voice_on=body.voice
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    except Exception:
        logger.exception("assistant chat failed")
        yield f"data: {json.dumps({'type': 'error', 'text': mn.ASSISTANT_FAILED})}\n\n"
    finally:
        # The stream may outlive the request's dependency; give the connection back.
        db.close()


@router.post(
    "/chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-Sent Events: `status`, `paragraph` (`id`, `text`), `audio` "
            "(`id`, base64 MP3), `error`, then `done`.",
            "content": {"text/event-stream": {}},
        }
    },
)
def chat(body: AssistantChat, db: DbSession, _: StaffUser) -> StreamingResponse:
    """One question, answered paragraph by paragraph as Claude writes it."""
    if not body.message.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Empty message")
    raw = body.context.model_dump() if body.context else None
    context = assistant.clean_context(db, raw)
    return StreamingResponse(
        _frames(db, body, context),
        media_type="text/event-stream",
        # nginx must not buffer it, or every paragraph arrives at the end.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
