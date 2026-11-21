import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from canvas_frame import Canvas

from prepare_source_material import (IMAGE_RE, folder_files, image_name_key, prepare_source_material,
                                     register_image_folder)

INTERNAL_ROOT = "_internal"

CANONICAL_DIRS = [
    f"{INTERNAL_ROOT}/00_project",
    f"{INTERNAL_ROOT}/00_project/source/assets",
    f"{INTERNAL_ROOT}/01_content",
    f"{INTERNAL_ROOT}/02_svg_source",
    f"{INTERNAL_ROOT}/03_png_preview",
    f"{INTERNAL_ROOT}/04_validation",
    f"{INTERNAL_ROOT}/05_review/versions",
    f"{INTERNAL_ROOT}/06_ppt_output",
    f"{INTERNAL_ROOT}/06_workbench",
    f"{INTERNAL_ROOT}/07_candidates",
    f"{INTERNAL_ROOT}/ref",
]

STARTER_FILES = {
    f"{INTERNAL_ROOT}/01_content/page_content.json": json.dumps(
        {"project": "", "source_path": "", "pages": []}, ensure_ascii=False, indent=2
    ),
    f"{INTERNAL_ROOT}/00_project/page_manifest.json": json.dumps(
        {
            "project": "", "version": "5.0", "route": "slides",
            "template_intake": {"mode": "autonomous"},
            "pages": [],
        },
        ensure_ascii=False, indent=2,
    ),
    f"{INTERNAL_ROOT}/00_project/flow_events.jsonl": "",
}

# visual-plan.json（上游 video-idea-system 的画面契约）的字段。这个清单只属于这一层
# 适配器：ppt-hell 的核心（project_state、校验器、审阅、转换）不认识它。
PLAN_SCREEN_KEYS = {
    "screen_id", "beat_id", "title", "question", "must_show", "must_express",
    "exact_labels", "evidence", "sample", "footage_request", "kick_word",
}
PLAN_SAMPLE_KEYS = {"layout", "assets", "captions", "note", "cols", "thumbCols"}
PLAN_ASSET_KEYS = {
    "kind", "path", "label", "span", "mark", "zoom", "dim", "columns", "lines",
    "viewport", "limit",
}
PLAN_ROOT_KEYS = {"contract_version", "title", "script_hash", "screens", "style_id", "production_mode", "frame_preset"}
PLAN_CONTRACT = "5.0"
PAGE_KEY_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")

# 契约里 `must_show` 以「文字：」开头的条目是**正文**（不属于花字层）。
# 标记本身是契约的标记，不是要画上屏的字。
BODY_MARKERS = ("文字：", "文字:")
# `content` 按来源分组，让做画面看得出哪一条来自哪一类。
CONTENT_GROUPS = (
    ("正文", "body"),
    ("必须出现的内容", "must_show"),
    ("原样标签", "exact_labels"),
    ("花字", "captions"),
)


def source_asset_index(manifest):
    """Registered manifest → {file name key: (file name, asset ID)}.

    Every registered file name appears in `occurrences` (a deduplicated picture carries
    one occurrence per file that fed it), so this index is the complete list of registered
    images.
    """
    index = {}
    for asset in manifest.get("assets", []):
        for occurrence in asset.get("occurrences", []):
            name = occurrence["original_ref"]
            index[image_name_key(name)] = (name, asset["asset_id"])
    return index


def _strings(value, where):
    """A visual-plan string list → the non-empty strings it holds."""
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{where} must be an array of strings")
    return [item.strip() for item in value if item.strip()]


def _split_must_show(items):
    """`must_show` → (正文, 必须出现的内容)。

    「文字：」是契约的标记，不是正文；剥掉标记，剩下的才是要出现在画面上的字。
    """
    body, on_screen = [], []
    for item in items:
        marker = next((m for m in BODY_MARKERS if item.startswith(m)), "")
        if marker:
            text = item[len(marker):].strip()
            if text:
                body.append(text)
        else:
            on_screen.append(item)
    return body, on_screen


