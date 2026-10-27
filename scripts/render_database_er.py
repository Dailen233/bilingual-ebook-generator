#!/usr/bin/env python3
"""Export a review ER SVG from explicit MySQL CREATE TABLE statements.

Python standard library only. Does not connect to a database or launch a browser.
This is a deliberately small parser for the project's design-DDL format, not a
MySQL syntax validator. It fails on unparsed table items and non-self FK cycles.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Column:
    name: str
    kind: str
    nullable: bool
    keys: list[str] = field(default_factory=list)


@dataclass
class Table:
    name: str
    columns: list[Column]
    unique: list[tuple[str, ...]]


@dataclass
class ForeignKey:
    child: str
    columns: tuple[str, ...]
    parent: str
    targets: tuple[str, ...]


def names(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"`([^`]+)`", value))


def parse(sql: str) -> tuple[list[Table], list[ForeignKey]]:
    # This input format puts explanatory SQL comments on their own lines.
    sql = re.sub(r"(?m)^\s*--.*$", "", sql)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    blocks = list(re.finditer(
        r"(?ms)^\s*CREATE\s+TABLE\s+`([^`]+)`\s*\((.*?)^\)\s*ENGINE\s*=.*?;",
        sql,
    ))
    if len(blocks) != len(re.findall(r"(?im)^\s*CREATE\s+TABLE\b", sql)):
        raise ValueError("Unparsed CREATE TABLE; expected explicit backticks and ENGINE clause")
    if not blocks:
        raise ValueError("No active CREATE TABLE statements")
    tables, foreign = [], []
    for block in blocks:
        table_name, body = block.group(1), block.group(2)
        columns, primary, unique, indexes = [], (), [], []
        for raw_line in body.splitlines():
            line = raw_line.strip().rstrip(",")
            if not line:
                continue
            col = re.match(r"`([^`]+)`\s+([A-Za-z]+(?:\([^)]*\))?(?:\s+UNSIGNED)?)(.*)$", line)
            if col:
                columns.append(Column(col.group(1), col.group(2).upper(), "NOT NULL" not in col.group(3).upper()))
                continue
            pk = re.match(r"PRIMARY KEY\s*\(([^)]*)\)", line, re.I)
            if pk:
                primary = names(pk.group(1))
                continue
            uk = re.match(r"UNIQUE (?:KEY|INDEX)\s+`[^`]+`\s*\(([^)]*)\)", line, re.I)
            if uk:
                unique.append(names(uk.group(1)))
                continue
            fk = re.match(r"(?:CONSTRAINT\s+`[^`]+`\s+)?FOREIGN KEY\s*\(([^)]*)\)\s+REFERENCES\s+`([^`]+)`\s*\(([^)]*)\)", line, re.I)
            if fk:
                foreign.append(ForeignKey(table_name, names(fk.group(1)), fk.group(2), names(fk.group(3))))
                continue
            ix = re.match(r"(?:KEY|INDEX)\s+`[^`]+`\s*\(([^)]*)\)", line, re.I)
            if ix:
                indexes.append(names(ix.group(1)))
                continue
            if re.match(r"(?:CONSTRAINT\s+`[^`]+`\s+)?CHECK\s*\(", line, re.I):
                # CHECK expressions must be single-line in this intentionally limited format.
                if not line.endswith(")"):
                    raise ValueError(f"Multi-line CHECK not supported in {table_name}")
                continue
            raise ValueError(f"Unparsed table item in {table_name}: {line[:100]}")
        if not primary:
            raise ValueError(f"Missing primary key in {table_name}")
        by_name = {c.name: c for c in columns}
        if len(by_name) != len(columns):
            raise ValueError(f"Duplicate column in {table_name}")
        for name in primary:
            by_name[name].keys.append("PK")
            by_name[name].nullable = False
        for group in unique:
            for name in group:
                by_name[name].keys.append("UK" if len(group) == 1 else "U*")
        for group in indexes:
            for name in group:
                if not any(k in by_name[name].keys for k in ("PK", "UK", "U*", "IX")):
                    by_name[name].keys.append("IX")
        tables.append(Table(table_name, columns, [primary, *unique]))
    by_table = {t.name: t for t in tables}
    if len(by_table) != len(tables):
        raise ValueError("Duplicate table names")
    for fk in foreign:
        if fk.parent not in by_table:
            raise ValueError(f"Unknown referenced table: {fk.parent}")
        child_cols = {c.name: c for c in by_table[fk.child].columns}
        parent_cols = {c.name: c for c in by_table[fk.parent].columns}
        if len(fk.columns) != len(fk.targets):
            raise ValueError(f"Mismatched FK arity in {fk.child}")
        for name, target in zip(fk.columns, fk.targets):
            if name not in child_cols or target not in parent_cols:
                raise ValueError(f"Unknown FK column in {fk.child}")
            if "FK" not in child_cols[name].keys:
                child_cols[name].keys.append("FK")
    return tables, foreign


def render(tables: list[Table], foreign: list[ForeignKey], source_hash: str, revision: str, overview: bool) -> str:
    by_table = {t.name: t for t in tables}
    dependencies = {t.name: {f.parent for f in foreign if f.child == t.name and f.parent != t.name} for t in tables}
    levels: dict[str, int] = {}
    while len(levels) < len(tables):
        eligible = [t.name for t in tables if t.name not in levels and dependencies[t.name] <= levels.keys()]
        if not eligible:
            raise ValueError("Non-self FK cycle: diagram needs an explicit cycle layout")
        for name in eligible:
            levels[name] = max((levels[p] + 1 for p in dependencies[name]), default=0)
    max_level = max(levels.values())
    layers = [[t for t in tables if levels[t.name] == rank] for rank in range(max_level + 1)]
    x_columns = max(3, max(map(len, layers)))
    if x_columns > 5:
        raise ValueError("More than five entities on a level; split into module diagrams")
    width, gap, margin, row_h, header_h = 560, 72, 190, 28, 88
    total_width = 2 * margin + x_columns * width + (x_columns - 1) * gap
    visible: dict[str, list[Column]] = {}
    for table in tables:
        visible[table.name] = [c for c in table.columns if not overview or any(k in c.keys for k in ("PK", "FK", "UK", "U*")) or c.name in ("status", "stage", "role", "session_type", "revoked_at")]
    positions = {}
    y = 190
    for layer in layers:
        count = len(layer)
        # Keep the processing chain to the left and the outputs to the right.
        if count == 1:
            slots = [(x_columns - 1) / 2]
        elif count == 2:
            slots = [0, x_columns - 1]
        else:
            slots = list(range(count))
        max_h = 0
        for slot, table in zip(slots, layer):
            h = header_h + row_h * len(visible[table.name]) + 16
            positions[table.name] = (margin + slot * (width + gap), y, width, h)
            max_h = max(max_h, h)
        y += max_h + 116
    height = y + 65
    esc = html.escape
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" viewBox="0 0 {total_width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Yiban core database review model</title>',
        f'<desc id="desc">{len(tables)} tables, {len(foreign)} foreign keys. Derived from active CREATE TABLE statements. Source revision {esc(revision)}. Draft; not a complete product schema and not database execution evidence.</desc>',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8Z" fill="#6b8989"/></marker></defs>',
        '<style>text{font-family:DejaVu Sans,Arial,sans-serif;fill:#1c3544}.mono{font-family:DejaVu Sans Mono,monospace}.edge{fill:none;stroke:#6b8989;stroke-width:2;marker-end:url(#arrow)}.secondary{stroke-dasharray:7 5;stroke:#a6b3b5}.edge-label{font-size:15px;paint-order:stroke;stroke:#f7f5ed;stroke-width:6;stroke-linejoin:round}.muted{fill:#5f7078}.key{fill:#9c731f;font-weight:bold}</style>',
        f'<rect width="{total_width}" height="{height}" fill="#f7f5ed"/>',
        '<text x="190" y="55" font-size="18" letter-spacing="4" fill="#9c731f">YIBAN / DATABASE DESIGN REVIEW</text>',
        f'<text x="190" y="102" font-size="32" font-weight="bold">Core model - {"key overview" if overview else "all columns"}</text>',
        f'<text x="190" y="135" font-size="17" class="muted">DRAFT | {len(tables)} tables / {len(foreign)} foreign keys | source {esc(revision)}</text>',
        '<text x="190" y="160" font-size="15" class="muted">Green: implemented accounts. Blue: proposed core + planned extensions (moderation / reading). user.status/disabled_* are planned (M2), not in 0001.</text>']
    for index, fk in enumerate(foreign):
        px, py, pw, ph = positions[fk.parent]
        cx, cy, cw, ch = positions[fk.child]
        fk_cols = {c.name: c for c in by_table[fk.child].columns}
        parent_card = "0..1" if any(fk_cols[n].nullable for n in fk.columns) else "1"
        child_card = "0..1" if any(set(key) <= set(fk.columns) for key in by_table[fk.child].unique) else "0..N"
        label = f'{parent_card} : {child_card} | {", ".join(fk.columns)}'
        if fk.parent == fk.child:
            sx, sy = px + pw, py + 74
            ex, ey = sx, sy + 72
            rail = sx + 105
            path = f'M {sx} {sy} L {rail} {sy} L {rail} {ey} L {ex} {ey}'
            lx, ly, anchor = sx + 14, sy - 14, "start"
        elif levels[fk.child] == levels[fk.parent] + 1:
            sx, sy = px + pw / 2, py + ph
            ex, ey = cx + cw / 2, cy
            mid = (sy + ey) / 2
            path = f'M {sx} {sy} L {sx} {mid} L {ex} {mid} L {ex} {ey}'
            lx, ly, anchor = ex + 14, ey - 17, "start"
        else:
            right = cx > px
            sx = px + pw if right else px
            ex = cx + cw if right else cx
            sy, ey = py + 55, cy + 55
            rail = total_width - 65 - 12 * (index % 3) if right else 65 + 12 * (index % 3)
            path = f'M {sx} {sy} L {rail} {sy} L {rail} {ey} L {ex} {ey}'
            lx, ly, anchor = (ex + 14, ey - 15, "start") if right else (ex - 14, ey - 15, "end")
        klass = "edge secondary" if levels[fk.child] > levels[fk.parent] + 1 else "edge"
        out.append(f'<path class="{klass}" d="{path}"/>')
        # Long-rail labels only show cardinality; the actual FK is marked in the table.
        if "secondary" in klass:
            label = f'{parent_card} : {child_card}'
        out.append(f'<text class="edge-label" text-anchor="{anchor}" x="{lx}" y="{ly}">{esc(label)}</text>')
    for table in tables:
        x, top, w, h = positions[table.name]
        implemented = table.name in ("user", "user_session")
        header = "#e5eeea" if implemented else "#e5edf1"
        accent = "#357362" if implemented else "#41657c"
        out += [f'<g id="table-{esc(table.name)}">', f'<rect x="{x}" y="{top}" width="{w}" height="{h}" rx="10" fill="#fffef9" stroke="#aab9bb" stroke-width="1.5"/>',
            f'<path d="M{x+10} {top}H{x+w-10}Q{x+w} {top} {x+w} {top+10}V{top+50}H{x}V{top+10}Q{x} {top} {x+10} {top}Z" fill="{header}"/>',
            f'<text class="mono" x="{x+16}" y="{top+31}" font-size="22" font-weight="bold">{esc(table.name)}</text>',
            f'<text x="{x+w-16}" y="{top+30}" text-anchor="end" font-size="12" fill="{accent}">{"IMPLEMENTED" if implemented else "PROPOSED"}</text>',
            f'<text x="{x+16}" y="{top+75}" font-size="13" class="muted">KEY</text>',
            f'<text x="{x+114}" y="{top+75}" font-size="13" class="muted">COLUMN</text>',
            f'<text x="{x+358}" y="{top+75}" font-size="13" class="muted">TYPE / NULL</text>']
        for row, col in enumerate(visible[table.name]):
            row_y = top + header_h + row * row_h
            if row % 2 == 0:
                out.append(f'<rect x="{x+1}" y="{row_y-2}" width="{w-2}" height="{row_h}" fill="#f2f4ef"/>')
            kinds = "/".join(k for k in ("PK", "FK", "UK", "U*", "IX") if k in col.keys)
            null_mark = " ?" if col.nullable else ""
            # Types may wrap overlong qualifiers, keeping field names intact.
            kind = col.kind.replace(" UNSIGNED", " U")
            out += [f'<text x="{x+16}" y="{row_y+18}" font-size="12" class="key">{esc(kinds)}</text>',
                f'<text x="{x+114}" y="{row_y+18}" font-size="15" class="mono">{esc(col.name)}</text>',
                f'<text x="{x+358}" y="{row_y+18}" font-size="13" class="mono muted">{esc(kind+null_mark)}</text>']
        out.append('</g>')
    out += [f'<text x="190" y="{height-90}" font-size="16" class="muted">Links: referenced table to referencing table. 1 : 0..N = one parent, zero or more child rows.</text>',
        f'<text x="190" y="{height-62}" font-size="15" class="muted">? = nullable. U = UNSIGNED. U* = participates in a composite unique key. See SQL for full definitions.</text>',
        f'<text x="190" y="{height-34}" font-size="13" class="mono muted">Source SHA-256: {source_hash}</text>', '</svg>']
    svg = "\n".join(out)
    ET.fromstring(svg)
    return svg


MODULES = {
    "accounts": ("账号与会话", {"user", "user_session"}),
    "generation": ("生成与成果", {"upload_file", "task", "chapter", "paragraph", "translation_unit", "book", "book_file"}),
    "moderation": ("举报审核与管理留痕", {"report", "disposition", "audit_log"}),
    "reading": ("书签与阅读位置", {"bookmark", "reading_progress"}),
}

MODULE_NOTES = {
    "accounts": "user 为已实现表；其中 status / disabled_reason / disabled_at 为 M2 计划扩展列（用户启停与审核处置落点），当前迁移未实现。",
}


def _assert_no_card_overlap(lanes, label_points, cards):
    """坐标检查：水平通道与标签不得落入任何表卡片内部；违规抛 ValueError（让渲染显式失败，而非静默产出坏图）。"""
    for i, y in enumerate(lanes):
        for x, y0, w, h, name in cards:
            if y0 < y < y0 + h:
                raise ValueError(f"外部边水平通道 lane[{i}] y={y} 落入表 {name} 卡片内部 [{y0}, {y0 + h}]")
    for lx, ly, text in label_points:
        for x, y0, w, h, name in cards:
            if x <= lx <= x + w and y0 <= ly <= y0 + h:
                raise ValueError(f"标签 {text!r} ({lx}, {ly}) 落入表 {name} 卡片内部")


def render_module(tables, foreign, focus, title, module_key, source_hash, revision) -> str:
    """渲染单一模块图：模块内表全字段 + 内部边实线（正交、走卡片外）；跨模块外部父表画成紧凑
    EXTERNAL 卡 + 虚线边（错层走线，标签不重叠）；外部子表关系以文字说明，不丢失关系。"""
    focus_tables = [t for t in tables if t.name in focus]
    parent_names = sorted({f.parent for f in foreign if f.child in focus and f.parent not in focus})
    child_names = sorted({f.child for f in foreign if f.parent in focus and f.child not in focus})
    internal = [f for f in foreign if f.child in focus and f.parent in focus and f.parent != f.child]
    external = [f for f in foreign if f.child in focus and f.parent in parent_names]

    width, gap, margin, row_h, header_h = 500, 60, 170, 26, 86
    vgap = 100
    heights = {t.name: header_h + row_h * len(t.columns) + 16 for t in focus_tables}

    # —— 树形布局：子表在父表下一层，父表居中对齐其子表（列槽），避免同层堆叠与连线遮挡 ——
    children: dict[str, list[str]] = {t.name: [] for t in focus_tables}
    for fk in internal:
        children.setdefault(fk.parent, []).append(fk.child)
    for k in children:
        children[k] = sorted(set(children[k]))
    has_parent = {fk.child for fk in internal}
    roots = sorted(t.name for t in focus_tables if t.name not in has_parent)

    slots: dict[str, float] = {}
    _counter = [0]

    def _assign(n):
        ch = children.get(n, [])
        if not ch:
            slots[n] = _counter[0]
            _counter[0] += 1
        else:
            for c in ch:
                _assign(c)
            slots[n] = (slots[ch[0]] + slots[ch[-1]]) / 2
    for r in roots:
        _assign(r)

    depth: dict[str, int] = {}

    def _set_depth(n, d):
        depth[n] = d
        for c in children.get(n, []):
            _set_depth(c, d + 1)
    for r in roots:
        _set_depth(r, 0)

    max_slot = max(slots.values()) if slots else 0
    n_slots = int(max_slot) + 1
    max_depth = max(depth.values())

    y_by_depth = {}
    y = 190
    for d in range(max_depth + 1):
        y_by_depth[d] = y
        rows = [t.name for t in focus_tables if depth[t.name] == d]
        y += (max((heights[n] for n in rows), default=0) + vgap)
    focus_bottom = y

    positions = {}
    for t in focus_tables:
        positions[t.name] = (margin + slots[t.name] * (width + gap), y_by_depth[depth[t.name]], width, heights[t.name])

    # 外部边水平通道：自 focus_bottom 下方逐条错开（每条独立 y，标签不重叠）
    ext_width, ext_h, ext_gap = 240, 64, 40
    lanes = [focus_bottom + 16 + i * 24 for i in range(len(external))]
    # 外部父表整体放到最后一条通道下方，预留标签间距（通道/标签绝不落入卡片内部）
    ext_y = (lanes[-1] + 40) if lanes else (focus_bottom + 20)
    ext_positions = {}
    for i, pn in enumerate(parent_names):
        ext_positions[pn] = (margin + i * (ext_width + ext_gap), ext_y, ext_width, ext_h)

    # 坐标检查：收集所有卡片盒（模块内表 + 外部父表），校验水平通道不落入任何卡片内部
    cards = [(positions[t.name][0], positions[t.name][1], positions[t.name][2], positions[t.name][3], t.name)
             for t in focus_tables]
    cards += [(ext_positions[pn][0], ext_positions[pn][1], ext_positions[pn][2], ext_positions[pn][3], pn)
              for pn in parent_names]
    _assert_no_card_overlap(lanes, [], cards)

    total_width = max(2 * margin + n_slots * width + (n_slots - 1) * gap,
                      margin + len(parent_names) * (ext_width + ext_gap) - ext_gap + margin)

    esc = html.escape
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{ext_y + ext_h + 160}" viewBox="0 0 {total_width} {ext_y + ext_h + 160}">',
        f'<title>{esc(title)}</title>',
        f'<desc>Module diagram ({len(focus_tables)} tables). Derived from schema.sql, source {esc(revision)}. Draft, not execution evidence.</desc>',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8Z" fill="#6b8989"/></marker><marker id="arrowExt" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8Z" fill="#b58900"/></marker></defs>',
        '<style>text{font-family:DejaVu Sans,Arial,sans-serif;fill:#1c3544}.mono{font-family:DejaVu Sans Mono,monospace}.edge{fill:none;stroke:#6b8989;stroke-width:2;marker-end:url(#arrow)}.ext{fill:none;stroke:#b58900;stroke-width:2;stroke-dasharray:7 5;marker-end:url(#arrowExt)}.edge-label{font-size:13px;paint-order:stroke;stroke:#f7f5ed;stroke-width:6;stroke-linejoin:round}.muted{fill:#5f7078}.key{fill:#9c731f;font-weight:bold}</style>',
        f'<rect width="{total_width}" height="{ext_y + ext_h + 160}" fill="#f7f5ed"/>',
        f'<text x="{margin}" y="60" font-size="18" letter-spacing="3" fill="#9c731f">YIBAN / MODULE</text>',
        f'<text x="{margin}" y="105" font-size="30" font-weight="bold">{esc(title)}</text>',
        f'<text x="{margin}" y="140" font-size="15" class="muted">模块图 | {len(focus_tables)} 张表 | source {esc(revision)} | 实线=模块内关系 · 虚线=跨模块外部引用（EXTERNAL）</text>']

    # 内部边：实线正交（父表底边中点 → 层间空行 → 子表顶边中点），走卡片外
    label_points = []
    for fk in internal:
        px, py, pw, ph = positions[fk.parent]
        cx, cy, cw, ch = positions[fk.child]
        sx, sy = px + pw / 2, py + ph
        tx, ty = cx + cw / 2, cy
        mid = (sy + ty) / 2
        out.append(f'<path class="edge" d="M {sx} {sy} L {sx} {mid} L {tx} {mid} L {tx} {ty}"/>')
        out.append(f'<text class="edge-label" text-anchor="middle" x="{(sx+tx)/2}" y="{mid-8}">{esc(", ".join(fk.columns))}</text>')
        label_points.append(((sx + tx) / 2, mid - 8, ", ".join(fk.columns)))

    # 外部边：虚线错层走线（子表底边中点 → 独立水平通道 → 父表顶边中点），标签逐条错开
    for idx, fk in enumerate(external):
        cx, cy, cw, ch = positions[fk.child]
        ex, ey, ew, eh = ext_positions[fk.parent]
        sx, sy = cx + cw / 2, cy + ch
        lane = lanes[idx]
        tx = ex + ew / 2
        out.append(f'<path class="ext" d="M {sx} {sy} L {sx} {lane} L {tx} {lane} L {tx} {ey}"/>')
        out.append(f'<text class="edge-label" text-anchor="start" x="{sx+8}" y="{lane-8}">{esc(", ".join(fk.columns))}</text>')
        label_points.append((sx + 8, lane - 8, ", ".join(fk.columns)))

    _assert_no_card_overlap([], label_points, cards)

    def draw_card(name, x, y, w, h, cols, external=False):
        implemented = name in ("user", "user_session")
        header = "#e8e2d4" if external else ("#e5eeea" if implemented else "#e5edf1")
        accent = "#8a6d1f" if external else ("#357362" if implemented else "#41657c")
        tag = "EXTERNAL" if external else ("IMPLEMENTED" if implemented else "PROPOSED")
        block = [f'<g id="table-{esc(name)}">', f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#fffef9" stroke="#aab9bb" stroke-width="1.5"/>',
            f'<path d="M{x+10} {y}H{x+w-10}Q{x+w} {y} {x+w} {y+10}V{y+50}H{x}V{y+10}Q{x} {y} {x+10} {y}Z" fill="{header}"/>',
            f'<text class="mono" x="{x+16}" y="{y+31}" font-size="22" font-weight="bold">{esc(name)}</text>',
            f'<text x="{x+w-16}" y="{y+30}" text-anchor="end" font-size="12" fill="{accent}">{tag}</text>',
            f'<text x="{x+16}" y="{y+75}" font-size="13" class="muted">KEY</text>',
            f'<text x="{x+114}" y="{y+75}" font-size="13" class="muted">COLUMN</text>',
            f'<text x="{x+350}" y="{y+75}" font-size="13" class="muted">TYPE / NULL</text>']
        for row, col in enumerate(cols):
            ry = y + header_h + row * row_h
            if row % 2 == 0:
                block.append(f'<rect x="{x+1}" y="{ry-2}" width="{w-2}" height="{row_h}" fill="#f2f4ef"/>')
            kinds = "/".join(k for k in ("PK", "FK", "UK", "U*", "IX") if k in col.keys)
            block += [f'<text x="{x+16}" y="{ry+18}" font-size="12" class="key">{esc(kinds)}</text>',
                f'<text x="{x+114}" y="{ry+18}" font-size="15" class="mono">{esc(col.name)}</text>',
                f'<text x="{x+350}" y="{ry+18}" font-size="13" class="mono muted">{esc(col.kind.replace(" UNSIGNED", " U") + (" ?" if col.nullable else ""))}</text>']
        block.append('</g>')
        out.extend(block)

    for t in focus_tables:
        x, y, w, h = positions[t.name]
        draw_card(t.name, x, y, w, h, t.columns)
    for pn in parent_names:
        x, y, w, h = ext_positions[pn]
        out += [f'<g id="ext-{esc(pn)}">', f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#fffef9" stroke="#b58900" stroke-width="1.5"/>',
            f'<path d="M{x+10} {y}H{x+w-10}Q{x+w} {y} {x+w} {y+10}V{y+40}H{x}V{y+10}Q{x} {y} {x+10} {y}Z" fill="#e8e2d4"/>',
            f'<text class="mono" x="{x+16}" y="{y+26}" font-size="17" font-weight="bold">{esc(pn)}</text>',
            f'<text x="{x+w-14}" y="{y+25}" text-anchor="end" font-size="11" fill="#8a6d1f">EXTERNAL</text>',
            f'<text x="{x+16}" y="{y+54}" font-size="12" class="muted">id (PK) · 仅引用</text>', '</g>']

    foot_y = ext_y + ext_h + 30
    note = MODULE_NOTES.get(module_key)
    if note:
        out.append(f'<text x="{margin}" y="{foot_y}" font-size="14" class="muted">{esc(note)}</text>')
        foot_y += 26
    if child_names:
        out.append(f'<text x="{margin}" y="{foot_y}" font-size="14" class="muted">本模块表被外部表引用：{esc(", ".join(child_names))}（见完整图 / 对应模块图）</text>')
        foot_y += 26
    out.append(f'<text x="{margin}" y="{foot_y}" font-size="12" class="mono muted">Source SHA-256: {source_hash}</text>')
    out.append('</svg>')
    svg = "\n".join(out)
    ET.fromstring(svg)
    return svg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sql", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--revision", default="working-tree")
    parser.add_argument("--overview", action="store_true")
    parser.add_argument("--module", choices=list(MODULES), default=None, help="渲染单一模块图")
    args = parser.parse_args()
    try:
        data = args.sql.read_bytes()
        tables, foreign = parse(data.decode("utf-8"))
        source_hash = hashlib.sha256(data).hexdigest()
        if args.module:
            title, focus = MODULES[args.module]
            svg = render_module(tables, foreign, focus, title, args.module, source_hash, args.revision)
        else:
            svg = render(tables, foreign, source_hash, args.revision, args.overview)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(svg, encoding="utf-8")
    except (OSError, ValueError, KeyError) as exc:
        print(f"ER export failed: {exc}", file=sys.stderr)
        return 1
    print(f"SVG exported: {len(tables)} tables, {sum(len(t.columns) for t in tables)} columns, {len(foreign)} foreign keys")
    print("No database was contacted. This is not MySQL DDL execution validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
