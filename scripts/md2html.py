#!/usr/bin/env python3
"""极简 Markdown → HTML 转换器（仅 Python 标准库）。

用途：为本仓「需求正文 / 数据库说明 / 字段字典 / 页面数据对应表」生成可直接
阅读的 HTML，原始 Markdown 保留为下载入口。只覆盖本仓文档实际用到的语法：
标题、表格、代码块、引用、列表、行内 code/粗体/链接；未覆盖语法按普通文本透出。
"""
import html
import re
import sys
from pathlib import Path

_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = _LINK.sub(r'<a href="\2">\1</a>', s)
    return s


def _is_table_sep(line: str) -> bool:
    t = line.strip()
    return t.startswith("|") and "-" in t and re.fullmatch(r"\|?[\s:|-]+\|?", t) is not None


def _block_start(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.startswith("```"):
        return True
    if re.match(r"^#{1,6}\s", s):
        return True
    if s.startswith("|"):
        return True
    if s.startswith(">"):
        return True
    if re.fullmatch(r"[-*_]{3,}", s):
        return True
    if re.match(r"^[-*]\s+", s):
        return True
    if re.match(r"^\d+\.\s+", s):
        return True
    return False


def convert(text: str) -> str:
    lines = text.split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()

        if not s:
            i += 1
            continue

        if s.startswith("```"):
            out.append("<pre><code>")
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                out.append(html.escape(lines[i]))
                i += 1
            i += 1  # 跳过结束 ```
            out.append("</code></pre>")
            continue

        if s.startswith("|") and i + 1 < n and _is_table_sep(lines[i + 1]):
            header = [c.strip() for c in s.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append("<table>")
            out.append("<thead><tr>" + "".join(f"<th>{_inline(h)}</th>" for h in header) + "</tr></thead>")
            out.append("<tbody>")
            for r in rows:
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table>")
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        if re.fullmatch(r"[-*_]{3,}", s):
            out.append("<hr>")
            i += 1
            continue

        if s.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            out.append("<blockquote>" + "<br>".join(_inline(b) for b in buf) + "</blockquote>")
            continue

        if re.match(r"^[-*]\s+", s):
            buf = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                buf.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(b)}</li>" for b in buf) + "</ul>")
            continue

        if re.match(r"^\d+\.\s+", s):
            buf = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                buf.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            out.append("<ol>" + "".join(f"<li>{_inline(b)}</li>" for b in buf) + "</ol>")
            continue

        # 段落：累积到空行或下一个块
        buf = [lines[i]]
        i += 1
        while i < n and lines[i].strip() and not _block_start(lines[i]):
            buf.append(lines[i])
            i += 1
        out.append("<p>" + _inline("<br>".join(b.strip() for b in buf)) + "</p>")

    return "\n".join(out)


_WRAP = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:#1c3544;background:#f7f5ed;margin:0;line-height:1.65}}
main{{max-width:980px;margin:0 auto;padding:24px 20px 60px}}
h1{{border-bottom:2px solid #357362;padding-bottom:8px;font-size:24px}}
h2{{border-left:4px solid #357362;padding-left:10px;margin-top:30px;font-size:19px}}
h3{{font-size:15px;color:#9c731f}}
table{{border-collapse:collapse;width:100%;font-size:13.5px;margin:10px 0}}
th,td{{border:1px solid #d8e0dd;padding:6px 10px;text-align:left;vertical-align:top}}
th{{background:#eef3f0}}
code{{background:#eef3f0;padding:1px 5px;border-radius:4px;font-family:ui-monospace,Menlo,monospace;font-size:12.5px}}
blockquote{{border-left:4px solid #d8e0dd;margin:10px 0;padding:6px 14px;color:#5f7078;background:#fffef9}}
pre{{background:#f0ede3;padding:12px;border-radius:8px;overflow:auto}}
.note{{font-size:12.5px;color:#5f7078;border-top:1px solid #d8e0dd;margin-top:32px;padding-top:10px}}
</style>
</head>
<body><main>
{body}
<p class="note">本文档由对应 Markdown 用 scripts/md2html.py 生成；原始 Markdown 为权威源，可下载/直读。</p>
</main></body></html>
"""


def main() -> int:
    # HTML 与源 Markdown 同目录生成，保证文档内相对链接（指向兄弟 md/svg 等）不失效。
    pairs = [
        ("需求分析与设计文档说明.md", "需求分析与设计文档说明.html", "需求分析与设计文档说明"),
        ("docs/database-design/README.md", "docs/database-design/数据库设计说明.html", "数据库设计说明"),
        ("docs/database-design/02-字段字典.md", "docs/database-design/字段字典.html", "字段字典"),
        ("docs/database-design/03-页面数据对应表.md", "docs/database-design/页面数据对应表.html", "页面数据对应表"),
    ]
    for src, dst, title in pairs:
        body = convert(Path(src).read_text(encoding="utf-8"))
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_text(_WRAP.format(title=html.escape(title), body=body), encoding="utf-8")
        print("generated", dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