def _content_lines(screen, screen_id, caps):
    """上屏内容，按来源分组并去掉完全重复的条目。

    同一信息在 `must_show` 与 `exact_labels` 里各写一份是上游常见的写法；
    画面上它只有一处，所以这里只留第一次出现的那条。**不**要求 `exact_labels`
    是 `must_show` 的子集——子集关系不是契约的要求，去重才是。
    """
    body, on_screen = _split_must_show(_strings(screen.get("must_show"), f"{screen_id}.must_show"))
    groups = {
        "body": body,
        "must_show": on_screen,
        "exact_labels": _strings(screen.get("exact_labels"), f"{screen_id}.exact_labels"),
        "captions": caps,
    }
    seen, lines = set(), []
    for heading, key in CONTENT_GROUPS:
        unique = []
        for item in dict.fromkeys(groups[key]):
            if item in seen:
                continue
            seen.add(item)
            unique.append(item)
        if unique:
            lines.append(f"【{heading}】")
            lines.extend(unique)
    return lines


def _asset_reference(asset, screen_id, index, folder, accounted):
    """One visual-plan sample asset → its registered asset ID, or notes-only material.

    `path` is upstream's path relative to its own asset root (e.g.
    `deliverable/assets/shots/s02-01.png`), so a flat `--assets` folder is matched by
    full name first and by base name second. Images become registered IDs; every other
    kind (csv/html/glob/video) cannot be a registered source asset, so it is carried
    into notes verbatim instead of being dropped.

    `label` is the caption under the picture **on the review page** — it is not on-screen
    text and never enters `content`.
    """
    if not isinstance(asset, dict):
        raise ValueError(f"{screen_id}: every sample asset must be an object")
    kind = asset.get("kind")
    path = asset.get("path")
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError(f"{screen_id}: every sample asset needs a kind (image/csv/html/glob/video)")
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"{screen_id}: every sample asset needs a path")
    path = path.strip()
    extra = {k: v for k, v in asset.items() if k not in {"kind", "path", "label"}}
    label = str(asset.get("label") or "").strip()
    described = f"{kind} {path}" + (f"（审阅页图注：{label}）" if label else "")
    if extra:
        described += " " + json.dumps(extra, ensure_ascii=False, sort_keys=True)
    if kind != "image":
        return None, None, f"样张素材（{kind}，不是登记图片，未成为源资产）：{described}"
    slash = path.replace("\\", "/")
    candidates = [path] + ([slash.rsplit("/", 1)[-1]] if "/" in slash else [])
    for candidate in candidates:
        key = image_name_key(candidate)
        if key in index:
            accounted.add(key)
            return index[key][1], index[key][0], f"样张素材：{described}"
    raise ValueError(
        f"{screen_id}: sample asset path is not in the --assets folder: {path}"
        f" (folder has: {', '.join(sorted(folder)) or 'no files'})"
    )


