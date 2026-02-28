"""Monitoring infrastructure: per-analysis timing, log collection, and SSE support."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Log entry model
# ---------------------------------------------------------------------------

class LogLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"


@dataclass
class LogEntry:
    timestamp: str
    level: str
    stage: str
    message: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "stage": self.stage,
            "message": self.message,
        }

    def to_sse(self) -> str:
        import json
        return f"data: {json.dumps(self.to_dict())}\n\n"


# ---------------------------------------------------------------------------
# Stage timing model
# ---------------------------------------------------------------------------

@dataclass
class StageTiming:
    stage: str
    start_time: float = 0.0
    end_time: float = 0.0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "start_time": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat() if self.start_time else None,
            "end_time": datetime.fromtimestamp(self.end_time, tz=timezone.utc).isoformat() if self.end_time else None,
            "duration_seconds": round(self.duration_seconds, 2),
        }


# ---------------------------------------------------------------------------
# Per-analysis tracker
# ---------------------------------------------------------------------------

STAGE_NAMES = [
    "extracting",
    "parsing",
    "scoring",
    "post_processing",
    "generating_narrative",
    "generating_report",
]


@dataclass
class AnalysisRecord:
    """Complete record of a single analysis run."""
    analysis_id: str
    client_name: str = ""
    filename: str = ""
    file_size_bytes: int = 0
    page_count: int = 0
    status: str = "pending"
    start_time: float = 0.0
    end_time: float = 0.0
    total_duration_seconds: float = 0.0
    stage_timings: dict[str, StageTiming] = field(default_factory=dict)
    logs: list[LogEntry] = field(default_factory=list)
    error: Optional[str] = None
    # Claude API stats
    scoring_input_tokens: int = 0
    scoring_output_tokens: int = 0
    narrative_input_tokens: int = 0
    narrative_output_tokens: int = 0
    # SSE subscribers
    _subscribers: list[asyncio.Queue] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        return {
            "analysis_id": self.analysis_id,
            "client_name": self.client_name,
            "filename": self.filename,
            "file_size_bytes": self.file_size_bytes,
            "page_count": self.page_count,
            "status": self.status,
            "start_time": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat() if self.start_time else None,
            "end_time": datetime.fromtimestamp(self.end_time, tz=timezone.utc).isoformat() if self.end_time else None,
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "stage_timings": {k: v.to_dict() for k, v in self.stage_timings.items()},
            "error": self.error,
            "scoring_input_tokens": self.scoring_input_tokens,
            "scoring_output_tokens": self.scoring_output_tokens,
            "narrative_input_tokens": self.narrative_input_tokens,
            "narrative_output_tokens": self.narrative_output_tokens,
        }

    def add_log(self, level: str, stage: str, message: str) -> None:
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level,
            stage=stage,
            message=message,
        )
        self.logs.append(entry)
        # Notify SSE subscribers
        for q in self._subscribers:
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                pass  # drop if subscriber is too slow

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def start_stage(self, stage: str) -> None:
        now = time.time()
        # Close previous stage if any
        for s in self.stage_timings.values():
            if s.end_time == 0.0 and s.start_time > 0:
                s.end_time = now
                s.duration_seconds = s.end_time - s.start_time
        self.stage_timings[stage] = StageTiming(stage=stage, start_time=now)
        self.status = stage
        self.add_log("INFO", stage, f"Stage started: {stage}")

    def end_stage(self, stage: str) -> float:
        now = time.time()
        if stage in self.stage_timings:
            t = self.stage_timings[stage]
            t.end_time = now
            t.duration_seconds = t.end_time - t.start_time
            self.add_log("INFO", stage, f"Stage completed: {stage} ({t.duration_seconds:.1f}s)")
            return t.duration_seconds
        return 0.0

    def mark_started(self) -> None:
        self.start_time = time.time()
        self.status = "running"
        self.add_log("INFO", "pipeline", f"Analysis started for {self.filename}")

    def mark_completed(self) -> None:
        self.end_time = time.time()
        self.total_duration_seconds = self.end_time - self.start_time
        self.status = "completed"
        self.add_log("INFO", "pipeline", f"Analysis completed in {self.total_duration_seconds:.1f}s")
        # Send sentinel to close SSE streams
        for q in self._subscribers:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def mark_failed(self, error: str) -> None:
        self.end_time = time.time()
        if self.start_time:
            self.total_duration_seconds = self.end_time - self.start_time
        self.status = "failed"
        self.error = error
        self.add_log("ERROR", "pipeline", f"Analysis failed: {error}")
        for q in self._subscribers:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass


# ---------------------------------------------------------------------------
# Global registry
# ---------------------------------------------------------------------------

class MonitoringRegistry:
    """Global singleton holding all analysis records."""

    def __init__(self):
        self._records: dict[str, AnalysisRecord] = {}

    def create(self, analysis_id: str, client_name: str = "", filename: str = "",
               file_size_bytes: int = 0) -> AnalysisRecord:
        record = AnalysisRecord(
            analysis_id=analysis_id,
            client_name=client_name,
            filename=filename,
            file_size_bytes=file_size_bytes,
        )
        self._records[analysis_id] = record
        return record

    def get(self, analysis_id: str) -> Optional[AnalysisRecord]:
        return self._records.get(analysis_id)

    def list_all(self) -> list[dict]:
        """Return all records sorted by start_time descending."""
        records = sorted(
            self._records.values(),
            key=lambda r: r.start_time or 0,
            reverse=True,
        )
        return [r.to_dict() for r in records]


# Module-level singleton
registry = MonitoringRegistry()
