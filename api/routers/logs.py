"""Endpoints de logs — historial y streaming SSE en tiempo real."""
import asyncio
import json
from datetime import datetime
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.auth import get_current_user
from api.db import get_conn

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/")
def list_logs(
    pipeline_id: Optional[int] = Query(None),
    agent_id: Optional[int] = Query(None),
    level: Optional[str] = Query(None, pattern="^(info|warning|error)$"),
    status: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
    _=Depends(get_current_user),
):
    conditions = []
    params = []

    if pipeline_id:
        conditions.append("l.pipeline_id = %s")
        params.append(pipeline_id)
    if agent_id:
        conditions.append("l.agent_id = %s")
        params.append(agent_id)
    if level:
        conditions.append("l.level = %s")
        params.append(level)
    if status:
        conditions.append("l.status = %s")
        params.append(status)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params += [limit, offset]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT l.id, l.pipeline_id, p.name AS pipeline_name,
                       l.agent_id, a.name AS agent_name,
                       l.run_at, l.level, l.message,
                       l.article_title, l.article_url, l.status
                FROM run_logs l
                LEFT JOIN pipelines p ON p.id = l.pipeline_id
                LEFT JOIN agents a ON a.id = l.agent_id
                {where}
                ORDER BY l.run_at DESC
                LIMIT %s OFFSET %s
            """, params)
            rows = cur.fetchall()

    # Serializar datetimes
    result = []
    for row in rows:
        r = dict(row)
        if isinstance(r.get("run_at"), datetime):
            r["run_at"] = r["run_at"].isoformat()
        result.append(r)
    return result


@router.get("/stream")
async def stream_logs(
    pipeline_id: Optional[int] = Query(None),
    _=Depends(get_current_user),
):
    """SSE — emite los últimos logs cada 2 segundos."""
    last_id = [0]

    async def event_generator() -> AsyncGenerator[str, None]:
        while True:
            try:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        query = "SELECT id, level, message, article_title, status, run_at FROM run_logs WHERE id > %s"
                        params = [last_id[0]]
                        if pipeline_id:
                            query += " AND pipeline_id = %s"
                            params.append(pipeline_id)
                        query += " ORDER BY id LIMIT 50"
                        cur.execute(query, params)
                        rows = cur.fetchall()

                for row in rows:
                    row = dict(row)
                    if isinstance(row.get("run_at"), datetime):
                        row["run_at"] = row["run_at"].isoformat()
                    last_id[0] = row["id"]
                    yield f"data: {json.dumps(row)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.delete("/")
def clear_logs(
    pipeline_id: Optional[int] = Query(None),
    _=Depends(get_current_user),
):
    """Borra logs. Con ?pipeline_id=X borra solo los de ese pipeline."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            if pipeline_id:
                cur.execute("DELETE FROM run_logs WHERE pipeline_id = %s", (pipeline_id,))
            else:
                cur.execute("DELETE FROM run_logs")
        conn.commit()
    return {"message": "Logs eliminados"}