def adapt_visual_plan(plan, manifest, folder, unknown=None):
    """视觉契约 visual-plan.json → ppt-hell 的 page_content.json。

    这里是两套词汇之间**唯一**的适配点。ppt-hell 的核心只认 page_content.json。

    身份直传：`screens[].screen_id` 是上游稳定的屏 ID，原样成为 `pages[].page_key`——
    不改名、不重新编号、不另开一套 ID 空间。它的合法性仍按 ppt-hell 的 page_key 规则
    检查，不合格就报错而不是替上游改名。

    分流只按一个问题：**这条信息该不该出现在屏幕上？**
      上屏 → `content`：`must_show`（去掉「文字：」标记后按正文／必须出现的内容分组）、
             `exact_labels`、`sample.captions`（花字）。`sample.assets[].label` 是审阅页的
             图注，不是上屏文字，不进 `content`。
      理由、来源与追溯 → `notes`：`question`、`must_express`、`evidence`、`beat_id`、
       `sample` 的样张说明。
    认不出的字段既不进 `content` 也不留在 `notes`：它们被收进 `unknown` 交回调用方打印，
    由人当场裁决（契约升级加字段时不能直接把这条路打死）。
    """
    if not isinstance(plan, dict):
        raise ValueError("visual-plan.json must be an object")
    if plan.get("contract_version") != PLAN_CONTRACT:
        raise ValueError(
            f"the visual-plan.json route needs contract_version {PLAN_CONTRACT!r} with a screens "
            f"array; found {plan.get('contract_version')!r}"
        )
    if plan.get("production_mode") == "footage-montage":
        raise ValueError(
            f"visual-plan.json declares production_mode='footage-montage' (style_id={plan.get('style_id')!r}): "
            "实景/档案混剪风格无需经过 planners-ppt-hell 画静态 SVG 页面，请直接交接给 video-craft 走 montage 路线"
        )
    if not str(plan.get("title") or "").strip():
        raise ValueError("visual-plan.json must carry a non-empty title")
    screens = plan.get("screens")
    if not isinstance(screens, list) or not screens:
        raise ValueError("visual-plan.json must carry a non-empty screens array")
    plan_extra = {k: v for k, v in plan.items() if k not in PLAN_ROOT_KEYS}

    index = source_asset_index(manifest)
    accounted = set()
    seen_paths = {}
    pages = []
    for screen in screens:
        if not isinstance(screen, dict):
            raise ValueError("every entry in screens must be an object")
        screen_id = str(screen.get("screen_id") or "").strip()
        if not PAGE_KEY_RE.fullmatch(screen_id):
            raise ValueError(
                "visual-plan.json screen_id becomes this project's page_key unchanged, and "
                f"{screen_id!r} is not a legal page_key (letter first, then letters/digits/_/-, "
                "at most 64); fix it upstream instead of renaming it here"
            )
        if any(p["page_key"] == screen_id for p in pages):
            raise ValueError(f"duplicate screen_id: {screen_id}")

        sample = screen.get("sample") or {}
        if not isinstance(sample, dict):
            raise ValueError(f"{screen_id}: sample must be an object")
        caps = _strings(sample.get("captions"), f"{screen_id}.sample.captions")
        content = _content_lines(screen, screen_id, caps)
        title = str(screen.get("title") or "").strip()
        if not title:
            raise ValueError(f"{screen_id}: title is required")

        notes = [
            f"上游画面契约：visual-plan.json {plan.get('contract_version')}"
            f" · script_hash {plan.get('script_hash') or '(空)'}",
        ]
        if screen.get("beat_id"):
            notes.append(f"beat_id：{screen['beat_id']}")
        if screen.get("question"):
            notes.append(f"本段口播要回答的问题：{screen['question']}")
        if screen.get("must_express"):
            notes.append("必须表达的语义事实：" + "；".join(_strings(screen["must_express"], "must_express")))
        if screen.get("evidence"):
            notes.append("证据与来源：" + "；".join(_strings(screen["evidence"], "evidence")))
        if sample:
            shape = "，".join(f"{k}={sample[k]}" for k in ("layout", "cols", "thumbCols") if sample.get(k) is not None)
            notes.append(f"样张：{shape}" + (f" — {sample['note']}" if sample.get("note") else ""))

        asset_ids = []
        for asset in sample.get("assets") or []:
            asset_id, file_name, line = _asset_reference(asset, screen_id, index, folder, accounted)
            notes.append(line)
            if asset_id is None:
                continue
            raw = str(asset["path"]).strip()
            other = seen_paths.setdefault(file_name, raw)
            if other != raw:
                raise ValueError(
                    f"{screen_id}: two different sample asset paths ({other} and {raw}) resolve to "
                    f"the same file in the --assets folder ({file_name}); flattening made them ambiguous"
                )
            if asset_id not in asset_ids:
                asset_ids.append(asset_id)

        # 没有上屏文字是合法的：这一屏可以就是一张画面。真正不成立的只有既无文字也无图的
        # 空屏——没有任何东西可看。图片到这里才解析完，所以判据放在这里。
        if not content and not asset_ids:
            raise ValueError(
                f"{screen_id}: this screen has neither on-screen text (must_show, exact_labels "
                "or captions) nor a registered image, so the page would be blank; fix the "
                "contract upstream rather than padding it here"
            )

        unmapped = {k: v for k, v in screen.items() if k not in PLAN_SCREEN_KEYS}
        unmapped.update({f"sample.{k}": v for k, v in sample.items() if k not in PLAN_SAMPLE_KEYS})
        for asset in sample.get("assets") or []:
            unmapped.update(
                {f"sample.assets[].{k}": v for k, v in asset.items() if k not in PLAN_ASSET_KEYS}
            )
        if unmapped and unknown is not None:
            unknown.extend({"where": screen_id, "field": field, "value": value}
                           for field, value in sorted(unmapped.items()))

        pages.append({
            "page_key": screen_id,
            "mode": "读",
            "title": title,
            "content": "\n".join(content),
            "copy_confirmed": True,
            "source_assets": asset_ids,
            "notes": "\n".join(notes),
        })

    # 契约根部的字段是整份契约的，报一次就够——每屏重复一遍只会把真正的问题淹掉。
    if plan_extra and unknown is not None:
        unknown.extend({"where": "(整个契约)", "field": key, "value": value}
                       for key, value in sorted(plan_extra.items()))

    dropped = sorted(index[key][0] for key in set(index) - accounted)
    if dropped:
        raise ValueError(
            "--assets 是「素材库」，不是交付包；交付包是 <包>/assets/，里面只放 visual-plan.json "
            "引用的那几张图。\n"
            "下面这些图在这份素材库里，但没有任何一屏引用它们 "
            "(these images are in the folder but no screen in visual-plan.json references them):\n  "
            + "\n  ".join(dropped)
            + "\n两条正确做法：把 --assets 指向 <包>/assets/；或者在契约里补上引用它们的屏。\n"
            "禁止为了通过这道检查去删除源素材——那是作者的材料，不是交付物。\n"
            "（这道检查本身保留：它防的是静默丢图。）"
        )
    return {
        "project": str(plan["title"]).strip(),
        "source_path": "",
        "pages": pages,
        "unused_assets": {},
    }


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


