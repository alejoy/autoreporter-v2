from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from api.auth import get_current_user
from api.db import get_conn

router = APIRouter(prefix="/agents", tags=["agents"])


class FeedIn(BaseModel):
    url: str
    label: Optional[str] = None
    active: bool = True


class FeedOut(BaseModel):
    id: int
    url: str
    label: Optional[str]
    active: bool


class AgentIn(BaseModel):
    name: str
    agent_type: str
    prompt_selection: str
    prompt_writing: str
    keywords_required: Optional[list[str]] = None
    keywords_skip: Optional[list[str]] = None
    max_topics: int = 3
    wp_category: Optional[str] = None
    llm_config_id: Optional[int] = None
    active: bool = True
    feeds: list[FeedIn] = []


class AgentOut(BaseModel):
    id: int
    name: str
    agent_type: str
    prompt_selection: str
    prompt_writing: str
    keywords_required: Optional[list[str]]
    keywords_skip: Optional[list[str]]
    max_topics: int
    wp_category: Optional[str]
    llm_config_id: Optional[int]
    active: bool
    feeds: list[FeedOut] = []


def _fetch_feeds(cur, agent_id: int) -> list[dict]:
    cur.execute("""
        SELECT id, url, label, active FROM agent_feeds
        WHERE agent_id = %s ORDER BY id
    """, (agent_id,))
    return cur.fetchall()


def _replace_feeds(cur, agent_id: int, feeds: list[FeedIn]):
    cur.execute("DELETE FROM agent_feeds WHERE agent_id = %s", (agent_id,))
    for f in feeds:
        cur.execute("""
            INSERT INTO agent_feeds (agent_id, url, label, active)
            VALUES (%s, %s, %s, %s)
        """, (agent_id, f.url, f.label, f.active))


@router.get("/", response_model=list[AgentOut])
def list_agents(_=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, agent_type, prompt_selection, prompt_writing,
                       keywords_required, keywords_skip, max_topics, wp_category,
                       llm_config_id, active
                FROM agents ORDER BY id
            """)
            rows = cur.fetchall()
            result = []
            for row in rows:
                row = dict(row)
                row["feeds"] = _fetch_feeds(cur, row["id"])
                result.append(row)
    return result


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: int, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, agent_type, prompt_selection, prompt_writing,
                       keywords_required, keywords_skip, max_topics, wp_category,
                       llm_config_id, active
                FROM agents WHERE id = %s
            """, (agent_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Agente no encontrado")
            row = dict(row)
            row["feeds"] = _fetch_feeds(cur, agent_id)
    return row


@router.post("/", response_model=AgentOut, status_code=201)
def create_agent(body: AgentIn, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO agents
                    (name, agent_type, prompt_selection, prompt_writing,
                     keywords_required, keywords_skip, max_topics, wp_category,
                     llm_config_id, active)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id, name, agent_type, prompt_selection, prompt_writing,
                          keywords_required, keywords_skip, max_topics, wp_category,
                          llm_config_id, active
            """, (body.name, body.agent_type, body.prompt_selection, body.prompt_writing,
                  body.keywords_required, body.keywords_skip, body.max_topics,
                  body.wp_category, body.llm_config_id, body.active))
            row = dict(cur.fetchone())
            _replace_feeds(cur, row["id"], body.feeds)
            row["feeds"] = _fetch_feeds(cur, row["id"])
        conn.commit()
    return row


@router.put("/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: int, body: AgentIn, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE agents SET
                    name=%s, agent_type=%s, prompt_selection=%s, prompt_writing=%s,
                    keywords_required=%s, keywords_skip=%s, max_topics=%s, wp_category=%s,
                    llm_config_id=%s, active=%s
                WHERE id=%s
                RETURNING id, name, agent_type, prompt_selection, prompt_writing,
                          keywords_required, keywords_skip, max_topics, wp_category,
                          llm_config_id, active
            """, (body.name, body.agent_type, body.prompt_selection, body.prompt_writing,
                  body.keywords_required, body.keywords_skip, body.max_topics,
                  body.wp_category, body.llm_config_id, body.active, agent_id))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Agente no encontrado")
            row = dict(row)
            _replace_feeds(cur, agent_id, body.feeds)
            row["feeds"] = _fetch_feeds(cur, agent_id)
        conn.commit()
    return row


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: int, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM agents WHERE id = %s", (agent_id,))
        conn.commit()
