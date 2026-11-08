#!/usr/bin/env python3
"""
resolve_video_vault.py — 解析私有视频风格库（~/.config/planners/video-vault 或 $PLANNERS_VIDEO_VAULT）中供 planners-ppt-hell 使用的静态画面规则（page.md）、画框安全区（frames/*.json）与多模态锚点图（anchors/）。
无私有库时优雅降级为开源通用模式（default-clean）。
"""

import argparse
import json
import os
from pathlib import Path

DEFAULT_VAULT_LINK = Path.home() / ".config" / "planners" / "video-vault"


def find_vault_root():
    for candidate in (os.environ.get("PLANNERS_VIDEO_VAULT"), str(DEFAULT_VAULT_LINK)):
        if not candidate:
            continue
        p = Path(candidate).expanduser()
        try:
            real = p.resolve()
            if (real / "manifest.json").is_file() and (real / "styles").is_dir():
                return real
        except OSError:
            continue
    return None


def resolve_style(style_id=None, frame_preset=None):
    vault = find_vault_root()
    if not vault:
        return {
            "vault_available": False,
            "mode": "open-source-default",
            "style_id": style_id or "default-clean",
            "production_mode": "keyframe-svg",
            "canvas": {"width": 1920, "height": 1080},
            "page_rules": "# 开源通用视频静态画面规范 (default-clean)\n- 画幅默认 1920×1080，保持清晰视觉层级与字幕安全区留白。\n- 元素按语义分组并赋予可读 id，便于下游 Video Craft 绑定时间轴。",
            "anchors": [],
        }

    manifest = json.loads((vault / "manifest.json").read_text(encoding="utf-8"))
    styles = manifest.get("styles", [])
    sid = style_id if style_id in styles else (styles[0] if styles else "line-art")
    sdir = vault / "styles" / sid
    meta = json.loads((sdir / "style.json").read_text(encoding="utf-8")) if (sdir / "style.json").is_file() else {}
    page_md = (sdir / "page.md").read_text(encoding="utf-8").strip() if (sdir / "page.md").is_file() else ""

    preset_name = frame_preset or meta.get("default_frame_preset", "landscape-left-host").split("/")[0].strip()
    frame_file = vault / "frames" / f"{preset_name}.json"
    frame_data = json.loads(frame_file.read_text(encoding="utf-8")) if frame_file.is_file() else {"canvas": {"width": 1920, "height": 1080}}

    anchors_dir = sdir / "anchors"
    anchors = sorted(str(p) for p in anchors_dir.iterdir() if p.is_file() and not p.name.startswith(".")) if anchors_dir.is_dir() else []

    return {
        "vault_available": True,
        "vault_path": str(vault),
        "mode": "private-vault",
        "style_id": sid,
        "name": meta.get("name", sid),
        "production_mode": meta.get("production_mode", "keyframe-svg"),
        "frame_preset": preset_name,
        "frame": frame_data,
        "tokens": meta.get("tokens", {}),
        "page_rules": page_md,
        "anchors": anchors,
    }


def main():
    parser = argparse.ArgumentParser(description="Resolve video style rules and frame preset from Private Video Vault.")
    parser.add_argument("--style", default=None, help="Target style_id (e.g. line-art, collage)")
    parser.add_argument("--frame", default=None, help="Optional frame_preset override")
    args = parser.parse_args()
    print(json.dumps(resolve_style(args.style, args.frame), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
