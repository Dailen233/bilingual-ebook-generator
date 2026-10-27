#!/usr/bin/env python3
"""译伴数据库目标模型 —— 独立设计验证库验收工具（MySQL 8.4，受保护）。

用途：在【全新、独立】的 yiban_design_review 库中，实际执行 schema.sql、读取真实
元数据（表/列/注释/外键/唯一约束/索引/CHECK），并用合成数据验证关键约束后回滚。

安全边界（必须遵守）：
  1) 只操作独立库 YIBAN_DESIGN_DB（默认 yiban_design_review），绝不连接 yiban_api_dev /
     yiban_api_test，不修改既有迁移。
  2) 目标库非空则【停止】，不 DROP / TRUNCATE / 覆盖。
  3) 凭据仅从环境变量读取（本机私有配置导出），不打印、不落盘、不写入报告 URL。
  4) 合成测试数据在单事务内回滚；DDL（CREATE TABLE）不依赖事务回滚（MySQL 隐式提交）。

运行方式（示例，凭据来自本机私有配置，不要打印）：
    set -a; . /path/to/.env.dev-db; set +a      # 导出 MYSQL_ROOT_PASSWORD / MYSQL_PORT 等
    python3 -m venv 提供的解释器 scripts/validate_design_mysql.py

环境变量：
    YIBAN_MYSQL_HOST        默认 127.0.0.1
    YIBAN_MYSQL_PORT        默认 3307
    YIBAN_MYSQL_ROOT_USER   默认 root
    YIBAN_MYSQL_ROOT_PASSWORD  必填（root 密码）
    YIBAN_DESIGN_DB         默认 yiban_design_review
    YIBAN_SCHEMA_SQL        默认 docs/database-design/schema.sql（相对仓库根）
"""
import os
import sys
from pathlib import Path

try:
    import pymysql
except ImportError:
    print("缺少 pymysql：请在已安装 pymysql 的解释器（如 yiban-api/.venv）下运行。")
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: str) -> None:
    """从本机私有 .env 读取 KEY=VALUE 到环境（仅 setdefault，不覆盖已显式传入的值，不打印）。"""
    if not path or not Path(path).exists():
        return
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            os.environ.setdefault(k, v.strip())


if "--env-file" in sys.argv:
    _i = sys.argv.index("--env-file")
    if _i + 1 < len(sys.argv):
        _load_env_file(sys.argv[_i + 1])

# 兼容 docker-compose .env 的键名：MYSQL_PORT / MYSQL_ROOT_PASSWORD
if "MYSQL_PORT" in os.environ and "YIBAN_MYSQL_PORT" not in os.environ:
    os.environ["YIBAN_MYSQL_PORT"] = os.environ["MYSQL_PORT"]
if "MYSQL_ROOT_PASSWORD" in os.environ and "YIBAN_MYSQL_ROOT_PASSWORD" not in os.environ:
    os.environ["YIBAN_MYSQL_ROOT_PASSWORD"] = os.environ["MYSQL_ROOT_PASSWORD"]

HOST = os.environ.get("YIBAN_MYSQL_HOST", "127.0.0.1")
PORT = int(os.environ.get("YIBAN_MYSQL_PORT", "3307"))
USER = os.environ.get("YIBAN_MYSQL_ROOT_USER", "root")
PASSWORD = os.environ.get("YIBAN_MYSQL_ROOT_PASSWORD", "")
DESIGN_DB = os.environ.get("YIBAN_DESIGN_DB", "yiban_design_review")
SCHEMA_SQL = os.environ.get("YIBAN_SCHEMA_SQL", str(ROOT / "docs/database-design/schema.sql"))

