from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal

from psycopg2.extras import Json

from api.auth import get_current_user
from api.db import get_conn

router = APIRouter(prefix="/agents", tags=["agents"])

_FIELDS = """id, name, agent_type, prompt_selection, prompt_writing,
             keywords_required, keywords_skip, max_topics, wp_category,
             llm_config_id, fallback_llm_config_id, wp_author_id, post_status,
             extra_config, active"""


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
    fallback_llm_config_id: Optional[int] = None
    wp_author_id: Optional[int] = None
    post_status: Literal["publish", "draft"] = "publish"
    extra_config: dict = {}
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
    fallback_llm_config_id: Optional[int]
    wp_author_id: Optional[int]
    post_status: str
    extra_config: dict
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
            cur.execute(f"SELECT {_FIELDS} FROM agents ORDER BY id")
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
            cur.execute(f"SELECT {_FIELDS} FROM agents WHERE id = %s", (agent_id,))
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
            cur.execute(f"""
                INSERT INTO agents
                    (name, agent_type, prompt_selection, prompt_writing,
                     keywords_required, keywords_skip, max_topics, wp_category,
                     llm_config_id, fallback_llm_config_id, wp_author_id, post_status,
                     extra_config, active)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING {_FIELDS}
            """, (body.name, body.agent_type, body.prompt_selection, body.prompt_writing,
                  body.keywords_required, body.keywords_skip, body.max_topics,
                  body.wp_category, body.llm_config_id, body.fallback_llm_config_id,
                  body.wp_author_id, body.post_status, Json(body.extra_config), body.active))
            row = dict(cur.fetchone())
            _replace_feeds(cur, row["id"], body.feeds)
            row["feeds"] = _fetch_feeds(cur, row["id"])
        conn.commit()
    return row


@router.put("/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: int, body: AgentIn, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE agents SET
                    name=%s, agent_type=%s, prompt_selection=%s, prompt_writing=%s,
                    keywords_required=%s, keywords_skip=%s, max_topics=%s, wp_category=%s,
                    llm_config_id=%s, fallback_llm_config_id=%s, wp_author_id=%s,
                    post_status=%s, extra_config=%s, active=%s
                WHERE id=%s
                RETURNING {_FIELDS}
            """, (body.name, body.agent_type, body.prompt_selection, body.prompt_writing,
                  body.keywords_required, body.keywords_skip, body.max_topics,
                  body.wp_category, body.llm_config_id, body.fallback_llm_config_id,
                  body.wp_author_id, body.post_status, Json(body.extra_config), body.active, agent_id))
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
