"""
Handler de logging que espeja en la DB (run_logs) exactamente lo mismo
que se ve en la terminal. Se cuelga del logger raíz una sola vez por
corrida, así cualquier logger (Orchestrator, WordPressClient,
DuplicateChecker, cada agente) queda registrado sin tener que llamar
a db.save_log() a mano en cada línea.
"""

import logging

_LEVEL_MAP = {
    logging.DEBUG: "info",
    logging.INFO: "info",
    logging.WARNING: "warning",
    logging.ERROR: "error",
    logging.CRITICAL: "error",
}


class DBLogHandler(logging.Handler):
    def __init__(self, pipeline_id: int, agent_ids_by_name: dict[str, int] | None = None):
        super().__init__(level=logging.INFO)
        self.pipeline_id = pipeline_id
        self.agent_ids_by_name = agent_ids_by_name or {}

    def emit(self, record: logging.LogRecord) -> None:
        try:
            import db  # import diferido para evitar ciclos al cargar el módulo
            level = _LEVEL_MAP.get(record.levelno, "info")
            agent_id = self.agent_ids_by_name.get(record.name)
            db.save_log(self.pipeline_id, agent_id, level, record.getMessage())
        except Exception:
            pass  # un fallo de logging nunca debe tirar abajo la corrida
