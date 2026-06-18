-- =============================================================
-- AutoReporter — Schema PostgreSQL
-- =============================================================

-- Extensión para UUIDs (opcional; usamos SERIAL por simplicidad)
-- CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- -------------------------------------------------------------
-- 1. LLM CONFIGS
--    Un registro por proveedor/modelo que quieras usar.
--    La api_key se guarda encriptada a nivel de aplicación.
-- -------------------------------------------------------------
CREATE TABLE llm_configs (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,           -- etiqueta legible: "Gemini Flash", "Claude Sonnet"
    provider        VARCHAR(50)  NOT NULL,           -- "gemini" | "openai" | "anthropic"
    model_name      VARCHAR(100) NOT NULL,           -- "gemini-2.5-flash", "gpt-4o", "claude-sonnet-4-6"
    api_key_enc     TEXT         NOT NULL,           -- API key encriptada (AES-256 en la app)
    temperature     NUMERIC(3,2) NOT NULL DEFAULT 0.5,
    max_tokens      INTEGER,
    active          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------------
-- 2. SITES
--    Cada sitio WordPress que recibirá publicaciones.
-- -------------------------------------------------------------
CREATE TABLE sites (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL,           -- "Portal Neuquén", "Diario Nacional"
    wp_url          VARCHAR(500) NOT NULL UNIQUE,    -- "https://miportal.com"
    wp_user         VARCHAR(150) NOT NULL,
    wp_password_enc TEXT         NOT NULL,           -- Application Password encriptada
    active          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------------
-- 3. AGENTS
--    Plantilla de agente reutilizable (no está atado a un sitio).
--    El agente define QUÉ buscar y CÓMO redactar.
-- -------------------------------------------------------------
CREATE TABLE agents (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(150) NOT NULL,        -- "Municipal Neuquén", "Nacional Genérico"
    agent_type          VARCHAR(50)  NOT NULL,        -- "municipal" | "provincial" | "nacional" | "sociedad" | "clima" | "horoscopo"
    prompt_selection    TEXT         NOT NULL,        -- prompt para elegir noticias del RSS
    prompt_writing      TEXT         NOT NULL,        -- prompt para redactar el artículo
    keywords_required   TEXT[],                      -- ["neuquén","neuquen"] — NULL = sin filtro
    keywords_skip       TEXT[],                      -- ["en vivo","minuto a minuto"]
    max_topics          SMALLINT     NOT NULL DEFAULT 3,
    wp_category         VARCHAR(150),                -- nombre de categoría en WordPress
    llm_config_id       INTEGER      REFERENCES llm_configs(id) ON DELETE SET NULL,
    fallback_llm_config_id INTEGER   REFERENCES llm_configs(id) ON DELETE SET NULL,  -- proveedor de respaldo si el primario falla
    wp_author_id        INTEGER,                     -- ID de usuario WP que firma las publicaciones de este agente
    post_status         VARCHAR(10)  NOT NULL DEFAULT 'publish' CHECK (post_status IN ('publish','draft')),
    active              BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------------
-- 4. AGENT FEEDS
--    URLs de RSS asociadas a un agente. N feeds por agente.
-- -------------------------------------------------------------
CREATE TABLE agent_feeds (
    id          SERIAL PRIMARY KEY,
    agent_id    INTEGER      NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    url         VARCHAR(500) NOT NULL,
    label       VARCHAR(150),                        -- "LM Neuquén - Últimas", "Infobae"
    active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (agent_id, url)
);

-- -------------------------------------------------------------
-- 5. PIPELINES
--    Une un sitio con un horario. Los agentes se asignan
--    en la tabla puente pipeline_agents.
-- -------------------------------------------------------------
CREATE TABLE pipelines (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,               -- "Neuquén AM", "Nacional Diario"
    site_id     INTEGER      NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    cron_expr   VARCHAR(100) NOT NULL DEFAULT '0 10 * * *',  -- expresión cron UTC
    dry_run     BOOLEAN      NOT NULL DEFAULT FALSE,
    active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------------
-- 6. PIPELINE ↔ AGENTS  (many-to-many)
--    Define qué agentes corren en cada pipeline y en qué orden.
-- -------------------------------------------------------------
CREATE TABLE pipeline_agents (
    id          SERIAL PRIMARY KEY,
    pipeline_id INTEGER      NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
    agent_id    INTEGER      NOT NULL REFERENCES agents(id)   ON DELETE CASCADE,
    run_order   SMALLINT     NOT NULL DEFAULT 0,     -- orden de ejecución dentro del pipeline
    active      BOOLEAN      NOT NULL DEFAULT TRUE,
    UNIQUE (pipeline_id, agent_id)
);

-- -------------------------------------------------------------
-- 7. RUN LOGS
--    Cada evento generado durante la ejecución de un pipeline.
--    level: "info" | "warning" | "error"
--    status (para artículos): "published" | "skipped" | "dry_run" | "error"
-- -------------------------------------------------------------
CREATE TABLE run_logs (
    id              BIGSERIAL    PRIMARY KEY,
    pipeline_id     INTEGER      REFERENCES pipelines(id) ON DELETE SET NULL,
    agent_id        INTEGER      REFERENCES agents(id)    ON DELETE SET NULL,
    run_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    level           VARCHAR(10)  NOT NULL DEFAULT 'info'   CHECK (level IN ('info','warning','error')),
    message         TEXT         NOT NULL,
    article_title   VARCHAR(500),                    -- título del artículo (si aplica)
    article_url     VARCHAR(500),                    -- URL publicada en WP (si aplica)
    status          VARCHAR(20)                      CHECK (status IN ('published','skipped','dry_run','error'))
);

-- =============================================================
-- ÍNDICES
-- =============================================================
CREATE INDEX idx_agent_feeds_agent       ON agent_feeds(agent_id);
CREATE INDEX idx_pipeline_agents_pipe    ON pipeline_agents(pipeline_id);
CREATE INDEX idx_pipeline_agents_agent   ON pipeline_agents(agent_id);
CREATE INDEX idx_run_logs_pipeline       ON run_logs(pipeline_id);
CREATE INDEX idx_run_logs_run_at         ON run_logs(run_at DESC);
CREATE INDEX idx_run_logs_level          ON run_logs(level);

-- =============================================================
-- TRIGGERS: updated_at automático
-- =============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_llm_configs_updated   BEFORE UPDATE ON llm_configs   FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_sites_updated         BEFORE UPDATE ON sites          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_agents_updated        BEFORE UPDATE ON agents         FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_pipelines_updated     BEFORE UPDATE ON pipelines      FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =============================================================
-- SEED DATA — ejemplo funcional basado en el AutoReporter actual
-- =============================================================

-- LLM config
INSERT INTO llm_configs (name, provider, model_name, api_key_enc, temperature)
VALUES ('Gemini 2.5 Flash', 'gemini', 'gemini-2.5-flash', 'REEMPLAZAR_CON_KEY_ENCRIPTADA', 0.5);

-- Sitio WordPress de ejemplo
INSERT INTO sites (name, wp_url, wp_user, wp_password_enc)
VALUES ('Portal Neuquén', 'https://tuportal.com', 'admin', 'REEMPLAZAR_CON_PASSWORD_ENCRIPTADA');

-- Agentes
INSERT INTO agents (name, agent_type, prompt_selection, prompt_writing, keywords_required, keywords_skip, max_topics, wp_category, llm_config_id)
VALUES
(
    'Municipal Neuquén', 'municipal',
    'Elegí los 3 más relevantes EXCLUSIVAMENTE sobre la ciudad de Neuquén capital: servicios municipales, obras, transporte, seguridad o economía local. DESCARTÁ cualquier noticia de otras ciudades o provincias.',
    'Sos un redactor periodístico para un portal de noticias de la ciudad de Neuquén capital.',
    ARRAY['neuquén','neuquen','neuquino','neuquina'],
    ARRAY['minuto a minuto','en vivo','sigue la sesión','cobertura en vivo'],
    3, 'MUNICIPALES', 1
),
(
    'Provincial Neuquén', 'provincial',
    'Elegí los 3 más relevantes EXCLUSIVAMENTE sobre la provincia de Neuquén: política provincial, economía, obras, salud o seguridad.',
    'Sos un redactor periodístico para un portal de noticias de la provincia de Neuquén, Argentina.',
    ARRAY['neuquén','neuquen','neuquino','neuquina'],
    ARRAY['minuto a minuto','en vivo'],
    3, 'PROVINCIA', 1
),
(
    'Nacional', 'nacional',
    'Elegí los 3 más importantes del día para los argentinos. Priorizá política nacional, economía, justicia o seguridad.',
    'Sos un redactor periodístico para un portal de noticias de Argentina.',
    NULL,
    ARRAY['minuto a minuto','en vivo'],
    3, 'Nacional', 1
),
(
    'Sociedad', 'sociedad',
    'Elegí los 2 más relevantes de interés humano y social: historias de personas, comunidad, educación, salud, cultura.',
    'Sos un redactor periodístico para un portal de noticias de interés social y humano de Neuquén.',
    NULL,
    ARRAY['minuto a minuto','en vivo'],
    2, 'SOCIEDAD', 1
);

-- Feeds por agente
INSERT INTO agent_feeds (agent_id, url, label) VALUES
-- Municipal (id=1)
(1, 'https://www.lmneuquen.com/rss/ultimas-noticias.xml', 'LM Neuquén - Últimas'),
(1, 'https://www.lmneuquen.com/rss/neuquen.xml',          'LM Neuquén - Neuquén'),
(1, 'https://www.rionegro.com.ar/feed/',                  'Río Negro'),
-- Provincial (id=2)
(2, 'https://www.lmneuquen.com/rss/neuquen.xml',          'LM Neuquén - Neuquén'),
(2, 'https://www.rionegro.com.ar/feed/',                  'Río Negro'),
-- Nacional (id=3)
(3, 'https://www.lanacion.com.ar/arc/outboundfeeds/rss/', 'La Nación'),
(3, 'https://www.infobae.com/feeds/rss/',                 'Infobae'),
(3, 'https://www.perfil.com/feed',                        'Perfil'),
(3, 'https://www.lmneuquen.com/rss/pais.xml',             'LM Neuquén - País'),
-- Sociedad (id=4)
(4, 'https://www.perfil.com/feed',                        'Perfil'),
(4, 'https://www.lmneuquen.com/rss/ultimas-noticias.xml', 'LM Neuquén - Últimas');

-- Pipeline de ejemplo
INSERT INTO pipelines (name, site_id, cron_expr)
VALUES ('Portal Neuquén - Mañana', 1, '0 10 * * *');

-- Asignar agentes al pipeline (en orden)
INSERT INTO pipeline_agents (pipeline_id, agent_id, run_order) VALUES
(1, 1, 1),  -- Municipal
(1, 2, 2),  -- Provincial
(1, 3, 3),  -- Nacional
(1, 4, 4);  -- Sociedad
