"""Endpoints para disparar pipelines manualmente."""
import subprocess
import sys
import os
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from api.auth import get_current_user
from api.db import get_conn

router = APIRouter(prefix="/runs", tags=["runs"])

ENGINE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "engine")


class RunRequest(BaseModel):
    pipeline_id: int
    dry_run: bool = False
    agents: Optional[list[str]] = None   # tipos: ["municipal", "clima"]


class RunStatus(BaseModel):
    message: str
    pipeline_id: int


def _execute_pipeline(pipeline_id: int, dry_run: bool, agents: list[str] | None):
    cmd = [sys.executable, "main.py", "--pipeline", str(pipeline_id)]
    if dry_run:
        cmd.append("--dry-run")
    if agents:
        cmd += ["--agents"] + agents
    subprocess.run(cmd, cwd=ENGINE_DIR, check=False)


@router.post("/", response_model=RunStatus, status_code=202)
def trigger_run(body: RunRequest, background: BackgroundTasks, _=Depends(get_current_user)):
    # Verificar que el pipeline existe
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM pipelines WHERE id = %s AND active = TRUE", (body.pipeline_id,))
            if not cur.fetchone():
                raise HTTPException(404, "Pipeline no encontrado o inactivo")

    background.add_task(_execute_pipeline, body.pipeline_id, body.dry_run, body.agents)
    return RunStatus(message="Pipeline iniciado en segundo plano", pipeline_id=body.pipeline_id)
