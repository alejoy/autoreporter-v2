from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import Optional

from api.auth import get_current_user
from api.db import get_conn
from api.crypto import encrypt, decrypt

router = APIRouter(prefix="/sites", tags=["sites"])


class SiteIn(BaseModel):
    name: str
    wp_url: str
    wp_user: str
    wp_password: str   # plana — se encripta al guardar
    active: bool = True


class SiteOut(BaseModel):
    id: int
    name: str
    wp_url: str
    wp_user: str
    active: bool


@router.get("/", response_model=list[SiteOut])
def list_sites(_=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, wp_url, wp_user, active FROM sites ORDER BY id")
            return cur.fetchall()


@router.get("/{site_id}", response_model=SiteOut)
def get_site(site_id: int, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, wp_url, wp_user, active FROM sites WHERE id = %s", (site_id,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Sitio no encontrado")
    return row


@router.post("/", response_model=SiteOut, status_code=201)
def create_site(body: SiteIn, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sites (name, wp_url, wp_user, wp_password_enc, active)
                VALUES (%s, %s, %s, %s, %s) RETURNING id, name, wp_url, wp_user, active
            """, (body.name, body.wp_url, body.wp_user, encrypt(body.wp_password), body.active))
            row = cur.fetchone()
        conn.commit()
    return row


@router.put("/{site_id}", response_model=SiteOut)
def update_site(site_id: int, body: SiteIn, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE sites SET name=%s, wp_url=%s, wp_user=%s,
                    wp_password_enc=%s, active=%s
                WHERE id=%s
                RETURNING id, name, wp_url, wp_user, active
            """, (body.name, body.wp_url, body.wp_user,
                  encrypt(body.wp_password), body.active, site_id))
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "Sitio no encontrado")
    return row


@router.delete("/{site_id}", status_code=204)
def delete_site(site_id: int, _=Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sites WHERE id = %s", (site_id,))
        conn.commit()
