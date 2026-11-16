"""Schema per the build plan: sets + segments now; tracks/fingerprints arrive with v2.

Features/waveform/transitions live in a JSON blob on the set row to start (the plan's
"JSONB blob per set" option); segments are real rows since the UI and later the
fingerprinter address them individually."""

import datetime as dt
import secrets
import uuid

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _new_id() -> str:
    return uuid.uuid4().hex


class SetRecord(Base):
    __tablename__ = "sets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    # Capability token for mutations (e.g. tracklist import): returned once at
    # creation to the uploader; share links carry only the set id.
    edit_token: Mapped[str] = mapped_column(String(64), default=lambda: secrets.token_hex(16))
    title: Mapped[str] = mapped_column(String(300))
    audio_key: Mapped[str] = mapped_column(String(500))
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|processing|done|failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # null = never run, else running|done|failed
    identify_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=lambda: dt.datetime.now(dt.UTC)
    )

    segments: Mapped[list["SegmentRecord"]] = relationship(
        back_populates="set_", cascade="all, delete-orphan", order_by="SegmentRecord.start_s"
    )


class SegmentRecord(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_id: Mapped[str] = mapped_column(ForeignKey("sets.id"), index=True)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    transition_start_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    transition_end_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    bpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    camelot_key: Mapped[str | None] = mapped_column(String(4), nullable=True)
    key_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Naming can come from an imported tracklist today or fingerprinting (v2) later.
    artist: Mapped[str | None] = mapped_column(String(300), nullable=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)

    set_: Mapped[SetRecord] = relationship(back_populates="segments")

    def to_dict(self) -> dict:
        return {
            "start_s": self.start_s,
            "end_s": self.end_s,
            "transition_start_s": self.transition_start_s,
            "transition_end_s": self.transition_end_s,
            "bpm": self.bpm,
            "camelot_key": self.camelot_key,
            "key_confidence": self.key_confidence,
            "track_id": self.track_id,
            "match_confidence": self.match_confidence,
            "artist": self.artist,
            "title": self.title,
        }
