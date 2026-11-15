"""Stored answers: an analytic page's answer, kept with no expiry (docs/adr/0014).

One row per page and variant (a Game Plan tab of one fixture, a Map's Playbook,
a my team's overview over 30 days, ...), under the key the page is asked by. It
holds the answer as gzip JSON and the data stamp it was computed at. A page whose
stamp has moved is still answered from its row at once while the worker computes
it again (`app/services/warmer.py`), so nobody waits on a slow query: the page
says it is being refreshed and fetches it again.

Derived, like the Replays and the Reviews: deleting every row loses nothing but
the time to compute them again.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import BigId, DateTime6, MediumBlob, utcnow


class StoredAnswer(Base):
    __tablename__ = "stored_answers"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    # sha1 of `key`: the unique index, since a key can run past an index's length.
    key_hash: Mapped[str] = mapped_column(String(40), unique=True)
    key: Mapped[str] = mapped_column(String(512))
    kind: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(Integer)
    # How to compute it again outside the request: the page's parameters and the
    # scope it was read under (`answers.Spec`).
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    stamp: Mapped[str] = mapped_column(String(200))
    payload: Mapped[bytes] = mapped_column(MediumBlob)
    size: Mapped[int] = mapped_column(Integer, default=0, doc="Bytes of JSON before gzip.")
    compute_ms: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime6, default=utcnow)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime6, index=True)
    # A page read it stale: the worker computes it before anything else.
    wanted_at: Mapped[datetime | None] = mapped_column(DateTime6, index=True)
