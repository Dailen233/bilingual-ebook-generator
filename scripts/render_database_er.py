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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sql", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--revision", default="working-tree")
    parser.add_argument("--overview", action="store_true")
    args = parser.parse_args()
    try:
        data = args.sql.read_bytes()
        tables, foreign = parse(data.decode("utf-8"))
        svg = render(tables, foreign, hashlib.sha256(data).hexdigest(), args.revision, args.overview)
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
