"""
Capa de acceso a la base de datos.
Lee la config del pipeline desde Postgres y devuelve dataclasses listas para usar.
"""

import os
from dataclasses import dataclass, field

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class LLMConfig:
    id: int
    provider: str          # "gemini" | "openai" | "anthropic"
    model_name: str
    api_key: str           # ya desencriptada por la app
    temperature: float = 0.5
    max_tokens: int = 1500


@dataclass
class AgentConfig:
    id: int
    name: str
    agent_type: str
    prompt_selection: str
    prompt_writing: str
    keywords_required: list[str] = field(default_factory=list)
    keywords_skip: list[str] = field(default_factory=list)
    max_topics: int = 3
    wp_category: str = ""
    feeds: list[str] = field(default_factory=list)
    llm: LLMConfig | None = None
    llm_fallback: LLMConfig | None = None
    wp_author_id: int | None = None
    post_status: str = "publish"
    extra_config: dict = field(default_factory=dict)


@dataclass
class SiteConfig:
    id: int
    name: str
    wp_url: str
    wp_user: str
    wp_password: str       # ya desencriptada


@dataclass
class PipelineConfig:
    id: int
    name: str
    dry_run: bool
    site: SiteConfig
    agents: list[AgentConfig] = field(default_factory=list)


# ── Queries ────────────────────────────────────────────────────────────────────

