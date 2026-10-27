#!/usr/bin/env python3
"""发布包构建与校验（stdlib）。

流程：按白名单复制到独立暂存目录 → 生成 SHA256SUMS（排除自身）→ 立即本地执行
`sha256sum -c` 必须全部通过 → 核对包内 HTML 相对链接与资源存在性。
不打包 .git / 私有配置 / 临时产物。
"""
import datetime
import gzip
import hashlib
import re
import shutil
import subprocess
import sys
import tarfile
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
    "docs/database-design/er-overview.svg",
    "docs/database-design/er-module-accounts.svg", "docs/database-design/er-module-generation.svg",
    "docs/database-design/er-module-moderation.svg", "docs/database-design/er-module-reading.svg",
    "docs/database-design/04-设计验证记录.md",
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


def _git_short_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def export_tar(base: Path, dest_dir: Path, commit_short: str) -> Path:
    """把已校验的发布目录打成 tar.gz（文件按序、tar 成员 mtime/属主归零 + gzip 头时间戳固定，
    以求字节级可复现），返回包路径。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    tarpath = dest_dir / f"bilingual-ebook-generator-{commit_short}.tar.gz"
    with open(tarpath, "wb") as fobj:
        # gzip 头含 MTIME 字段，须显式固定为 0，否则默认写当前时间、破坏字节级可复现。
        with gzip.GzipFile(filename="", mode="wb", fileobj=fobj, compresslevel=9, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                for p in sorted(base.rglob("*")):
                    if not p.is_file():
                        continue
                    info = tar.gettarinfo(str(p), arcname=p.relative_to(base).as_posix())
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    with open(p, "rb") as f:
                        tar.addfile(info, f)
    return tarpath


def check_links(base: Path):
    """核对目录内 HTML 的本地相对链接/资源存在性。

    保留 <script src="..."> 的外部 JS 引用（先提取，再移除脚本正文）；
    脚本正文里动态拼接的 href/src 属 JS 字符串，予以忽略（不整段丢弃 script 时漏掉外部 JS）。
    返回 (是否全部存在, 失效列表)。
    """
    missing = []
    for p in sorted(base.rglob("*.html")):
        text = p.read_text(encoding="utf-8", errors="replace")
        # 1) 先提取 <script ... src="..."> 的资源引用（含 type/module 等属性的 opener）
        script_srcs = re.findall(r'<script\b[^>]*\bsrc="([^"]+)"', text, flags=re.I)
        # 2) 移除 <script>/<style> 正文（其中的动态拼接字符串忽略），但 src 已在上面保留
        text = re.sub(r"<script\b[^>]*>.*?</script>", "", text, flags=re.S | re.I)
        text = re.sub(r"<style\b[^>]*>.*?</style>", "", text, flags=re.S | re.I)
        # 3) 常规 href/src 属性 + 保留的外部 script src 一并检查
        refs = re.findall(r'(?:href|src)="([^"]+)"', text) + script_srcs
        for target in refs:
            target = target.strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#", "javascript:", "data:")):
                continue
            resolved = ((base / target.lstrip("/")) if target.startswith("/") else (p.parent / target)).resolve()
            if not resolved.exists():
                missing.append(f"{p.relative_to(base)} -> {target}")
    return missing


def main() -> int:
    args = sys.argv[1:]
    if "--links-only" in args:
        i = args.index("--links-only")
        base = Path(args[i + 1]) if i + 1 < len(args) else None
        if not base or not base.is_dir():
            print("用法：python3 scripts/build_release.py --links-only <暂存目录>")
            return 2
        missing = check_links(base)
        if missing:
            print("[STOP] 存在失效相对链接/资源：")
            for x in missing:
                print("   ", x)
            return 1
        print("[RESULT] 相对链接/资源存在性核对通过")
        return 0

    tar_dir = None
    if "--tar" in args:
        i = args.index("--tar")
        if i + 1 < len(args):
            tar_dir = Path(args[i + 1])

    out = Path(args[0]) if args else (
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

    # 相对链接/资源存在性核对（保留 <script src>，忽略脚本正文动态串）
    missing = check_links(out)
    if missing:
        print("[STOP] 存在失效相对链接/资源：")
        for x in missing:
            print("   ", x)
        return 1
    print("[RESULT] 相对链接/资源存在性核对通过")

    total = sum(p.stat().st_size for p in manifest)
    print(f"[INFO] 发布包 {out}：{len(manifest)} 文件，{total} 字节")
    if tar_dir:
        tarpath = export_tar(out, tar_dir, _git_short_sha())
        print(f"[INFO] tar.gz 导出：{tarpath}")
        print(f"[INFO] tar.gz SHA-256：{_sha256(tarpath)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
