-- Migración 002: configuración extra flexible por agente (JSON).
-- Usado por horóscopo (imagen de placa) y clima (ciudad/coordenadas/zonas SMN),
-- para que un mismo tipo de agente sirva para distintos sitios sin compartir
-- la ubicación o la imagen de otro portal.
ALTER TABLE agents
    ADD COLUMN extra_config JSONB NOT NULL DEFAULT '{}'::jsonb;
