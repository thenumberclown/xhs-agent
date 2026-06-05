"""CLI entry point for XHS Agent — AI copywriting assistant."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from .config import get_settings
from .storage.database import Database
from .storage.vector_store import get_vector_store
from .utils.ollama_client import get_client, OllamaClient

# Lazy imports for agent modules (not loaded until needed)
# to avoid circular imports

app = typer.Typer(
    name="xhs-agent",
    help="AI-powered copywriting agent for Xiaohongshu & Douyin",
)
console = Console()

# Subcommands
serve_app = typer.Typer()
import_cmd = typer.Typer()
track_cmd = typer.Typer()
stats_cmd = typer.Typer()

app.add_typer(serve_app, name="serve", help="Start API server")
app.add_typer(import_cmd, name="import", help="Import reference cases")
app.add_typer(track_cmd, name="track", help="Track post performance")
app.add_typer(stats_cmd, name="stats", help="View learning statistics")


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )


def _get_db() -> Database:
    return Database()


def _check_ollama() -> bool:
    client = get_client()
    if not client.health_check():
        console.print("[red]❌ Ollama 服务未运行[/red]")
        console.print("  请先启动: [bold]~/.ollama/bin/bin/ollama serve[/bold]")
        return False
    return True


# ─── Main generate command ────────────────────────────────────


@app.command()
def generate(
    product_name: str = typer.Option(..., "--product", "-p", help="产品名称"),
    product_desc: str = typer.Option(..., "--desc", "-d", help="产品描述"),
    platform: str = typer.Option("xiaohongshu", "--platform", help="目标平台 (xiaohongshu/douyin)"),
    audience: str = typer.Option("", "--audience", "-a", help="目标受众"),
    style: str = typer.Option("", "--style", "-s", help="风格要求"),
    versions: int = typer.Option(3, "--versions", "-v", help="生成版本数 (A/B测试)"),
    no_review: bool = typer.Option(False, "--no-review", help="跳过审核"),
) -> None:
    """生成宣发文案。输入产品信息，输出多版本文案。"""
    _setup_logging()
    logger = logging.getLogger(__name__)

    if not _check_ollama():
        raise typer.Exit(1)

    console.print(Panel.fit(
        f"[bold cyan]📝 XHS Agent — 文案生成[/bold cyan]\n"
        f"产品: {product_name}\n平台: {platform}\n目标: {audience or '通用'}",
        title="任务开始",
    ))

    # Lazy imports
    from .agents.research import ResearchAgent
    from .agents.analyzer import AnalyzeAgent
    from .agents.writer import WriteAgent
    from .agents.reviewer import ReviewAgent
    from .platforms.xiaohongshu import get_xhs, XiaohongshuPlatform

    db = _get_db()
    xhs = get_xhs()
    client = get_client()

    # Step 1: Research — get reference cases
    console.print("[bold]🔍 Step 1/5: 搜索参考案例...[/bold]")
    research = ResearchAgent(db=db)
    success_cases = research.get_success_cases(platform=platform, limit=5)
    all_cases = research.get_all_cases(platform=platform, limit=20)

    if not all_cases:
        console.print("[yellow]⚠️  未找到已有参考案例，将使用内置模板生成[/yellow]")
        console.print("  提示: 先用 [bold]xhs-agent import file --file cases.json[/bold] 导入案例")
    else:
        console.print(f"  ✓ 已加载 {len(all_cases)} 个参考案例 (其中 {len(success_cases)} 个成功案例)")

    # Step 2: Analyze — formulate strategy
    console.print("[bold]📊 Step 2/5: 分析案例 & 制定策略...[/bold]")
    analyzer = AnalyzeAgent(client=client)

    # Analyze success cases for insights
    if success_cases:
        analyses = analyzer.analyze_batch(success_cases)
        summary = analyzer.summarize_patterns(analyses)
        console.print(f"  ✓ 主流标题公式: {', '.join(summary.headline_formulas_used)}")
        console.print(f"  ✓ 推荐结构: {summary.structure_pattern}")
    else:
        summary = None

    strategy = analyzer.choose_strategy(
        product_name=product_name,
        product_desc=product_desc,
        target_audience=audience,
        style_notes=style,
        success_cases=research.format_for_prompt(success_cases),
    )
    console.print(f"  ✓ 策略: {strategy.content_type.value} / {strategy.headline_formula} / {strategy.tone}")

    # Step 3: Write — generate copy
    console.print("[bold]✍️  Step 3/5: 生成文案...[/bold]")
    writer = WriteAgent(client=client)

    headlines = writer.generate_headlines(
        product_name=product_name,
        product_desc=product_desc,
        strategy=strategy,
        count=5,
    )

    # Show top headlines
    for i, h in enumerate(headlines[:3]):
        console.print(f"  [{i+1}] {h.title} (评分: {h.score}/10)")

    # Generate copies for top-rated headlines
    copies = writer.generate_multi(
        product_name=product_name,
        product_desc=product_desc,
        strategy=strategy,
        headlines=headlines,
        examples=research.format_for_prompt(success_cases),
        max_versions=versions,
    )

    # Step 4: Review — quality check
    if not no_review:
        console.print("[bold]🔍 Step 4/5: 质量审核...[/bold]")
        reviewer = ReviewAgent(client=client)
        approved_copies = []

        for copy in copies:
            report = reviewer.review(copy.title, copy.body, copy.hashtags)
            copy.quality_score = float(report.overall_score)

            status_icon = "✅" if report.passed else "❌"
            console.print(
                f"  [{status_icon}] v{copy.version} 「{copy.title}」 得分: {report.overall_score}/100"
            )
            if report.similarity_warning:
                console.print(f"    [yellow]⚠️  {report.similarity_warning}[/yellow]")
            if report.compliance_issues:
                for issue in report.compliance_issues:
                    console.print(f"    [red]• {issue}[/red]")

            if report.passed:
                approved_copies.append(copy)

        if not approved_copies:
            console.print("[red]❌ 所有版本均未通过审核，请调整后重试[/red]")
            raise typer.Exit(1)
        copies = approved_copies
        console.print(f"  ✓ {len(copies)}/{len(copies)} 个版本通过审核")
    else:
        console.print("[dim]⏭️  Step 4/5: 跳过审核[/dim]")

    # Step 5: Save to database
    console.print("[bold]💾 Step 5/5: 保存结果...[/bold]")
    task_id = db.create_task({
        "product_name": product_name,
        "product_desc": product_desc,
        "platform": platform,
        "content_type": strategy.content_type.value if strategy.content_type else None,
        "target_audience": audience,
        "keywords": summary.top_keywords if summary else [],
        "style_notes": style,
        "status": "generated",
    })

    saved_ids = []
    for copy in copies:
        copy.task_id = task_id
        copy_id = db.save_copy({
            "task_id": task_id,
            "version": copy.version,
            "title": copy.title,
            "body": copy.body,
            "hashtags": copy.hashtags,
            "cover_suggestion": copy.cover_suggestion,
            "publish_time_hint": copy.publish_time_hint,
            "quality_score": copy.quality_score,
        })
        saved_ids.append(copy_id)

    console.print(f"  ✓ 任务 #{task_id} 已保存，{len(saved_ids)} 个版本 (IDs: {saved_ids})")

    # Display results
    console.print("\n" + "=" * 60)
    console.print("[bold green]📄 生成结果[/bold green]")
    console.print("=" * 60)

    for i, copy in enumerate(copies):
        output = xhs.format_output(
            title=copy.title,
            body=copy.body,
            hashtags=copy.hashtags,
            cover_hint=copy.cover_suggestion,
            publish_time=copy.publish_time_hint,
        )
        console.print(f"\n[bold]版本 {copy.version} (ID: {saved_ids[i]})[/bold]")
        console.print(output)

    console.print(f"\n[dim]任务ID: {task_id} | 发布后请用 [bold]xhs-agent track --copy-id <ID>[/bold] 追踪效果[/dim]")


# ─── Import commands ──────────────────────────────────────────


@import_cmd.command("file")
def import_file(
    filepath: Path = typer.Argument(..., help="JSON文件路径，包含案例数组"),
) -> None:
    """从JSON文件批量导入参考案例"""
    _setup_logging()

    if not filepath.exists():
        console.print(f"[red]❌ 文件不存在: {filepath}[/red]")
        raise typer.Exit(1)

    from .agents.research import ResearchAgent
    db = _get_db()
    research = ResearchAgent(db=db)
    ids = research.import_from_json(filepath)

    console.print(f"[green]✓ 成功导入 {len(ids)} 个案例[/green]")
    console.print(f"  案例 IDs: {ids}")


@import_cmd.command("single")
def import_single(
    title: str = typer.Option(..., "--title", "-t", help="标题"),
    body: str = typer.Option("", "--body", "-b", help="正文"),
    platform: str = typer.Option("xiaohongshu", "--platform", help="平台"),
    likes: int = typer.Option(0, "--likes", help="点赞数"),
    collects: int = typer.Option(0, "--collects", help="收藏数"),
    comments: int = typer.Option(0, "--comments", help="评论数"),
    quality: str = typer.Option("neutral", "--quality", "-q", help="质量标签 (success/neutral/failure)"),
) -> None:
    """手动录入单个参考案例"""
    _setup_logging()

    from .agents.research import ResearchAgent
    db = _get_db()
    research = ResearchAgent(db=db)
    ref_id = research.import_case(
        title=title,
        body=body,
        platform=platform,
        likes=likes,
        collects=collects,
        comments=comments,
        quality_label=quality,
    )

    console.print(f"[green]✓ 已导入案例 #{ref_id}: {title}[/green]")


# ─── Track commands ───────────────────────────────────────────


@track_cmd.command("record")
def track_record(
    copy_id: int = typer.Option(..., "--copy-id", "-c", help="文案ID"),
    likes: int = typer.Option(0, "--likes", help="点赞数"),
    collects: int = typer.Option(0, "--collects", help="收藏数"),
    comments: int = typer.Option(0, "--comments", help="评论数"),
    shares: int = typer.Option(0, "--shares", help="分享数"),
    views: int = typer.Option(0, "--views", help="曝光量"),
    notes: str = typer.Option("", "--notes", "-n", help="备注"),
    promote: bool = typer.Option(False, "--promote", help="如果表现好，自动提升为参考案例"),
) -> None:
    """记录文案发布后的表现数据"""
    _setup_logging()

    from .agents.tracker import TrackerAgent
    db = _get_db()
    tracker = TrackerAgent(db=db)

    perf_id = tracker.record_performance(
        copy_id=copy_id,
        likes=likes,
        collects=collects,
        comments=comments,
        shares=shares,
        views=views,
        notes=notes,
    )

    # Calculate CES
    xhs_ces = likes + collects + comments * 4 + shares * 4
    console.print(f"[green]✓ 已记录表现数据 (ID: {perf_id})[/green]")
    console.print(f"  CES 评分: {xhs_ces}")

    # Evaluate
    evaluation = tracker.evaluate_copy(copy_id)
    emoji = {"success": "🌟", "neutral": "📊", "pending": "⏳", "failure": "📉"}
    console.print(f"  评价: {emoji.get(evaluation, '?')} {evaluation}")

    # Auto-promote if successful
    if promote and evaluation == "success":
        ref_id = tracker.promote_to_reference(copy_id)
        if ref_id:
            console.print(f"[green]  ✓ 已自动提升为参考案例 #{ref_id}，将用于后续生成[/green]")
        else:
            console.print("[yellow]  ⚠ 未达到提升阈值[/yellow]")

    # Index in vector store
    tracker.index_successful_copy(copy_id)


# ─── Stats commands ───────────────────────────────────────────


@stats_cmd.command("show")
def stats_show(
    platform: str = typer.Option("xiaohongshu", "--platform", "-p", help="平台"),
) -> None:
    """查看学习统计"""
    _setup_logging()

    from .agents.tracker import TrackerAgent
    db = _get_db()
    tracker = TrackerAgent(db=db)
    stats = tracker.get_learning_stats(platform=platform)

    table = Table(title=f"📊 {platform} 学习统计")
    table.add_column("指标", style="cyan")
    table.add_column("数值", style="green")

    table.add_row("总任务数", str(stats["total"]))
    table.add_row("成功率", f"{stats['success_rate']}%")
    table.add_row("平均CES", str(stats["avg_ces"]))
    table.add_row("趋势", stats["trend"])
    table.add_row("近期成功率", f"{stats['recent_rate']}%")

    console.print(table)

    # Show top performing copies
    best = db.get_best_copies(platform=platform, limit=5)
    if best:
        console.print("\n[bold]🏆 Top 5 最佳文案:[/bold]")
        for i, c in enumerate(best):
            console.print(f"  [{i+1}] {c['title'][:50]}... (CES: {c.get('ces_score', 0):.1f})")


@stats_cmd.command("cases")
def stats_cases(
    platform: str = typer.Option("xiaohongshu", "--platform", "-p", help="平台"),
) -> None:
    """查看已收集的参考案例统计"""
    _setup_logging()
    db = _get_db()
    total = db.count_references(platform=platform)
    successes = len(db.list_references(platform=platform, quality_label="success"))
    failures = len(db.list_references(platform=platform, quality_label="failure"))

    console.print(f"[bold]📚 {platform} 参考案例库[/bold]")
    console.print(f"  总计: {total}")
    console.print(f"  成功: {successes} | 失败: {failures} | 中性: {total - successes - failures}")


# ─── Server commands ──────────────────────────────────────────


@serve_app.command("start")
def serve_start(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port"),
    workers: int = typer.Option(4, "--workers", "-w"),
) -> None:
    """启动 FastAPI 服务"""
    _setup_logging()
    import uvicorn
    console.print(f"[bold]🚀 XHS Agent API 启动: http://{host}:{port}[/bold]")
    console.print(f"[dim]文档: http://{host}:{port}/docs[/dim]")
    uvicorn.run("src.api:app", host=host, port=port, workers=workers, log_level="info")


# ─── Novel promotion commands ─────────────────────────────────


def _load_novel_profile(profile_path: str = "") -> dict:
    """Load novel metadata from a JSON profile file.

    Returns empty dict if file is missing, so template defaults kick in.
    """
    path = Path(profile_path) if profile_path else Path("data/novel_profile.json")
    if not path.exists():
        logger = logging.getLogger(__name__)
        logger.warning("Novel profile not found: %s, using template defaults", path)
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


novel_app = typer.Typer(help="小说宣发专用命令")
app.add_typer(novel_app, name="novel")


@novel_app.command("ingest")
def novel_ingest(
    chapters_dir: str = typer.Option(
        ..., "--chapters", "-c", help="章节目录路径"
    ),
    settings_dir: str = typer.Option(
        "", "--settings", "-s", help="设定文档目录路径（可选）"
    ),
    promo_file: str = typer.Option(
        "", "--promo", "-p", help="已有宣发文案文件路径（可选）"
    ),
) -> None:
    """将小说内容摄入到知识库（RAG）"""
    _setup_logging()

    from .agents.knowledge import NovelKnowledgeBase

    kb = NovelKnowledgeBase()

    chapters_path = Path(chapters_dir)
    if not chapters_path.exists():
        console.print(f"[red]❌ 章节目录不存在: {chapters_dir}[/red]")
        raise typer.Exit(1)

    # Ingest chapters
    with console.status("[bold]正在摄入章节..."):
        chunk_count = kb.ingest_directory(chapters_path, "*.md")

    console.print(f"[green]✓ 已摄入 {chunk_count} 个文本块[/green]")

    # Ingest settings
    if settings_dir:
        settings_path = Path(settings_dir)
        if settings_path.exists():
            with console.status("[bold]正在摄入设定文档..."):
                for fp in settings_path.glob("*.md"):
                    kb.ingest_settings(fp)
            console.print(f"[green]✓ 设定文档已摄入[/green]")

    # Ingest promo material
    if promo_file:
        promo_path = Path(promo_file)
        if promo_path.exists():
            with console.status("[bold]正在摄入宣发参考..."):
                kb.ingest_promo_material(promo_path)
            console.print(f"[green]✓ 宣发参考已摄入[/green]")

    # Show stats
    stats = kb.stats
    console.print(f"\n[bold]知识库状态:[/bold] {stats['total_chunks']} 个文本块")


@novel_app.command("extract")
def novel_extract(
    chapter_file: str = typer.Option(
        ..., "--chapter", "-c", help="章节文件路径"
    ),
    output_file: str = typer.Option(
        "", "--output", "-o", help="输出JSON文件路径（可选）"
    ),
) -> None:
    """提取章节关键信息（模板驱动）"""
    _setup_logging()

    from .agents.extractor import ChapterExtractor

    path = Path(chapter_file)
    if not path.exists():
        console.print(f"[red]❌ 文件不存在: {chapter_file}[/red]")
        raise typer.Exit(1)

    extractor = ChapterExtractor()

    with console.status("[bold]正在分析章节..."):
        result = extractor.extract_file(path)

    # Display
    console.print(f"\n[bold green]📋 {result['title']}[/bold green]")
    console.print(f"[cyan]一句话:[/cyan] {result['one_liner']}")
    console.print(f"\n[cyan]核心场景:[/cyan]")
    for s in result.get("core_scenes", []):
        console.print(f"  • {s[:100]}")
    console.print(f"\n[cyan]关键异常:[/cyan]")
    for a in result.get("anomalies", []):
        console.print(f"  • [{a.get('location', '?')}] {a.get('detail', a.get('what', ''))[:120]}")
    console.print(f"\n[cyan]角色高光:[/cyan]")
    for m in result.get("character_moments", []):
        console.print(f"  • {m.get('character', '?')}: {m.get('moment', '')[:100]}")
    console.print(f"\n[cyan]可引用金句:[/cyan]")
    for q in result.get("quotable_lines", []):
        console.print(f"  「{q[:120]}」")
    console.print(f"\n[cyan]钩子元素:[/cyan] {', '.join(result.get('hook_elements', []))}")

    if output_file:
        import json
        Path(output_file).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        console.print(f"\n[green]✓ 已保存到 {output_file}[/green]")


@novel_app.command("promote")
def novel_promote(
    chapter_file: str = typer.Option(
        ..., "--chapter", "-c", help="章节文件路径"
    ),
    profile: str = typer.Option(
        "", "--profile", help="小说配置文件路径（默认 data/novel_profile.json）"
    ),
    novel_name: str = typer.Option(
        "", "--name", "-n", help="小说名称（覆盖配置文件）"
    ),
    platform_name: str = typer.Option(
        "", "--site", help="发布平台名称（覆盖配置文件）"
    ),
    chapter_count: str = typer.Option(
        "", "--count", help="已更新章节数（覆盖配置文件）"
    ),
    target_platform: str = typer.Option(
        "xiaohongshu", "--platform", "-p", help="目标宣发平台"
    ),
    use_rag: bool = typer.Option(
        True, "--rag/--no-rag", help="是否使用RAG知识库增强"
    ),
    use_llm: bool = typer.Option(
        False, "--use-llm", help="使用LLM动态生成策略和标题（替代纯模板）"
    ),
    no_review: bool = typer.Option(
        False, "--no-review", help="跳过质量审核"
    ),
    output_dir: str = typer.Option(
        "", "--output", "-o", help="输出目录（默认打印到终端）"
    ),
) -> None:
    """一站式小说宣发文案生成（提取+模板+RAG+审核）"""
    _setup_logging()
    logger = logging.getLogger(__name__)

    from .agents.extractor import ChapterExtractor
    from .agents.templates import TemplateEngine
    from .agents.knowledge import NovelKnowledgeBase

    path = Path(chapter_file)
    if not path.exists():
        console.print(f"[red]❌ 文件不存在: {chapter_file}[/red]")
        raise typer.Exit(1)

    # Load novel profile
    profile_data = _load_novel_profile(profile)
    if not profile_data and not novel_name:
        console.print("[yellow]⚠️ 未找到配置文件且未指定 --name，将使用模板默认值[/yellow]")

    # Build novel_meta: profile data + CLI overrides
    novel_meta = dict(profile_data)  # Start with profile
    if novel_name:
        novel_meta["novel_name"] = novel_name
    if platform_name:
        novel_meta["platform_name"] = platform_name
    if chapter_count:
        novel_meta["chapter_count"] = chapter_count

    # Ensure closing_paragraph has interpolated values
    if "closing_paragraph" in novel_meta:
        novel_meta["closing_paragraph"] = novel_meta["closing_paragraph"].format(
            novel_name=novel_meta.get("novel_name", ""),
            chapter_count=novel_meta.get("chapter_count", ""),
        )

    console.print(f"[dim]📖 {novel_meta.get('novel_name', '未知')} | "
                  f"{novel_meta.get('platform_name', '未知')} | "
                  f"{novel_meta.get('chapter_count', '?')}章[/dim]")

    # Step 1: Extract chapter details
    console.print("[bold]📋 Step 1/4: 提取章节关键信息...[/bold]")
    extractor = ChapterExtractor()
    extraction = extractor.extract_file(path)

    console.print(f"  ✓ 章节: {extraction['title']}")
    console.print(f"  ✓ 一句话: {extraction['one_liner']}")
    console.print(f"  ✓ 发现 {len(extraction['anomalies'])} 个异常点, "
                  f"{len(extraction['quotable_lines'])} 条可引用金句")

    # Step 2: RAG retrieval (optional)
    if use_rag:
        console.print("[bold]🔍 Step 2/4: RAG检索相关知识...[/bold]")
        try:
            kb = NovelKnowledgeBase()
            chapter_context = kb.retrieve_for_chapter(extraction["title"], n_results=5)
            style_refs = kb.retrieve_style_reference(target_platform)

            if chapter_context:
                console.print(f"  ✓ 检索到 {len(chapter_context)} 个相关片段")
            if style_refs:
                console.print(f"  ✓ 检索到 {len(style_refs)} 个风格参考")

            rag_context = kb.format_context(chapter_context + style_refs)
        except Exception as e:
            console.print(f"  [yellow]⚠ RAG检索失败: {e}，跳过[/yellow]")
            rag_context = ""
    else:
        console.print("[dim]⏭️  Step 2/4: 跳过RAG[/dim]")
        rag_context = ""

    # Step 3: Fill templates (optionally with LLM strategy)
    console.print(f"[bold]✍️  Step 3/4: 生成 {target_platform} 宣发文案...[/bold]")

    if use_llm:
        client = get_client()
        if client.health_check():
            novel_meta = _apply_llm_strategy(client, extraction, novel_meta, target_platform)
        else:
            console.print("[yellow]⚠ Ollama 未运行，回退到纯模板模式[/yellow]")

    engine = TemplateEngine()
    results = engine.fill_all(target_platform, extraction, novel_meta, rag_context=rag_context)

    # Display results
    console.print(f"\n{'='*60}")
    for i, r in enumerate(results):
        console.print(f"\n[bold]版本 {i+1}: {r['name']}[/bold]")
        console.print(f"[bold]标题:[/bold] {r['title']}")
        console.print(f"\n{r['body']}")
        if r.get("cover_suggestion"):
            console.print(f"\n🖼️  封面建议: {r['cover_suggestion']}")
        if r.get("publish_time_hint"):
            console.print(f"⏰ 发布时机: {r['publish_time_hint']}")
        console.print(f"\n{'='*60}")

    # Step 4: Quality review
    if not no_review:
        console.print("[bold]🔍 Step 4/4: 质量审核...[/bold]")
        from .agents.reviewer import ReviewAgent

        client = get_client()
        if client.health_check():
            reviewer = ReviewAgent(client=client)

            passed_results = []
            for r in results:
                title = r.get("title", "")
                body = r.get("body", "")
                report = reviewer.review(title, body, novel_meta.get("hashtags", []))

                status_icon = "✅" if report.passed else "❌"
                console.print(
                    f"  [{status_icon}] {r['name']}: {report.overall_score}/100"
                )
                if report.compliance_issues:
                    for issue in report.compliance_issues:
                        console.print(f"    [red]• {issue}[/red]")
                if report.quality_issues:
                    for issue in report.quality_issues[:2]:
                        console.print(f"    [yellow]⚠ {issue}[/yellow]")
                if report.similarity_warning:
                    console.print(f"    [yellow]⚠ {report.similarity_warning}[/yellow]")

                if report.passed:
                    passed_results.append(r)

            if not passed_results:
                console.print("[red]❌ 所有版本均未通过审核[/red]")
                console.print("[yellow]建议: 调整 novel_profile.json 或使用 --no-review 跳过[/yellow]")
                raise typer.Exit(1)

            dropped = len(results) - len(passed_results)
            if dropped > 0:
                console.print(f"  [dim]已排除 {dropped} 个未通过版本[/dim]")
            results = passed_results
        else:
            console.print("[yellow]⚠ Ollama 未运行，跳过审核[/yellow]")
    else:
        console.print("[dim]⏭️  Step 4/4: 跳过审核[/dim]")

    # Save to files
    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        for i, r in enumerate(results):
            fname = f"{extraction['title']}_{target_platform}_v{i+1}.md"
            filepath = out_path / fname
            lines = [f"# {r['title']}", "", r['body']]
            if r.get("cover_suggestion"):
                lines.append(f"\n🖼️ 封面建议: {r['cover_suggestion']}")
            if r.get("publish_time_hint"):
                lines.append(f"⏰ 发布时机: {r['publish_time_hint']}")
            filepath.write_text("\n".join(lines), encoding="utf-8")
            console.print(f"  ✓ 已保存: {filepath}")

    console.print(f"\n[dim]提示: 如需调整风格，编辑 data/novel_profile.json 后重新运行。[/dim]")


# ─── LLM strategy helpers ───────────────────────────────────────


def _apply_llm_strategy(
    client,
    extraction: dict,
    novel_meta: dict,
    target_platform: str,
) -> dict:
    """Use novel-specific prompts to generate dynamic strategy and headlines.

    Mutates and returns novel_meta with LLM-generated content injected.
    """
    from .prompts.novel import (
        NOVEL_STRATEGY_SYSTEM, NOVEL_STRATEGY_USER,
        NOVEL_HEADLINE_SYSTEM, NOVEL_HEADLINE_USER,
    )

    console = Console()

    # Build selling points from extraction
    anomalies = extraction.get("anomalies", [])
    moments = extraction.get("character_moments", [])
    quotes = extraction.get("quotable_lines", [])

    selling_points = [
        f"章节: {extraction.get('title', '')}",
        f"一句话钩子: {extraction.get('one_liner', '')}",
    ]
    if anomalies:
        selling_points.append(f"关键异常: {anomalies[0].get('detail', '')[:100]}")
    if moments:
        selling_points.append(f"角色高光: {moments[0].get('moment', '')[:100]}")
    if quotes:
        selling_points.append(f"金句: {quotes[0][:100]}")

    # 1. LLM Strategy selection
    try:
        strategy = client.chat_json([
            {"role": "system", "content": NOVEL_STRATEGY_SYSTEM},
            {"role": "user", "content": NOVEL_STRATEGY_USER.format(
                product_name=novel_meta.get("novel_name", ""),
                product_desc=extraction.get("one_liner", ""),
                target_audience=f"{target_platform} 小说推荐受众",
                style_notes=f"本章情感走向: {extraction.get('emotional_arc', '')}",
                key_selling_points="\n".join(selling_points),
                success_cases="（使用内置模板参考）",
            )},
        ], temperature=0.5)

        novel_meta["llm_strategy"] = strategy
        console.print(f"  ✓ LLM策略: {strategy.get('content_type', '?')} / "
                      f"{strategy.get('headline_formula', '?')} / "
                      f"{strategy.get('tone', '?')}")
    except Exception as e:
        console.print(f"  [yellow]⚠ LLM策略生成失败: {e}[/yellow]")

    # 2. LLM Headline generation
    try:
        headlines_result = client.chat_json([
            {"role": "system", "content": NOVEL_HEADLINE_SYSTEM},
            {"role": "user", "content": NOVEL_HEADLINE_USER.format(
                product_name=novel_meta.get("novel_name", ""),
                key_selling_points="\n".join(selling_points),
                content_type=novel_meta.get("llm_strategy", {}).get(
                    "content_type", "emotional"
                ),
                target_audience=f"{target_platform} 用户",
                tone=novel_meta.get("llm_strategy", {}).get("tone", "亲切口语"),
                count=3,
            )},
        ], temperature=0.8)

        novel_meta["generated_headlines"] = headlines_result.get("candidates", [])
        if novel_meta["generated_headlines"]:
            console.print(f"  ✓ LLM生成了 {len(novel_meta['generated_headlines'])} 个候选标题")
    except Exception as e:
        console.print(f"  [yellow]⚠ LLM标题生成失败: {e}[/yellow]")

    return novel_meta


# ─── Setup command ────────────────────────────────────────────


@app.command()
def setup() -> None:
    """初始化环境：检查依赖、创建数据目录、初始化数据库"""
    _setup_logging()

    console.print("[bold]🔧 XHS Agent 初始化检查[/bold]\n")

    # Check Ollama
    client = get_client()
    if client.health_check():
        console.print("[green]✓[/green] Ollama 服务运行中")
        models = client.list_models()
        if models:
            console.print(f"  可用模型: {', '.join(models)}")
        else:
            console.print("  [yellow]⚠ 未检测到模型，请运行: ollama pull qwen3:8b[/yellow]")
    else:
        console.print("[red]✗[/red] Ollama 服务未运行")
        console.print("  请先启动: [bold]~/.ollama/bin/bin/ollama serve[/bold]")

    # Check database
    db = _get_db()
    try:
        db.init()
        console.print("[green]✓[/green] 数据库初始化成功")
    except Exception as e:
        console.print(f"[red]✗[/red] 数据库初始化失败: {e}")

    # Check vector store
    try:
        vs = get_vector_store()
        cases_count = vs.count_cases()
        copies_count = vs.count_copies()
        console.print(f"[green]✓[/green] 向量存储就绪 (案例: {cases_count}, 文案: {copies_count})")
    except Exception as e:
        console.print(f"[red]✗[/red] 向量存储初始化失败: {e}")

    # Check data dirs
    settings = get_settings()
    for d in [settings.data_dir, settings.cases_dir, settings.outputs_dir]:
        d.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓[/green] 目录: {d}")

    console.print("\n[bold green]初始化完成！[/bold green]")
    console.print("快速开始:")
    console.print("  1. 导入参考案例: [bold]xhs-agent import file --file cases.json[/bold]")
    console.print("  2. 生成文案:     [bold]xhs-agent generate -p '产品名' -d '产品描述'[/bold]")


# ─── Entry point ──────────────────────────────────────────────


def main() -> None:
    app()


if __name__ == "__main__":
    main()
