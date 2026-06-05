"""Video Generator — image slideshow + emotional TTS + subtitles → MP4.

Requires: edge-tts, ffmpeg (installed in Docker).
No GPU needed.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse

app = FastAPI(title="视频生成工具", version="0.1.0")

TTS_VOICES = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",    # 女声 活泼自然
    "yunxi": "zh-CN-YunxiNeural",          # 男声 沉稳专业
    "xiaochen": "zh-CN-XiaochenNeural",    # 女声 青春活力
    "yunyang": "zh-CN-YunyangNeural",      # 男声 新闻播报
    "xiaohan": "zh-CN-XiaohanNeural",      # 女声 温柔
}
TTS_RATE = {"慢": "-15%", "稍慢": "-8%", "正常": "+0%", "稍快": "+8%", "快": "+15%"}

# ─── SSML: Smart Emotion Injection ───────────────────────────


def build_ssml(text: str, voice: str = "xiaoxiao", rate: str = "正常") -> str:
    """Auto-inject SSML emotions based on text punctuation and keywords."""
    voice_name = TTS_VOICES.get(voice, TTS_VOICES["xiaoxiao"])
    rate_val = TTS_RATE.get(rate, "+0%")

    # Split into sentences, assign emotion per sentence
    sentences = re.split(r"(?<=[。！？\n])", text)
    segments = []

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue

        # Detect emotion from content
        emotion, degree = _detect_emotion(sent)

        # Add emphasis on keywords
        sent = _add_emphasis(sent)

        if emotion:
            segments.append(
                f'<mstts:express-as style="{emotion}" styledegree="{degree}">'
                f'<prosody rate="{rate_val}">{sent}</prosody>'
                f"</mstts:express-as>"
            )
        else:
            segments.append(f'<prosody rate="{rate_val}">{sent}</prosody>')

        # Add pause between sentences
        segments.append('<break time="400ms"/>')

    ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
       xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="zh-CN">
  <voice name="{voice_name}">
    {" ".join(segments)}
  </voice>
</speak>"""
    return ssml


def _detect_emotion(sent: str) -> tuple[str | None, int]:
    """Detect emotional style from sentence content."""
    # Excitement markers
    if re.search(r"[！!]{1,}|千万别|太.*了|绝了|震惊|惊人|竟然|居然|不可思议", sent):
        return ("excited", 2)
    # Question → friendly rising tone
    if re.search(r"[？?]", sent):
        return ("friendly", 2)
    # Suspense → gentle mysterious
    if re.search(r"……|\.\.\.|——|突然|发现|真相|谜|秘密|隐藏|地下|深处|暗", sent):
        return ("gentle", 1)
    # Emphasis markers
    if re.search(r"最|第一|不是.*而是|重要|关键|必须|一定", sent):
        return ("friendly", 2)
    # Sad/emotional
    if re.search(r"眼泪|哭|悲伤|难过|走不出来|缓了|失眠", sent):
        return ("sad", 1)
    # Shocking reveal
    if re.search(r"注意|警告|小心|别|不要|千万", sent):
        return ("excited", 2)

    return (None, 1)


def _add_emphasis(sent: str) -> str:
    """Add SSML emphasis on key novel-related terms."""
    keywords = [
        "守秘人", "林默", "档案科", "霍格沃茨", "克苏鲁", "异常", "记录",
        "伏笔", "细节", "真相", "封印", "石门", "地下", "笔记",
    ]
    for kw in keywords:
        if kw in sent:
            sent = sent.replace(kw, f'<emphasis level="strong">{kw}</emphasis>')
    return sent


# ─── Subtitle Generation ────────────────────────────────────


def generate_srt(text: str, duration_sec: float) -> str:
    """Generate SRT subtitles from text, timed to audio duration."""
    # Split into subtitle-sized chunks (max 20 chars per line for mobile)
    chunks = _chunk_for_subtitle(text, max_chars=18)

    if not chunks:
        return ""

    # Distribute evenly across duration
    time_per_chunk = duration_sec / len(chunks)

    lines = []
    for i, chunk in enumerate(chunks):
        start = i * time_per_chunk
        end = (i + 1) * time_per_chunk
        lines.append(f"{i + 1}")
        lines.append(f"{_fmt_time(start)} --> {_fmt_time(end)}")
        lines.append(chunk)
        lines.append("")

    return "\n".join(lines)


