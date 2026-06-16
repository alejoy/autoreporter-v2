from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from api.auth import get_current_user
from api.db import get_conn
from api.crypto import encrypt

router = APIRouter(prefix="/llm-configs", tags=["llm_configs"])


class LLMConfigIn(BaseModel):
    name: str
    provider: str        # "gemini" | "openai" | "anthropic"
    model_name: str
    api_key: str
    temperature: float = 0.5
    max_tokens: Optional[int] = 1500
    active: bool = True


class LLMConfigOut(BaseModel):
    id: int
    name: str
    provider: str
    model_name: str
    temperature: float
    max_tokens: Optional[int]
    active: bool


@router.get("/", response_model=list[LLMConfigOut])
def list_configs(_=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, provider, model_name, temperature, max_tokens, active
                FROM llm_configs ORDER BY id
            """)
            return cur.fetchall()


@router.get("/{config_id}", response_model=LLMConfigOut)
def get_config(config_id: int, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, provider, model_name, temperature, max_tokens, active
                FROM llm_configs WHERE id = %s
            """, (config_id,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Config LLM no encontrada")
    return row


@router.post("/", response_model=LLMConfigOut, status_code=201)
def create_config(body: LLMConfigIn, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO llm_configs
                    (name, provider, model_name, api_key_enc, temperature, max_tokens, active)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, name, provider, model_name, temperature, max_tokens, active
            """, (body.name, body.provider, body.model_name,
                  encrypt(body.api_key), body.temperature, body.max_tokens, body.active))
            row = cur.fetchone()
        conn.commit()
    return row


@router.put("/{config_id}", response_model=LLMConfigOut)
def update_config(config_id: int, body: LLMConfigIn, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE llm_configs SET name=%s, provider=%s, model_name=%s,
                    api_key_enc=%s, temperature=%s, max_tokens=%s, active=%s
                WHERE id=%s
                RETURNING id, name, provider, model_name, temperature, max_tokens, active
            """, (body.name, body.provider, body.model_name,
                  encrypt(body.api_key), body.temperature, body.max_tokens,
                  body.active, config_id))
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "Config LLM no encontrada")
    return row


@router.delete("/{config_id}", status_code=204)
def delete_config(config_id: int, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM llm_configs WHERE id = %s", (config_id,))
        conn.commit()
