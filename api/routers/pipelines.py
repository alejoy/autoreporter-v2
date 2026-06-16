from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from api.auth import get_current_user
from api.db import get_conn

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


class PipelineAgentIn(BaseModel):
    agent_id: int
    run_order: int = 0
    active: bool = True


class PipelineAgentOut(BaseModel):
    agent_id: int
    agent_name: str
    agent_type: str
    run_order: int
    active: bool


class PipelineIn(BaseModel):
    name: str
    site_id: int
    cron_expr: str = "0 10 * * *"
    dry_run: bool = False
    active: bool = True
    agents: list[PipelineAgentIn] = []


class PipelineOut(BaseModel):
    id: int
    name: str
    site_id: int
    site_name: str
    cron_expr: str
    dry_run: bool
    active: bool
    agents: list[PipelineAgentOut] = []


def _fetch_agents(cur, pipeline_id: int) -> list[dict]:
    cur.execute("""
        SELECT pa.agent_id, a.name AS agent_name, a.agent_type, pa.run_order, pa.active
        FROM pipeline_agents pa
        JOIN agents a ON a.id = pa.agent_id
        WHERE pa.pipeline_id = %s
        ORDER BY pa.run_order
    """, (pipeline_id,))
    return cur.fetchall()


def _replace_agents(cur, pipeline_id: int, agents: list[PipelineAgentIn]):
    cur.execute("DELETE FROM pipeline_agents WHERE pipeline_id = %s", (pipeline_id,))
    for a in agents:
        cur.execute("""
            INSERT INTO pipeline_agents (pipeline_id, agent_id, run_order, active)
            VALUES (%s, %s, %s, %s)
        """, (pipeline_id, a.agent_id, a.run_order, a.active))


@router.get("/", response_model=list[PipelineOut])
def list_pipelines(_=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.name, p.site_id, s.name AS site_name,
                       p.cron_expr, p.dry_run, p.active
                FROM pipelines p JOIN sites s ON s.id = p.site_id
                ORDER BY p.id
            """)
            rows = cur.fetchall()
            result = []
            for row in rows:
                row = dict(row)
                row["agents"] = _fetch_agents(cur, row["id"])
                result.append(row)
    return result


@router.get("/{pipeline_id}", response_model=PipelineOut)
def get_pipeline(pipeline_id: int, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.name, p.site_id, s.name AS site_name,
                       p.cron_expr, p.dry_run, p.active
                FROM pipelines p JOIN sites s ON s.id = p.site_id
                WHERE p.id = %s
            """, (pipeline_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Pipeline no encontrado")
            row = dict(row)
            row["agents"] = _fetch_agents(cur, pipeline_id)
    return row


@router.post("/", response_model=PipelineOut, status_code=201)
def create_pipeline(body: PipelineIn, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pipelines (name, site_id, cron_expr, dry_run, active)
                VALUES (%s,%s,%s,%s,%s)
                RETURNING id
            """, (body.name, body.site_id, body.cron_expr, body.dry_run, body.active))
            pid = cur.fetchone()["id"]
            _replace_agents(cur, pid, body.agents)
        conn.commit()
    return get_pipeline(pid, _)


@router.put("/{pipeline_id}", response_model=PipelineOut)
def update_pipeline(pipeline_id: int, body: PipelineIn, _=Depends(get_current_user)):
    from api.scheduler import reschedule_pipeline
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE pipelines SET name=%s, site_id=%s, cron_expr=%s,
                    dry_run=%s, active=%s
                WHERE id=%s
            """, (body.name, body.site_id, body.cron_expr,
                  body.dry_run, body.active, pipeline_id))
            if cur.rowcount == 0:
                raise HTTPException(404, "Pipeline no encontrado")
            _replace_agents(cur, pipeline_id, body.agents)
        conn.commit()
    reschedule_pipeline(pipeline_id, body.cron_expr, body.active)
    return get_pipeline(pipeline_id, _)


@router.delete("/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: int, _=Depends(get_current_user)):
    from api.scheduler import remove_pipeline
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pipelines WHERE id = %s", (pipeline_id,))
        conn.commit()
    remove_pipeline(pipeline_id)
