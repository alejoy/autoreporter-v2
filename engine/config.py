"""
config.py — v2: solo variables de entorno del sistema.
Toda la config de agentes, feeds y LLM vive en la base de datos.
"""
import os

# URL de conexion a PostgreSQL
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Clave para encriptar/desencriptar secrets en la DB (32 bytes en hex = 64 chars)
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")

# Umbral de similitud para deteccion de duplicados
DUPLICATE_SIMILARITY_THRESHOLD = float(os.environ.get("DUPLICATE_THRESHOLD", "0.85"))