def load_pipeline(pipeline_id: int) -> PipelineConfig:
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Pipeline + Site
            cur.execute("""
                SELECT p.id, p.name, p.dry_run,
                       s.id AS site_id, s.name AS site_name,
                       s.wp_url, s.wp_user, s.wp_password_enc
                FROM pipelines p
                JOIN sites s ON s.id = p.site_id
                WHERE p.id = %s AND p.active = TRUE
            """, (pipeline_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Pipeline {pipeline_id} no encontrado o inactivo.")

            site = SiteConfig(
                id=row["site_id"],
                name=row["site_name"],
                wp_url=row["wp_url"],
                wp_user=row["wp_user"],
                wp_password=_decrypt(row["wp_password_enc"]),
            )
            pipeline = PipelineConfig(
                id=row["id"],
                name=row["name"],
                dry_run=row["dry_run"],
                site=site,
            )

            # Agentes del pipeline (ordenados)
            cur.execute("""
                SELECT a.id, a.name, a.agent_type,
                       a.prompt_selection, a.prompt_writing,
                       a.keywords_required, a.keywords_skip,
                       a.max_topics, a.wp_category,
                       a.wp_author_id, a.post_status, a.extra_config,
                       l.id AS llm_id, l.provider, l.model_name,
                       l.api_key_enc, l.temperature, l.max_tokens,
                       lf.id AS fallback_id, lf.provider AS fallback_provider, lf.model_name AS fallback_model_name,
                       lf.api_key_enc AS fallback_api_key_enc, lf.temperature AS fallback_temperature, lf.max_tokens AS fallback_max_tokens
                FROM pipeline_agents pa
                JOIN agents a ON a.id = pa.agent_id
                LEFT JOIN llm_configs l  ON l.id = a.llm_config_id
                LEFT JOIN llm_configs lf ON lf.id = a.fallback_llm_config_id
                WHERE pa.pipeline_id = %s AND pa.active = TRUE AND a.active = TRUE
                ORDER BY pa.run_order
            """, (pipeline_id,))
            agents_rows = cur.fetchall()

            agent_ids = [r["id"] for r in agents_rows]

            # Feeds por agente (una sola query)
            feeds_by_agent: dict[int, list[str]] = {aid: [] for aid in agent_ids}
            if agent_ids:
                cur.execute("""
                    SELECT agent_id, url
                    FROM agent_feeds
                    WHERE agent_id = ANY(%s) AND active = TRUE
                    ORDER BY id
                """, (agent_ids,))
                for f in cur.fetchall():
                    feeds_by_agent[f["agent_id"]].append(f["url"])

            for r in agents_rows:
                llm = None
                if r["llm_id"]:
                    llm = LLMConfig(
                        id=r["llm_id"],
                        provider=r["provider"],
                        model_name=r["model_name"],
                        api_key=_decrypt(r["api_key_enc"]),
                        temperature=float(r["temperature"]),
                        max_tokens=r["max_tokens"] or 1500,
                    )
                llm_fallback = None
                if r["fallback_id"]:
                    llm_fallback = LLMConfig(
                        id=r["fallback_id"],
                        provider=r["fallback_provider"],
                        model_name=r["fallback_model_name"],
                        api_key=_decrypt(r["fallback_api_key_enc"]),
                        temperature=float(r["fallback_temperature"]),
                        max_tokens=r["fallback_max_tokens"] or 1500,
                    )
                pipeline.agents.append(AgentConfig(
                    id=r["id"],
                    name=r["name"],
                    agent_type=r["agent_type"],
                    prompt_selection=r["prompt_selection"],
                    prompt_writing=r["prompt_writing"],
                    keywords_required=r["keywords_required"] or [],
                    keywords_skip=r["keywords_skip"] or [],
                    max_topics=r["max_topics"],
                    wp_category=r["wp_category"] or "",
                    feeds=feeds_by_agent[r["id"]],
                    llm=llm,
                    llm_fallback=llm_fallback,
                    wp_author_id=r["wp_author_id"],
                    post_status=r["post_status"] or "publish",
                    extra_config=r["extra_config"] or {},
                ))

    return pipeline


def get_recent_source_urls(days: int = 21) -> list[str]:
    """
    URLs FUENTE (no las del post publicado en WP) de notas publicadas en los
    últimos `days` días, para sembrar el dedup por URL entre corridas — sin
    esto, el DuplicateChecker solo tenía los links de WP en el cache (que
    nunca matchean contra una URL de una fuente externa) y dependía 100% del
    fuzzy matching de títulos parafraseados por la IA, que falla de forma
    intermitente cuando la fuente reescribe el título cada día.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT article_url FROM run_logs
                    WHERE status = 'published'
                      AND article_url IS NOT NULL
                      AND run_at >= NOW() - (%s || ' days')::interval
                """, (days,))
                return [row["article_url"] for row in cur.fetchall() if row["article_url"]]
    except Exception as e:
        print(f"[db.get_recent_source_urls ERROR] {e}")
        return []


def save_log(pipeline_id: int, agent_id: int | None, level: str,
             message: str, article_title: str = "", article_url: str = "",
             status: str = "") -> None:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO run_logs
                        (pipeline_id, agent_id, level, message, article_title, article_url, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    pipeline_id,
                    agent_id or None,
                    level,
                    message,
                    article_title or None,
                    article_url or None,
                    status or None,
                ))
            conn.commit()
    except Exception as e:
        # No queremos que un fallo de log rompa el agente
        print(f"[db.save_log ERROR] {e}")


# ── Encriptación simple (AES-256-GCM via cryptography) ────────────────────────

_SECRET_KEY = os.environ.get("ENCRYPTION_KEY", "").encode()  # 32 bytes en hex


def _decrypt(enc_value: str) -> str:
    """Desencripta un valor guardado con encrypt(). Si no hay clave, devuelve el valor tal cual."""
    if not _SECRET_KEY or not enc_value or enc_value.startswith("REEMPLAZAR"):
        return enc_value
    try:
        import base64
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = bytes.fromhex(_SECRET_KEY.decode())
        data = base64.b64decode(enc_value)
        nonce, ciphertext = data[:12], data[12:]
        return AESGCM(key).decrypt(nonce, ciphertext, None).decode()
    except Exception:
        return enc_value


def encrypt(plain: str) -> str:
    """Encripta un valor para guardar en la DB."""
    import os as _os
    import base64
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = bytes.fromhex(_SECRET_KEY.decode())
    nonce = _os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plain.encode(), None)
    return base64.b64encode(nonce + ct).decode()