EXPECTED_TABLES = [
    "user", "user_session", "upload_file", "task", "chapter", "paragraph",
    "translation_unit", "book", "book_file", "report", "disposition", "audit_log",
    "bookmark", "reading_progress",
]
EXPECTED_FKS = 24
# 关键约束/索引（必须存在）
EXPECTED_CHECKS = [
    "chk_task_counters", "chk_report_target", "chk_book_failed_units",
    "chk_book_file_size", "chk_upload_file_size", "chk_chapter_seq",
    "chk_paragraph_seq", "chk_unit_seq", "chk_unit_retry",
]
EXPECTED_KEYS = [
    "uk_user_email", "uk_user_session_jti", "uk_upload_file_storage_ref",
    "uk_task_retry_of", "uk_task_completion_key", "ix_task_status",
    "ix_task_owner_id", "ix_task_file_id", "uk_chapter_task_seq",
    "uk_paragraph_chapter_seq", "uk_unit_paragraph_seq", "uk_book_task_id",
    "uk_book_file_book_format", "ix_report_status", "ix_report_reporter_id",
    "ix_audit_log_report", "ix_audit_log_actor", "ix_audit_log_target",
    "uk_reading_progress_user_book", "ix_bookmark_user_book",
]


def _mask(url: str) -> str:
    # 绝不打印含密码的 URL；本工具不构造凭据 URL。
    return url


