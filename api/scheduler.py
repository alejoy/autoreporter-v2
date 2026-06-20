"""
Scheduler dinámico — carga todos los pipelines activos al arrancar
y los reprograma automáticamente cuando se crean/editan/eliminan.

IMPORTANTE: este módulo asume un único proceso uvicorn (--workers 1).
BackgroundScheduler no tiene lock entre procesos — si la API corre con más
de un worker, cada uno arranca su propia instancia y todos disparan el mismo
cron al mismo tiempo, duplicando publicaciones. Ver deploy/install.sh.
"""
import os
import sys
import subprocess
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger("scheduler")

ENGINE_DIR = os.path.join(os.path.dirname(__file__), "..", "engine")

_scheduler = BackgroundScheduler(timezone="America/Argentina/Buenos_Aires")


def _run_pipeline(pipeline_id: int):
    log.info(f"[Scheduler] Ejecutando pipeline {pipeline_id}")
    subprocess.run(
        [sys.executable, "main.py", "--pipeline", str(pipeline_id)],
        cwd=ENGINE_DIR,
        check=False,
    )


def start(app):
    """Llama a esta función en el startup de FastAPI."""
    from api.db import get_conn

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, cron_expr FROM pipelines WHERE active = TRUE
                """)
                pipelines = cur.fetchall()
    except Exception as e:
        log.error(f"No se pudo conectar a la DB para cargar pipelines: {e}")
        pipelines = []

    for p in pipelines:
        _add_job(p["id"], p["cron_expr"])
        log.info(f"Pipeline {p['id']} programado: {p['cron_expr']}")

    _scheduler.start()
    log.info(f"Scheduler iniciado con {len(pipelines)} pipelines.")


def _add_job(pipeline_id: int, cron_expr: str):
    parts = cron_expr.split()
    if len(parts) != 5:
        log.warning(f"Cron inválido para pipeline {pipeline_id}: {cron_expr}")
        return
    minute, hour, day, month, day_of_week = parts
    _scheduler.add_job(
        _run_pipeline,
        CronTrigger(
            minute=minute, hour=hour,
            day=day, month=month, day_of_week=day_of_week,
        ),
        args=[pipeline_id],
        id=f"pipeline_{pipeline_id}",
        replace_existing=True,
    )


def reschedule_pipeline(pipeline_id: int, cron_expr: str, active: bool):
    if active:
        _add_job(pipeline_id, cron_expr)
        log.info(f"Pipeline {pipeline_id} reprogramado: {cron_expr}")
    else:
        remove_pipeline(pipeline_id)


def remove_pipeline(pipeline_id: int):
    job_id = f"pipeline_{pipeline_id}"
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
        log.info(f"Pipeline {pipeline_id} removido del scheduler.")
