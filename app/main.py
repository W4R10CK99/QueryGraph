import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.orchestrator import init_mcp, teardown_mcp, run_pipeline
from app.dashboard_builder import build_dashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
#
# FIX: MCP client and schema are now initialised ONCE at startup, not on
# every request. This eliminates the per-request subprocess fork cost.
# FastAPI's lifespan context manager is the correct place for this.
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("App startup: initialising MCP client and caching schema...")
    await init_mcp()
    logger.info("Startup complete.")
    yield
    logger.info("App shutdown: tearing down MCP client...")
    await teardown_mcp()


app = FastAPI(
    title="NL Dashboard API",
    version="0.2.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — restrict in production, open for local dev
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # TODO: lock down to your frontend origin in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Natural language query")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.post("/ask")
async def ask(req: QueryRequest):
    """
    Accepts a natural-language query, runs the full pipeline, and returns
    a dashboard schema ready for the frontend to render.
    """
    try:
        # Run pipeline: planner → SQL generation → MCP data fetch
        pipeline_result = await run_pipeline(req.query)

        # Build clean frontend-ready dashboard from raw pipeline output
        dashboard = build_dashboard(pipeline_result["dashboard"])

        return {"dashboard": dashboard}

    except RuntimeError as e:
        # MCP not initialised — server config issue
        logger.error("Runtime error in /ask: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail=str(e))

    except Exception as e:
        logger.error("Unhandled error in /ask: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal pipeline error. Check server logs.")


@app.get("/health")
async def health():
    """Simple liveness check."""
    return {"status": "ok"}