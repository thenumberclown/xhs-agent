"""FastAPI web API for XHS Agent."""

from __future__ import annotations

import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
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


# ─── Novel Promote API ───────────────────────────────────────


@app.post("/novel/promote")
async def novel_promote_api(
    file: UploadFile = File(..., description="章节 .md 文件"),
    platform: str = Form("xiaohongshu"),
    use_rag: str = Form("true"),
    no_review: str = Form("false"),
):
    """上传章节文件，返回宣发文案。"""
    import json

    # Save uploaded file to temp
    content = (await file.read()).decode("utf-8")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from .agents.extractor import ChapterExtractor
        from .agents.templates import TemplateEngine
        from .agents.knowledge import NovelKnowledgeBase

        path = Path(tmp_path)

        # Load profile
        profile_path = Path("data/novel_profile.json")
        if profile_path.exists():
            novel_meta = json.loads(profile_path.read_text(encoding="utf-8"))
        else:
            novel_meta = {}

        # Step 1: Extract
        extractor = ChapterExtractor()
        extraction = extractor.extract_file(path)

        # Step 2: RAG
        rag_text = ""
        if use_rag.lower() == "true":
            try:
                kb = NovelKnowledgeBase()
                chapter_ctx = kb.retrieve_for_chapter(extraction["title"], n_results=5)
                style_refs = kb.retrieve_style_reference(platform)
                rag_text = kb.format_context(chapter_ctx + style_refs)
            except Exception:
                pass

        # Step 3: Templates
        engine = TemplateEngine()
        results = engine.fill_all(platform, extraction, novel_meta, rag_context=rag_text)

        # Step 4: Review (optional)
        if no_review.lower() != "true":
            from .utils.ollama_client import get_client
            from .agents.reviewer import ReviewAgent
            client = get_client()
            if client.health_check():
                reviewer = ReviewAgent(client=client)
                passed = []
                for r in results:
                    report = reviewer.review(
                        r["title"], r["body"], novel_meta.get("hashtags", [])
                    )
                    r["score"] = report.overall_score
                    r["passed"] = report.passed
                    r["compliance_issues"] = report.compliance_issues
                    r["quality_issues"] = report.quality_issues
                    r["suggestions"] = report.suggestions
                    if report.passed:
                        passed.append(r)
                if passed:
                    results = passed

        return {
            "chapter_title": extraction["title"],
            "one_liner": extraction["one_liner"],
            "platform": platform,
            "versions": results,
        }

    finally:
        # Clean up temp file
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass


# ─── Web UI ──────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def web_ui():
    """Simple web UI for novel copy generation."""
    return HTML_NOVEL_UI


