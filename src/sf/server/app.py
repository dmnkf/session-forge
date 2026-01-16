"""FastAPI application exposed by `sf serve`."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from sf.core.orchestrator import (
    OrchestratorError,
    send_prompt,
    start_session,
    stop_session,
    sync_feature,
)
from sf.core.state import StateStore

app = FastAPI(title="Session Forge API", version="0.1.0")
store = StateStore()


class SyncRequest(BaseModel):
    feature: str
    repo: Optional[str] = None
    dry_run: bool = False


class SessionRequest(BaseModel):
    feature: str
    repo: str
    llm: str = Field(default="claude")
    host: Optional[str] = None
    subdir: Optional[str] = None
    command: Optional[str] = None
    dry_run: bool = False


class PromptRequest(BaseModel):
    feature: str
    repo: str
    llm: str = Field(default="claude")
    prompt_file: Optional[str] = None
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    max_bytes: Optional[int] = None
    host: Optional[str] = None


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/state")
def state() -> dict:
    snapshot = store.dump_state()
    return snapshot


@app.post("/sync")
def sync(payload: SyncRequest) -> dict:
    try:
        summary = sync_feature(
            payload.feature,
            repo=payload.repo,
            dry_run=payload.dry_run,
        )
    except OrchestratorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"results": summary}


@app.post("/sessions/start")
def start(payload: SessionRequest) -> dict:
    try:
        result = start_session(
            payload.feature,
            payload.repo,
            llm=payload.llm,
            host=payload.host,
            subdir=payload.subdir,
            command=payload.command,
            dry_run=payload.dry_run,
        )
    except OrchestratorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.post("/sessions/stop")
def stop(payload: SessionRequest) -> dict:
    try:
        result = stop_session(
            payload.feature,
            payload.repo,
            llm=payload.llm,
            host=payload.host,
        )
    except OrchestratorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.post("/prompt")
def prompt(payload: PromptRequest) -> dict:
    prompt_file = Path(payload.prompt_file) if payload.prompt_file else None
    try:
        result = send_prompt(
            payload.feature,
            payload.repo,
            llm=payload.llm,
            prompt_file=prompt_file,
            include=payload.include,
            exclude=payload.exclude,
            max_bytes=payload.max_bytes,
            host=payload.host,
        )
    except OrchestratorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


__all__ = ["app"]
