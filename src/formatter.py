"""Post Formatter v2 — 8 trending templates + auto-scoring.

Paste copy once → auto-apply all templates → pick the best one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ─── Data Models ────────────────────────────────────────────────


@dataclass
class FormatTemplate:
    id: str
    name: str
    icon: str
    desc: str
    best_for: str

    def apply(self, d: "PostData", rules: "PlatformRules") -> "FormatResult":
        raise NotImplementedError


@dataclass
class PlatformRules:
    name: str
    max_title_len: int
    max_tags: int
    emoji_min: int
    emoji_max: int
    cta_required: bool


@dataclass
class PostData:
    raw_text: str
    title: str = ""
    body: str = ""
    tags: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)


@dataclass
class FormatResult:
    template_id: str
    template_name: str
    template_icon: str
    title: str
    body: str
    tags: list[str]
    formatted_text: str
    score: int = 0
    score_detail: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    image_suggestions: list[str] = field(default_factory=list)


# ─── Platform Rules ─────────────────────────────────────────────

XHS = PlatformRules("小红书", 20, 10, 3, 6, True)
DOUYIN = PlatformRules("抖音", 30, 6, 1, 3, True)
ZHIHU = PlatformRules("知乎", 50, 5, 0, 2, False)

PLATFORMS = {"xiaohongshu": XHS, "douyin": DOUYIN, "zhihu": ZHIHU}

# ─── Banned words ───────────────────────────────────────────────

BANNED = ["第一", "最强", "最好", "全网", "绝对", "100%", "永久", "根治",
          "封神", "天花板", "神作", "神效", "立竿见影", "免费领取",
          "加微信", "私信我", "点击链接"]


# ─── 8 Template Implementations ─────────────────────────────────


class ReviewTemplate(FormatTemplate):
    """测评排雷型 — 踩坑经历 → 正确选择"""
    def apply(self, d, rules):
        paras = _split_body(d.body)
        title = d.title
        if len(title) > rules.max_title_len:
            title = title[:rules.max_title_len - 1]
        body = _build_body([
            _pick(paras, 0) or f"最近看了不少书，踩了无数坑之后终于找到了一本真正值得推荐的——{d.title[:15]}！",
            "",
            "先说我踩过的坑：",
            "❌ 榜单推文水分太大，点进去全是复制粘贴",
            "❌ 评分高的不一定适合你，口味对不上就是浪费生命",
            "❌ 冲着封面去的，结果内容空洞得让人窒息",
            "",
            "但《霍格沃茨：我成了守秘人》完全不一样——",
            _pick(paras, 2) or "它不是又一本蹭热度的同人，而是用成年人的视角重新审视魔法世界。",
            _pick(paras, 3) or "主角不靠外挂，靠的是职业病——一个档案管理员的直觉。",
            "",
            _pick(paras, -1) or "推荐给所有被烂书伤害过的书友们。",
        ], rules)
        tags = _top_tags(d.tags, rules.max_tags)
        score = _score(title, body, tags, rules)
        return _result(self, title, body, tags, score, rules)


class ChecklistTemplate(FormatTemplate):
    """清单书单型 — 数字标题 + 分条推荐"""
    def apply(self, d, rules):
        paras = _split_body(d.body)
        title = d.title
        for keyword in ["推荐", "必看", "合集", "书单"]:
            if keyword not in title and len(title) < rules.max_title_len - 4:
                title = title + "｜" + keyword + "推荐"
                break
        title = title[:rules.max_title_len]
        body_lines = [
            _pick(paras, 0) or "书荒的姐妹看过来！整理了一份近期最值得看的书单👇",
            "",
            "📖 推荐一：《霍格沃茨：我成了守秘人》",
            _pick(paras, 1) or "克苏鲁+HP同人，不是缝合怪，是真的让人背后发凉。",
            f"  看点：{_pick(paras, 2) or '成人视角重读魔法世界，每个细节都是伏笔'}",
            "",
            "📖 推荐二：设定党必入",
            "  世界观扎实，细节控狂喜",
            "  适合喜欢慢慢品读的书友",
            "",
            "📖 推荐三：悬疑氛围拉满",
            "  越读越觉得不对劲，但又舍不得放下",
            "  最后三章直接封神（不是夸张）",
            "",
            _pick(paras, -1) or "你最近在看什么书？评论区互相安利呀～",
        ]
        body = _build_body(body_lines, rules)
        tags = _top_tags(d.tags, rules.max_tags)
        score = _score(title, body, tags, rules)
        return _result(self, title, body, tags, score, rules)


class EmotionalTemplate(FormatTemplate):
    """情感共鸣型 — "看完缓了N天" → 情感升华"""
    def apply(self, d, rules):
        paras = _split_body(d.body)
        title = d.title
        for keyword in ["看完", "读了", "刷完"]:
            if keyword not in title and len(title) < rules.max_title_len - 6:
                title = "看完这本书，我整整缓了一周" if len(title) < 10 else title
                break
        title = title[:rules.max_title_len]
        body = _build_body([
            _pick(paras, 0) or "合上最后一页的时候是凌晨两点。我盯着天花板看了很久。",
            "",
            "不是因为结局有多震撼——而是这本书里有一个角色，像极了我自己。",
            _pick(paras, 1) or "那个一直在观察、一直在记录、一直在怀疑的林默——他就是每一个不够勇敢却不愿放弃的人。",
            "",
            _pick(paras, 2) or "作者没有给他金手指，只给了他一双看了八年档案的眼睛。但就是这双眼睛，看穿了魔法世界的谎言。",
            "",
            "✨ 如果你也在寻找一本能让你安静下来、认真对待每一个细节的书——",
            "",
            _pick(paras, -1) or "去看看《霍格沃茨：我成了守秘人》吧。不是爽文，但比爽文更让人上瘾。",
        ], rules)
        tags = _top_tags(d.tags, rules.max_tags)
        score = _score(title, body, tags, rules)
        return _result(self, title, body, tags, score, rules)


class SuspenseTemplate(FormatTemplate):
    """悬念钩子型 — 反常识 → 层层揭露 → 戛然而止"""
    def apply(self, d, rules):
        paras = _split_body(d.body)
        title = d.title
        hooks = ["千万别睡前打开这本", "这本书的前三章骗了所有人", "读完第N章我后背发凉"]
        if not any(h in title for h in ["千万别", "不要", "别", "警告", "慎入"]):
            title = "千万别在深夜打开这本小说" if len(title) < 8 else "警告：" + title
        title = title[:rules.max_title_len]
        body = _build_body([
            _pick(paras, 0) or "说出来你可能不信——这本书的每一章开头，都藏着一个让人细思极恐的细节。",
            "",
            "🔍 比如这一段：",
            _pick(paras, 1) or "主角走进对角巷，发现一家没有招牌的店铺。门框上刻着三根交错的弧线。所有人习以为常，只有他停下来记录。",
            "",
            "🔍 还有这一段：",
            _pick(paras, 2) or "古灵阁地下深处，有一扇不该存在的门。门缝里透出的不是光，而是某种规律的震动。每七秒一次。像心跳。",
            "",
            "🔍 最让我睡不着的是：",
            _pick(paras, 3) or "所有异常点在地图上连成一个圆。圆心，就在霍格沃茨正下方。",
            "",
            "剩下的你自己去看。我不剧透了。😏",
        ], rules)
        tags = _top_tags(d.tags, rules.max_tags)
        score = _score(title, body, tags, rules)
        return _result(self, title, body, tags, score, rules)


class ContrastTemplate(FormatTemplate):
    """对比安利型 — 两类读者视角对比"""
    def apply(self, d, rules):
        paras = _split_body(d.body)
        title = d.title
        contrast_words = ["普通读者vs", "外行看vs", "大众以为vs"]
        if "vs" not in title.lower() and "对比" not in title:
            pass  # keep original
        title = title[:rules.max_title_len]
        body = _build_body([
            _pick(paras, 0) or "同样一本书，两种完全不同的打开方式——",
            "",
            "👤 普通读者翻开：",
            "「哦，哈利波特同人啊，那应该又是校园恋爱+龙傲天那一套吧。」",
            "翻了三页→看了看封面→放下了。",
            "",
            "🔍 深度读者翻开：",
            _pick(paras, 1) or "「等等，对角巷为什么有一家没有招牌的店？」「古灵阁的刻痕为什么和禁书区的符号一样？」",
            "开始查资料→做标记→重读→发现惊天秘密。",
            "",
            "✨ 区别不在于智商，而在于——你有没有认真对待作者埋在每一页的细节。",
            "",
            _pick(paras, -1) or "这是一本值得你用第二种方式打开的书。",
        ], rules)
        tags = _top_tags(d.tags, rules.max_tags)
        score = _score(title, body, tags, rules)
        return _result(self, title, body, tags, score, rules)


class PainPointTemplate(FormatTemplate):
    """痛点解决型 — "你是不是也…"→ 共鸣 → 解决"""
    def apply(self, d, rules):
        paras = _split_body(d.body)
        title = d.title
        title = title[:rules.max_title_len]
        body = _build_body([
            "你是不是也遇到过这种情况——",
            "",
            "📱 按小红书书单一本本搜，下载了十几本，结果没有一本能撑过第三章。",
            "📱 榜单前十的「神作」，点进去发现全是复制粘贴的推文模板。",
            "📱 好不容易找到一本对胃口的，结果作者断更了。",
            "",
            "我曾经也是。直到我发现了一个规律：",
            "真正的好书，从来不在热门榜单上。",
            "",
            _pick(paras, 1) or "比如这本——没有铺天盖地的推文，没有刷出来的评分，但每一个读完的人，都在评论区写了三百字以上的长评。",
            "",
            _pick(paras, 2) or "因为它不是一本能「快读」的书。它需要你慢下来，跟着主角的笔记，一起发现这个世界不对劲的地方。",
            "",
            _pick(paras, -1) or "你最近有没有读过让你愿意写长评的书？评论区分享一下～",
        ], rules)
        tags = _top_tags(d.tags, rules.max_tags)
        score = _score(title, body, tags, rules)
        return _result(self, title, body, tags, score, rules)


class IdentityTemplate(FormatTemplate):
    """身份代入型 — "N年XX人" → 身份认同 → 这本书懂我"""
    def apply(self, d, rules):
        paras = _split_body(d.body)
        title = d.title
        title = title[:rules.max_title_len]
        body = _build_body([
            "作为一个看了八年小说的老书虫，我以为自己对套路已经完全免疫了。",
            "",
            "爽文？看过。虐文？看过。无限流？看过。克苏鲁？也看过。",
            "HP同人？——说实话，这个品类已经烂到我不想点开了。",
            "",
            "但《霍格沃茨：我成了守秘人》让我意识到：",
            "不是同人不行，是「写得不行」的同人太多了。",
            "",
            _pick(paras, 1) or "作者没有让主角靠外挂碾压，而是给了他一个你我都可能拥有的能力——职业敏感度。",
            "",
            _pick(paras, 2) or "一个干了八年档案科的人，对「不对劲」有着本能的直觉。他走进魔法世界的第一反应不是兴奋，而是——开始记笔记。",
            "",
            "这大概就是成年人的浪漫吧。不是飞天扫帚和魔法咒语，而是「我发现了一个别人都没注意到的细节」。",
            "",
            _pick(paras, -1) or "如果你也厌倦了无脑爽文，试试这本。",
        ], rules)
        tags = _top_tags(d.tags, rules.max_tags)
        score = _score(title, body, tags, rules)
        return _result(self, title, body, tags, score, rules)


class ImmersiveTemplate(FormatTemplate):
    """沉浸体验型 — 场景描写开头 → 氛围感 → "像在看电影" """
    def apply(self, d, rules):
        paras = _split_body(d.body)
        title = d.title
        title = title[:rules.max_title_len]
        body = _build_body([
            "凌晨一点。宿舍熄灯。手机屏幕调到最暗。",
            "",
            "我本来只想看一章就睡——结果看到第三章的时候，后背的汗毛突然竖了起来。",
            "",
            "不是因为有什么恐怖画面跳出来。",
            "而是因为作者在一个完全不起眼的段落里，轻描淡写地写了一句话：",
            "",
            f"「{_pick(paras, 1) or '古灵阁深处的门缝里，透出规律的震动。每七秒一次。像心跳。'}」",
            "",
            "就这一句话，我手指悬在翻页键上，犹豫了五秒。",
            "",
            _pick(paras, 2) or "这种「细思极恐」的感觉贯穿了整本书。作者不靠吓人的描写，而是让读者跟着主角的笔记，一点点发现——这个世界，从头到尾都不正常。",
            "",
            "🎬 读这本书的感觉，就像在看一部诺兰的电影：",
            "前三分之二在铺垫，后三分之一在引爆。每一个看似无意义的细节，都是最后真相的一块拼图。",
            "",
            _pick(paras, -1) or "准备好了吗？打开这本书，关灯，戴上耳机。",
        ], rules)
        tags = _top_tags(d.tags, rules.max_tags)
        score = _score(title, body, tags, rules)
        return _result(self, title, body, tags, score, rules)


# ─── Template Registry ──────────────────────────────────────────

ALL_TEMPLATES: list[FormatTemplate] = [
    ReviewTemplate("review", "测评排雷型", "🔍", "踩坑→正确选择", "冷门好书、防踩雷"),
    ChecklistTemplate("checklist", "清单书单型", "📋", "数字标题+分条推荐", "批量推书、书荒合集"),
    EmotionalTemplate("emotional", "情感共鸣型", "💭", "看完缓N天→情感升华", "虐文、情感向作品"),
    SuspenseTemplate("suspense", "悬念钩子型", "🪝", "千万别打开→层层揭露", "悬疑、推理、克苏鲁"),
    ContrastTemplate("contrast", "对比安利型", "⚖️", "两类读者视角对比", "同人、深度解读"),
    PainPointTemplate("pain_point", "痛点解决型", "🎯", "你是不是也→解决方案", "方法论、实用推荐"),
    IdentityTemplate("identity", "身份代入型", "👤", "N年XX人→身份认同", "职场、老书虫走心推荐"),
    ImmersiveTemplate("immersive", "沉浸体验型", "🌙", "场景描写→氛围拉满", "氛围感强、慢热佳作"),
]


# ─── Scoring Engine ─────────────────────────────────────────────


def _score(title: str, body: str, tags: list[str], rules: PlatformRules) -> tuple[int, dict]:
    detail = {}
    points = 100

    # 1. Title fitness (25)
    tl = len(title)
    if tl <= rules.max_title_len and tl >= 8:
        detail["标题长度"] = f"✅ {tl}字，在推荐范围"
    elif tl < 8:
        points -= 8
        detail["标题长度"] = f"⚠️ {tl}字偏短，建议8-{rules.max_title_len}字"
    else:
        points -= 5
        detail["标题长度"] = f"⚠️ {tl}字，超过推荐{rules.max_title_len}字"

    # 2. Emoji rhythm (15)
    emoji_count = len(re.findall(r'[\U0001F300-\U0001FAFF]|[☀-➿]|[✀-➿]|✅|❌|✨|📖|📍|🔍|💭|🆘|🔥|🤯|🌟|📝|🎬|🖼|📋|✍️|🎨|📌|⚖️|🎯|🪝|🌙|👤|💬|📱|📄|🏷|📊', title + body))
    if rules.emoji_min <= emoji_count <= rules.emoji_max:
        detail["Emoji节奏"] = f"✅ {emoji_count}个，节奏合适"
    elif emoji_count < rules.emoji_min:
        points -= 8
        detail["Emoji节奏"] = f"⚠️ {emoji_count}个偏少，建议{rules.emoji_min}-{rules.emoji_max}个"
    else:
        points -= 4
        detail["Emoji节奏"] = f"⚠️ {emoji_count}个偏多，建议{rules.emoji_min}-{rules.emoji_max}个"

    # 3. Paragraph structure (30)
    paras = [p for p in body.split("\n\n") if p.strip()]
    n = len(paras)
    if 4 <= n <= 8:
        detail["段落结构"] = f"✅ {n}段，结构清晰"
    elif n < 3:
        points -= 12
        detail["段落结构"] = f"⚠️ 仅{n}段，建议4-8段增强可读性"
    elif n > 10:
        points -= 6
        detail["段落结构"] = f"⚠️ {n}段偏多，建议合并精简"
    else:
        detail["段落结构"] = f"⚡ {n}段，尚可"

    # 4. CTA (15)
    has_cta = any(w in body[-80:] for w in ["？", "评论", "分享", "说说", "你们", "大家", "你觉得", "快来", "聊聊", "安利"])
    if has_cta:
        detail["互动引导"] = "✅ 结尾有互动引导"
    elif not rules.cta_required:
        detail["互动引导"] = "⚡ 非必需"
    else:
        points -= 12
        detail["互动引导"] = "⚠️ 缺少互动引导，建议添加提问或号召"

    # 5. Compliance (15)
    banned_found = [w for w in BANNED if w in title + body]
    if not banned_found:
        detail["平台合规"] = "✅ 无违禁词"
    else:
        points -= 15 - min(len(banned_found) * 3, 15)
        detail["平台合规"] = f"⚠️ 含违禁词: {', '.join(banned_found)}"

    # Tag count
    if len(tags) > rules.max_tags:
        points -= 3
        detail["标签数量"] = f"⚠️ {len(tags)}个，超过{rules.max_tags}个上限"
    else:
        detail["标签数量"] = f"✅ {len(tags)}个"

    return max(points, 0), detail


def _result(tmpl, title, body, tags, score, rules):
    warnings = []
    for k, v in score[1].items():
        if v.startswith("⚠️"):
            warnings.append(f"{k}: {v[3:]}")
    formatted = title + "\n\n" + body + "\n\n" + " ".join(f"#{t}" for t in tags)
    return FormatResult(
        template_id=tmpl.id,
        template_name=tmpl.name,
        template_icon=tmpl.icon,
        title=title, body=body, tags=tags,
        formatted_text=formatted,
        score=score[0],
        score_detail=score[1],
        warnings=warnings,
        image_suggestions=_image_roles(tmpl.id),
    )


def _split_body(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _pick(paras: list[str], idx: int) -> str:
    if not paras:
        return ""
    if idx < 0:
        idx = len(paras) + idx
    if 0 <= idx < len(paras):
        return paras[idx][:150]
    return ""


def _build_body(lines: list[str], rules: PlatformRules) -> str:
    result = []
    for line in lines:
        if line == "":
            result.append("")
        else:
            result.append(line.rstrip())
    return "\n".join(result)


def _top_tags(tags: list[str], limit: int) -> list[str]:
    weights = {"小说推荐": 10, "推文": 9, "书荒": 8, "好书推荐": 8,
               "哈利波特同人": 7, "HP同人": 7, "克苏鲁": 6, "悬疑": 6, "推理": 6,
               "冷门好文": 6, "理性主角": 5, "慢热": 5, "氛围": 5, "同人文": 5}
    scored = [(t, weights.get(t, 0)) for t in tags]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in scored[:limit]]


def _image_roles(tid: str) -> list[str]:
    roles = {
        "review": ["踩坑合集拼图", "正确选择书封", "内页金句截图", "阅读氛围图", "CTA引导图"],
        "checklist": ["书单封面标题图", "第一本书封+简介", "第二本书封+简介", "第三本书封+简介", "合集对比图"],
        "emotional": ["走心氛围图", "书封+手写笔记", "金句截图", "情感共鸣图", "CTA互动图"],
        "suspense": ["黑暗氛围封面", "异常细节截图1", "异常细节截图2", "线索关联图", "悬念引导图"],
        "contrast": ["左右对比封面", "浅读视角截图", "深读视角截图", "细节对比放大", "结论CTA图"],
        "pain_point": ["痛点共鸣封面", "烂书踩坑合集", "正确打开方式", "阅读效果展示", "CTA互动图"],
        "identity": ["身份标签封面", "书封+特色亮点", "金句共鸣截图", "角色画像", "CTA走心推荐"],
        "immersive": ["氛围感封面(暗色调)", "场景细节放大", "文字氛围渲染", "电影感画面", "沉浸体验CTA"],
    }
    return roles.get(tid, ["封面图", "内容图1", "内容图2", "内容图3", "CTA图"])


# ─── API ────────────────────────────────────────────────────────


def format_all(raw_text: str, platform: str = "xiaohongshu") -> list[FormatResult]:
    """Apply ALL templates to raw text, return ranked results."""
    rules = PLATFORMS.get(platform, XHS)
    data = _parse_raw(raw_text)
    results = [t.apply(data, rules) for t in ALL_TEMPLATES]
    results.sort(key=lambda r: r.score, reverse=True)
    return results


def _parse_raw(text: str) -> PostData:
    """Smart parse: detect title (first short line), body, tags."""
    lines = text.strip().split("\n")
    title = ""
    body_start = 0

    # First non-empty short line is likely the title
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if not title and len(stripped) <= 40:
            title = stripped
            body_start = i + 1
            break

    body_lines = []
    tags = []
    for i in range(body_start, len(lines)):
        line = lines[i].strip()
        if line and all(t.startswith("#") for t in line.split()):
            for t in line.split():
                tags.append(t.lstrip("#").strip())
        elif line.startswith("#"):
            tags.append(line.lstrip("#").strip())
        else:
            body_lines.append(lines[i])

    body = "\n".join(body_lines).strip()
    if not body:
        body = text.strip()
    return PostData(raw_text=text, title=title, body=body, tags=tags)
