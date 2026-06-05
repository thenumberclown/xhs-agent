"""Image Gen Service — Web UI + ComfyUI bridge for novel promo images.

Self-contained. Uses Ollama for Chinese→English prompt translation.
ComfyUI API: POST /prompt → GET /history/{id} → GET /view
"""

from __future__ import annotations

import json
import os
import time
import uuid
import httpx
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, Response

COMFY = os.environ.get("COMFY_URL", "http://localhost:8188")
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")

app = FastAPI(title="宣发图片生成", version="0.1.0")

# ─── ComfyUI Client ──────────────────────────────────────────


def comfy_prompt(workflow: dict) -> str:
    """Submit workflow, return prompt_id."""
    r = httpx.post(f"{COMFY}/prompt", json={"prompt": workflow}, timeout=10)
    r.raise_for_status()
    return r.json()["prompt_id"]


def comfy_wait(prompt_id: str, timeout: int = 120) -> dict | None:
    """Poll until generation completes. Returns outputs dict or None if timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = httpx.get(f"{COMFY}/history/{prompt_id}", timeout=10)
        r.raise_for_status()
        data = r.json()
        if prompt_id in data:
            return data[prompt_id].get("outputs", {})
        time.sleep(2)
    return None


def comfy_image_url(filename: str, subfolder: str = "", img_type: str = "output") -> str:
    """Build URL to fetch generated image."""
    params = f"filename={filename}&type={img_type}"
    if subfolder:
        params += f"&subfolder={subfolder}"
    return f"{COMFY}/view?{params}"


# ─── Prompt Translation (Ollama) ─────────────────────────────


def translate_prompt(chinese: str, style: str = "") -> str:
    """Build SD English prompt from Chinese description + style template.

    Uses template-based construction for speed/reliability.
    Ollama-based translation available as fallback but adds latency.
    """
    if not chinese.strip():
        return ""

    style_keywords = {
        "dark": "dark atmospheric, cinematic lighting, gothic, Cthulhu horror vibes, moody, fog, mysterious",
        "warm": "warm tones, cozy atmosphere, soft golden lighting, magical realism, ethereal glow",
        "book": "book cover design, elegant composition, minimalist, literary aesthetic, clean typography space",
        "poster": "movie poster style, dramatic composition, bold, eye-catching, cinematic",
    }

    quality = "highly detailed, 8k, sharp focus, professional"
    style_suffix = style_keywords.get(style, "")
    prompt = f"{chinese}, {style_suffix}, {quality}".strip(", ")

    # Try Ollama enhancement in background, but use template result immediately
    try:
        sys_prompt = (
            "You are a SD prompt expert. Enhance this prompt to be more descriptive and visual. "
            "Add sensory details, lighting, composition. Output ONLY the enhanced English prompt, "
            "no explanation. Keep under 150 words."
        )
        r = httpx.post(
            f"{OLLAMA}/api/chat",
            json={
                "model": "qwen3:4b",
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"Enhance: {prompt}"},
                ],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 150},
            },
            timeout=30,
        )
        r.raise_for_status()
        enhanced = r.json()["message"]["content"].strip()
        if enhanced and len(enhanced) > 10:
            return enhanced
    except Exception:
        pass

    return prompt


# ─── Workflow Builder ────────────────────────────────────────


def build_workflow(
    positive: str,
    negative: str = "",
    width: int = 512,
    height: int = 768,
    steps: int = 20,
    cfg: float = 7.0,
    seed: int = -1,
) -> dict:
    """Build a simple txt2img ComfyUI workflow JSON for SDXL Turbo."""
    if seed < 0:
        seed = hash(uuid.uuid4()) % (2**31)

    # SDXL Turbo works best with low steps and low CFG
    actual_steps = min(steps, 8)  # Turbo doesn't need many steps
    actual_cfg = 1.5  # Turbo models work best with CFG ~1.0-2.0

    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "dreamshaperXL_sfwTurboDpmppSDE.safetensors"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": positive, "clip": ["1", 1]},
            "_meta": {"title": "Positive Prompt"},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative or "low quality, blurry, distorted, ugly, bad anatomy, watermark, text",
                "clip": ["1", 1],
            },
            "_meta": {"title": "Negative Prompt"},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": actual_steps,
                "cfg": actual_cfg,
                "sampler_name": "dpmpp_sde",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "xhs_promo", "images": ["6", 0]},
        },
    }


# ─── Routes ─────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


@app.post("/generate")
async def generate(
    prompt_cn: str = Form(""),
    image_type: str = Form("cover"),
    style: str = Form("dark"),
    width: int = Form(512),
    height: int = Form(768),
    steps: int = Form(20),
):
    """Generate an image via ComfyUI."""
    if not prompt_cn.strip():
        return {"error": "请输入画面描述"}

    # Translate prompt
    en_prompt = translate_prompt(prompt_cn, style)

    # Build type-specific prefix
    type_hint = {
        "cover": "book cover design, no text, atmospheric, ",
        "quote": "clean background with space for text, minimal, ",
        "scene": "cinematic scene, story illustration, ",
        "character": "character portrait, detailed face, fantasy, ",
    }.get(image_type, "")

    full_prompt = type_hint + en_prompt

    # Image size by type
    sizes = {
        "cover": (512, 768),    # 3:4 portrait
        "quote": (512, 512),    # 1:1 square
        "scene": (768, 512),    # 4:3 landscape
        "character": (512, 768),
    }
    w, h = sizes.get(image_type, (512, 768))

    # Build and submit workflow
    workflow = build_workflow(positive=full_prompt, width=w, height=h, steps=steps)
    print(f"DEBUG prompt: {full_prompt[:100]}", flush=True)
    print(f"DEBUG workflow preview: {json.dumps(workflow)[:300]}", flush=True)
    pid = comfy_prompt(workflow)

    # Wait for result
    outputs = comfy_wait(pid, timeout=180)
    if not outputs:
        return {"error": "生成超时，请重试"}

    # Extract image info
    images = []
    for node_id, output in outputs.items():
        for img in output.get("images", []):
            images.append({
                "filename": img["filename"],
                "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output"),
                "url": comfy_image_url(img["filename"], img.get("subfolder", ""), img.get("type", "output")),
            })

    return {
        "success": True,
        "prompt_id": pid,
        "en_prompt": full_prompt,
        "images": images,
    }


@app.get("/proxy-image")
async def proxy_image(filename: str, subfolder: str = "", img_type: str = "output"):
    """Proxy ComfyUI images to avoid CORS issues."""
    url = comfy_image_url(filename, subfolder, img_type)
    r = httpx.get(url, timeout=10)
    return Response(content=r.content, media_type="image/png")


# ─── HTML UI ─────────────────────────────────────────────────


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🖼 宣发图片生成</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;background:#f0ebe3;color:#333}
.topbar{background:#fff;padding:.8rem 1.5rem;display:flex;align-items:center;gap:1rem;box-shadow:0 1px 4px rgba(0,0,0,.05)}
.topbar h1{font-size:1.2rem;color:#e74c3c}
.main{max-width:1000px;margin:0 auto;padding:1.5rem;display:flex;gap:1.5rem;flex-wrap:wrap}
.panel{flex:1;min-width:300px}
.card{background:#fff;border-radius:12px;padding:1.2rem;margin-bottom:1rem;box-shadow:0 2px 8px rgba(0,0,0,.04)}
.card h3{font-size:14px;color:#888;margin-bottom:.8rem;text-transform:uppercase;letter-spacing:1px}
label{display:block;font-size:13px;color:#666;margin:.6rem 0 .3rem}
select,input[type="text"],textarea{width:100%;padding:.5rem .8rem;border:1px solid #ddd;border-radius:6px;font-size:14px;font-family:inherit}
textarea{min-height:80px;resize:vertical}
textarea:focus,select:focus,input:focus{outline:none;border-color:#e74c3c}
.row{display:flex;gap:.5rem}
.row>*{flex:1}
.btn{background:#e74c3c;color:#fff;border:none;padding:.6rem 1.5rem;border-radius:8px;cursor:pointer;font-size:15px;font-weight:600;width:100%}
.btn:hover{background:#c0392b}
.btn:disabled{background:#ccc;cursor:not-allowed}
.result{margin-top:1rem;text-align:center}
.result img{max-width:100%;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.1)}
.spinner{text-align:center;padding:2rem;color:#888}
.spinner .dot{display:inline-block;width:12px;height:12px;border-radius:50%;background:#e74c3c;margin:0 4px;animation:bounce 1.4s infinite}
.spinner .dot:nth-child(2){animation-delay:.2s}.spinner .dot:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}
.error{color:#e74c3c;padding:1rem;text-align:center}
.hint{font-size:12px;color:#999;margin-top:3px}
.prompt-box{background:#f8f8f8;padding:.8rem;border-radius:6px;font-size:12px;color:#555;margin-top:.5rem;word-break:break-all;max-height:80px;overflow-y:auto}
.quick-tags{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.5rem}
.quick-tag{font-size:12px;padding:.25rem .6rem;background:#fde8e8;color:#e74c3c;border-radius:12px;cursor:pointer;border:none}
.quick-tag:hover{background:#e74c3c;color:#fff}
</style>
</head>
<body>
<div class="topbar"><h1>🖼 宣发图片生成</h1><span style="font-size:12px;color:#999">基于 ComfyUI</span></div>

<div class="main">
<div class="panel">
  <div class="card">
    <h3>📝 图片描述</h3>
    <label>图片类型</label>
    <select id="imgType">
      <option value="cover">封面标题图 (3:4)</option>
      <option value="quote">金句卡片 (1:1)</option>
      <option value="scene">场景氛围图 (4:3)</option>
      <option value="character">角色画像 (3:4)</option>
    </select>

    <label>画面描述（中文即可）</label>
    <textarea id="promptCn" placeholder="例如：暗黑风格的霍格沃茨城堡，月光透过窗户照进来，地面上有诡异的符文在发光，克苏鲁风格的恐怖氛围"></textarea>

    <label>风格</label>
    <select id="style">
      <option value="dark">暗黑克苏鲁</option>
      <option value="warm">温暖魔法</option>
      <option value="book">书封设计</option>
      <option value="poster">海报风格</option>
    </select>

    <div style="display:flex;gap:.5rem;margin-top:.8rem">
      <div style="flex:1"><label>步数</label><input type="number" id="steps" value="20" min="10" max="50"></div>
    </div>

    <button class="btn" id="genBtn" onclick="generate()" style="margin-top:1rem">🚀 生成图片</button>
  </div>

  <div class="card">
    <h3>🎯 快捷描述</h3>
    <div class="quick-tags">
      <button class="quick-tag" onclick="fill('dark Hogwarts castle, ancient stone door with glowing runes, Cthulhu atmosphere, moonlight')">霍格沃茨石门</button>
      <button class="quick-tag" onclick="fill('mysterious underground chamber, circular stone pattern on floor, eerie blue light, tentacle shadows')">地下密室</button>
      <button class="quick-tag" onclick="fill('old wizard reading forbidden book in library, floating candles, dark magic energy, dust motes in light')">禁书区探索</button>
      <button class="quick-tag" onclick="fill('young man with notebook, observing magical world, analytical gaze, wizard robe, Hogwarts background')">档案员林默</button>
      <button class="quick-tag" onclick="fill('golden letters on dark parchment background, elegant typography space, magical sparkles, book aesthetic')">金句卡片</button>
    </div>
  </div>
</div>

<div class="panel">
  <div class="card">
    <h3>🖼 生成结果</h3>
    <div id="result">
      <div style="text-align:center;color:#bbb;padding:3rem 1rem">
        <div style="font-size:3rem">🖼</div>
        <p style="margin-top:.5rem">输入描述，点击生成</p>
      </div>
    </div>
    <div id="promptInfo" style="display:none" class="prompt-box"></div>
  </div>
</div>
</div>

<script>
function fill(text) {
  document.getElementById('promptCn').value = text;
}

async function generate() {
  var promptCn = document.getElementById('promptCn').value.trim();
  if (!promptCn) { alert('请输入画面描述'); return; }

  var btn = document.getElementById('genBtn');
  btn.disabled = true; btn.textContent = '⏳ 生成中...';
  document.getElementById('result').innerHTML = '<div class="spinner"><div class="dot"></div><div class="dot"></div><div class="dot"></div><p style="margin-top:1rem">AI 正在生成图片，约需 30-120 秒...</p></div>';

  try {
    var form = new FormData();
    form.append('prompt_cn', promptCn);
    form.append('image_type', document.getElementById('imgType').value);
    form.append('style', document.getElementById('style').value);
    form.append('steps', document.getElementById('steps').value);

    var r = await fetch('/generate', { method: 'POST', body: form });
    var d = await r.json();
    if (d.error) { showError(d.error); return; }

    var html = '';
    for (var i = 0; i < (d.images||[]).length; i++) {
      html += '<img src="/proxy-image?filename=' + encodeURIComponent(d.images[i].filename) + '&subfolder=' + encodeURIComponent(d.images[i].subfolder||'') + '&img_type=' + encodeURIComponent(d.images[i].type||'output') + '" alt="生成图片" style="max-width:100%;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.1)">';
      html += '<div style="margin-top:.5rem"><a href="/proxy-image?filename=' + encodeURIComponent(d.images[i].filename) + '&subfolder=' + encodeURIComponent(d.images[i].subfolder||'') + '&img_type=' + encodeURIComponent(d.images[i].type||'output') + '" download style="color:#27ae60;font-size:13px;text-decoration:none">⬇ 下载图片</a></div>';
    }
    document.getElementById('result').innerHTML = html;

    var pi = document.getElementById('promptInfo');
    pi.style.display = 'block';
    pi.innerHTML = '<strong>英文提示词:</strong> ' + esc(d.en_prompt || '');

  } catch(e) {
    showError('请求失败: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = '🚀 生成图片';
  }
}

function showError(msg) {
  document.getElementById('result').innerHTML = '<div class="error">❌ ' + esc(msg) + '</div>';
}

function esc(s) { if(!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="info")