def _chunk_for_subtitle(text: str, max_chars: int = 18) -> list[str]:
    """Split text into mobile-friendly subtitle chunks."""
    # First split by sentences
    raw = re.split(r"(?<=[。！？，,、])", text)
    chunks = []
    current = ""
    for seg in raw:
        seg = seg.strip()
        if not seg:
            continue
        if len(current) + len(seg) <= max_chars:
            current += seg
        else:
            if current:
                chunks.append(current)
            # If single segment too long, split by word boundary
            if len(seg) > max_chars:
                for i in range(0, len(seg), max_chars):
                    chunks.append(seg[i : i + max_chars])
            else:
                current = seg
    if current:
        chunks.append(current)
    return chunks


def _fmt_time(sec: float) -> str:
    """Format seconds to SRT timestamp."""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ─── FFmpeg Video Assembly ──────────────────────────────────


def get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def make_video(
    images: list[str],
    audio_path: str,
    srt_path: str,
    output_path: str,
    title_text: str = "",
) -> bool:
    """Assemble video: images slideshow + audio + subtitles."""
    duration = get_audio_duration(audio_path)
    img_count = len(images)
    if img_count == 0 or duration <= 0:
        return False

    time_per_img = duration / img_count
    fade_ms = min(0.3, time_per_img * 0.15)  # 15% fade, max 0.3s

    # Build ffmpeg filter for image slideshow with Ken Burns zoom
    img_inputs = []
    filter_parts = []

    for i, img in enumerate(images):
        img_inputs.extend(["-loop", "1", "-t", str(time_per_img), "-i", img])

    # Complex filter: zoompan each image + concat
    for i in range(img_count):
        # Ken Burns: subtle zoom in (1.0 → 1.05) over the image duration
        zoom_filter = (
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,"
            f"zoompan=z='min(zoom+0.0003,1.05)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s=1080x1920:fps=30,"
            f"trim=duration={time_per_img},"
            f"fade=t=in:d={fade_ms}:alpha=0,"
            f"fade=t=out:d={fade_ms}:alpha=0,"
            f"setpts=PTS-STARTPTS[v{i}];"
        )
        filter_parts.append(zoom_filter)

    concat_inputs = "".join(f"[v{i}]" for i in range(img_count))
    filter_parts.append(f"{concat_inputs}concat=n={img_count}:v=1:a=0[outv]")

    filter_str = ";".join(filter_parts)

    # Subtitles: burn into video
    # Escape SRT path for FFmpeg
    subtitle_filter = f"subtitles={srt_path}:force_style='FontSize=14,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=1.5,Alignment=2,MarginV=80'"

    cmd = [
        "ffmpeg", "-y",
        *img_inputs,
        "-i", audio_path,
        "-filter_complex", filter_str,
        "-map", "[outv]",
        "-map", f"{img_count}:a",
        "-vf", subtitle_filter,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr[:500]}")
        return False
    return True


# ─── Routes ─────────────────────────────────────────────────


