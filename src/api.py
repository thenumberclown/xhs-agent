"""FastAPI web API for XHS Agent."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .storage.database import Database
from .storage.vector_store import get_vector_store

logger = logging.getLogger(__name__)

db: Database | None = None


def get_db() -> Database:
    global db
    if db is None:
        db = Database()
        db.init()
    return db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    get_db()
    get_vector_store()
    logger.info("XHS Agent API started")
    yield


app = FastAPI(
    title="XHS Agent",
    description="AI-powered copywriting agent for Xiaohongshu & Douyin",
    version="0.1.0",
    lifespan=lifespan,
)


# ─── Request/Response models ──────────────────────────────


class GenerateRequest(BaseModel):
    product_name: str = Field(..., description="产品名称")
    product_desc: str = Field(..., description="产品描述")
    platform: str = Field(default="xiaohongshu", description="目标平台")
    audience: str = Field(default="", description="目标受众")
    style: str = Field(default="", description="风格要求")
    versions: int = Field(default=3, ge=1, le=5, description="生成版本数")


class CopyOutput(BaseModel):
    version: int
    title: str
    body: str
    hashtags: list[str]
    cover_suggestion: str
    quality_score: Optional[float] = None


class GenerateResponse(BaseModel):
    task_id: int
    product_name: str
    platform: str
    copies: list[CopyOutput]


class TaskListResponse(BaseModel):
    tasks: list[dict]


class TaskDetailResponse(BaseModel):
    task: dict
    copies: list[dict]


# ─── Routes ─────────────────────────────────────────────


@app.get("/health")
async def health():
    """Health check endpoint."""
    vs = get_vector_store()
    return {
        "status": "ok",
        "service": "xhs-agent",
        "db_ok": True,
        "vector_store_cases": vs.count_cases(),
    }


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """Generate copywriting content for a product."""
    from .agents.research import ResearchAgent
    from .agents.analyzer import AnalyzeAgent
    from .agents.writer import WriteAgent
    from .agents.reviewer import ReviewAgent
    from .utils.ollama_client import get_client, OllamaClient

    client = get_client()
    if not client.health_check():
        raise HTTPException(503, "Ollama service not available")

    db_obj = get_db()
    research = ResearchAgent(db=db_obj)

    # Get references
    success_cases = research.get_success_cases(platform=req.platform, limit=5)
    all_cases = research.get_all_cases(platform=req.platform, limit=20)

    # Analyze + strategy
    analyzer = AnalyzeAgent(client=client)
    if success_cases:
        analyses = analyzer.analyze_batch(success_cases)
        summary = analyzer.summarize_patterns(analyses)
    else:
        summary = None

    strategy = analyzer.choose_strategy(
        product_name=req.product_name,
        product_desc=req.product_desc,
        target_audience=req.audience,
        style_notes=req.style,
        success_cases=research.format_for_prompt(success_cases),
    )

    # Write
    writer = WriteAgent(client=client)
    headlines = writer.generate_headlines(
        product_name=req.product_name,
        product_desc=req.product_desc,
        strategy=strategy,
        count=5,
    )

    copies = writer.generate_multi(
        product_name=req.product_name,
        product_desc=req.product_desc,
        strategy=strategy,
        headlines=headlines,
        examples=research.format_for_prompt(success_cases),
        max_versions=req.versions,
    )

    # Review
    reviewer = ReviewAgent(client=client)
    for copy in copies:
        report = reviewer.review(copy.title, copy.body, copy.hashtags)
        copy.quality_score = float(report.overall_score)

    # Save
    task_id = db_obj.create_task({
        "product_name": req.product_name,
        "product_desc": req.product_desc,
        "platform": req.platform,
        "content_type": strategy.content_type.value if strategy.content_type else None,
        "target_audience": req.audience,
        "keywords": summary.top_keywords if summary else [],
        "style_notes": req.style,
        "status": "generated",
    })

    copy_outputs = []
    for copy in copies:
        copy.task_id = task_id
        db_obj.save_copy({
            "task_id": task_id,
            "version": copy.version,
            "title": copy.title,
            "body": copy.body,
            "hashtags": copy.hashtags,
            "cover_suggestion": copy.cover_suggestion,
            "publish_time_hint": copy.publish_time_hint,
            "quality_score": copy.quality_score,
        })
        copy_outputs.append(CopyOutput(
            version=copy.version,
            title=copy.title,
            body=copy.body,
            hashtags=copy.hashtags,
            cover_suggestion=copy.cover_suggestion,
            quality_score=copy.quality_score,
        ))

    return GenerateResponse(
        task_id=task_id,
        product_name=req.product_name,
        platform=req.platform,
        copies=copy_outputs,
    )


@app.get("/tasks", response_model=TaskListResponse)
async def list_tasks(platform: str = "xiaohongshu", limit: int = 20):
    """List recent tasks."""
    tasks = get_db().list_tasks(platform=platform, limit=limit)
    return TaskListResponse(tasks=tasks)


@app.get("/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task(task_id: int):
    """Get a task with its generated copies."""
    task = get_db().get_task(task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    copies = get_db().list_copies(task_id=task_id)
    return TaskDetailResponse(task=task, copies=copies)


@app.get("/references")
async def list_references(platform: str = "xiaohongshu", limit: int = 50):
    """List reference cases."""
    return {
        "references": get_db().list_references(platform=platform, limit=limit),
        "total": get_db().count_references(platform=platform),
    }


@app.get("/stats")
async def get_stats(platform: str = "xiaohongshu"):
    """Get learning statistics."""
    from .agents.tracker import TrackerAgent
    tracker = TrackerAgent(db=get_db())
    return tracker.get_learning_stats(platform=platform)