def fail(msg: str):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def main() -> int:
    if not PASSWORD:
        fail("未提供 YIBAN_MYSQL_ROOT_PASSWORD（凭据须经环境变量注入，不打印）")

    print(f"[INFO] 连接 {USER}@{HOST}:{PORT}（库未指定）")
    try:
        conn = pymysql.connect(host=HOST, port=PORT, user=USER, password=PASSWORD,
                               connect_timeout=8, autocommit=True, charset="utf8mb4")
    except Exception as e:
        fail(f"连接失败：{type(e).__name__} {str(e)[:160]}（不含凭据）")

    cur = conn.cursor()
    cur.execute("SELECT VERSION(), @@hostname, @@port, @@version_comment")
    ver, hostname, srv_port, ver_comment = cur.fetchone()
    print(f"[INFO] 服务器版本={ver} 主机={hostname} 服务器port={srv_port} 注释={ver_comment}")
    if not str(ver).startswith("8.4"):
        print(f"[WARN] 版本 {ver} 非 8.4 系，继续（仅提示）")
    if srv_port != PORT:
        print(f"[INFO] 连接端口 {PORT} 与服务器 @@port {srv_port} 不一致（可能为容器端口映射）")

    # 目标库状态：不存在则创建；存在且空则复用；存在且非空则停止。
    cur.execute("SHOW DATABASES")
    existing = {r[0] for r in cur.fetchall()}
    if DESIGN_DB in existing:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s", (DESIGN_DB,))
        n = cur.fetchone()[0]
        if n > 0:
            fail(f"目标库 {DESIGN_DB} 已存在且含 {n} 张表；停止（不 DROP/TRUNCATE/覆盖）")
        print(f"[CHECK] 目标库 {DESIGN_DB} 已存在且为空，复用")
    else:
        cur.execute(f"CREATE DATABASE `{DESIGN_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
        print(f"[CHECK] 已创建独立库 {DESIGN_DB}")

    # 执行 schema.sql（DDL，MySQL 隐式提交，不依赖事务回滚）
    sql_text = Path(SCHEMA_SQL).read_text(encoding="utf-8")
    stmts = []
    for raw in sql_text.split(";"):
        # 去掉纯注释行（本设计仅用 -- 行注释，无 /* */）
        body = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("--"))
        body = body.strip()
        if body:
            stmts.append(body)
    print(f"[INFO] 解析到 {len(stmts)} 条语句")

    cur.execute(f"USE `{DESIGN_DB}`")
    created = 0
    for st in stmts:
        cur.execute(st)
        if st.lstrip().upper().startswith("CREATE TABLE"):
            created += 1
    print(f"[CHECK] 已执行 {created} 条 CREATE TABLE（DDL 隐式提交）")

    # 读取真实元数据
    cur.execute(
        "SELECT table_name, table_comment FROM information_schema.tables "
        "WHERE table_schema=%s ORDER BY table_name", (DESIGN_DB,))
    tables = {r[0]: r[1] for r in cur.fetchall()}
    missing = [t for t in EXPECTED_TABLES if t not in tables]
    extra = [t for t in tables if t not in EXPECTED_TABLES]
    print(f"[CHECK] 表数={len(tables)}（期望 {len(EXPECTED_TABLES)}）")
    if missing:
        fail(f"缺表：{missing}")
    if extra:
        fail(f"多余表：{extra}")

    col_total = 0
    for t in EXPECTED_TABLES:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=%s AND table_name=%s",
            (DESIGN_DB, t))
        col_total += cur.fetchone()[0]
    print(f"[CHECK] 列总数={col_total}")

    # 外键
    cur.execute(
        "SELECT table_name, constraint_name, referenced_table_name FROM "
        "information_schema.key_column_usage WHERE table_schema=%s AND referenced_table_name IS NOT NULL "
        "ORDER BY table_name, constraint_name", (DESIGN_DB,))
    fks = cur.fetchall()
    print(f"[CHECK] 外键数={len(fks)}（期望 {EXPECTED_FKS}）")
    if len(fks) != EXPECTED_FKS:
        fail(f"外键数不符：{len(fks)} != {EXPECTED_FKS}")

    # 唯一约束 / 索引
    cur.execute(
        "SELECT DISTINCT index_name FROM information_schema.statistics "
        "WHERE table_schema=%s", (DESIGN_DB,))
    keys = {r[0] for r in cur.fetchall()}
    miss_keys = [k for k in EXPECTED_KEYS if k not in keys]
    if miss_keys:
        fail(f"缺少索引：{miss_keys}")
    print(f"[CHECK] 关键索引/唯一键 {len(EXPECTED_KEYS)} 个均存在")

    # CHECK 约束
    cur.execute(
        "SELECT constraint_name FROM information_schema.table_constraints "
        "WHERE table_schema=%s AND constraint_type='CHECK'", (DESIGN_DB,))
    checks = {r[0] for r in cur.fetchall()}
    miss_checks = [c for c in EXPECTED_CHECKS if c not in checks]
    if miss_checks:
        fail(f"缺少 CHECK：{miss_checks}")
    print(f"[CHECK] 关键 CHECK {len(EXPECTED_CHECKS)} 个均存在")

    # ---- 合成数据 + 约束验证（单事务，最后回滚）----
    cur.execute("SET autocommit=0")
    def ins(sql, args):
        cur.execute(sql, args)

    uid = "usr-admin-0001"
    uid2 = "usr-user-0002"
    fid = "file-0001"
    tid = "task-0001"
    cid = "chap-0001"
    pid = "para-0001"
    uid_ = "unit-0001"
    bid = "book-0001"

    ins("INSERT INTO user(id,email,password_hash,display_name,role,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,NOW(6),NOW(6))",
        (uid, "a@example.com", "x", "管理员", "admin"))
    ins("INSERT INTO user(id,email,password_hash,display_name,role,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,NOW(6),NOW(6))",
        (uid2, "b@example.com", "x", "用户", "user"))
    ins("INSERT INTO upload_file(id,owner_id,original_name,storage_ref,ext,size_bytes,sha256,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,NOW(6))",
        (fid, uid, "sample.txt", fid + ".txt", ".txt", 100, "a" * 64))
    ins("INSERT INTO task(id,owner_id,file_id,src_lang,tgt_lang,svc_key,style_key,status,total_units,done_units,failed_units,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6))",
        (tid, uid, fid, "en", "zh", "deepl", "literary", "running", 3, 2, 1))
    ins("INSERT INTO chapter(id,task_id,seq_no,title) VALUES(%s,%s,%s,%s)", (cid, tid, 1, "Chapter 1"))
    ins("INSERT INTO paragraph(id,chapter_id,seq_no,source_text) VALUES(%s,%s,%s,%s)", (pid, cid, 1, "Hello."))
    ins("INSERT INTO translation_unit(id,paragraph_id,seq_no,source_text,status,retry_count) VALUES(%s,%s,%s,%s,%s,%s)", (uid_, pid, 1, "Hello.", "translated", 0))
    ins("INSERT INTO book(id,owner_id,task_id,name,src_lang,tgt_lang,created_at) VALUES(%s,%s,%s,%s,%s,%s,NOW(6))",
        (bid, uid, tid, "Sample", "en", "zh"))
    print("[TEST] 基础合成数据插入成功")

    def expect_fail(name, sql, args, want_hint):
        try:
            cur.execute(sql, args)
            print(f"[TEST] {name}: 未报错（应被拒绝） -> FAIL")
            return False
        except Exception as e:
            msg = str(e)
            if want_hint and want_hint not in msg:
                print(f"[TEST] {name}: 报错但缺关键词 {want_hint!r}: {msg[:120]}")
                return False
            print(f"[TEST] {name}: 被拒绝（符合预期）")
            return True

    ok = True
    # 唯一约束
    ok &= expect_fail("唯一-重复邮箱", "INSERT INTO user(id,email,password_hash,display_name,role,created_at,updated_at) VALUES('x1','a@example.com','x','n','user',NOW(6),NOW(6))", (), "Duplicate")
    ok &= expect_fail("唯一-章节(任务,序号)重复", "INSERT INTO chapter(id,task_id,seq_no) VALUES('x2',%s,1)", (tid,), "Duplicate")
    # 外键
    ok &= expect_fail("外键-章节指向不存在任务", "INSERT INTO chapter(id,task_id,seq_no) VALUES('x3','no-such-task',2)", (), "foreign key")
    # 顺序字段
    ok &= expect_fail("顺序-章节 seq_no=0", "INSERT INTO chapter(id,task_id,seq_no) VALUES('x4',%s,0)", (tid,), "constraint")
    ok &= expect_fail("顺序-段落 seq_no 负数", "INSERT INTO paragraph(id,chapter_id,seq_no,source_text) VALUES('x5',%s,-1,'x')", (cid,), "constraint")
    # 非负计数
    ok &= expect_fail("计数-task failed_units 负数", "INSERT INTO task(id,owner_id,file_id,src_lang,tgt_lang,svc_key,style_key,status,total_units,done_units,failed_units,created_at,updated_at) VALUES('x6',%s,%s,'en','zh','d','l','pending',3,2,-1,NOW(6),NOW(6))", (uid, fid), "constraint")
    ok &= expect_fail("计数-task failed_units>done_units", "INSERT INTO task(id,owner_id,file_id,src_lang,tgt_lang,svc_key,style_key,status,total_units,done_units,failed_units,created_at,updated_at) VALUES('x7',%s,%s,'en','zh','d','l','pending',3,1,2,NOW(6),NOW(6))", (uid, fid), "constraint")
    ok &= expect_fail("计数-book failed_units 负数", "INSERT INTO book(id,owner_id,task_id,name,src_lang,tgt_lang,failed_units,created_at) VALUES('x8',%s,%s,'n','en','zh',-1,NOW(6))", (uid, tid), "constraint")
    # 文件大小
    ok &= expect_fail("大小-upload_file 负数", "INSERT INTO upload_file(id,owner_id,original_name,storage_ref,ext,size_bytes,sha256,created_at) VALUES('x9',%s,'n','r','.txt',-5,%s,NOW(6))", (uid, "b" * 64), "constraint")
    ok &= expect_fail("大小-book_file 负数", "INSERT INTO book_file(id,book_id,format,storage_ref,size_bytes,generated_at) VALUES('x10',%s,'epub','r',-1,NOW(6))", (bid,), "constraint")
    # 举报目标二选一
    ok &= expect_fail("举报-对象双空", "INSERT INTO report(id,reporter_id,reason,status,created_at) VALUES('r1',%s,'r','pending',NOW(6))", (uid,), "constraint")
    ok &= expect_fail("举报-对象双设", "INSERT INTO report(id,reporter_id,reported_user_id,book_id,reason,status,created_at) VALUES('r2',%s,%s,%s,'r','pending',NOW(6))", (uid, uid2, bid), "constraint")
    # 正例：举报对象=书籍（应成功）
    try:
        cur.execute("INSERT INTO report(id,reporter_id,book_id,reason,status,created_at) VALUES('r3',%s,%s,'r','pending',NOW(6))", (uid, bid))
        print("[TEST] 举报-对象=书籍（恰一非空）: 成功（符合预期）")
    except Exception as e:
        print(f"[TEST] 举报-对象=书籍: 意外失败 {str(e)[:120]} -> FAIL")
        ok = False

    conn.rollback()
    print("[INFO] 合成测试数据已回滚（DDL 已隐式提交，不在回滚范围）")

    if not ok:
        fail("存在未按预期拒绝的用例")
    print(f"[RESULT] PASS：{DESIGN_DB} 元数据与关键约束验证通过，测试数据已回滚")
    return 0


if __name__ == "__main__":
    sys.exit(main())
