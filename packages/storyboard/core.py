#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""story2prompt —— 极简提示词工具（B 方案）

零依赖、零配置、零 API key：
  故事/一句话 → 分镜表 → 可直接粘贴到 即梦 / 可灵 / Seedance 的提示词包。

用法：
  python story2prompt.py --demo
  python story2prompt.py --story 我的故事.txt --duration 60 --aspect 9:16 --style 悬疑
  python story2prompt.py --text "深夜，外卖员在电梯里接到一通没有声音的电话……"
"""

from __future__ import annotations

import argparse
import html
import math
import re
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

STYLES = {
    "悬疑": {
        "prefix": "电影感悬疑短片，冷调高反差，写实摄影，35mm 胶片质感，浅景深",
        "light": "冷青主色 + 局部暖黄光源，侧逆光突出轮廓",
        "mood": "压抑、不安、逐渐收紧的紧张感",
        "negative": "卡通、3D 渲染、过曝、低清、僵硬表情、多余手指、文字水印、塑料质感",
    },
    "写实": {
        "prefix": "纪实电影风格，自然光，写实摄影，真实质感",
        "light": "自然光为主，柔和过渡，局部补光",
        "mood": "克制、生活化、情绪内敛",
        "negative": "卡通、3D 渲染、过曝、低清、舞台感、文字水印",
    },
    "都市": {
        "prefix": "都市剧情短片，霓虹夜景，电影感调色",
        "light": "霓虹冷调 + 招牌暖色点缀，高反差",
        "mood": "疏离、躁动、夜色中的孤独",
        "negative": "卡通、3D 渲染、过曝、低清、文字水印",
    },
    "古风": {
        "prefix": "东方古风电影质感，水墨留白构图，写意光影",
        "light": "柔和顶光与烛火暖光，雾气层次",
        "mood": "静谧、悠远、克制的情绪张力",
        "negative": "现代元素、卡通、3D 渲染、过曝、文字水印",
    },
    "动画": {
        "prefix": "高质量二维动画电影，手绘质感，细腻背景美术",
        "light": "风格化光影，色彩饱和度适中",
        "mood": "温暖或奇幻的情绪氛围",
        "negative": "写实照片、3D 渲染、低清、崩坏、文字水印",
    },
}

ASPECTS = {
    "9:16": "竖屏 9:16",
    "16:9": "横屏 16:9",
    "1:1": "方形 1:1",
}

NEGATIVE_BASE = "模糊、低清晰度、畸形、多手多指、文字、水印、subtitle"

PHASES = ("建立", "升级", "反转")

SHOT_SIZES = {
    "建立": ["远景", "全景", "中景", "中近景", "中景"],
    "升级": ["中景", "中近景", "近景", "近景", "中近景"],
    "反转": ["近景", "特写", "近景", "特写", "大特写"],
}

MOVES = {
    "建立": ["固定机位", "缓慢推近", "轻微横移", "固定机位", "缓慢拉远"],
    "升级": ["跟随拍摄", "手持轻微晃动", "快速推近", "横移跟拍", "缓慢推近"],
    "反转": ["快速推近", "固定机位", "手持晃动", "急推", "缓慢拉远"],
}

SOUND_HINTS = {
    "雨": "雨声、水滴",
    "电话": "电话铃、听筒电流声",
    "铃": "铃声",
    "心跳": "低频心跳",
    "门": "门轴声、脚步",
    "血": "低频嗡鸣",
    "笑": "远处轻笑",
    "夜": "夜晚环境底噪",
    "海": "海浪声",
    "风": "风声",
}


def clean_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^#{1,6}\s*", "", line)
    line = re.sub(r"^[>\-\*•]+\s*", "", line)
    return line.strip()


def split_units(story: str) -> list[str]:
    lines = [ln for ln in story.splitlines() if not ln.strip().startswith("#")]
    lines = [clean_line(ln) for ln in lines]
    units: list[str] = []
    opens, closes = "「『“‘", "」』”’"
    for line in lines:
        if not line:
            continue
        buf = ""
        depth = 0
        for ch in line:
            buf += ch
            if ch in opens:
                depth += 1
            elif ch in closes and depth > 0:
                depth -= 1
            if ch in "。！？!?；;" and depth == 0:
                piece = buf.strip()
                if piece:
                    units.append(piece)
                buf = ""
        piece = buf.strip()
        if piece:
            units.append(piece)
    return units


def split_long(unit: str, limit: int = 60) -> list[str]:
    if len(unit) <= limit:
        return [unit]
    # 只在引号外按逗号切分，避免切断台词
    opens, closes = "「『“‘", "」』”’"
    pieces: list[str] = []
    buf, depth = "", 0
    for ch in unit:
        if ch in opens:
            depth += 1
        elif ch in closes and depth > 0:
            depth -= 1
        if ch in "，,、" and depth == 0:
            piece = buf.strip("，,、 ")
            if piece:
                pieces.append(piece)
            buf = ""
        else:
            buf += ch
    tail = buf.strip("，,、 ")
    if tail:
        pieces.append(tail)
    if len(pieces) <= 1:
        return [unit]
    merged, current = [], ""
    for piece in pieces:
        if current and len(current) + len(piece) > limit:
            merged.append(current)
            current = piece
        else:
            current = (current + "，" + piece).strip("，")
    if current:
        merged.append(current)
    return merged


def is_dialogue(unit: str) -> bool:
    return bool(re.search(r"[「“\"'][^」”\"']+[」”\"']", unit))


def extract_dialogue(unit: str) -> str:
    match = re.search(r"[「“\"']([^」”\"']+)[」”\"']", unit)
    return match.group(1) if match else ""


def scene_of(unit: str) -> str:
    scene = re.sub(r"[「“\"'][^」”\"']*[」”\"']", "", unit)
    return scene.strip("：:，,。 ") or unit


def guess_title(story: str) -> str:
    for line in story.splitlines():
        raw = line.strip()
        if raw.startswith("#"):
            title = clean_line(raw)
            title = re.sub(r"[（(].*?[）)]", "", title).strip()
            if title:
                return title[:24]
    for line in story.splitlines():
        line = clean_line(line)
        if line and not line.endswith(("。", "！", "？")):
            return line[:24]
    return "未命名短片"


def phase_of(index: int, total: int) -> str:
    pos = (index + 1) / max(total, 1)
    if pos <= 0.3:
        return "建立"
    if pos <= 0.75:
        return "升级"
    return "反转"


def pick_sounds(text: str) -> str:
    sounds = [value for key, value in SOUND_HINTS.items() if key in text]
    return "、".join(sounds[:2]) if sounds else "环境底噪、轻微呼吸声"


def character_anchor(story: str) -> str:
    """从故事里猜主角称呼：优先「名字：」行，其次高频「角色+动作」，兜底「主角」。"""
    skip_prefix = {"字幕浮现", "字幕", "旁白", "画外音", "内心", "画面", "镜头", "提示", "音效"}
    for line in story.splitlines():
        line = clean_line(line)
        if "：" in line:
            name = line.split("：", 1)[0].strip()
            if 1 < len(name) <= 6 and name not in skip_prefix and not re.search(r"[「」“”]", name):
                return name
    verbs = "趴在|看向|接起|推门|踢|走|跑|站|坐|转身|抬头|低头|伸手|摘下|拿着|迟疑|盯着"
    candidates = re.findall(rf"([\u4e00-\u9fa5]{{2,4}})(?={verbs})", story)
    stop = {"自己", "声音", "电话", "人影", "听筒", "店员自己"}
    from collections import Counter

    ranked = [
        (name, count)
        for name, count in Counter(candidates).most_common()
        if name not in stop
    ]
    if ranked:
        return ranked[0][0]
    return "主角"


def build_shots(story: str, duration: int, shots_target: int | None) -> tuple[list[dict], str]:
    units = split_units(story)
    if not units:
        raise ValueError("故事内容为空，请至少提供一句话。")
    title = guess_title(story)
    character = character_anchor(story)
    if shots_target is None:
        shots_target = max(6, min(24, round(duration / 4.5)))
    # 将长句拆短，凑到目标镜头数
    expanded: list[str] = []
    for unit in units:
        expanded.extend(split_long(unit))
    while len(expanded) < shots_target:
        # 拆分最长的句子
        idx = max(range(len(expanded)), key=lambda i: len(expanded[i]))
        pieces = split_long(expanded[idx], limit=max(24, len(expanded[idx]) // 2))
        if len(pieces) <= 1:
            break
        expanded[idx : idx + 1] = pieces
    if len(expanded) > shots_target:
        merged: list[str] = []
        step = len(expanded) / shots_target
        for i in range(shots_target):
            chunk = expanded[int(i * step) : int((i + 1) * step)] or [expanded[-1]]
            merged.append("；".join(x.rstrip("。") for x in chunk))
        expanded = merged

    total = len(expanded)
    per_shot = max(2.0, round(duration / total, 1))
    shots = []
    for i, unit in enumerate(expanded):
        phase = phase_of(i, total)
        size = SHOT_SIZES[phase][i % len(SHOT_SIZES[phase])]
        move = MOVES[phase][i % len(MOVES[phase])]
        dialogue = extract_dialogue(unit)
        scene = scene_of(unit)
        shots.append(
            {
                "no": i + 1,
                "phase": phase,
                "duration": per_shot,
                "size": size,
                "move": move,
                "scene": scene,
                "dialogue": dialogue,
                "sound": pick_sounds(unit),
                "transition": "切" if i % 3 else ("叠化" if phase == "建立" else "硬切"),
                "raw": unit,
            }
        )
    return shots, title, character


def shot_prompt(shot: dict, *, style: dict, aspect: str, character: str) -> str:
    aspect_label = ASPECTS.get(aspect, aspect)
    lines = [
        style["prefix"],
        f"{aspect_label}构图，单镜 {shot['duration']}s",
        f"景别：{shot['size']}；运镜：{shot['move']}",
        f"画面：{shot['scene']}",
    ]
    if shot["dialogue"]:
        lines.append(f"人物：{character}；台词情绪：{shot['dialogue']}")
    lines.append(f"光线与色调：{style['light']}")
    lines.append(f"氛围：{style['mood']}")
    lines.append("细节：真实材质、自然皮肤质感、电影级构图、浅景深")
    lines.append("画质：4K、电影质感、真实光影、无文字水印")
    return "；".join(lines)


def negative_prompt(style: dict) -> str:
    return f"{style['negative']}、{NEGATIVE_BASE}"


def fmt_table(shots: list[dict]) -> str:
    rows = [
        "| 镜号 | 阶段 | 时长 | 景别 | 运镜 | 画面 / 台词 | 音效 | 转场 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for shot in shots:
        scene = shot["scene"].replace("|", "／")
        dialogue = shot["dialogue"].replace("|", "／")
        text = scene + (f"（台词：{dialogue}）" if dialogue else "")
        rows.append(
            f"| {shot['no']:02d} | {shot['phase']} | {shot['duration']}s | {shot['size']} | "
            f"{shot['move']} | {text} | {shot['sound']} | {shot['transition']} |"
        )
    return "\n".join(rows)


def _html_table(shots: list[dict]) -> str:
    cells = ["镜号", "阶段", "时长", "景别", "运镜", "画面 / 台词", "音效", "转场"]
    rows = ["<table><thead><tr>"]
    rows.extend(f"<th>{html.escape(c)}</th>" for c in cells)
    rows.append("</tr></thead><tbody>")
    for shot in shots:
        scene = shot["scene"]
        dialogue = shot["dialogue"]
        text = scene + (f"（台词：{dialogue}）" if dialogue else "")
        values = [
            f"{shot['no']:02d}", shot["phase"], f"{shot['duration']}s", shot["size"],
            shot["move"], text, shot["sound"], shot["transition"],
        ]
        rows.append("<tr>")
        rows.extend(f"<td>{html.escape(v)}</td>" for v in values)
        rows.append("</tr>")
    rows.append("</tbody></table>")
    return "".join(rows)


def build_prompt_md(shots: list[dict], *, title: str, style_name: str, style: dict,
                    aspect: str, character: str, duration: int) -> str:
    lines = [
        f"# 《{title}》提示词包（{style_name} · {aspect} · {duration}s）",
        "",
        f"- 角色锚点：{character}",
        f"- 全片统一前缀：{style['prefix']}",
        f"- 统一负面词：{negative_prompt(style)}",
        f"- 生成建议：先用同一张参考图锁定人物，再逐镜生成；每镜单独提交更稳。",
        "",
    ]
    for shot in shots:
        lines.append(f"## 镜 {shot['no']:02d} · {shot['size']} · {shot['duration']}s")
        lines.append("")
        lines.append("**画面提示词：**")
        lines.append("")
        lines.append("```")
        lines.append(shot_prompt(shot, style=style, aspect=aspect, character=character))
        lines.append("```")
        lines.append("")
        lines.append(f"**负面提示词：** {negative_prompt(style)}")
        if shot["dialogue"]:
            lines.append(f"**台词：** {shot['dialogue']}")
        lines.append("")
    return "\n".join(lines)


def build_html(shots: list[dict], *, title: str, style_name: str, style: dict,
               aspect: str, character: str, duration: int) -> str:
    cards = []
    all_prompts = []
    for shot in shots:
        prompt = shot_prompt(shot, style=style, aspect=aspect, character=character)
        all_prompts.append(prompt)
        safe_prompt = html.escape(prompt)
        dialogue = (
            f"<div class='dialogue'>台词：{html.escape(shot['dialogue'])}</div>"
            if shot["dialogue"]
            else ""
        )
        cards.append(
            f"""
            <section class="card">
              <div class="card-head">
                <span class="no">镜 {shot['no']:02d}</span>
                <span class="tag">{html.escape(shot['phase'])} · {html.escape(shot['size'])} · {shot['duration']}s</span>
                <button class="copy" data-prompt="{safe_prompt}">复制提示词</button>
              </div>
              <div class="scene">{html.escape(shot['scene'])}</div>
              {dialogue}
              <div class="meta">运镜：{html.escape(shot['move'])} ｜ 音效：{html.escape(shot['sound'])} ｜ 转场：{html.escape(shot['transition'])}</div>
              <pre class="prompt">{safe_prompt}</pre>
            </section>
            """
        )
    table_html = _html_table(shots)
    negative = negative_prompt(style)
    all_block = "\n".join(all_prompts)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>《{html.escape(title)}》分镜与提示词</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 24px; background: #0f1115; color: #e6e8ee;
         font: 14px/1.6 "Segoe UI", "Microsoft YaHei", sans-serif; }}
  h1 {{ margin: 0 0 6px; font-size: 22px; }}
  .sub {{ color: #9aa3b2; margin-bottom: 18px; }}
  .toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 18px; }}
  button {{ padding: 6px 12px; border-radius: 8px; border: 1px solid #2c3340;
            background: #1a1f29; color: #e6e8ee; cursor: pointer; }}
  button:hover {{ border-color: #4b6b9a; }}
  .primary {{ background: #2f6fdf; border-color: #2f6fdf; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0 24px;
           font-size: 12.5px; }}
  th, td {{ border: 1px solid #262d39; padding: 6px 8px; vertical-align: top; }}
  th {{ background: #171c25; text-align: left; }}
  .card {{ background: #151a23; border: 1px solid #262d39; border-radius: 10px;
           padding: 12px 14px; margin-bottom: 12px; }}
  .card-head {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
  .no {{ font-weight: 700; color: #7fb0ff; }}
  .tag {{ color: #9aa3b2; font-size: 12px; }}
  .copy {{ margin-left: auto; padding: 4px 10px; font-size: 12px; }}
  .scene {{ margin: 8px 0 4px; }}
  .dialogue {{ color: #ffd479; }}
  .meta {{ color: #8d96a6; font-size: 12px; margin: 4px 0 8px; }}
  pre.prompt {{ margin: 0; padding: 10px; background: #0d1117; border-radius: 8px;
                white-space: pre-wrap; word-break: break-word; font-size: 12.5px;
                color: #c9d4e3; }}
  .neg {{ color: #ff9a9a; font-size: 12px; margin-top: 4px; }}
  footer {{ color: #6f7787; font-size: 12px; margin-top: 28px; }}
</style>
</head>
<body>
  <h1>《{html.escape(title)}》分镜与提示词</h1>
  <div class="sub">{html.escape(style_name)} ｜ {html.escape(aspect)} ｜ {duration}s ｜ {len(shots)} 镜 ｜ 角色：{html.escape(character)}</div>
  <div class="toolbar">
    <button class="primary" id="copy-all">复制全部提示词</button>
    <button id="copy-neg">复制负面提示词</button>
  </div>
  {table_html}
  <div class="toolbar"><button id="copy-all-2">复制全部提示词（纯文本逐行）</button></div>
  {''.join(cards)}
  <div class="neg">统一负面词：{html.escape(negative)}</div>
  <footer>由 story2prompt 生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')} · 提示词可直接粘贴到 即梦 / 可灵 / Seedance 等平台</footer>
<script>
  const ALL = {all_block!r}.replace(/\\\\n/g, "\\n");
  const NEG = {negative!r};
  function copy(text) {{
    navigator.clipboard && navigator.clipboard.writeText(text).then(
      () => toast("已复制"),
      () => fallback(text)
    );
    if (!navigator.clipboard) fallback(text);
  }}
  function fallback(text) {{
    const ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand("copy"); ta.remove(); toast("已复制");
  }}
  function toast(msg) {{
    const el = document.createElement("div");
    el.textContent = msg;
    el.style.cssText = "position:fixed;right:20px;bottom:20px;background:#2f6fdf;color:#fff;padding:6px 12px;border-radius:8px;z-index:9";
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 1200);
  }}
  document.addEventListener("click", (event) => {{
    const btn = event.target.closest("button");
    if (!btn) return;
    if (btn.dataset.prompt) copy(btn.dataset.prompt);
    else if (btn.id.startsWith("copy-all")) copy(ALL);
    else if (btn.id === "copy-neg") copy(NEG);
  }});
</script>
</body>
</html>
"""


