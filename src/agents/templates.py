"""Template-driven copy generator — optimized from real successful novel promo.

Key patterns extracted from author's own high-performing promotional material.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ─── Template Data Structures ────────────────────────────────


@dataclass
class CopyTemplate:
    name: str
    platform: str
    description: str
    title_template: str
    body_template: str
    hashtags: list[str] = field(default_factory=list)


# ─── Xiaohongshu Templates (from gold standard) ──────────────

XHS_STANDARD = CopyTemplate(
    name="标准种草型",
    platform="xiaohongshu",
    description="作者验证过的最佳模板——结构化+细节+情感收尾",
    title_template="{emoji}{title_hook}",
    body_template="""{hook_line}

📖{novel_name}
📍{platform_name}｜已{chapter_count}章｜{genre_tags}

{character_setup}

✨ {detail_header_1}：
{detail_body_1}

✨ {detail_header_2}：
{detail_body_2}

✨ {closer_line}

{emotional_cta}

{hashtags_line}""",
    hashtags=[
        "哈利波特同人", "克苏鲁", "小说推荐", "冷门好文",
        "HP同人", "推理小说",
    ],
)

XHS_CONTRAST = CopyTemplate(
    name="对比安利型",
    platform="xiaohongshu",
    description="用版本对比/风格对比制造记忆点,适合多版本推广",
    title_template="{emoji}{contrast_title}",
    body_template="""{contrast_hook}

📖{novel_name}
📍{platform_name}｜已{chapter_count}章

{version_setup}

区别在哪？
{version_detail_1}

{version_detail_2}

{version_detail_3}

✨ 氛围感拉满：
{atmosphere_detail}

{closer_urgency}

{hashtags_line}""",
    hashtags=[
        "刺猬猫小说", "哈利波特同人", "克苏鲁", "慢热好文", "小说推荐",
    ],
)

XHS_QUICK = CopyTemplate(
    name="快速钩子型",
    platform="xiaohongshu",
    description="轻量短文案——适合发多个章节或日常更新",
    title_template="{emoji}{one_liner}",
    body_template="""{hook_line}

📖{novel_name} ｜ {platform_name}

{bullet_1}
{bullet_2}
{bullet_3}

{closing_punch}

{hashtags_line}""",
    hashtags=[
        "哈利波特同人", "小说推荐", "冷门神作", "克苏鲁",
    ],
)

XHS_TEMPLATES = [XHS_STANDARD, XHS_CONTRAST, XHS_QUICK]


# ─── Douyin Templates ────────────────────────────────────────

DOUYIN_HOOK = CopyTemplate(
    name="黄金5秒型",
    platform="douyin",
    description="前5秒强钩子+反常识+具体场景",
    title_template="{douyin_title}",
    body_template="""【视频结构：30-45秒】

🎬 **画面 0-5s**：{visual_hook}

🗣 **口播 0-5s（黄金钩子）**：
"{hook_5s}"

🎬 **画面 5-15s**：{visual_build}

🗣 **口播 5-15s（展开）**：
{script_build}

🎬 **画面 15-25s**：{visual_reveal}

🗣 **口播 15-25s（高潮）**：
{script_reveal}

🎬 **画面 25-35s**：书封/链接弹窗

🗣 **口播 25-35s（收尾）**：
{script_close}

📌 **建议BGM**：{bgm_suggestion}

{hashtags_line}""",
    hashtags=[
        "小说推荐", "哈利波特", "同人文", "推书", "好书推荐",
    ],
)

DOUYIN_TEMPLATES = [DOUYIN_HOOK]


# ─── Zhihu Templates ─────────────────────────────────────────

ZHIHU_DEEP = CopyTemplate(
    name="深度安利型",
    platform="zhihu",
    description="长文深度推荐，结构化分析",
    title_template="HP同人的天花板式切入：{title_hook}",
    body_template="""{opening_hook}

> {subtitle}

{setup_section}

{detail_section}

**这就是整本书的独特之处——**

{core_appeal}

**版本特点：**

{version_features}

{closing_recommendation}

{tags_line}""",
    hashtags=[],
)

ZHIHU_TEMPLATES = [ZHIHU_DEEP]


# ─── Station-internal Templates ──────────────────────────────

STATION_INTRO = CopyTemplate(
    name="站内简介型",
    platform="station",
    description="用于番茄/刺猬猫/起点站内的书籍简介",
    title_template="",
    body_template="""**一句话简介：**
{one_liner}

**详细简介：**

{character_intro}

{setting_detail_1}

