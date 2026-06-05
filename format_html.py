"""Self-contained format server — no xhs-agent dependencies.
Build: docker build -f Dockerfile.format -t xhs-format .
Run:   docker run -d -p 8001:8001 xhs-format
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI(title="排版工具", version="0.2.0")

# ─── Dataclasses ────────────────────────────────────────────


@dataclass
class FormatTemplate:
    tid: str
    name: str
    icon: str
    desc: str
    best_for: str


@dataclass
class PlatformRules:
    name: str
    max_title_len: int
    max_tags: int
    emoji_min: int
    emoji_max: int
    cta_required: bool


XHS = PlatformRules("小红书", 20, 10, 3, 6, True)
DOUYIN = PlatformRules("抖音", 30, 6, 1, 3, True)
ZHIHU = PlatformRules("知乎", 50, 5, 0, 2, False)
PLATFORMS = {"xiaohongshu": XHS, "douyin": DOUYIN, "zhihu": ZHIHU}

BANNED = ["第一", "最强", "最好", "全网", "绝对", "100%", "永久", "根治",
          "封神", "天花板", "神作", "神效", "免费领取", "加微信", "私信我", "点击链接"]

TAG_WEIGHTS = {"小说推荐": 10, "推文": 9, "书荒": 8, "好书推荐": 8,
               "哈利波特同人": 7, "HP同人": 7, "克苏鲁": 6, "悬疑": 6,
               "推理": 6, "冷门好文": 6, "理性主角": 5, "慢热": 5,
               "氛围": 5, "同人文": 5, "种草": 5, "剧情": 4}


def _parse(text: str):
    """Smart parse: title, body, tags from raw text."""
    lines = text.strip().split("\n")
    title = ""
    body_start = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        if not title and len(s) <= 40:
            title = s
            body_start = i + 1
            break
    tags = []
    body_lines = []
    for i in range(body_start, len(lines)):
        line = lines[i].strip()
        if line.startswith("#"):
            tags.append(line.lstrip("#").strip())
        elif line and all(t.startswith("#") for t in line.split()):
            for t in line.split():
                tags.append(t.lstrip("#").strip())
        else:
            body_lines.append(lines[i])
    body = "\n".join(body_lines).strip()
    if not body:
        body = text.strip()
    return title, body, tags


def _paras(body: str) -> list[str]:
    return [p.strip() for p in body.strip().split("\n\n") if p.strip()]


def _pick(paras, idx):
    if not paras:
        return ""
    if idx < 0:
        idx = len(paras) + idx
    return paras[idx][:150] if 0 <= idx < len(paras) else ""


def _sort_tags(tags, limit):
    scored = [(t, TAG_WEIGHTS.get(t, 0)) for t in tags]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in scored[:limit]]


def _score(title, body, tags, rules):
    detail = {}
    points = 100
    # title
    tl = len(title)
    if 8 <= tl <= rules.max_title_len:
        detail["标题长度"] = f"✅ {tl}字，在推荐范围"
    elif tl < 8:
        points -= 8
        detail["标题长度"] = f"⚠️ {tl}字偏短，建议8-{rules.max_title_len}字"
    else:
        points -= 5
        detail["标题长度"] = f"⚠️ {tl}字，超过推荐{rules.max_title_len}字"
    # emoji
    ec = len(re.findall(r'[\U0001F300-\U0001FAFF]|[☀-➿]|[✀-➿]|✅|❌|✨|📖|📍|🔍|💭|🆘|🔥|🤯|🌟|📝|🎬|🖼|📋|✍️|🎨|📌|⚖️|🎯|🪝|🌙|👤|💬|📱|📄|🏷|📊', title + body))
    if rules.emoji_min <= ec <= rules.emoji_max:
        detail["Emoji节奏"] = f"✅ {ec}个，节奏合适"
    elif ec < rules.emoji_min:
        points -= 8; detail["Emoji节奏"] = f"⚠️ {ec}个偏少，建议{rules.emoji_min}-{rules.emoji_max}个"
    else:
        points -= 4; detail["Emoji节奏"] = f"⚠️ {ec}个偏多，建议{rules.emoji_min}-{rules.emoji_max}个"
    # paragraphs
    ps = [p for p in body.split("\n\n") if p.strip()]
    n = len(ps)
    if 4 <= n <= 8:
        detail["段落结构"] = f"✅ {n}段，结构清晰"
    elif n < 3:
        points -= 12; detail["段落结构"] = f"⚠️ 仅{n}段，建议4-8段"
    elif n > 10:
        points -= 6; detail["段落结构"] = f"⚠️ {n}段偏多"
    else:
        detail["段落结构"] = f"⚡ {n}段，尚可"
    # CTA
    has_cta = any(w in body[-80:] for w in ["？", "评论", "分享", "说说", "你们", "大家", "你觉得", "快来", "聊聊", "安利"])
    if has_cta:
        detail["互动引导"] = "✅ 结尾有互动引导"
    elif not rules.cta_required:
        detail["互动引导"] = "⚡ 非必需"
    else:
        points -= 12; detail["互动引导"] = "⚠️ 缺少互动引导"
    # compliance
    bf = [w for w in BANNED if w in title + body]
    if not bf:
        detail["平台合规"] = "✅ 无违禁词"
    else:
        points -= min(len(bf) * 3, 15)
        detail["平台合规"] = f"⚠️ 含违禁词: {', '.join(bf)}"
    if len(tags) > rules.max_tags:
        points -= 3; detail["标签数量"] = f"⚠️ {len(tags)}个超过{rules.max_tags}上限"
    else:
        detail["标签数量"] = f"✅ {len(tags)}个"
    return max(points, 0), detail


def _images(tid):
    m = {
        "review": ["踩坑合集拼图", "正确选择书封", "内页金句截图", "阅读氛围图", "CTA引导图"],
        "checklist": ["书单封面标题图", "第一本书封+简介", "第二本书封+简介", "第三本书封+简介", "合集对比图"],
        "emotional": ["走心氛围图", "书封+手写笔记", "金句截图", "情感共鸣图", "CTA互动图"],
        "suspense": ["黑暗氛围封面", "异常细节截图1", "异常细节截图2", "线索关联图", "悬念引导图"],
        "contrast": ["左右对比封面", "浅读视角截图", "深读视角截图", "细节对比放大", "结论CTA图"],
        "pain_point": ["痛点共鸣封面", "烂书踩坑合集", "正确打开方式", "阅读效果展示", "CTA互动图"],
        "identity": ["身份标签封面", "书封+特色亮点", "金句共鸣截图", "角色画像", "CTA走心推荐"],
        "immersive": ["氛围感封面(暗色调)", "场景细节放大", "文字氛围渲染", "电影感画面", "沉浸体验CTA"],
    }
    return m.get(tid, ["封面图", "内容图1", "内容图2", "内容图3", "CTA图"])


# ─── 8 Templates ───────────────────────────────────────────


def _apply_review(title, body, tags, rules):
    ps = _paras(body)
    body = _build([
        _pick(ps, 0) or "踩了无数坑之后终于找到一本真正值得推荐的",
        "",
        "先说我踩过的坑：",
        "❌ 榜单推文水分太大，点进去全是复制粘贴",
        "❌ 评分高的不一定适合你的口味",
        "❌ 冲着封面去的，结果内容空洞得让人窒息",
        "",
        "但这本完全不一样——",
        _pick(ps, 2) or "不是又一本蹭热度的同人",
        _pick(ps, 3) or "主角不靠外挂，靠的是职业病",
        "",
        _pick(ps, -1) or "推荐给所有被烂书伤害过的书友们。",
    ])
    sc = _score(title, body, tags, rules)
    return _fmt("review", "测评排雷型", "🔍", title, body, tags, sc, _images("review"))


def _apply_checklist(title, body, tags, rules):
    ps = _paras(body)
    if "推荐" not in title and "书单" not in title:
        if len(title) < rules.max_title_len - 4:
            title = title + "｜推荐推荐" if title else "近期最值得看的书单推荐"
    title = title[:rules.max_title_len]
    b = _build([
        _pick(ps, 0) or "书荒的姐妹看过来！整理了一份近期最值得看的书单👇",
        "",
        "📖 推荐一：《霍格沃茨：我成了守秘人》",
        _pick(ps, 1) or "克苏鲁+HP同人，不是缝合怪",
        f"  看点：{_pick(ps,2) or '成人视角重读魔法世界'}",
        "",
        "📖 推荐二：设定党必入", "  世界观扎实，细节控狂喜", "  适合喜欢慢慢品读的书友",
        "",
        "📖 推荐三：悬疑氛围拉满", "  越读越觉得不对劲", "  最后几章直接引爆",
        "",
        _pick(ps, -1) or "你最近在看什么书？评论区互相安利～",
    ])
    sc = _score(title, b, tags, rules)
    return _fmt("checklist", "清单书单型", "📋", title, b, tags, sc, _images("checklist"))


def _apply_emotional(title, body, tags, rules):
    ps = _paras(body)
    if len(title) < 10:
        title = "看完这本书，我整整缓了一周"
    title = title[:rules.max_title_len]
    b = _build([
        _pick(ps, 0) or "合上最后一页的时候是凌晨两点。盯着天花板看了很久。",
        "",
        "不是因为结局有多震撼——而是这本书里有一个角色，像极了我自己。",
        _pick(ps, 1) or "那个一直在观察、记录、怀疑的主角——他就是每一个不够勇敢却不愿放弃的人。",
        "",
        _pick(ps, 2) or "作者没有给他金手指，只给了他一双看过世界的眼睛。",
        "",
        "✨ 如果你在寻找一本能让你安静下来、认真对待每一个细节的书——",
        _pick(ps, -1) or "去看看这本书吧。不是爽文，但比爽文更让人上瘾。",
    ])
    sc = _score(title, b, tags, rules)
    return _fmt("emotional", "情感共鸣型", "💭", title, b, tags, sc, _images("emotional"))


def _apply_suspense(title, body, tags, rules):
    ps = _paras(body)
    if not any(h in title for h in ["千万别", "不要", "别", "警告", "慎入"]):
        title = "千万别在深夜打开这本小说" if len(title) < 8 else "警告：" + title
    title = title[:rules.max_title_len]
    b = _build([
        _pick(ps, 0) or "说出来你可能不信——这本书每章开头都藏着一个细思极恐的细节。",
        "",
        "🔍 比如这一段：",
        _pick(ps, 1) or "主角走进对角巷，发现一家没有招牌的店铺。所有人习以为常，只有他停下来记录。",
        "",
        "🔍 还有这一段：",
        _pick(ps, 2) or "地下深处有一扇不该存在的门。门缝里透出的不是光，而是规律的震动。每七秒一次。像心跳。",
        "",
        "🔍 最让我睡不着的是：",
        _pick(ps, 3) or "所有异常点在地图上连成一个圆。圆心就在正下方。",
        "",
        "剩下的你自己去看。我不剧透了。😏",
    ])
    sc = _score(title, b, tags, rules)
    return _fmt("suspense", "悬念钩子型", "🪝", title, b, tags, sc, _images("suspense"))


def _apply_contrast(title, body, tags, rules):
    ps = _paras(body)
    title = title[:rules.max_title_len]
    b = _build([
        _pick(ps, 0) or "同样一本书，两种完全不同的打开方式——",
        "",
        "👤 普通读者翻开：",
        "「哦，HP同人啊，应该又是校园恋爱+龙傲天那一套吧。」翻了三页→看了看封面→放下了。",
        "",
        "🔍 深度读者翻开：",
        _pick(ps, 1) or "「等等，对角巷为什么有一家没有招牌的店？」翻开笔记本→做标记→重读→发现惊天秘密。",
        "",
        "✨ 区别不在于智商，而在于——你有没有认真对待作者埋在每一页的细节。",
        _pick(ps, -1) or "这是一本值得你用第二种方式打开的书。",
    ])
    sc = _score(title, b, tags, rules)
    return _fmt("contrast", "对比安利型", "⚖️", title, b, tags, sc, _images("contrast"))


def _apply_pain(title, body, tags, rules):
    ps = _paras(body)
    title = title[:rules.max_title_len]
    b = _build([
        "你是不是也遇到过——",
        "📱 按书单一本本搜，下载了十几本，没有一本撑过第三章。",
        "📱 榜单前十「神作」，点进去全是复制粘贴。",
        "📱 好不容易找到对胃口的，结果作者断更了。",
        "",
        "我曾经也是。直到发现一个规律：真正的好书，从来不在热门榜单上。",
        "",
        _pick(ps, 1) or "比如这本——没有铺天盖地的推文，但每个读完的人都在评论区写了三百字长评。",
        _pick(ps, 2) or "它不是一本能「快读」的书。需要你慢下来，跟着主角，一起发现这个世界不对劲的地方。",
        "",
        _pick(ps, -1) or "你最近有没有读过让你愿意写长评的书？评论区分享一下～",
    ])
    sc = _score(title, b, tags, rules)
    return _fmt("pain_point", "痛点解决型", "🎯", title, b, tags, sc, _images("pain_point"))


def _apply_identity(title, body, tags, rules):
    ps = _paras(body)
    title = title[:rules.max_title_len]
    b = _build([
        "作为一个看了八年小说的老书虫，我以为对套路已经完全免疫了。",
        "",
        "爽文？看过。虐文？看过。无限流？看过。克苏鲁？也看过。HP同人？——说实话，这个品类已经烂到我不想点开了。",
        "",
        "但这本书让我意识到：不是同人不行，是「写得不行」的同人太多了。",
        "",
        _pick(ps, 1) or "作者没有让主角靠外挂碾压，而是给了他一个你我都可能拥有的能力——职业敏感度。",
        _pick(ps, 2) or "一个干了八年档案科的人，对「不对劲」有着本能的直觉。他走进魔法世界的第一反应不是兴奋，而是开始记笔记。",
        "",
        "这大概就是成年人的浪漫吧。不是飞天扫帚和魔咒，而是「我发现了一个别人都没注意到的细节」。",
        _pick(ps, -1) or "如果你也厌倦了无脑爽文，试试这本。",
    ])
    sc = _score(title, b, tags, rules)
    return _fmt("identity", "身份代入型", "👤", title, b, tags, sc, _images("identity"))


def _apply_immersive(title, body, tags, rules):
    ps = _paras(body)
    title = title[:rules.max_title_len]
    b = _build([
        "凌晨一点。宿舍熄灯。手机屏幕调到最暗。",
        "",
        "本来只想看一章就睡——结果看到第三章的时候，后背的汗毛突然竖了起来。",
        "",
        "不是因为有什么恐怖画面跳出来。而是因为作者在一个完全不起眼的段落里，写了一句话：",
        _pick(ps, 1) or "「古灵阁深处的门缝里，透出规律的震动。每七秒一次。像心跳。」",
        "",
        "就这一句话，手指悬在翻页键上，犹豫了五秒。",
        _pick(ps, 2) or "这种「细思极恐」的感觉贯穿了整本书。",
        "",
        "🎬 读这本书就像在看诺兰的电影：前三分之二铺垫，后三分之一引爆。每个细节都是真相的拼图。",
        _pick(ps, -1) or "准备好了吗？关灯，戴上耳机。",
    ])
    sc = _score(title, b, tags, rules)
    return _fmt("immersive", "沉浸体验型", "🌙", title, b, tags, sc, _images("immersive"))


def _build(lines):
    return "\n".join(l.rstrip() if l else "" for l in lines)


def _fmt(tid, name, icon, title, body, tags, sc, imgs):
    s, d = sc
    warnings = [f"{k}: {v[3:]}" for k, v in d.items() if v.startswith("⚠️")]
    formatted = title + "\n\n" + body + "\n\n" + " ".join(f"#{t}" for t in tags)
    return {"id": tid, "name": name, "icon": icon, "title": title, "body": body,
            "tags": tags, "formatted_text": formatted, "score": s, "score_detail": d,
            "warnings": warnings, "images": imgs}


TEMPLATES = [
    ("review", _apply_review), ("checklist", _apply_checklist),
    ("emotional", _apply_emotional), ("suspense", _apply_suspense),
    ("contrast", _apply_contrast), ("pain_point", _apply_pain),
    ("identity", _apply_identity), ("immersive", _apply_immersive),
]


def format_all(text: str, platform: str = "xiaohongshu"):
    rules = PLATFORMS.get(platform, XHS)
    title, body, tags = _parse(text)
    tags = _sort_tags(tags, rules.max_tags)
    results = [fn(title, body, tags, rules) for _, fn in TEMPLATES]
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


# ─── Routes ────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


@app.post("/format-all")
async def api_format_all(text: str = Form(""), platform: str = Form("xiaohongshu")):
    return {"results": format_all(text, platform)}


# ─── HTML ──────────────────────────────────────────────────


HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🎨 文案排版工具</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;background:#f0ebe3;color:#333}
.topbar{background:#fff;padding:.8rem 1.5rem;display:flex;align-items:center;gap:1rem;box-shadow:0 1px 4px rgba(0,0,0,.05);position:sticky;top:0;z-index:10}
.topbar h1{font-size:1.2rem;color:#e74c3c}
.topbar select{padding:.4rem .8rem;border:1px solid #ddd;border-radius:6px;font-size:14px}
.btn{padding:.5rem 1.2rem;border:none;border-radius:6px;cursor:pointer;font-weight:600;font-size:14px;color:#fff}
.btn-format{background:#e74c3c}.btn-format:hover{background:#c0392b}.btn-format:disabled{background:#ccc;cursor:not-allowed}
.main{display:flex;height:calc(100vh - 56px)}
.left{width:340px;min-width:340px;background:#fff;padding:1rem;display:flex;flex-direction:column;gap:.8rem;overflow-y:auto}
.left textarea{width:100%;height:100%;min-height:300px;flex:1;border:2px solid #eee;border-radius:10px;padding:1rem;font-size:14px;line-height:1.7;font-family:inherit;resize:none}
.left textarea:focus{outline:none;border-color:#e74c3c}
.hint{font-size:12px;color:#999}
.right{flex:1;overflow-y:auto;padding:1rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1rem}
.card{background:#fff;border-radius:12px;padding:1rem;box-shadow:0 2px 8px rgba(0,0,0,.04);border:2px solid transparent;transition:.2s}
.card:hover{box-shadow:0 4px 16px rgba(0,0,0,.08)}
.card-header{display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem}
.card-icon{font-size:1.5rem}.card-name{font-weight:700;font-size:15px}
.card-score{margin-left:auto;font-size:1.3rem;font-weight:700}
.score-high{color:#27ae60}.score-mid{color:#e67e22}.score-low{color:#e74c3c}
.card-badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;background:#ffeaa7;color:#d35400;font-weight:700}
.card-detail{font-size:12px;color:#888;margin-top:.5rem;line-height:1.6}
.card-detail span{display:block}.card-warn{color:#e67e22}
.cc{display:flex;gap:.4rem;margin-top:.6rem}
.cc button{font-size:12px;padding:.3rem .8rem;border:none;border-radius:6px;cursor:pointer;color:#fff;font-weight:600}
.cc .cc1{background:#27ae60}.cc .cc2{background:#888}
.phone{width:280px;margin:.8rem auto 0;background:#fafafa;border-radius:16px;padding:14px 12px;border:1px solid #eee}
.phone-top{display:flex;align-items:center;gap:6px;margin-bottom:8px}
.phone-avatar{width:24px;height:24px;border-radius:50%;background:#e74c3c;color:#fff;font-size:12px;display:flex;align-items:center;justify-content:center}
.phone-user{font-size:11px;font-weight:600}
.phone-title{font-size:13px;font-weight:700;margin-bottom:6px;line-height:1.5}
.phone-body{font-size:11px;line-height:1.6;color:#555;max-height:100px;overflow:hidden;white-space:pre-wrap}
.phone-tags{font-size:10px;color:#3498db;margin-top:6px}
.empty{text-align:center;padding:4rem 1rem;color:#bbb}
.empty .big{font-size:4rem}.empty p{margin-top:1rem}
@media(max-width:800px){.main{flex-direction:column}.left{width:100%;min-width:0;height:200px}}
</style>
</head>
<body>
<div class="topbar">
  <h1>🎨 文案排版</h1>
  <select id="plat"><option value="xiaohongshu">小红书</option><option value="douyin">抖音</option><option value="zhihu">知乎</option></select>
  <button class="btn btn-format" onclick="go()">🔄 生成全部排版</button>
</div>
<div class="main">
<div class="left">
  <div class="hint">📋 粘贴文案（标题+正文+#标签）：</div>
  <textarea id="inp" placeholder="在此粘贴文案...

标题和正文会自动识别
标签以 # 开头即可
如：#哈利波特同人 #小说推荐"></textarea>
</div>
<div class="right" id="out">
  <div class="empty"><div class="big">📝</div><p>粘贴文案，点击按钮<br>自动生成 8 种排版 + 评分</p></div>
</div>
</div>
<script>
var cur=null;
async function go(){
  var t=document.getElementById('inp').value.trim();
  if(!t){alert('请先粘贴文案');return}
  var b=document.querySelector('.btn-format');b.disabled=true;b.textContent='⏳ 生成中...';
  document.getElementById('out').innerHTML='<div class="empty"><div class="big">⏳</div><p>正在生成 8 种排版...</p></div>';
  try{
    var f=new FormData();f.append('text',t);f.append('platform',document.getElementById('plat').value);
    var r=await fetch('/format-all',{method:'POST',body:f});
    if(!r.ok)throw new Error('Server error: '+r.status);
    var d=await r.json();cur=d;show(d);
  }catch(e){
    document.getElementById('out').innerHTML='<div class="empty"><div class="big">❌</div><p>'+e.message+'</p></div>';
  }finally{b.disabled=false;b.textContent='🔄 生成全部排版';}
}
function show(d){
  var rs=d.results||[],h='<div class="grid">';
  for(var i=0;i<rs.length;i++){
    var r=rs[i],best=(i===0&&r.score>=80),sc=r.score>=80?'score-high':(r.score>=60?'score-mid':'score-low');
    h+='<div class="card"><div class="card-header"><span class="card-icon">'+esc(r.icon)+'</span><span class="card-name">'+esc(r.name)+'</span>';
    if(best)h+='<span class="card-badge">⭐推荐</span>';
    h+='<span class="card-score '+sc+'">'+r.score+'</span></div><div class="card-detail">';
    var ks=Object.keys(r.score_detail||{});
    for(var j=0;j<ks.length;j++){var v=r.score_detail[ks[j]];h+='<span class="'+(v.indexOf('⚠️')===0?'card-warn':'')+'">'+esc(v)+'</span>';}
    h+='</div><div class="phone"><div class="phone-top"><div class="phone-avatar">📖</div><div class="phone-user">推书小助手 · 刚刚</div></div>';
    h+='<div class="phone-title">'+esc(r.title||'标题')+'</div><div class="phone-body">'+esc((r.body||'').substring(0,120))+'...</div>';
    h+='<div class="phone-tags">'+(r.tags||[]).map(function(t){return'#'+esc(t)}).join(' ')+'</div></div>';
    h+='<div class="cc"><button class="cc1" onclick="cp(\''+r.id+'\',1)">📋 复制全文</button><button class="cc2" onclick="cp(\''+r.id+'\',2)">🏷 复制标签</button></div></div>';
  }
  document.getElementById('out').innerHTML=h+'</div>';
}
function cp(id,m){
  var r=null;for(var i=0;i<(cur?.results||[]).length;i++){if(cur.results[i].id===id){r=cur.results[i];break}}
  if(!r)return;var t=m===1?r.formatted_text:(r.tags||[]).map(function(t){return'#'+t}).join(' ');
  var ta=document.createElement('textarea');ta.value=t;ta.style.position='fixed';ta.style.left='-9999px';
  document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);
  flash(m===1?'📋 已复制全文！':'🏷 已复制标签！');
}
function flash(m){var e=document.createElement('div');e.textContent=m;e.style.cssText='position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#27ae60;color:#fff;padding:.6rem 1.5rem;border-radius:8px;z-index:999;font-weight:600;';document.body.appendChild(e);setTimeout(function(){e.remove()},1500)}
function esc(s){if(!s)return'';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