DEMO_STORY = """# 午夜来电（60 秒竖屏悬疑）
深夜，便利店的灯管嗡嗡作响，雨点敲着玻璃。
店员趴在收银台打盹，座机突然响起。
他迟疑地接起，听筒里传来与自己一模一样的声音：「听我说，30 秒后有人会进店。」
店员看向门口，雨幕里出现一个撑伞的人影。
电话里的声音急促起来：「别让他碰到柜台下的纸箱。」
人影推门进来，径直走向柜台。
店员下意识把纸箱往脚边踢了踢。
人影摘下兜帽，是七天后的店员自己，手里拿着同一部听筒。
字幕浮现：每一次接通，都是另一次逃亡。"""


PLATFORMS = {"jimeng": "即梦", "kling": "可灵", "seedance": "Seedance"}

KLING_MOVES = {
    "固定机位": "固定",
    "缓慢推近": "推近",
    "快速推近": "快速推近",
    "缓慢拉远": "拉远",
    "急推": "急推",
    "轻微横移": "左移",
    "横移跟拍": "右移",
    "跟随拍摄": "跟随",
    "手持轻微晃动": "手持",
    "手持晃动": "手持",
}


def fmt_srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fmt_timecode(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def platform_prompt(shot: dict, *, platform: str, style: dict, aspect: str,
                    character: str) -> str:
    aspect_label = ASPECTS.get(aspect, aspect)
    base = shot_prompt(shot, style=style, aspect=aspect, character=character)
    if platform == "jimeng":
        return base
    if platform == "kling":
        move = KLING_MOVES.get(shot["move"], shot["move"])
        parts = [
            f"{aspect_label}，{shot['duration']}s",
            f"景别：{shot['size']}",
            f"运镜：{move}",
            f"画面：{shot['scene']}",
        ]
        if shot["dialogue"]:
            parts.append(f"人物：{character}")
        parts.extend([f"光线：{style['light']}", f"氛围：{style['mood']}", style["prefix"]])
        return "；".join(parts)
    # seedance
    parts = [
        f"{aspect_label}，单镜 {shot['duration']}s，{shot['size']}，{shot['move']}",
        shot["scene"],
    ]
    if shot["dialogue"]:
        parts.append(f"台词情绪：{shot['dialogue']}")
    parts.extend([
        style["light"],
        style["mood"],
        style["prefix"],
        "4K，电影质感，无文字水印",
    ])
    return "；".join(parts)


def build_platform_files(out: Path, shots: list[dict], *, style: dict, aspect: str,
                         character: str) -> tuple[dict[str, Path], Path]:
    files: dict[str, Path] = {}
    for key, label in PLATFORMS.items():
        lines = [
            platform_prompt(s, platform=key, style=style, aspect=aspect, character=character)
            for s in shots
        ]
        path = out / f"{label}提示词.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        files[label] = path
    neg = out / "平台-负面词.txt"
    neg.write_text(negative_prompt(style) + "\n", encoding="utf-8")
    return files, neg


def build_srt(shots: list[dict]) -> str:
    blocks = []
    t = 0.0
    for shot in shots:
        text = (shot["dialogue"] or shot["scene"]).replace("\n", " ").strip()
        if len(text) > 60:
            text = text[:58] + "…"
        blocks.append(
            f"{shot['no']}\n{fmt_srt_time(t)} --> {fmt_srt_time(t + shot['duration'])}\n{text}"
        )
        t += shot["duration"]
    return "\n\n".join(blocks) + "\n"


def build_dub_md(shots: list[dict], *, title: str, character: str, style_name: str) -> str:
    rows = [
        "| 镜号 | 时间码 | 时长 | 角色 | 台词/旁白 | 情绪建议 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    t = 0.0
    for shot in shots:
        line = (shot["dialogue"] or "（无台词，环境/动作）").replace("|", "／")
        emo = (
            "压低、克制" if shot["phase"] == "建立"
            else ("加快、紧张" if shot["phase"] == "升级" else "停顿后爆发")
        )
        rows.append(
            f"| {shot['no']:02d} | {fmt_timecode(t)} | {shot['duration']}s | "
            f"{character} | {line} | {emo} |"
        )
        t += shot["duration"]
    return (
        f"# 《{title}》配音清单（{style_name}）\n\n"
        + "\n".join(rows)
        + "\n\n> 建议：TTS 语速 4.2–4.8 字/秒；升级段可加呼吸声；反转段结尾留 0.3s 静默。\n"
    )


def build_compare(shots: list[dict], *, title: str, styles: list[str], aspect: str,
                  character: str, duration: int) -> tuple[str, str]:
    md = [f"# 《{title}》多风格对比（{aspect} · {duration}s）", ""]
    html_cards = []
    for shot in shots:
        md.append(f"## 镜 {shot['no']:02d} · {shot['size']} · {shot['duration']}s")
        md.append("")
        grid = []
        for name in styles:
            style = STYLES[name]
            prompt = shot_prompt(shot, style=style, aspect=aspect, character=character)
            md.append(f"### {name}")
            md.append("")
            md.append(f"```\n{prompt}\n```")
            md.append("")
            safe = html.escape(prompt, quote=True)
            grid.append(
                f"<div class='style'><h4>{html.escape(name)}"
                f"<button class='copy' data-prompt=\"{safe}\">复制</button></h4>"
                f"<pre class='prompt'>{safe}</pre></div>"
            )
        html_cards.append(
            f"<section class='card'><div class='card-head'><span class='no'>镜 {shot['no']:02d}</span>"
            f"<span class='tag'>{html.escape(shot['size'])} · {shot['duration']}s</span></div>"
            f"<div class='grid'>{''.join(grid)}</div></section>"
        )
    page_html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>《{html.escape(title)}》多风格对比</title>
<style>
 :root {{ color-scheme: dark; }}
 body {{ margin:0; padding:24px; background:#0f1115; color:#e6e8ee;
        font:14px/1.6 "Segoe UI","Microsoft YaHei",sans-serif; }}
 h1 {{ margin:0 0 6px; }} .sub {{ color:#9aa3b2; margin-bottom:16px; }}
 .card {{ background:#151a23; border:1px solid #262d39; border-radius:10px; padding:12px 14px; margin-bottom:14px; }}
 .card-head {{ display:flex; gap:10px; align-items:center; margin-bottom:8px; }}
 .no {{ color:#7fb0ff; font-weight:700; }} .tag {{ color:#9aa3b2; font-size:12px; }}
 .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px; }}
 .style {{ background:#0d1117; border:1px solid #232a36; border-radius:8px; padding:10px; }}
 .style h4 {{ margin:0 0 8px; display:flex; align-items:center; gap:8px; }}
 .copy {{ margin-left:auto; padding:3px 10px; font-size:12px; border-radius:6px;
          border:1px solid #2c3340; background:#1a1f29; color:#e6e8ee; cursor:pointer; }}
 pre.prompt {{ margin:0; white-space:pre-wrap; word-break:break-word; font-size:12px;
               color:#c9d4e3; }}
</style></head>
<body>
 <h1>《{html.escape(title)}》多风格对比</h1>
 <div class="sub">{html.escape(' ｜ '.join(styles))} ｜ {html.escape(aspect)} ｜ {duration}s ｜ {len(shots)} 镜 ｜ 角色：{html.escape(character)}</div>
 <div class="toolbar"><button id="copy-all">复制全部（逐镜·逐风格）</button></div>
 {''.join(html_cards)}
<script>
 const ALL = document.getElementById('copy-all');
 const lines = Array.from(document.querySelectorAll('.style pre.prompt')).map(el => el.textContent);
 function toast(msg) {{ const el=document.createElement('div'); el.textContent=msg;
   el.style.cssText='position:fixed;right:20px;bottom:20px;background:#2f6fdf;color:#fff;padding:6px 12px;border-radius:8px;z-index:9';
   document.body.appendChild(el); setTimeout(()=>el.remove(),1200); }}
 function fallback(text) {{ const ta=document.createElement('textarea'); ta.value=text;
   document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); toast('已复制'); }}
 function copy(text) {{ if (navigator.clipboard) navigator.clipboard.writeText(text).then(()=>toast('已复制'),()=>fallback(text));
   else fallback(text); }}
 document.addEventListener('click', (event) => {{
   const btn = event.target.closest('button'); if (!btn) return;
   if (btn.id === 'copy-all') copy(lines.join('\\n\\n'));
   else if (btn.dataset.prompt) copy(btn.dataset.prompt);
 }});
</script></body></html>"""
    return "\n".join(md), page_html


def run(args: argparse.Namespace) -> int:
    if args.demo:
        story = DEMO_STORY
        title_hint = "午夜来电"
    elif args.story:
        story = Path(args.story).read_text(encoding="utf-8-sig")
        title_hint = Path(args.story).stem
    elif args.text:
        story = args.text
        title_hint = "未命名短片"
    else:
        print("请粘贴故事（空行结束，Ctrl+Z 回车结束）：", file=sys.stderr)
        story = sys.stdin.read()
        title_hint = "未命名短片"
    story = story.strip()
    if not story:
        print("错误：故事内容为空。", file=sys.stderr)
        return 2

    style_name = args.style if args.style in STYLES else "悬疑"
    style = dict(STYLES[style_name])
    style["prefix"] = args.prefix or style["prefix"]
    if args.aspect not in ASPECTS:
        print(f"错误：--aspect 只支持 {', '.join(ASPECTS)}", file=sys.stderr)
        return 2

    try:
        shots, title, character = build_shots(story, args.duration, args.shots)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    if args.title:
        title = args.title
    elif not args.demo:
        title = title_hint if title_hint != "未命名短片" else title

    out = Path(args.out or f"output-{title}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "分镜表.md").write_text(
        f"# 《{title}》分镜表\n\n" + fmt_table(shots) + "\n", encoding="utf-8"
    )
    (out / "提示词包.md").write_text(
        build_prompt_md(shots, title=title, style_name=style_name, style=style,
                        aspect=args.aspect, character=character, duration=args.duration),
        encoding="utf-8",
    )
    prompts_txt = "\n".join(
        shot_prompt(shot, style=style, aspect=args.aspect, character=character)
        for shot in shots
    )
    (out / "prompts.txt").write_text(prompts_txt + "\n", encoding="utf-8")
    html_path = out / "分镜与提示词.html"
    html_path.write_text(
        build_html(shots, title=title, style_name=style_name, style=style,
                   aspect=args.aspect, character=character, duration=args.duration),
        encoding="utf-8",
    )

    print(f"已生成：{out.resolve()}")
    print(f"  - 分镜表.md           {len(shots)} 镜")
    print(f"  - 提示词包.md         每镜画面提示词 + 负面词")
    print(f"  - prompts.txt         纯文本逐行（可批量粘贴）")
    print(f"  - 分镜与提示词.html   双击打开，逐个复制")

    if not getattr(args, "no_platforms", False):
        files, neg = build_platform_files(
            out, shots, style=style, aspect=args.aspect, character=character
        )
        print(f"  - 平台提示词：{'、'.join(f'{label}提示词.txt' for label in files)} + 平台-负面词.txt")

    if not getattr(args, "no_subs", False):
        (out / "字幕.srt").write_text(build_srt(shots), encoding="utf-8")
        (out / "配音清单.md").write_text(
            build_dub_md(shots, title=title, character=character, style_name=style_name),
            encoding="utf-8",
        )
        print("  - 字幕.srt / 配音清单.md")

    if args.compare:
        names = [n.strip() for n in args.compare.replace("，", ",").split(",") if n.strip() in STYLES]
        if names:
            compare_md, compare_html = build_compare(
                shots, title=title, styles=names, aspect=args.aspect,
                character=character, duration=args.duration,
            )
            (out / "多风格对比.md").write_text(compare_md + "\n", encoding="utf-8")
            (out / "多风格对比.html").write_text(compare_html, encoding="utf-8")
            print(f"  - 多风格对比.md / 多风格对比.html（{'、'.join(names)}）")
        else:
            print(f"  ! --compare 未识别风格，可选：{', '.join(STYLES)}", file=sys.stderr)

    print()
    print("下一步：打开 分镜与提示词.html → 复制提示词 → 粘贴到 即梦/可灵/Seedance 生成。")
    if args.open:
        webbrowser.open(html_path.resolve().as_uri())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="story2prompt —— 故事 → 分镜 → 可粘贴提示词包（零依赖、零配置）"
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--story", help="故事文本文件路径（UTF-8）")
    src.add_argument("--text", help="直接传入故事文本")
    src.add_argument("--demo", action="store_true", help="用内置演示故事《午夜来电》")
    parser.add_argument("--out", help="输出目录（默认 output-<标题>）")
    parser.add_argument("--title", help="短片标题")
    parser.add_argument("--duration", type=int, default=60, help="总时长秒数（默认 60）")
    parser.add_argument("--shots", type=int, help="镜头数（默认按时长自动 6–24）")
    parser.add_argument("--aspect", default="9:16", choices=list(ASPECTS), help="画幅")
    parser.add_argument("--style", default="悬疑", choices=list(STYLES), help="风格")
    parser.add_argument("--prefix", help="覆盖风格前缀（可选）")
    parser.add_argument("--compare", help="多风格对比，如「悬疑,写实,都市」")
    parser.add_argument("--no-platforms", action="store_true", help="不生成 即梦/可灵/Seedance 分平台提示词")
    parser.add_argument("--no-subs", action="store_true", help="不生成 字幕.srt / 配音清单.md")
    parser.add_argument("--open", action="store_true", help="生成后自动打开 HTML")
    args = parser.parse_args(argv)
    if not (args.demo or args.story or args.text):
        args.demo = True
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
