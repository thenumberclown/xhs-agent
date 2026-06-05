"""Format Server v2 — paste once, see 8 templates with scores, pick best.

Usage: python -m src.format_server  → http://localhost:8001
"""

from __future__ import annotations

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from .formatter import format_all

app = FastAPI(title="文案排版工具 v2", version="0.2.0")


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


@app.post("/format-all")
async def format_all_api(
    text: str = Form(""),
    platform: str = Form("xiaohongshu"),
):
    results = format_all(text, platform)
    return {
        "results": [
            {
                "id": r.template_id,
                "name": r.template_name,
                "icon": r.template_icon,
                "title": r.title,
                "body": r.body,
                "tags": r.tags,
                "formatted_text": r.formatted_text,
                "score": r.score,
                "score_detail": r.score_detail,
                "warnings": r.warnings,
                "images": r.image_suggestions,
            }
            for r in results
        ]
    }


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🎨 文案排版工具</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
       background: #f0ebe3; color: #333; }
.topbar { background: #fff; padding: .8rem 1.5rem; display: flex; align-items: center;
          gap: 1rem; box-shadow: 0 1px 4px rgba(0,0,0,.05); position: sticky; top:0; z-index:10; }
.topbar h1 { font-size: 1.2rem; color: #e74c3c; }
.topbar select { padding: .4rem .8rem; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
.topbar .btn { padding: .5rem 1.2rem; border: none; border-radius: 6px; cursor: pointer;
               font-weight: 600; font-size: 14px; color:#fff; }
.btn-format { background: #e74c3c; }
.btn-format:hover { background: #c0392b; }
.btn-copy { background: #27ae60; font-size: 12px; padding: .3rem .8rem; margin-left: .5rem; }
.btn-copy:hover { background: #219a52; }
.main { display: flex; height: calc(100vh - 56px); }
/* Left: input */
.left { width: 340px; min-width: 340px; background: #fff; padding: 1rem;
        display: flex; flex-direction: column; gap: .8rem; overflow-y: auto; }
.left textarea { width: 100%; height: 100%; min-height: 300px; flex: 1;
    border: 2px solid #eee; border-radius: 10px; padding: 1rem; font-size: 14px;
    line-height: 1.7; font-family: inherit; resize: none; }
.left textarea:focus { outline: none; border-color: #e74c3c; }
.left .hint { font-size: 12px; color: #999; }
/* Right: results */
.right { flex: 1; overflow-y: auto; padding: 1rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
        gap: 1rem; }
.card { background: #fff; border-radius: 12px; padding: 1rem;
        box-shadow: 0 2px 8px rgba(0,0,0,.04); cursor: pointer; transition: all .2s;
        border: 2px solid transparent; position: relative; }
.card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.08); }
.card.selected { border-color: #e74c3c; box-shadow: 0 4px 20px rgba(231,76,60,.15); }
.card-header { display: flex; align-items: center; gap: .5rem; margin-bottom: .5rem; }
.card-icon { font-size: 1.5rem; }
.card-name { font-weight: 700; font-size: 15px; }
.card-score { margin-left: auto; font-size: 1.3rem; font-weight: 700; }
.score-high { color: #27ae60; }
.score-mid { color: #e67e22; }
.score-low { color: #e74c3c; }
.card-badge { display: inline-block; padding: 1px 8px; border-radius: 10px;
              font-size: 11px; background: #def7ec; color: #27ae60; }
.card-badge.best { background: #ffeaa7; color: #d35400; font-weight: 700; }
.card-detail { font-size: 12px; color: #888; margin-top: .5rem; line-height: 1.6; }
.card-detail span { display: block; }
.card-warn { color: #e67e22; }
/* Phone preview inside card */
.phone { width: 280px; margin: .8rem auto 0; background: #fafafa; border-radius: 16px;
         padding: 14px 12px; border: 1px solid #eee; }
.phone-top { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.phone-avatar { width: 24px; height: 24px; border-radius: 50%; background: #e74c3c;
                color: #fff; font-size: 12px; display: flex; align-items: center;
                justify-content: center; }
.phone-user { font-size: 11px; font-weight: 600; }
.phone-title { font-size: 13px; font-weight: 700; margin-bottom: 6px; line-height: 1.5; }
.phone-body { font-size: 11px; line-height: 1.6; color: #555;
              max-height: 120px; overflow: hidden; white-space: pre-wrap; }
.phone-tags { font-size: 10px; color: #3498db; margin-top: 6px; }
/* Expanded detail */
.detail-panel { display: none; background: #fff; border-radius: 12px; padding: 1.5rem;
                margin-bottom: 1rem; box-shadow: 0 2px 8px rgba(0,0,0,.04); }
.detail-panel.show { display: block; }
.detail-panel .detail-title { font-size: 18px; font-weight: 700; margin-bottom: 1rem; }
.detail-images { display: flex; gap: .5rem; flex-wrap: wrap; margin: .8rem 0; }
.detail-images span { background: #f0f0f0; padding: .3rem .7rem; border-radius: 6px;
                       font-size: 12px; color: #666; }
/* Empty state */
.empty { text-align: center; padding: 4rem 1rem; color: #bbb; }
.empty .big { font-size: 4rem; }
.empty p { margin-top: 1rem; }

@media (max-width: 800px) { .main { flex-direction: column; } .left { width:100%; min-width:0; height:200px; } }
</style>
</head>
<body>

<div class="topbar">
  <h1>🎨 文案排版</h1>
  <select id="platform" onchange="doFormat()">
    <option value="xiaohongshu">小红书</option>
    <option value="douyin">抖音</option>
    <option value="zhihu">知乎</option>
  </select>
  <button class="btn btn-format" onclick="doFormat()">🔄 生成全部排版</button>
  <span style="font-size:12px;color:#999;">粘贴文案后自动生成8种排版 + 评分</span>
</div>

<div class="main">

<div class="left">
  <div class="hint">📋 粘贴完整文案（标题+正文+标签）：</div>
  <textarea id="textInput" placeholder="在此粘贴文案...

标题和正文会自动识别
标签以 # 开头即可
如：#哈利波特同人 #小说推荐"></textarea>
</div>

<div class="right" id="results">
  <div class="empty">
    <div class="big">📝</div>
    <p>在左边粘贴文案<br>自动生成 8 种排版，带评分<br>选最好的复制</p>
  </div>
</div>

</div>

<script>
let currentData = null;
let selectedId = null;

async function doFormat() {
  const text = document.getElementById('textInput').value.trim();
  if (!text) { alert('请先粘贴文案'); return; }

  const btn = document.querySelector('.btn-format');
  btn.disabled = true;
  btn.textContent = '⏳ 生成中...';
  document.getElementById('results').innerHTML = '<div class="empty"><div class="big">⏳</div><p>正在生成 8 种排版...</p></div>';

  try {
    const form = new FormData();
    form.append('text', text);
    form.append('platform', document.getElementById('platform').value);

    const resp = await fetch('/format-all', { method: 'POST', body: form });
    if (!resp.ok) throw new Error('Server error: ' + resp.status);
    const data = await resp.json();
    currentData = data;
    renderResults(data);
  } catch(e) {
    document.getElementById('results').innerHTML = '<div class="empty"><div class="big">❌</div><p>出错了: ' + e.message + '</p></div>';
  } finally {
    btn.disabled = false;
    btn.textContent = '🔄 生成全部排版';
  }
}

function renderResults(data) {
  var results = data.results || [];
  if (!results.length) { document.getElementById('results').innerHTML = '<div class="empty"><p>无结果</p></div>'; return; }

  var html = '<div class="grid">';
  for (var i = 0; i < results.length; i++) {
    var r = results[i];
    var isBest = (i === 0 && r.score >= 80);
    var scoreClass = r.score >= 80 ? 'score-high' : (r.score >= 60 ? 'score-mid' : 'score-low');
    var selected = r.id === selectedId ? ' selected' : '';

    html += '<div class="card' + selected + '" onclick="selectCard(\'' + r.id + '\')" id="card-' + r.id + '">';
    html += '<div class="card-header">';
    html += '<span class="card-icon">' + esc(r.icon) + '</span>';
    html += '<span class="card-name">' + esc(r.name) + '</span>';
    if (isBest) html += '<span class="card-badge best">⭐ 推荐</span>';
    html += '<span class="card-score ' + scoreClass + '">' + r.score + '</span>';
    html += '</div>';

    // Score details
    html += '<div class="card-detail">';
    var keys = Object.keys(r.score_detail || {});
    for (var j = 0; j < keys.length; j++) {
      var v = r.score_detail[keys[j]];
      var cls = v.indexOf('⚠️') === 0 ? 'card-warn' : '';
      html += '<span class="' + cls + '">' + esc(v) + '</span>';
    }
    html += '</div>';

    // Phone preview
    html += '<div class="phone">';
    html += '<div class="phone-top"><div class="phone-avatar">📖</div><div class="phone-user">推书小助手 · 刚刚</div></div>';
    html += '<div class="phone-title">' + esc(r.title || '标题') + '</div>';
    html += '<div class="phone-body">' + esc((r.body || '').substring(0, 150)) + '...</div>';
    html += '<div class="phone-tags">' + (r.tags || []).map(function(t) { return '#' + esc(t); }).join(' ') + '</div>';
    html += '</div>';

    // Buttons
    html += '<div style="margin-top:.6rem;display:flex;gap:.4rem">';
    html += '<button class="btn-copy" onclick="event.stopPropagation();copyText(\'' + r.id + '\')">📋 复制全文</button>';
    html += '<button class="btn-copy" onclick="event.stopPropagation();copyTags(\'' + r.id + '\')" style="background:#888">🏷 复制标签</button>';
    html += '</div>';
    html += '</div>';
  }
  html += '</div>';
  document.getElementById('results').innerHTML = html;
}

function selectCard(id) {
  selectedId = id;
  if (currentData) renderResults(currentData);
}

function copyText(id) {
  var r = findResult(id);
  if (!r) return;
  try {
    navigator.clipboard.writeText(r.formatted_text).then(function() { flash('📋 已复制全文！'); });
  } catch(e) {
    // Fallback for older browsers
    var ta = document.createElement('textarea');
    ta.value = r.formatted_text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    flash('📋 已复制全文！');
  }
}

function copyTags(id) {
  var r = findResult(id);
  if (!r) return;
  var text = (r.tags||[]).map(function(t){return '#'+t;}).join(' ');
  try {
    navigator.clipboard.writeText(text).then(function() { flash('🏷 已复制标签！'); });
  } catch(e) {
    var ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    flash('🏷 已复制标签！');
  }
}

function findResult(id) {
  if (!currentData) return null;
  var results = currentData.results || [];
  for (var i = 0; i < results.length; i++) {
    if (results[i].id === id) return results[i];
  }
  return null;
}

function flash(msg) {
  var el = document.createElement('div');
  el.textContent = msg;
  el.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#27ae60;color:#fff;padding:.6rem 1.5rem;border-radius:8px;z-index:999;font-weight:600;';
  document.body.appendChild(el);
  setTimeout(function() { el.remove(); }, 1500);
}

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
</script>
</body>
</html>"""


def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")


if __name__ == "__main__":
    main()