JOB_DIR = Path("/tmp/video_jobs")
JOB_DIR.mkdir(exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


@app.post("/generate-video")
async def generate_video(
    text: str = Form(""),
    title: str = Form(""),
    voice: str = Form("xiaoxiao"),
    rate: str = Form("正常"),
    images: list[UploadFile] = File([]),
):
    """Generate video from images + text."""
    if not text.strip():
        return {"error": "请输入口播文案"}
    if not images:
        return {"error": "请上传至少1张图片"}

    job_id = uuid.uuid4().hex[:12]
    work_dir = JOB_DIR / job_id
    work_dir.mkdir()

    try:
        # 1. Save images
        img_paths = []
        for i, img in enumerate(images):
            ext = Path(img.filename or "img.jpg").suffix or ".jpg"
            fpath = work_dir / f"img_{i:02d}{ext}"
            content = await img.read()
            fpath.write_bytes(content)
            img_paths.append(str(fpath))

        # 2. TTS with SSML
        ssml = build_ssml(text, voice, rate)
        ssml_path = work_dir / "script.ssml"
        ssml_path.write_text(ssml, encoding="utf-8")
        audio_path = work_dir / "audio.mp3"

        # Save SSML to temp file (edge-tts can read from file)
        result = subprocess.run(
            ["edge-tts", "--voice", TTS_VOICES.get(voice, TTS_VOICES["xiaoxiao"]),
             "-f", str(ssml_path), "--write-media", str(audio_path)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return {"error": f"TTS失败: {result.stderr[:200]}"}

        # 3. Get audio duration
        duration = get_audio_duration(str(audio_path))

        # 4. Generate SRT subtitles
        srt_content = generate_srt(text, duration)
        srt_path = work_dir / "subtitle.srt"
        srt_path.write_text(srt_content, encoding="utf-8")

        # 5. Assemble video
        output_path = work_dir / "output.mp4"
        if not make_video(img_paths, str(audio_path), str(srt_path), str(output_path), title):
            return {"error": "视频合成失败"}

        # 6. Return download URL
        return {
            "success": True,
            "job_id": job_id,
            "duration": round(duration, 1),
            "ssml_preview": ssml[:300],
            "download_url": f"/download/{job_id}",
        }

    except Exception as e:
        return {"error": str(e)}


@app.get("/download/{job_id}")
async def download_video(job_id: str):
    """Download generated video."""
    video_path = JOB_DIR / job_id / "output.mp4"
    if not video_path.exists():
        return {"error": "视频不存在或已过期"}
    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        filename=f"xhs_promo_{job_id}.mp4",
    )


# ─── HTML UI ─────────────────────────────────────────────────


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🎬 视频生成</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;background:#f0ebe3;color:#333}
.topbar{background:#fff;padding:.8rem 1.5rem;display:flex;align-items:center;gap:1rem;box-shadow:0 1px 4px rgba(0,0,0,.05)}
.topbar h1{font-size:1.2rem;color:#e74c3c}
.main{max-width:1000px;margin:0 auto;padding:1.5rem;display:flex;gap:1.5rem;flex-wrap:wrap}
.panel{flex:1;min-width:300px}
.card{background:#fff;border-radius:12px;padding:1.2rem;margin-bottom:1rem;box-shadow:0 2px 8px rgba(0,0,0,.04)}
.card h3{font-size:14px;color:#888;margin-bottom:.8rem}
label{display:block;font-size:13px;color:#666;margin:.6rem 0 .3rem}
textarea,input[type="text"],select{width:100%;padding:.5rem .8rem;border:1px solid #ddd;border-radius:6px;font-size:14px;font-family:inherit}
textarea{min-height:150px;resize:vertical}
textarea:focus,select:focus,input:focus{outline:none;border-color:#e74c3c}
.row{display:flex;gap:.5rem}.row>*{flex:1}
.btn{background:#e74c3c;color:#fff;border:none;padding:.6rem 1.5rem;border-radius:8px;cursor:pointer;font-size:15px;font-weight:600;width:100%}
.btn:hover{background:#c0392b}.btn:disabled{background:#ccc}
.file-drop{border:2px dashed #ddd;border-radius:8px;padding:1.5rem;text-align:center;cursor:pointer;transition:.2s}
.file-drop:hover{border-color:#e74c3c;background:#fff5f5}
.file-drop.has{padding:.5rem;text-align:left;border-color:#27ae60}
.file-drop .placeholder{color:#aaa;font-size:14px}
.file-preview{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.5rem}
.file-preview img{width:60px;height:80px;object-fit:cover;border-radius:4px}
.spinner{text-align:center;padding:2rem}
.spinner .dot{display:inline-block;width:12px;height:12px;border-radius:50%;background:#e74c3c;margin:0 4px;animation:bounce 1.4s infinite}
.spinner .dot:nth-child(2){animation-delay:.2s}.spinner .dot:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}
.result video{width:100%;max-width:360px;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.1)}
.result .dl{display:inline-block;margin-top:.5rem;padding:.4rem 1rem;background:#27ae60;color:#fff;text-decoration:none;border-radius:6px;font-size:14px}
</style>
</head>
<body>
<div class="topbar"><h1>🎬 视频生成</h1><span style="font-size:12px;color:#999">图片轮播 + 情感配音 + 字幕</span></div>

<div class="main">
<div class="panel">
  <div class="card">
    <h3>🖼 上传图片 (1-9张，9:16竖版)</h3>
    <div class="file-drop" id="dropZone" onclick="document.getElementById('imgInput').click()">
      <div class="placeholder" id="dropText">点击或拖拽上传图片</div>
      <div class="file-preview" id="imgPreview"></div>
    </div>
    <input type="file" id="imgInput" multiple accept="image/*" style="display:none" onchange="handleImages()">
  </div>

  <div class="card">
    <h3>🎙 配音设置</h3>
    <div class="row">
      <div><label>音色</label><select id="voice"><option value="xiaoxiao">活泼女声 (推荐)</option><option value="yunxi">沉稳男声</option><option value="xiaochen">青春女声</option><option value="xiaohan">温柔女声</option><option value="yunyang">新闻男声</option></select></div>
      <div><label>语速</label><select id="rate"><option value="正常" selected>正常</option><option value="稍慢">稍慢</option><option value="稍快">稍快</option><option value="慢">慢</option><option value="快">快</option></select></div>
    </div>
  </div>
</div>

<div class="panel">
  <div class="card">
    <h3>📝 口播文案</h3>
    <textarea id="textInput" placeholder="粘贴口播文案...

标点符号会自动触发情感：
！→ 兴奋  ？→ 上扬  ……→ 悬念  关键词自动加重音

示例:
千万别在深夜打开这本小说！
主角林默，前世档案科科长。穿越成了霍格沃茨的孤儿。
他的金手指不是系统——是一双看了八年档案的眼睛。
他发现，所有异常点在地图上连成一个圆。圆心就在地下。</textarea>
    <button class="btn" id="genBtn" onclick="generate()" style="margin-top:1rem">🎬 生成视频</button>
  </div>

  <div class="card">
    <h3>📹 生成结果</h3>
    <div class="result" id="result">
      <div style="text-align:center;color:#bbb;padding:2rem">
        <div style="font-size:3rem">🎬</div><p>上传说图片和文案，点击生成</p>
      </div>
    </div>
  </div>
</div>
</div>

<script>
var imageFiles = [];

function handleImages() {
  var files = document.getElementById('imgInput').files;
  imageFiles = Array.from(files).slice(0, 9);
  var dz = document.getElementById('dropZone');
  var dt = document.getElementById('dropText');
  var pv = document.getElementById('imgPreview');

  if (imageFiles.length > 0) {
    dz.classList.add('has');
    dt.textContent = imageFiles.length + ' 张图片已选择';
    pv.innerHTML = imageFiles.map(function(f) {
      return '<img src="' + URL.createObjectURL(f) + '" alt="preview">';
    }).join('');
  } else {
    dz.classList.remove('has');
    dt.textContent = '点击或拖拽上传图片';
    pv.innerHTML = '';
  }
}

async function generate() {
  var text = document.getElementById('textInput').value.trim();
  if (!text) { alert('请输入口播文案'); return; }
  if (!imageFiles.length) { alert('请上传至少1张图片'); return; }

  var btn = document.getElementById('genBtn');
  btn.disabled = true; btn.textContent = '⏳ 生成中...约30-60秒';
  document.getElementById('result').innerHTML = '<div class="spinner"><div class="dot"></div><div class="dot"></div><div class="dot"></div><p style="margin-top:1rem">正在合成视频...</p></div>';

  try {
    var form = new FormData();
    form.append('text', text);
    form.append('voice', document.getElementById('voice').value);
    form.append('rate', document.getElementById('rate').value);
    imageFiles.forEach(function(f) { form.append('images', f); });

    var r = await fetch('/generate-video', { method:'POST', body:form });
    var d = await r.json();
    if (d.error) { document.getElementById('result').innerHTML = '<div style="color:#e74c3c">❌ ' + esc(d.error) + '</div>'; return; }

    document.getElementById('result').innerHTML =
      '<video src="' + d.download_url + '" controls style="max-width:100%;max-height:500px;border-radius:8px"></video>' +
      '<div style="margin-top:.5rem"><a href="' + d.download_url + '" download class="dl">⬇ 下载视频 (' + d.duration + '秒)</a></div>' +
      '<div style="font-size:11px;color:#999;margin-top:.3rem">SSML: ' + esc((d.ssml_preview||'').substring(0,200)) + '...</div>';
  } catch(e) {
    document.getElementById('result').innerHTML = '<div style="color:#e74c3c">❌ ' + esc(e.message) + '</div>';
  } finally {
    btn.disabled = false; btn.textContent = '🎬 生成视频';
  }
}

function esc(s) { if(!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003, log_level="info")
