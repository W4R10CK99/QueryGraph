from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.orchestrator import run_pipeline

app = FastAPI()

# ---------------------------------------------------
# CORS
# ---------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------
# Request Model
# ---------------------------------------------------
class QueryRequest(BaseModel):
    query: str


# ---------------------------------------------------
# API Route
# ---------------------------------------------------
@app.post("/ask")
async def ask(req: QueryRequest):
    result = await run_pipeline(req.query)
    return result