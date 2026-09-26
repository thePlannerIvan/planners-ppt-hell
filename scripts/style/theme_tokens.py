#!/usr/bin/env python3
"""风格库读法：`video-craft/visual/themes/<id>/`（tokens.css + theme.json）。

视频画面路线的视觉身份来自**风格库**（配色与字型 token），不是模板库。这个脚本是
读它的唯一入口：

- `list`  库里有什么：id、name、nameZh、`theme.json` 的 preview 色值。
- `show <id>`  把 `tokens.css` 的 `:root` 块解析成键值对，**把 `var()` 展开成实际值**，
  并把**解析不掉的 token 明确报出来**——那些是主题自己的缺陷，不默默当没有。

主题目录的位置不写死：`--themes-dir` > 环境变量 `PPT_HELL_THEMES_DIR` > 默认按 Skill 根的
相对位置找（兄弟 Skill `video-craft/visual/themes`）。一个都找不到时报错说清找过哪里、
可以用什么覆盖。
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

# 主题目录的环境变量名。它让风格库换位置时不必改代码。
THEMES_DIR_ENV = "PPT_HELL_THEMES_DIR"

REQUIRED_THEME_FIELDS = ("id", "name", "nameZh")
PREVIEW_FIELDS = ("shell", "surface", "text", "accent")

COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
VAR_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)\s*(?:,([^()]*))?\)")
DECL_RE = re.compile(r"(--[A-Za-z0-9_-]+)\s*:")


class UnresolvedRef(Exception):
    """一个 token 的 `var()` 引用解析不掉（缺定义或成环）。"""

    def __init__(self, missing):
        super().__init__("unresolved var() reference")
        self.missing = list(missing)


def skill_root():
    return Path(__file__).resolve().parents[2]


def default_theme_dirs():
    """默认按 Skill 根的相对位置找。第一个存在的就是它。"""
    root = skill_root()
    return [
        root.parent / "video-craft" / "visual" / "themes",
        root / "assets" / "themes",
    ]


def resolve_themes_dir(explicit="", env=None):
    """风格库目录 + 它是从哪来的。找不到时报清楚的错，不猜一个空目录。"""
    environ = os.environ if env is None else env
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(f"--themes-dir 指向的不是一个目录：{path}")
        return path, "--themes-dir"
    from_env = str(environ.get(THEMES_DIR_ENV) or "").strip()
    if from_env:
        path = Path(from_env).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(f"环境变量 {THEMES_DIR_ENV} 指向的不是一个目录：{path}")
        return path, f"环境变量 {THEMES_DIR_ENV}"
    tried = default_theme_dirs()
    for candidate in tried:
        if candidate.is_dir():
            return candidate, "默认位置（Skill 根的相对位置）"
    raise ValueError(
        "找不到风格库目录。找过这些位置：\n  "
        + "\n  ".join(str(path) for path in tried)
        + f"\n可以用 --themes-dir <目录> 或环境变量 {THEMES_DIR_ENV} 指定风格库在哪。"
    )


def load_theme(theme_dir):
    """`theme.json` 当 JSON 解析并做最小校验：必需字段在不在。"""
    path = theme_dir / "theme.json"
    if not path.is_file():
        raise ValueError(f"{theme_dir.name}: 没有 theme.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{theme_dir.name}: theme.json 不是合法 JSON（{exc}）")
    if not isinstance(data, dict):
        raise ValueError(f"{theme_dir.name}: theme.json 的最外层必须是一个对象")
    problems = [key for key in REQUIRED_THEME_FIELDS if not str(data.get(key) or "").strip()]
    preview = data.get("preview")
    if not isinstance(preview, dict):
        problems.append("preview（对象）")
    else:
        problems += [f"preview.{key}" for key in PREVIEW_FIELDS
                     if not str(preview.get(key) or "").strip()]
    if problems:
        raise ValueError(f"{theme_dir.name}: theme.json 缺必需字段：{', '.join(problems)}")
    return data


def _root_block(css_text):
    """`:root` 块的内容（按花括号配平取，值里带括号也不会截断）。"""
    start = css_text.find(":root")
    if start < 0:
        return None
    opening = css_text.find("{", start)
    if opening < 0:
        return None
    depth = 0
    for index in range(opening, len(css_text)):
        char = css_text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return css_text[opening + 1:index]
    return None


def parse_root_tokens(css_text):
    """`tokens.css` 的 `:root` 块 → {token: 声明值}。

    注释先去掉；值是声明原文（只做空白归一），展开是下一步的事。
    """
    block = _root_block(COMMENT_RE.sub("", css_text))
    if block is None:
        raise ValueError("tokens.css 里没有 :root 块")
    declarations = {}
    for piece in block.split(";"):
        if ":" not in piece:
            continue
        name, value = piece.split(":", 1)
        name = name.strip()
        if DECL_RE.fullmatch(name + ":"):
            declarations[name] = " ".join(value.split())
    return declarations


def expand_tokens(declarations):
    """把 `var(--x)` 展开成实际值。

    返回 (resolved, unresolved)：

    - `resolved`：{token: 实际值}，值里已经没有 var()。
    - `unresolved`：list of {token, declared, expanded, missing}——**解析不掉的 token**，
      连同它缺的那几个名字。展开了一部分的值也一起给出，方便判断它本来想说什么。
    """
    resolved, unresolved = {}, {}

    def resolve(name, stack):
        if name in resolved:
            return resolved[name]
        if name in unresolved:
            raise UnresolvedRef(unresolved[name]["missing"])
        raw = declarations[name]
        if name in stack:
            cycle = stack[stack.index(name):] + [name]
            missing = ["循环引用：" + " → ".join(cycle)]
            unresolved[name] = {"token": name, "declared": raw, "expanded": raw, "missing": missing}
            raise UnresolvedRef(missing)
        missing = []

        def replace(match):
            ref = match.group(1)
            if ref not in declarations:
                if ref not in missing:
                    missing.append(ref)
                return match.group(0)
            try:
                return resolve(ref, stack + [name])
            except UnresolvedRef as exc:
                for item in exc.missing:
                    if item not in missing:
                        missing.append(item)
                return match.group(0)

        value = VAR_RE.sub(replace, raw)
        if missing:
            unresolved[name] = {"token": name, "declared": raw, "expanded": value, "missing": missing}
            raise UnresolvedRef(missing)
        resolved[name] = value
        return value

    for name in declarations:
        try:
            resolve(name, [])
        except UnresolvedRef:
            pass
    return resolved, list(unresolved.values())


def theme_directories(themes_dir):
    """风格库里的主题目录，按 id 排序。只认带 theme.json 或 tokens.css 的目录。"""
    return sorted((path for path in Path(themes_dir).iterdir()
                   if path.is_dir() and ((path / "theme.json").is_file() or (path / "tokens.css").is_file())),
                  key=lambda path: path.name)


def list_themes(themes_dir, source):
    """库里有什么。一个主题坏了就把它单独报出来，不让整张清单消失。"""
    themes, problems = [], []
    for theme_dir in theme_directories(themes_dir):
        try:
            data = load_theme(theme_dir)
        except ValueError as exc:
            problems.append({"id": theme_dir.name, "problem": str(exc)})
            continue
        item = {"id": theme_dir.name, "name": data["name"], "nameZh": data["nameZh"],
                "preview": {key: data["preview"][key] for key in PREVIEW_FIELDS}}
        if str(data["id"]) != theme_dir.name:
            problems.append({"id": theme_dir.name,
                             "problem": f"theme.json 里写的 id 是 {data['id']!r}，与目录名不一致"})
        if not (theme_dir / "tokens.css").is_file():
            problems.append({"id": theme_dir.name, "problem": "没有 tokens.css"})
        themes.append(item)
    return {"themes_dir": str(themes_dir), "themes_dir_source": source,
            "count": len(themes), "themes": themes, "problems": problems}


def show_theme(themes_dir, theme_id):
    """一个主题展开成什么样：`tokens.css` 的 `:root` 键值对，var() 全部展开。"""
    if not theme_id or "/" in theme_id or "\\" in theme_id or theme_id in (".", ".."):
        raise ValueError(f"主题 id 只能是目录名：{theme_id!r}")
    theme_dir = Path(themes_dir) / theme_id
    if not theme_dir.is_dir():
        known = ", ".join(path.name for path in theme_directories(themes_dir)) or "（一个都没有）"
        raise ValueError(f"风格库里没有这个主题：{theme_id}；库里有：{known}")
    theme = load_theme(theme_dir)
    tokens_path = theme_dir / "tokens.css"
    if not tokens_path.is_file():
        raise ValueError(f"{theme_id}: 没有 tokens.css，没有可展开的 token")
    declarations = parse_root_tokens(tokens_path.read_text(encoding="utf-8-sig"))
    resolved, unresolved = expand_tokens(declarations)
    return {
        "id": theme_dir.name,
        "name": theme["name"],
        "nameZh": theme["nameZh"],
        "preview": {key: theme["preview"][key] for key in PREVIEW_FIELDS},
        "tokens_file": str(tokens_path),
        "tokens": {name: resolved[name] for name in declarations if name in resolved},
        "unresolved": unresolved,
        "summary": {"tokens": len(declarations), "resolved": len(resolved),
                    "unresolved": len(unresolved)},
    }


def main():
    parser = argparse.ArgumentParser(description="Read the video-route style library (themes).")
    parser.add_argument("--themes-dir", default="",
                        help=f"风格库目录；默认按 Skill 根的相对位置找，也可用 {THEMES_DIR_ENV} 覆盖")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="库里有那些主题")
    show = sub.add_parser("show", help="一个主题的 token 展开成实际值")
    show.add_argument("theme_id")
    # 放在子命令后面也认（`show <id> --themes-dir <目录>` 读起来更顺）；
    # SUPPRESS 保证没给的时候不会把主解析器上的值覆盖成空。
    for child in (sub.choices["list"], sub.choices["show"]):
        child.add_argument("--themes-dir", dest="themes_dir", default=argparse.SUPPRESS,
                           help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        themes_dir, source = resolve_themes_dir(getattr(args, "themes_dir", ""))
        result = (list_themes(themes_dir, source) if args.command == "list"
                  else show_theme(themes_dir, args.theme_id))
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