_DOC_ANCHOR_RE = re.compile(r"\n?<!--\s*b:[A-Za-z0-9_.-]+\s*-->[ \t]*")


def _parse_frontmatter(raw_text):
    """Return (meta_dict, body_text) if text begins with valid YAML-like `---` frontmatter."""
    text = raw_text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return None, text
    meta = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip("\"'")
    return meta, text[end + 5:]


def _split_trailing_sources(page_lines):
    """Separate trailing contiguous `>` citation blockquotes at page end from section body lines."""
    end = len(page_lines)
    while end > 0 and not page_lines[end - 1].strip():
        end -= 1
    first_quote = end
    idx = end - 1
    saw_quote = False
    while idx >= 0:
        line = page_lines[idx]
        if line.lstrip().startswith(">"):
            saw_quote = True
            first_quote = idx
            idx -= 1
        elif not line.strip() and saw_quote:
            idx -= 1
        else:
            break
    if not saw_quote:
        return page_lines, ""
    sources = "\n".join(line.strip() for line in page_lines[first_quote:end] if line.strip())
    return page_lines[:first_quote], sources


def _collect_page_assets(raw_segments, asset_by_name):
    """Find registered asset IDs referenced by Markdown image syntax in page segments."""
    found = []
    for seg in raw_segments:
        for match in IMAGE_RE.finditer(seg):
            raw_ref = match.group(2).strip()
            ref = raw_ref[1:-1] if raw_ref.startswith("<") and raw_ref.endswith(">") else raw_ref
            if re.match(r"^(?:https?:)?//", ref):
                continue
            aid = asset_by_name.get(Path(ref).name)
            if aid and aid not in found:
                found.append(aid)
    return found


def parse_bypage_doc(normalized_text, source_manifest, normalized_source_path):
    """Parse normalized `planners-doc/2` (`doc: by-page`) Markdown into `page_content.json`, or None."""
    meta, body = _parse_frontmatter(normalized_text)
    if not meta or meta.get("contract") != "planners-doc/2" or meta.get("doc") != "by-page":
        return None

    clean_body = _DOC_ANCHOR_RE.sub("", body)
    asset_by_name = {
        Path(a["normalized_path"]).name: a["asset_id"]
        for a in source_manifest.get("assets", [])
        if not a.get("external") and a.get("normalized_path")
    }

    chapters = []
    raw_pages = []
    current_chapter = ""
    current_page = None

    for line in clean_body.splitlines():
        if line.startswith("# ") and not line.startswith("##"):
            current_chapter = line[2:].strip()
            chapters.append(current_chapter)
        elif line.startswith("## ") and not line.startswith("###"):
            if current_page is not None:
                raw_pages.append(current_page)
            current_page = {"chapter": current_chapter, "title": line[3:].strip(), "lines": []}
        elif current_page is not None:
            current_page["lines"].append(line)
    if current_page is not None:
        raw_pages.append(current_page)

    if not raw_pages:
        raise ValueError("planners-doc/2 by-page.md contains zero `##` pages")

    pages = []
    for idx, entry in enumerate(raw_pages, start=1):
        body_lines, sources_text = _split_trailing_sources(entry["lines"])
        sections = {"正文": [], "口播": [], "制作": []}
        active_sec = None
        for line in body_lines:
            if line.startswith("### "):
                name = line[4:].strip()
                active_sec = name if name in sections else None
            elif active_sec:
                sections[active_sec].append(line)

        content_text = "\n".join(sections["正文"]).strip()
        spoken_text = "\n".join(sections["口播"]).strip()
        prod_text = "\n".join(sections["制作"]).strip()
        source_assets = _collect_page_assets((content_text, prod_text), asset_by_name)
        if not content_text and not source_assets:
            raise ValueError(f"Page {idx} ({entry['title']}) has empty ### 正文 and no image assets")

        pages.append({
            "page_key": f"p{idx:02d}",
            "mode": "读",
            "chapter": entry["chapter"],
            "title": entry["title"],
            "content": content_text,
            "copy_confirmed": True,
            "notes": spoken_text,
            "production_notes": prod_text,
            "sources": sources_text,
            "source_assets": source_assets,
        })

    return {
        "project": meta.get("project") or "",
        "source_path": normalized_source_path,
        "source_assets_path": f"{INTERNAL_ROOT}/00_project/source/source_assets.json",
        "pages": pages,
    }


