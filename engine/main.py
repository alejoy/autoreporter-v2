#!/usr/bin/env python3
"""
AutoReporter v2 — Orquestador principal (config desde DB).

Uso:
  python main.py --pipeline 1
  python main.py --pipeline 1 --dry-run
  python main.py --pipeline 1 --agents municipal clima
"""

import sys
import time
import argparse

import db
from utils.logger import get_logger
from utils.wordpress_client import WordPressClient
from utils.duplicate_checker import DuplicateChecker

from agents.municipal_agent   import MunicipalAgent
from agents.provincial_agent  import ProvincialAgent
from agents.nacional_agent    import NacionalAgent
from agents.sociedad_agent    import SociedadAgent
from agents.horoscopo_agent   import HoroscopoAgent
from agents.clima_agent       import ClimaAgent

AGENT_CLASS_MAP = {
    "municipal":  MunicipalAgent,
    "provincial": ProvincialAgent,
    "nacional":   NacionalAgent,
    "sociedad":   SociedadAgent,
    "horoscopo":  HoroscopoAgent,
    "clima":      ClimaAgent,
}

log = get_logger("Orchestrator")


def parse_args():
    parser = argparse.ArgumentParser(description="AutoReporter v2")
    parser.add_argument("--pipeline", type=int, required=True, help="ID del pipeline a ejecutar")
    parser.add_argument("--dry-run", action="store_true", help="Simula sin publicar en WordPress")
    parser.add_argument("--agents", nargs="+", metavar="TYPE",
                        help="Tipos de agente a ejecutar (ej: municipal clima). Por defecto: todos los del pipeline.")
    return parser.parse_args()


def main():
    args = parse_args()

    log.info("=" * 60)
    log.info(f"AutoReporter v2 — Pipeline {args.pipeline} {'[DRY-RUN]' if args.dry_run else '[REAL]'}")
    log.info("=" * 60)

    try:
        pipeline = db.load_pipeline(args.pipeline)
    except Exception as e:
        log.error(f"No se pudo cargar el pipeline {args.pipeline}: {e}")
        sys.exit(1)

    log.info(f"Pipeline: {pipeline.name} → Sitio: {pipeline.site.name}")

    dry_run = args.dry_run or pipeline.dry_run

    agents_cfg = pipeline.agents
    if args.agents:
        tipos_filtro = {t.lower() for t in args.agents}
        agents_cfg = [a for a in agents_cfg if a.agent_type.lower() in tipos_filtro]
        if not agents_cfg:
            log.error(f"Ningún agente coincide con los tipos: {args.agents}")
            sys.exit(1)

    log.info(f"Agentes: {[a.name for a in agents_cfg]}")

    site = pipeline.site
    wp = WordPressClient(site.wp_url, site.wp_user, site.wp_password)

    categories = wp.get_categories()
    if not categories:
        log.error("No se pudieron cargar categorías de WordPress.")
        sys.exit(1)

    dup_checker = DuplicateChecker(threshold=0.85)
    recent_posts = wp.get_recent_posts(count=100)
    dup_checker.load_from_wp(recent_posts)

    all_results: dict[str, list[dict]] = {}

    for agent_cfg in agents_cfg:
        log.info(f"\n{'─'*50}\nIniciando {agent_cfg.name}\n{'─'*50}")

        AgentClass = AGENT_CLASS_MAP.get(agent_cfg.agent_type.lower())
        if not AgentClass:
            log.error(f"Tipo de agente desconocido: {agent_cfg.agent_type}")
            all_results[agent_cfg.name] = [{"title": "N/A", "status": "error", "reason": "tipo desconocido"}]
            continue

        category_id = categories.get(agent_cfg.wp_category)
        if not category_id:
            log.warning(f"Categoría '{agent_cfg.wp_category}' no encontrada en WP.")

        db.save_log(pipeline.id, agent_cfg.id, "info", f"Iniciando {agent_cfg.name}")

        try:
            agent = AgentClass(agent_cfg=agent_cfg, pipeline_id=pipeline.id)
            results = agent.run(wp, dup_checker, category_id, dry_run=dry_run)
            all_results[agent_cfg.name] = results
        except Exception as e:
            log.error(f"Error fatal en {agent_cfg.name}: {e}", exc_info=True)
            db.save_log(pipeline.id, agent_cfg.id, "error", f"Error fatal: {e}")
            all_results[agent_cfg.name] = [{"title": "N/A", "status": "error", "reason": str(e)}]

        time.sleep(3)

    _print_report(all_results, dry_run)


def _print_report(all_results: dict, dry_run: bool):
    log.info("\n" + "=" * 60)
    log.info(f"REPORTE FINAL {'[DRY-RUN]' if dry_run else ''}")
    log.info("=" * 60)

    totals = {"published": 0, "skipped": 0, "error": 0, "dry_run": 0}

    for agent_name, results in all_results.items():
        log.info(f"\n{agent_name}:")
        for r in results:
            status = r.get("status", "?")
            emoji = {"published": "✅", "skipped": "⏭️", "error": "❌", "dry_run": "🔍"}.get(status, "?")
            log.info(f"  {emoji} [{status.upper()}] {r.get('title','')[:70]} — {r.get('reason','')}")
            totals[status] = totals.get(status, 0) + 1

    log.info(
        f"\nTOTAL → Publicadas: {totals['published']} | "
        f"Duplicadas: {totals['skipped']} | "
        f"Errores: {totals['error']} | "
        f"Dry-run: {totals['dry_run']}"
    )


if __name__ == "__main__":
    main()
