#!/usr/bin/env python3
"""发布包构建与校验（stdlib）。

流程：按白名单复制到独立暂存目录 → 生成 SHA256SUMS（排除自身）→ 立即本地执行
`sha256sum -c` 必须全部通过 → 核对包内 HTML 相对链接与资源存在性。
不打包 .git / 私有配置 / 临时产物。
"""
import datetime
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 白名单（文件，相对仓库根）
FILES = [
    "index.html",
    "README.md", "CODEBUDDY.md",
    "需求分析与设计文档说明.md", "需求分析与设计文档说明.html",
    "数据库逻辑模型草案.md", "任务状态机与进度口径草案.md",
    "任务接口契约草案.md", "书库与成果接口契约草案.md",
    "docs/repository-organization.md", "docs/课程检查入口.md",
    "docs/浏览器人工验收清单.md", "docs/发布说明.md",
    "docs/database-design/README.md", "docs/database-design/数据库设计说明.html",
    "docs/database-design/01-er.md", "docs/database-design/01-er.mmd",
    "docs/database-design/02-字段字典.md", "docs/database-design/字段字典.html",
    "docs/database-design/03-页面数据对应表.md", "docs/database-design/页面数据对应表.html",
    "docs/database-design/schema.sql", "docs/database-design/er.svg",
    "docs/database-design/er-overview.svg", "docs/database-design/04-设计验证记录.md",
    "scripts/render_database_er.py", "scripts/md2html.py",
    "scripts/build_release.py", "scripts/validate_design_mysql.py",
]
# 白名单（目录，递归复制，保留字体与许可）
DIRS = ["prototype/v4"]

# 临时产物命名模式（复制目录时排除，双保险；白名单本就不含它们）
_EXCLUDE = re.compile(r"(^|/)(_seed.*|\.DS_Store|Thumbs\.db|.*~)$")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path("/tmp") / f"yiban-release-{datetime.datetime.now():%Y%m%d-%H%M%S}")
    if out.exists():
        print(f"[STOP] 暂存目录已存在：{out}（避免覆盖，请换目录）")
        return 2
    out.mkdir(parents=True)

    copied = []
    for rel in FILES:
        src = ROOT / rel
        if not src.exists():
            print(f"[STOP] 白名单文件缺失：{rel}")
            return 2
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)
    for d in DIRS:
        src = ROOT / d
        if not src.is_dir():
            print(f"[STOP] 白名单目录缺失：{d}")
            return 2
        shutil.copytree(src, out / d, ignore=shutil.ignore_patterns("_seed*", ".DS_Store", "*~"))
        for p in sorted((out / d).rglob("*")):
            if p.is_file():
                copied.append(str(p.relative_to(out)))
    print(f"[CHECK] 复制 {len(copied)} 个文件到 {out}")

    # 生成 SHA256SUMS（排除自身），相对路径，按路径排序
    manifest = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    lines = []
    for p in manifest:
        rel = p.relative_to(out).as_posix()
        lines.append(f"{_sha256(p)}  {rel}")
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[CHECK] 已生成 SHA256SUMS（{len(lines)} 条，排除自身）")

    # 立即本地执行 sha256sum -c
    proc = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=out,
                          capture_output=True, text=True)
    out_txt = (proc.stdout or "") + (proc.stderr or "")
    print(out_txt.strip())
    if proc.returncode != 0 or ": FAILED" in out_txt or ": 失败" in out_txt:
        print("[RESULT] 校验未全部通过")
        return 1
    print("[RESULT] sha256sum -c 全部通过")

    # 相对链接/资源存在性核对（仅本地相对路径）
    missing = []
    for p in sorted(out.rglob("*.html")):
        text = p.read_text(encoding="utf-8", errors="replace")
        # 仅核对真实 HTML 属性：排除 <script>/<style> 内动态拼接的 href/src
        text = re.sub(r"<script\b[^>]*>.*?</script>", "", text, flags=re.S | re.I)
        text = re.sub(r"<style\b[^>]*>.*?</style>", "", text, flags=re.S | re.I)
        for m in re.finditer(r'(?:href|src)="([^"]+)"', text):
            target = m.group(1).strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#", "javascript:", "data:")):
                continue
            resolved = ((out / target.lstrip("/")) if target.startswith("/") else (p.parent / target)).resolve()
            if not resolved.exists():
                missing.append(f"{p.relative_to(out)} -> {target}")
    if missing:
        print("[STOP] 存在失效相对链接：")
        for x in missing:
            print("   ", x)
        return 1
    print("[RESULT] 相对链接/资源存在性核对通过")

    total = sum(p.stat().st_size for p in manifest)
    print(f"[INFO] 发布包 {out}：{len(manifest)} 文件，{total} 字节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