def validate_sibling_fact_audit(source_path, source_bytes):
    """Verify sibling `fact-audit.json` when present alongside `by-page.md`."""
    audit_path = source_path.parent / "fact-audit.json"
    if not audit_path.is_file():
        return {"present": False}
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("contract_version") != "fact-audit/1.0.0":
        raise ValueError(f"Sibling fact-audit.json must use contract_version fact-audit/1.0.0: {audit_path}")
    expected_sha = hashlib.sha256(source_bytes).hexdigest()
    if (audit.get("artifact") or {}).get("sha256") != expected_sha:
        raise ValueError(
            f"Sibling fact-audit.json does not bind current {source_path.name} (sha256 mismatch); "
            "re-run planners-fact-check before handing off to planners-ppt-hell"
        )
    blocking = [
        f"{s.get('id', '?')}:{s.get('verdict')}"
        for s in (audit.get("suspects") or [])
        if s.get("verdict") in ("confirmed", "no_source", "pending")
    ]
    if blocking:
        raise ValueError(
            f"Sibling fact-audit.json has blocking/unresolved verdicts ({', '.join(blocking)}); "
            "resolve in planners-bypage before initializing PPT project"
        )
    return {
        "present": True,
        "path": str(audit_path),
        "sha256": sha256_file(audit_path),
        "checker": audit.get("checker"),
        "suspect_count": len(audit.get("suspects") or []),
    }