{setting_detail_2}

{core_line}

**标签：** {tags_line}""",
    hashtags=[],
)


# ─── Template Engine ─────────────────────────────────────────


class TemplateEngine:
    """Fills proven templates with extracted chapter details."""

    def __init__(self) -> None:
        self.xhs_templates = XHS_TEMPLATES
        self.douyin_templates = DOUYIN_TEMPLATES
        self.zhihu_templates = ZHIHU_TEMPLATES
        self.station_templates = [STATION_INTRO]

    def fill(
        self,
        template: CopyTemplate,
        extraction: dict,
        novel_meta: dict,
    ) -> dict:
        """Fill template, returning {"title": ..., "body": ..., "platform": ...}"""
        ctx = self._build_context(extraction, novel_meta, template)

        title = template.title_template.format(**ctx) if template.title_template else ""
        body = template.body_template.format(**ctx)

        return {
            "title": title.strip(),
            "body": body.strip(),
            "platform": template.platform,
            "name": template.name,
        }

    def fill_all(
        self,
        platform: str,
        extraction: dict,
        novel_meta: dict,
    ) -> list[dict]:
        """Fill all templates for a platform."""
        if platform == "xiaohongshu":
            templates = self.xhs_templates
        elif platform == "douyin":
            templates = self.douyin_templates
        elif platform == "zhihu":
            templates = self.zhihu_templates
        elif platform == "station":
            templates = self.station_templates
        else:
            templates = self.xhs_templates

        return [self.fill(t, extraction, novel_meta) for t in templates]

    def _build_context(self, ext: dict, meta: dict, template: CopyTemplate) -> dict:
        """Build template context from extraction + novel metadata."""
        anomalies = ext.get("anomalies", [])
        scenes = ext.get("core_scenes", [])
        moments = ext.get("character_moments", [])
        quotes = ext.get("quotable_lines", [])
        hooks = ext.get("hook_elements", [])
        tones = ext.get("tone_keywords", [])

        novel_name = meta.get("novel_name", "《霍格沃茨：我成了守秘人》")
        platform_name = meta.get("platform_name", "番茄小说")
        chapter_count = meta.get("chapter_count", "61")
        genre_tags = meta.get("genre_tags", "克苏鲁+HP同人")

        # ── Build specific content blocks ──

        # Title hooks — prefer one_liner over hook_elements
        title_hook = ext.get("one_liner", "") or (hooks[0] if hooks else "档案员视角重读哈利波特")
        contrast_title = f"HP同人居然能写出克苏鲁味！这本真的{meta.get('quality_word', '封神')}了！"
        one_liner = ext.get("one_liner", "一位档案员用系统思维重新发现魔法世界")

        # Hook line
        hook_line = self._make_hook_line(ext, meta)
        emotional_cta = meta.get("emotional_cta", "🆘 冷门好看到爆！快给我火！")

        # Character setup (✅ bullets)
        character_setup = self._make_character_setup(ext, meta)

        # Detail blocks (✨ sections)
        detail_blocks = self._make_detail_blocks(anomalies, moments, scenes)

        # Closer line
        closer_line = self._make_closer_line(ext, quotes)

        # Contrast template
        contrast_hook = f"给我冲{platform_name}版！！😭"
        version_setup = (
            f"如果说别人写HP同人是{meta.get('common_approach', '校园恋爱+龙傲天')}\n那{platform_name}这本就是完全不同的物种🔥"
        )
        version_details = self._make_version_details(anomalies)

        # Atmosphere
        atmosphere_detail = self._make_atmosphere(anomalies, moments)

        # Quick template bullets
        bullets = self._make_quick_bullets(anomalies, moments, quotes)

        # Douyin
        douyin_title = f"一个35岁的档案科长穿越到霍格沃茨，他的第一反应居然是..."
        hook_5s = (
            f"如果有一天你穿越到哈利波特的世界，你会干什么？"
            f"学魔法？骑扫帚？认识哈利？"
            f"——这个人的选择是：打开笔记本，开始记录异常。"
        )
        script_build = self._make_douyin_build(ext, anomalies)
        script_reveal = (
            f"他发现这些异常点在地图上连成一个圆——圆心就在霍格沃茨地下。"
            f"这不是又一本校园爽文，这是一本用成年人思维重新审视魔法世界的小说。"
        )
        script_close = f"想看完整版？左下角直接看。已更新{chapter_count}章，量大管饱。"
        visual_hook = "哈利波特电影片段快剪（0.5s每个），最后定格霍格沃茨城堡"
        visual_build = "档案室/笔记本/地图的俯拍镜头，字幕逐条弹出关键异常"
        visual_reveal = "CG风格地下圆形结构示意图，逐层展开"
        bgm_suggestion = "Hans Zimmer - Time (remix) / 低音弦乐营造悬疑感"

        # Hashtags
        hashtags_line = " ".join(f"#{t}" for t in meta.get("hashtags", template.hashtags))

        return {
            # ---- Common ----
            "emoji": self._pick_emoji(ext),
            "novel_name": novel_name,
            "platform_name": platform_name,
            "chapter_count": chapter_count,
            "genre_tags": genre_tags,
            "one_liner": one_liner,
            # ---- Title ----
            "title_hook": title_hook,
            "contrast_title": contrast_title,
            # ---- Standard template ----
            "hook_line": hook_line,
            "character_setup": character_setup,
            "detail_header_1": detail_blocks[0][0] if len(detail_blocks) > 0 else "最让我上头的是",
            "detail_body_1": detail_blocks[0][1] if len(detail_blocks) > 0 else "",
            "detail_header_2": detail_blocks[1][0] if len(detail_blocks) > 1 else "还有",
            "detail_body_2": detail_blocks[1][1] if len(detail_blocks) > 1 else "",
            "closer_line": closer_line,
            "emotional_cta": emotional_cta,
            # ---- Contrast template ----
            "contrast_hook": contrast_hook,
            "version_setup": version_setup,
            "version_detail_1": version_details[0] if len(version_details) > 0 else "",
            "version_detail_2": version_details[1] if len(version_details) > 1 else "",
            "version_detail_3": version_details[2] if len(version_details) > 2 else "",
            "atmosphere_detail": atmosphere_detail,
            "closer_urgency": emotional_cta,
            # ---- Quick template ----
            "bullet_1": bullets[0] if len(bullets) > 0 else "",
            "bullet_2": bullets[1] if len(bullets) > 1 else "",
            "bullet_3": bullets[2] if len(bullets) > 2 else "",
            "closing_punch": closer_line,
            # ---- Douyin ----
            "douyin_title": douyin_title,
            "hook_5s": hook_5s,
            "script_build": script_build,
            "script_reveal": script_reveal,
            "script_close": script_close,
            "visual_hook": visual_hook,
            "visual_build": visual_build,
            "visual_reveal": visual_reveal,
            "bgm_suggestion": bgm_suggestion,
            # ---- Zhihu ----
            "opening_hook": meta.get("zhihu_opening",
                f'说实话，看到"克苏鲁+HP"这个组合的时候我是拒绝的——又是一个蹭热度的缝合怪吧？结果看了三章，真香。'),
            "subtitle": meta.get("zhihu_subtitle",
                "克苏鲁+哈利波特，这个缝合怪作品意外地好吃"),
            "setup_section": self._make_zhihu_setup(ext, meta),
            "detail_section": self._make_zhihu_details(ext),
            "core_appeal": self._make_zhihu_core(ext),
            "version_features": self._make_zhihu_features(meta),
            "closing_recommendation": meta.get("zhihu_closing",
                "如果你喜欢番茄版的灵巧快节奏，也值得看看刺猬猫版——这不是同一个故事，这是同一个故事核的另一种演绎。"),
            "tags_line": meta.get("tags_line", "哈利波特同人 克苏鲁 悬疑 理性主角 慢热 氛围"),
            # ---- Station intro ----
            "character_intro": self._make_station_intro(ext, meta),
            "setting_detail_1": self._make_station_detail(anomalies, 0),
            "setting_detail_2": self._make_station_detail(anomalies, 1),
            "core_line": meta.get("core_line", "这是一座建立在封印之上的学校。而他，正在打开那本记录一切的手册。"),
            # ---- Hashtags ----
            "hashtags_line": hashtags_line,
        }

    # ─── Content builders ────────────────────────────────

    def _pick_emoji(self, ext: dict) -> str:
        tones = ext.get("tone_keywords", [])
        if "悬疑" in tones or "恐怖" in tones:
            return "🤯"
        if "冷静" in tones or "理性" in tones:
            return "🔥"
        if "情感" in tones:
            return "✨"
        return "🔥"

    def _make_hook_line(self, ext: dict, meta: dict) -> str:
        hooks = ext.get("hook_elements", [])
        if hooks:
            return f"这是什么神仙设定啊😭 {hooks[0]}？"
        return f"这是什么神仙设定啊😭"

    def _make_character_setup(self, ext: dict, meta: dict) -> str:
        lines = [
            "✅ 男主林默，前世档案科科长",
            "✅ 穿越成11岁孤儿，收到霍格沃茨信",
            "✅ 别人：学魔法！骑扫帚！",
            "✅ 他：打开笔记本，开始记录异常现象🔍",
        ]
        return "\n".join(lines)

    def _make_detail_blocks(
        self,
        anomalies: list,
        moments: list,
        scenes: list,
    ) -> list[tuple[str, str]]:
        """Create ✨ section blocks. Returns [(header, body), ...]."""
        blocks = []

        # Block 1: Best anomalies
        if anomalies:
            a = anomalies[0]
            loc = a.get("location", "")
            detail = a.get("detail", a.get("what", ""))
            header = f"最让我上头的是{loc}的细节——" if loc else "最让我上头的是——"
            body_lines = [f"他走进对角巷第一件事不是高兴", f"而是发现{detail}"]
            if len(anomalies) > 1:
                a2 = anomalies[1]
                body_lines.append(a2.get("detail", a2.get("what", ""))[:80])
            body_lines.append("📝 全部记下来，标记待查")
            blocks.append((header, "\n".join(body_lines)))

        # Block 2: Best moment
        if moments:
            m = moments[0]
            char = m.get("character", "主角")
            moment = m.get("moment", "")
            header = f"{char}的那段真的绝了——"
            body_lines = [moment[:120]]
            if len(moments) > 1:
                m2 = moments[1]
                body_lines.append(f"{m2.get('character', '')}: {m2.get('moment', '')[:80]}")
            blocks.append((header, "\n".join(body_lines)))
        elif len(anomalies) >= 3:
            a3 = anomalies[2]
            loc = a3.get("location", "")
            detail = a3.get("detail", a3.get("what", ""))
            header = "还有——"
            body_lines = [f"{loc}: {detail}"[:120]]
            blocks.append((header, "\n".join(body_lines)))

        # Fallback: scene-based
        if len(blocks) == 0:
            blocks.append(("最精彩的部分——", scenes[0][:120] if scenes else "每一页都在发现新的异常"))

        return blocks

    def _make_closer_line(self, ext: dict, quotes: list) -> str:
        if quotes:
            return f"他不是救世主。他只是个职业病晚期的大叔，在魔法世界用{ext.get('tone_keywords', ['系统思维'])[0] if ext.get('tone_keywords') else '档案思维'}破案罢了。"
        return "他不是救世主。他只是个职业病晚期的大叔，在魔法世界用档案思维破案罢了。"

    def _make_version_details(self, anomalies: list) -> list[str]:
        details = []
        if len(anomalies) >= 1:
            a = anomalies[0]
            details.append(
                f"番茄版：发现{a.get('what', '异常')}→快速标记→走剧情\n"
                f"刺猬猫版：发现异常→仔细观察→仔细记录→推理→标记→才走剧情"
            )
        if len(anomalies) >= 2:
            a2 = anomalies[1]
            details.append(f"多了至少50%的细节铺陈🤯")
        if len(anomalies) >= 3 or len(anomalies) == 2:
            # Use moments or scenes for third
            pass
        if len(details) < 2:
            details.append("HP原著名词直接使用，不用代称不硬躲")
        if len(details) < 3:
            details.append("恐怖浓度比番茄版高两个档次")
        return details

    def _make_atmosphere(self, anomalies: list, moments: list) -> str:
        if anomalies:
            a = anomalies[0]
            detail = a.get("detail", a.get("what", ""))
            loc = a.get("location", "")
            lines = [
                f"{loc}的{a.get('what', '细节')}",
                f"有细微的{detail[:60]}——不是普通磨损",
                "是某种「规则」的纹路",
                "像被什么东西反复抓挠留下的",
            ]
            # Add character quote if available
            for m in moments:
                if m.get("moment", ""):
                    lines.append(f"「{m['moment'][:60]}」")
                    break
            return "\n".join(lines)
        return "古灵阁深处的门框上有细微刻痕——不是普通磨损，是某种规则的纹路，像被什么东西反复抓挠留下的。"

    def _make_quick_bullets(
        self,
        anomalies: list,
        moments: list,
        quotes: list,
    ) -> list[str]:
        bullets = []
        for a in anomalies[:2]:
            detail = a.get("detail", a.get("what", ""))
            loc = a.get("location", "")
            bullets.append(f"✅ {loc}: {detail[:80]}" if loc else f"✅ {detail[:80]}")
        if not bullets:
            bullets.append("✅ 用档案思维拆解魔法世界")
        bullets.append(f"✅ {len(anomalies)}个异常点连成一个圆——圆心指向地下")
        if quotes:
            bullets.append(f"💬 「{quotes[0][:60]}」")
        return bullets

    def _make_douyin_build(self, ext: dict, anomalies: list) -> str:
        if len(anomalies) >= 2:
            a0, a1 = anomalies[0], anomalies[1]
            return (
                f"对角巷有个没有招牌的店，门框上刻着三根弧线。"
                f"古灵阁深处有一扇门——{a0.get('detail', a0.get('what', ''))[:60]}。"
                f"所有人说这很正常。但林默——一个干了八年档案科的人——开始记笔记。"
            )
        return (
            "他走对角巷，逛古灵阁，买魔杖——全程保持一个11岁小孩该有的好奇表情，"
            "心里在做另一件事：记录。招牌拼错了没人纠正→标记。"
            "魔杖盒内侧有螺旋文字→标记。"
        )

    def _make_zhihu_setup(self, ext: dict, meta: dict) -> str:
        anomalies = ext.get("anomalies", [])
        lines = [
            "**设定有多妙？**",
            "",
            "主角林默，前世是干了八年档案科的科长。穿越成1991年的孤儿，收到霍格沃茨录取通知书。",
            "",
            "但注意——他不是穿越成哈利·波特。他只是一个即将入学的普通学生。普通吗？他的职业敏感度不普通。",
            "",
            "他走进对角巷，发现：",
        ]
        for a in anomalies[:3]:
            loc = a.get("location", "")
            detail = a.get("detail", a.get("what", ""))
            lines.append(f"- {detail}" + (f"（{loc}）" if loc else ""))
        return "\n".join(lines)

    def _make_zhihu_details(self, ext: dict) -> str:
        anomalies = ext.get("anomalies", [])
        lines = [
            "他走进霍格沃茨，发现：",
        ]
        for a in anomalies[3:5] if len(anomalies) > 3 else anomalies[:2]:
            detail = a.get("detail", a.get("what", ""))
            lines.append(f"- {detail}")
        if len(lines) == 1:
            lines.append("- 走廊两侧的画，有几幅是空的——画布里没有人，但风景在动")
            lines.append('- 级长说"画中人可能出去串门了"——语气流畅到不像是真话')
        return "\n".join(lines)

    def _make_zhihu_core(self, ext: dict) -> str:
        return (
            "主角不是靠魔法有多强，而是靠「一个老档案管理员的直觉」来发现这个世界的不协调之处。"
            "他不当救世主，他只是在记笔记。越记越多，越记越深，"
            "直到发现霍格沃茨的地下埋着某个不可名状的东西。"
        )

    def _make_zhihu_features(self, meta: dict) -> str:
        platform = meta.get("platform_name", "刺猬猫")
        return (
            f"这个版本每章4000-5000字，保留了完整的沉浸感。恐怖氛围更浓，"
            f"那种「不可名状」的压抑感渗透在每一页里。\n\n"
            f"这种写法让人想起洛夫克拉夫特的铺垫方式——不是突然跳出个怪物吓你一跳，"
            f"而是让读者跟着主角，一点点察觉这个世界不对劲，直到恐惧像水一样从脚底漫上来。"
        )

    def _make_station_intro(self, ext: dict, meta: dict) -> str:
        return (
            f"林默，干了八年档案科，穿越了。\n\n"
            f"穿越成1991年即将入学霍格沃茨的孤儿，收到一封猫头鹰送来的信。"
            f"别人的第一反应是兴奋，他的第一反应是：这封信为什么没有落款联系电话？\n\n"
            f"他走对角巷，逛古灵阁，买魔杖——全程保持一个11岁小孩该有的好奇表情，"
            f"心里在做另一件事：**记录。**"
        )

    def _make_station_detail(self, anomalies: list, idx: int) -> str:
        if idx < len(anomalies):
            a = anomalies[idx]
            loc = a.get("location", "")
            detail = a.get("detail", a.get("what", ""))
            return f"{loc}的{detail} → 标记。" if loc else f"{detail} → 标记。"
        return ""

    def _make_douyin_full(self, ext: dict, meta: dict) -> str:
        """Build complete douyin script."""
        return ""  # placeholder — douyin template is complex enough as-is


# Export the default engine
_engine: TemplateEngine | None = None


def get_engine() -> TemplateEngine:
    global _engine
    if _engine is None:
        _engine = TemplateEngine()
    return _engine