HTML_NOVEL_UI = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XHS Agent - 小说宣发文案生成</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       background: #f5f0eb; color: #333; min-height: 100vh; }
.container { max-width: 900px; margin: 0 auto; padding: 2rem 1rem; }
header { text-align: center; margin-bottom: 2rem; }
header h1 { font-size: 1.8rem; color: #e74c3c; }
header p { color: #888; margin-top: .5rem; }
.card { background: #fff; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem;
        box-shadow: 0 2px 12px rgba(0,0,0,.06); }
.card h3 { margin-bottom: 1rem; color: #555; }
textarea { width: 100%; min-height: 200px; border: 2px solid #eee; border-radius: 8px;
           padding: 1rem; font-size: 14px; line-height: 1.8; resize: vertical;
           font-family: inherit; }
textarea:focus { outline: none; border-color: #e74c3c; }
input[type="file"] { margin: .5rem 0 1rem; }
.controls { display: flex; gap: 1rem; flex-wrap: wrap; align-items: center; margin-bottom: 1rem; }
.controls label { font-size: 14px; color: #666; }
.controls select, .controls input { padding: .5rem .8rem; border: 1px solid #ddd; border-radius: 6px;
                                    font-size: 14px; }
button { background: #e74c3c; color: #fff; border: none; padding: .7rem 2rem;
         border-radius: 8px; font-size: 15px; cursor: pointer; font-weight: 600; }
button:hover { background: #c0392b; }
button:disabled { background: #ccc; cursor: not-allowed; }
#spinner { display: none; text-align: center; padding: 2rem; color: #888; }
#results { display: none; }
.version { border: 1px solid #eee; border-radius: 10px; padding: 1.5rem; margin-bottom: 1rem;
           background: #fafafa; }
.version .vt { font-size: 1.1rem; font-weight: 700; color: #e74c3c; margin-bottom: .8rem; }
.version .vtitle { font-size: 1rem; font-weight: 600; color: #333; margin-bottom: .5rem; }
.version .vbody { white-space: pre-wrap; font-size: 14px; line-height: 1.8; color: #444; }
.version .vscore { display: inline-block; background: #27ae60; color: #fff; padding: 2px 10px;
                   border-radius: 12px; font-size: 13px; margin-top: .5rem; }
.version .vwarn { color: #e67e22; font-size: 13px; margin-top: .3rem; }
.version .vmeta { color: #888; font-size: 13px; margin-top: .8rem; border-top: 1px solid #eee;
                  padding-top: .5rem; }
.tabs { display: flex; gap: .5rem; margin-bottom: 1rem; }
.tab { padding: .5rem 1rem; border: none; border-radius: 6px; background: #eee; cursor: pointer;
       font-size: 14px; color: #555; }
.tab.active { background: #e74c3c; color: #fff; }
.error { color: #e74c3c; padding: 1rem; background: #fde8e8; border-radius: 8px; }
</style>
</head>
<body>

<div class="container">

<header>
  <h1>📝 XHS Agent</h1>
  <p>小说宣发文案生成器 — 输入章节，输出小红书/抖音文案</p>
</header>

<div class="card">
  <h3>📂 上传章节文件</h3>
  <input type="file" id="fileInput" accept=".md,.txt" onchange="loadFile()">
  <div style="color:#888;font-size:13px;margin-top:.3rem">支持 .md / .txt 格式</div>

  <h3 style="margin-top:1.2rem">✍️ 或直接粘贴内容</h3>
  <textarea id="textInput" placeholder="在此粘贴章节内容..."></textarea>

  <div class="controls" style="margin-top:1rem">
    <label>目标平台</label>
    <select id="platform">
      <option value="xiaohongshu">小红书</option>
      <option value="douyin">抖音</option>
      <option value="zhihu">知乎</option>
    </select>
    <label style="margin-left:1rem"><input type="checkbox" id="useRag" checked> RAG增强</label>
    <label><input type="checkbox" id="noReview"> 跳过审核</label>
  </div>

  <button id="generateBtn" onclick="generate()">🚀 生成文案</button>
</div>

<div id="spinner">⏳ 正在分析章节并生成文案，请耐心等待...</div>

<div id="error" class="error" style="display:none"></div>

<div id="results"></div>

</div>

<script>
async function loadFile() {
  const file = document.getElementById('fileInput').files[0];
  if (!file) return;
  const text = await file.text();
  document.getElementById('textInput').value = text;
}

async function generate() {
  const textInput = document.getElementById('textInput').value.trim();
  const fileInput = document.getElementById('fileInput').files[0];

  if (!textInput && !fileInput) {
    showError('请上传文件或粘贴章节内容');
    return;
  }

  const btn = document.getElementById('generateBtn');
  btn.disabled = true;
  document.getElementById('spinner').style.display = 'block';
  document.getElementById('results').style.display = 'none';
  document.getElementById('error').style.display = 'none';

  const form = new FormData();
  if (fileInput) {
    form.append('file', fileInput);
  } else {
    const blob = new Blob([textInput], {type: 'text/plain'});
    form.append('file', blob, 'chapter.txt');
  }
  form.append('platform', document.getElementById('platform').value);
  form.append('use_rag', document.getElementById('useRag').checked ? 'true' : 'false');
  form.append('no_review', document.getElementById('noReview').checked ? 'true' : 'false');

  try {
    const resp = await fetch('/novel/promote', { method: 'POST', body: form });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();

    let html = '';
    for (const v of data.versions || []) {
      html += '<div class="version">';
      html += '<div class="vt">' + escapeHtml(v.name || '版本') + '</div>';
      html += '<div class="vtitle">' + escapeHtml(v.title || '') + '</div>';
      html += '<div class="vbody">' + escapeHtml(v.body || '') + '</div>';
      if (v.score) {
        const color = v.score >= 70 ? '#27ae60' : '#e67e22';
        html += '<span class="vscore" style="background:' + color + '">审核: ' + v.score + '/100</span> ';
      }
      if (v.compliance_issues?.length) {
        html += '<div class="vwarn">⚠ ' + v.compliance_issues.join('; ') + '</div>';
      }
      if (v.cover_suggestion || v.publish_time_hint) {
        html += '<div class="vmeta">';
        if (v.cover_suggestion) html += '🖼 ' + escapeHtml(v.cover_suggestion) + '  ';
        if (v.publish_time_hint) html += '⏰ ' + escapeHtml(v.publish_time_hint);
        html += '</div>';
      }
      html += '</div>';
    }
    document.getElementById('results').innerHTML = html;
    document.getElementById('results').style.display = 'block';
  } catch(e) {
    showError('生成失败: ' + e.message);
  } finally {
    btn.disabled = false;
    document.getElementById('spinner').style.display = 'none';
  }
}

function showError(msg) {
  const el = document.getElementById('error');
  el.textContent = msg;
  el.style.display = 'block';
}

function escapeHtml(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
</script>

</body>
</html>"""
