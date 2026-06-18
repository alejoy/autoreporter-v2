-- Migración 001: fallback de LLM, autor WP por agente y modo borrador
ALTER TABLE agents
    ADD COLUMN fallback_llm_config_id INTEGER REFERENCES llm_configs(id) ON DELETE SET NULL,
    ADD COLUMN wp_author_id INTEGER,
    ADD COLUMN post_status VARCHAR(10) NOT NULL DEFAULT 'publish'
        CHECK (post_status IN ('publish', 'draft'));