def _write_manifest_state(staging, route, plan_path, plan, canvas=None, upstream=None):
    """项目状态记下路线与契约绑定：路线决定跑哪一半检查，绑定决定画面还算不算数。

    记的是契约文件自己的位置与内容摘要，加上它声明的 `script_hash`；稿子按
    「契约旁边那份 `script.md`」找，不另记一个路径——多一份地址就多一处会过期的说法。
    """
    path = staging / INTERNAL_ROOT / "00_project" / "page_manifest.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["route"] = route
    state["canvas"] = (canvas or Canvas()).as_dict()
    if upstream is not None:
        state["input_kind"] = "bypage-doc"
        state["upstream"] = upstream
    else:
        state["input_kind"] = "visual-plan" if plan_path else "standalone"
    if plan_path is not None:
        state["visual_plan"] = {
            "path": str(plan_path),
            "sha256": sha256_file(plan_path),
            "contract_version": str(plan.get("contract_version")),
            "script_hash": str(plan.get("script_hash") or ""),
        }
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _path_error(parser, label, raw, resolved):
    """路径类报错要说清它是相对哪个目录解析出来的。

    报错里那个拼出来的路径看起来像「文件真的不存在」，实际常常只是相对路径被按
    当前工作目录解析了。
    """
    where = "绝对路径" if Path(raw).expanduser().is_absolute() else "相对路径"
    parser.error(
        f"{label} not found: {resolved}\n"
        f"  （{label} 收到的是{where} {str(raw)!r}；相对路径按当前工作目录解析，"
        f"当前工作目录是 {Path.cwd()}。三个路径都给绝对路径最省事。）"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Initialize a Planner's PPT Hell project scaffold."
    )
    parser.add_argument("project_dir", help="Project output directory")
    route = parser.add_mutually_exclusive_group(required=True)
    route.add_argument("--source", help="Source Markdown, DOC, or DOCX path")
    route.add_argument("--assets", help="Flat folder of loose image files (route with no source document)")
    parser.add_argument("--plan", help="Upstream visual-plan.json handed over with the pack (with --assets)")
    parser.add_argument("--route", choices=("slides", "video"), help="Output route; defaults to slides for source, video for plan")
    parser.add_argument("--width", type=int, default=Canvas().width, help="Project canvas width in SVG pixels")
    parser.add_argument("--height", type=int, default=Canvas().height, help="Project canvas height in SVG pixels")
    args = parser.parse_args()
    try:
        canvas = Canvas(args.width, args.height)
    except ValueError as exc:
        parser.error(str(exc))
    output_route = args.route or ("video" if args.assets else "slides")
    if args.assets and output_route != "video":
        parser.error("--assets with --plan is the video production-pack adapter")
    if args.plan and not args.assets:
        parser.error("--plan belongs to the --assets route; the --source route writes its own content stub")

    source = assets = plan_path = None
    if args.source:
        source = Path(args.source).expanduser().resolve()
        if not source.is_file():
            _path_error(parser, "--source", args.source, source)
    else:
        assets = Path(args.assets).expanduser().resolve()
        if not assets.is_dir():
            _path_error(parser, "--assets", args.assets, assets)
        if not args.plan:
            parser.error(f"--assets {assets} needs --plan <visual-plan.json>: the pack carries it")
        plan_path = Path(args.plan).expanduser().resolve()
        if not plan_path.is_file():
            _path_error(parser, "--plan", args.plan, plan_path)

    root = Path(args.project_dir).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        parser.error(f"project directory is not empty; resume it instead of re-initializing: {root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.init-", dir=str(root.parent)))

    unknown = []
    plan = {}
    try:
        for dir_path in CANONICAL_DIRS:
            (staging / dir_path).mkdir(parents=True, exist_ok=True)

        for rel_path, text in STARTER_FILES.items():
            (staging / rel_path).write_text(text, encoding="utf-8")

        source_root = staging / INTERNAL_ROOT / "00_project" / "source"
        upstream_binding = None
        if source:
            try:
                source_manifest = prepare_source_material(staging, source, source_root)
                normalized_text = (staging / source_manifest["normalized_source"]).read_text(encoding="utf-8")
                parsed_bypage = parse_bypage_doc(normalized_text, source_manifest, source_manifest["normalized_source"])
                if parsed_bypage is not None:
                    audit_info = validate_sibling_fact_audit(source, source.read_bytes())
                    page_content = parsed_bypage
                    upstream_binding = {
                        "contract": "planners-doc/2",
                        "doc": "by-page",
                        "source_path": str(source),
                        "source_sha256": sha256_file(source),
                        "fact_audit": audit_info,
                    }
                else:
                    page_content = {
                        "project": "",
                        "source_path": source_manifest["normalized_source"],
                        "source_assets_path": f"{INTERNAL_ROOT}/00_project/source/source_assets.json",
                        "pages": [],
                    }
            except (OSError, UnicodeError, ValueError) as exc:
                parser.error(str(exc))
        else:
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                source_manifest = register_image_folder(staging, assets, source_root)
                page_content = adapt_visual_plan(plan, source_manifest, folder_files(assets), unknown)
            except (OSError, UnicodeError, ValueError) as exc:
                parser.error(str(exc))
        (staging / INTERNAL_ROOT / "01_content" / "page_content.json").write_text(
            json.dumps(page_content, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _write_manifest_state(staging, output_route, plan_path, plan, canvas, upstream=upstream_binding)

        if root.exists():
            root.rmdir()
        os.replace(staging, root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    print(f"Initialized project at: {root.resolve()}")
    if assets:
        print(f"Registered {source_manifest['image_count']} source image(s) from: {assets}")
    print("User-facing deliverables:")
    print("  02_visual_review.html")
    if output_route == "video":
        print("  SVG files and referenced assets (current saved revisions; no export required)")
    else:
        print("  final_deck.pptx")
    print("Internal workspace:")
    for d in CANONICAL_DIRS:
        print(f"  {d}/")
    for rel_path in STARTER_FILES:
        print(f"  {rel_path}")

    if unknown:
        # 认不出的字段当场点名，不再塞进一个没人读的「待裁决」收集器。
        print("warning: visual-plan.json 里有这个适配器认不出的字段（没有搬进任何产物，需要当场裁决）：",
              file=sys.stderr)
        for item in unknown:
            print(f"  {item['where']} · {item['field']} = {json.dumps(item['value'], ensure_ascii=False)}",
                  file=sys.stderr)
        print("  处理办法：在契约里改名成已认识的字段；如果它本来就是上屏内容，明确写进 must_show／"
              "exact_labels／captions。认不出的字段不会自己出现在画面上，这不是失败，是需要一个决定。",
              file=sys.stderr)


if __name__ == "__main__":
    main()
