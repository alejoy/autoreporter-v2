"""Punto de entrada de la API FastAPI."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import scheduler
from api.routers import auth, sites, llm_configs, agents, pipelines, runs, logs


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start(app)
    yield


app = FastAPI(
    title="AutoReporter API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # en prod: restringir al dominio del frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sites.router)
app.include_router(llm_configs.router)
app.include_router(agents.router)
app.include_router(pipelines.router)
app.include_router(runs.router)
app.include_router(logs.router)


@app.get("/health")
def health():
    return {"status": "ok"}
