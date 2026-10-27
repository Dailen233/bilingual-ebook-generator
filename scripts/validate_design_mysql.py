#!/usr/bin/env python3
"""译伴数据库目标模型 —— 独立设计验证库验收工具（MySQL 8.4，受保护）。

用途：在【全新、独立】的 yiban_design_review 库中，实际执行本仓 schema.sql、读取真实
元数据（表/列/类型/长度/NULL/默认/注释/外键/主键/唯一键/索引/CHECK）并与 schema.sql
逐项比对，再用合成数据验证关键约束后回滚。

安全边界（硬保护，不可经环境变量或参数改写）：
  1) 端点固定 127.0.0.1:3307（本机 dev 实例）；库名固定 yiban_design_review；
     执行文件固定为本仓 docs/database-design/schema.sql。
  2) 连接后先确认 MySQL 8.4.x，不符合在任何 DDL 前停止。
  3) 目标库非空则【停止】，不 DROP / TRUNCATE / 覆盖；禁止为复验自动删除。
  4) 凭据仅从本机私有 .env 读取，不打印、不落盘、不写入报告 URL。
  5) 合成测试数据在单事务内回滚；DDL（CREATE TABLE）不依赖事务回滚（MySQL 隐式提交）。

模式：
    python3 scripts/validate_design_mysql.py --env-file <本机私有.env>     # 首次导入：建库+DDL+深度核对+约束用例
    python3 scripts/validate_design_mysql.py --env-file <...> --readonly    # 纯只读深度核对（已存在库，不建表/不删数据）
    python3 scripts/validate_design_mysql.py --selftest                    # 离线替身测试（无需数据库）
"""
import re
import sys
from pathlib import Path

try:
    import pymysql
except ImportError:
    print("缺少 pymysql：请在已安装 pymysql 的解释器（如 yiban-api/.venv）下运行。")
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent

# ---- 硬保护：固定端点/库名/执行文件，不读环境变量 ----
ALLOWED_HOST = "127.0.0.1"
ALLOWED_PORT = 3307
ALLOWED_USER = "root"
ALLOWED_DB = "yiban_design_review"
SCHEMA_SQL = ROOT / "docs/database-design/schema.sql"


def _load_env_file(path: str) -> str:
    """只从本机私有 .env 取 MYSQL_ROOT_PASSWORD；返回密码，不打印。"""
    password = ""
    if path and Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                if k == "MYSQL_ROOT_PASSWORD":
                    password = v.strip()
    return password


# ---- 纯校验函数（不连库，供主流程与离线替身测试共同使用）----
def require_endpoint(host: str, port) -> None:
    if host != ALLOWED_HOST or int(port) != ALLOWED_PORT:
        raise ValueError(f"端点仅允许 {ALLOWED_HOST}:{ALLOWED_PORT}，拒绝 {host}:{port}")


def require_db_name(name: str) -> None:
    if name != ALLOWED_DB:
        raise ValueError(f"目标库仅允许 {ALLOWED_DB}，拒绝 {name}")


def require_version(ver: str) -> None:
    if not re.match(r"^8\.4(\.\d+)?$", str(ver).strip()):
        raise ValueError(f"仅接受 MySQL 8.4.x，实际 {ver}")


# ---- schema.sql 解析为「预期模型」（比对的可追溯来源）----
_COL_RE = re.compile(r"^\s*`([^`]+)`\s+([A-Za-z]+(?:\([^)]*\))?(?:\s+UNSIGNED)?)(.*)$")
_PK_RE = re.compile(r"PRIMARY KEY\s*\(([^)]*)\)", re.I)
_UK_RE = re.compile(r"UNIQUE (?:KEY|INDEX)\s+`([^`]+)`\s*\(([^)]*)\)", re.I)
_IX_RE = re.compile(r"(?:KEY|INDEX)\s+`([^`]+)`\s*\(([^)]*)\)", re.I)
_FK_RE = re.compile(r"(?:CONSTRAINT\s+`([^`]+)`\s+)?FOREIGN KEY\s*\(([^)]*)\)\s*REFERENCES\s+`([^`]+)`\s*\(([^)]*)\)", re.I)
_CK_RE = re.compile(r"(?:CONSTRAINT\s+`([^`]+)`\s+)?CHECK\s*\((.*)\)\s*$", re.I)
_TBL_COMMENT_RE = re.compile(r"COMMENT='([^']*)'")
_COL_COMMENT_RE = re.compile(r"COMMENT\s+'([^']*)'")
_COL_DEFAULT_RE = re.compile(r"DEFAULT\s+('[^']*'|\S+)", re.I)


def _names(s: str):
    return tuple(re.findall(r"`([^`]+)`", s))


def parse_schema(path) -> dict:
    """解析 schema.sql → {table: {comment, columns[{name,type,nullable,default,comment}], pk, unique{name:[cols]}, index{name:[cols]}, fk[{name,cols,ref_table,ref_cols}], check{name:clause}}}"""
    text = Path(path).read_text(encoding="utf-8")
    text = re.sub(r"(?m)^\s*--.*$", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    model = {}
    for m in re.finditer(r"(?ms)^\s*CREATE\s+TABLE\s+`([^`]+)`\s*\((.*?)^\)\s*ENGINE\s*=.*?;", text):
        name, body, full = m.group(1), m.group(2), m.group(0)
        tcomment = _TBL_COMMENT_RE.search(full)
        columns, pk, unique, indexes, fks, checks = [], (), {}, {}, [], {}
        for raw in body.splitlines():
            line = raw.strip().rstrip(",")
            if not line:
                continue
            col = _COL_RE.match(line)
            if col:
                cname, ctype, rest = col.group(1), col.group(2), col.group(3)
                nullable = "NOT NULL" not in rest.upper()
                default = None
                dm = _COL_DEFAULT_RE.search(rest)
                if dm:
                    d = dm.group(1)
                    default = d[1:-1] if (d.startswith("'") and d.endswith("'")) else d
                comment = _COL_COMMENT_RE.search(rest)
                columns.append({"name": cname, "type": ctype, "nullable": nullable,
                                "default": default, "comment": comment.group(1) if comment else ""})
                continue
            pk_m = _PK_RE.match(line)
            if pk_m:
                pk = _names(pk_m.group(1))
                continue
            uk = _UK_RE.match(line)
            if uk:
                unique[uk.group(1)] = list(_names(uk.group(2)))
                continue
            ix = _IX_RE.match(line)
            if ix:
                indexes[ix.group(1)] = list(_names(ix.group(2)))
                continue
            fk = _FK_RE.match(line)
            if fk:
                fks.append({"name": fk.group(1), "cols": list(_names(fk.group(2))),
                            "ref_table": fk.group(3), "ref_cols": list(_names(fk.group(4)))})
                continue
            ck = _CK_RE.match(line)
            if ck:
                checks[ck.group(1)] = ck.group(2).strip()
                continue
            # 其余（如 SET/语句间空行）忽略
        model[name] = {"comment": tcomment.group(1) if tcomment else "", "columns": columns,
                       "pk": pk, "unique": unique, "index": indexes, "fk": fks, "check": checks}
    return model


def _norm_check_clause(clause: str):
    """把 CHECK 子句规范化为可比较的「比较式集合」（忽略大小写/反引号/AND/OR/多余括号）。"""
    s = clause.lower().replace("`", "")
    parts = re.split(r"\band\b|\bor\b", s)
    comps = []
    for p in parts:
        p = p.strip().strip("()").strip()
        p = re.sub(r"\s+", " ", p)
        if p:
            comps.append(p)
    return sorted(comps)


def _diff(expected, actual, label) -> list[str]:
    return [f"{label}: 期望 {expected!r}，实际 {actual!r}"]


def deep_check(conn, model: dict) -> int:
    """只读核对：把 information_schema 与 schema.sql 解析结果逐项比对。返回 0=通过。"""
    cur = conn.cursor()
    diffs: list[str] = []

    # 1) 表 + 表注释
    cur.execute("SELECT table_name, table_comment FROM information_schema.tables WHERE table_schema=%s ORDER BY table_name",
                (ALLOWED_DB,))
    actual_tables = {r[0]: r[1] for r in cur.fetchall()}
    exp_names = sorted(model)
    if sorted(actual_tables) != exp_names:
        diffs.append(_diff(exp_names, sorted(actual_tables), "表名集合"))
    else:
        for t in exp_names:
            if actual_tables[t] != model[t]["comment"]:
                diffs.append(_diff(model[t]["comment"], actual_tables[t], f"{t}.表注释"))

    # 2) 列：名称/类型(含长度)/NULL/默认/注释
    cur.execute(
        "SELECT table_name, column_name, column_type, is_nullable, column_default, column_comment "
        "FROM information_schema.columns WHERE table_schema=%s ORDER BY table_name, ordinal_position",
        (ALLOWED_DB,))
    actual_cols = {}
    for t, c, ctype, isnull, cdef, ccomment in cur.fetchall():
        actual_cols.setdefault(t, {})[c] = (ctype, isnull, cdef, ccomment)
    col_total = 0
    for t in exp_names:
        exp_cols = {c["name"]: c for c in model[t]["columns"]}
        act_cols = actual_cols.get(t, {})
        if set(act_cols) != set(exp_cols):
            diffs.append(_diff(sorted(exp_cols), sorted(act_cols), f"{t}.列名集合"))
            continue
        col_total += len(exp_cols)
        for cname, e in exp_cols.items():
            act_type, act_null, act_def, act_comment = act_cols[cname]
            etype = e["type"].lower()
            if act_type != etype:
                diffs.append(_diff(etype, act_type, f"{t}.{cname}.类型/长度"))
            exp_null = "YES" if e["nullable"] else "NO"
            if act_null != exp_null:
                diffs.append(_diff(exp_null, act_null, f"{t}.{cname}.NULL"))
            if e["default"] is None:
                if act_def is not None:
                    diffs.append(_diff(None, act_def, f"{t}.{cname}.默认值"))
            else:
                if str(act_def) != str(e["default"]):
                    diffs.append(_diff(e["default"], act_def, f"{t}.{cname}.默认值"))
            if act_comment != e["comment"]:
                diffs.append(_diff(e["comment"], act_comment, f"{t}.{cname}.注释"))

    # 3) 外键：源列、目标表/列
    cur.execute(
        "SELECT constraint_name, table_name, column_name, referenced_table_name, referenced_column_name, ordinal_position "
        "FROM information_schema.key_column_usage WHERE table_schema=%s AND referenced_table_name IS NOT NULL "
        "ORDER BY constraint_name, ordinal_position", (ALLOWED_DB,))
    actual_fk = {}
    for cn, t, c, rt, rc, ordp in cur.fetchall():
        actual_fk.setdefault(cn, {"table": t, "cols": [], "ref_table": rt, "ref_cols": []})
        actual_fk[cn]["cols"].append((ordp, c))
        actual_fk[cn]["ref_cols"].append((ordp, rc))
    exp_fk = {f["name"]: (t, f) for t in exp_names for f in model[t]["fk"]}
    if set(actual_fk) != set(exp_fk):
        diffs.append(_diff(sorted(exp_fk), sorted(actual_fk), "外键名集合"))
    else:
        for name, (child_table, f) in exp_fk.items():
            a = actual_fk[name]
            a_cols = [c for _, c in sorted(a["cols"])]
            a_rc = [c for _, c in sorted(a["ref_cols"])]
            if a["table"] != child_table:
                diffs.append(_diff(child_table, a["table"], f"外键 {name}.子表"))
            if a_cols != f["cols"]:
                diffs.append(_diff(f["cols"], a_cols, f"外键 {name}.源列"))
            if a["ref_table"] != f["ref_table"] or a_rc != f["ref_cols"]:
                diffs.append(_diff(f"{f['ref_table']}({','.join(f['ref_cols'])})",
                                   f"{a['ref_table']}({','.join(a_rc)})", f"外键 {name}.目标"))

    # 4) 主键/唯一键/索引：列顺序 + 唯一性（区分「schema.sql 声明」与「MySQL 自动外键索引」）
    cur.execute(
        "SELECT table_name, index_name, non_unique, seq_in_index, column_name "
        "FROM information_schema.statistics WHERE table_schema=%s ORDER BY table_name, index_name, seq_in_index",
        (ALLOWED_DB,))
    actual_idx = {}
    for t, iname, nonuniq, seq, c in cur.fetchall():
        actual_idx.setdefault(t, {}).setdefault(iname, {"non_unique": nonuniq, "cols": []})
        actual_idx[t][iname]["cols"].append((seq, c))

    declared = {}       # table -> {name: (non_unique, [cols])}，来自 schema.sql
    declared_leftmost = {}  # table -> {列：存在以该列为最左的声明索引}
    for t in exp_names:
        declared[t] = {}
        declared[t]["PRIMARY"] = (0, list(model[t]["pk"]))
        for k, v in model[t]["unique"].items():
            declared[t][k] = (0, v)
        for k, v in model[t]["index"].items():
            declared[t][k] = (1, v)
        declared_leftmost[t] = {col_list[0] for _, col_list in declared[t].values() if col_list}

    auto = {}           # table -> {name: (1, [cols])}，MySQL 为外键列自动创建（名=外键约束名）
    for t in exp_names:
        auto[t] = {}
        for f in model[t]["fk"]:
            if f["cols"][0] not in declared_leftmost[t]:
                auto[t][f["name"]] = (1, list(f["cols"]))

    expected_idx = {t: {**declared[t], **auto[t]} for t in exp_names}
    total_declared = sum(len(declared[t]) for t in exp_names)
    total_auto = sum(len(auto[t]) for t in exp_names)

    for t in exp_names:
        act = actual_idx.get(t, {})
        if set(act) != set(expected_idx[t]):
            diffs.append(_diff(sorted(expected_idx[t]), sorted(act), f"{t}.索引名集合"))
            continue
        for iname, (nonuniq, cols) in expected_idx[t].items():
            a = act[iname]
            a_cols = [c for _, c in sorted(a["cols"])]
            if a_cols != cols:
                diffs.append(_diff(cols, a_cols, f"{t}.{iname}.列顺序"))
            if a["non_unique"] != nonuniq:
                diffs.append(_diff("唯一" if nonuniq == 0 else "非唯一",
                                   "唯一" if a["non_unique"] == 0 else "非唯一", f"{t}.{iname}.唯一性"))

    # 5) CHECK：名称、是否启用、定义（比较式集合）
    cur.execute(
        "SELECT tc.table_name, tc.constraint_name, tc.enforced, cc.check_clause "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.check_constraints cc "
        "  ON cc.constraint_schema=tc.constraint_schema AND cc.constraint_name=tc.constraint_name "
        "WHERE tc.table_schema=%s AND tc.constraint_type='CHECK'", (ALLOWED_DB,))
    actual_ck = {}
    for t, cn, enforced, clause in cur.fetchall():
        actual_ck[cn] = (t, enforced, clause)
    exp_ck = {cn: t for t in exp_names for cn in model[t]["check"]}
    if set(actual_ck) != set(exp_ck):
        diffs.append(_diff(sorted(exp_ck), sorted(actual_ck), "CHECK 名集合"))
    else:
        for cn, t in exp_ck.items():
            _, enforced, clause = actual_ck[cn]
            if enforced != "YES":
                diffs.append(_diff("YES", enforced, f"{t}.{cn}.启用"))
            if _norm_check_clause(clause) != _norm_check_clause(model[t]["check"][cn]):
                diffs.append(_diff(model[t]["check"][cn], clause, f"{t}.{cn}.定义"))

    # ---- 汇总输出 ----
    total_indexes = total_declared + total_auto
    print(f"[DEEP] 表 {len(exp_names)} 个 / 列 {col_total} 个 / 外键 {len(exp_fk)} 个 / CHECK {len(exp_ck)} 个")
    print(f"[DEEP] 索引与键：schema.sql 声明 {total_declared} 个（含主键 {len(exp_names)}）+ MySQL 自动外键索引 {total_auto} 个 = 全部 {total_indexes} 个")
    if diffs:
        print(f"[DEEP] 发现 {len(diffs)} 处不一致：")
        for d in diffs[:60]:
            print("   ", d)
        if len(diffs) > 60:
            print(f"   ... 其余 {len(diffs)-60} 处省略")
        return 1
    print("[DEEP] 逐表/逐列/逐注释/逐外键/逐索引/逐 CHECK 与 schema.sql 全部一致")
    return 0


def _constraint_cases(cur) -> bool:
    """13 个合成数据约束用例（在事务内执行，由调用方负责回滚）。返回是否全部符合预期。"""
    ins = cur.execute

    def expect_fail(name, sql, args, hint):
        try:
            ins(sql, args)
            print(f"[TEST] {name}: 未报错（应被拒绝） -> FAIL")
            return False
        except Exception as e:
            if hint and hint not in str(e):
                print(f"[TEST] {name}: 报错缺关键词 {hint!r}: {str(e)[:120]}")
                return False
            print(f"[TEST] {name}: 被拒绝（符合预期）")
            return True

    uid, uid2 = "usr-admin-0001", "usr-user-0002"
    fid, tid = "file-0001", "task-0001"
    cid, pid, unit = "chap-0001", "para-0001", "unit-0001"
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
    ins("INSERT INTO translation_unit(id,paragraph_id,seq_no,source_text,status,retry_count) VALUES(%s,%s,%s,%s,%s,%s)", (unit, pid, 1, "Hello.", "translated", 0))
    ins("INSERT INTO book(id,owner_id,task_id,name,src_lang,tgt_lang,created_at) VALUES(%s,%s,%s,%s,%s,%s,NOW(6))",
        (bid, uid, tid, "Sample", "en", "zh"))
    print("[TEST] 基础合成数据插入成功")

    ok = True
    ok &= expect_fail("唯一-重复邮箱", "INSERT INTO user(id,email,password_hash,display_name,role,created_at,updated_at) VALUES('x1','a@example.com','x','n','user',NOW(6),NOW(6))", (), "Duplicate")
    ok &= expect_fail("唯一-章节(任务,序号)重复", "INSERT INTO chapter(id,task_id,seq_no) VALUES('x2',%s,1)", (tid,), "Duplicate")
    ok &= expect_fail("外键-章节指向不存在任务", "INSERT INTO chapter(id,task_id,seq_no) VALUES('x3','no-such-task',2)", (), "foreign key")
    ok &= expect_fail("顺序-章节 seq_no=0", "INSERT INTO chapter(id,task_id,seq_no) VALUES('x4',%s,0)", (tid,), "constraint")
    ok &= expect_fail("顺序-段落 seq_no 负数", "INSERT INTO paragraph(id,chapter_id,seq_no,source_text) VALUES('x5',%s,-1,'x')", (cid,), "constraint")
    ok &= expect_fail("计数-task failed_units 负数", "INSERT INTO task(id,owner_id,file_id,src_lang,tgt_lang,svc_key,style_key,status,total_units,done_units,failed_units,created_at,updated_at) VALUES('x6',%s,%s,'en','zh','d','l','pending',3,2,-1,NOW(6),NOW(6))", (uid, fid), "constraint")
    ok &= expect_fail("计数-task failed_units>done_units", "INSERT INTO task(id,owner_id,file_id,src_lang,tgt_lang,svc_key,style_key,status,total_units,done_units,failed_units,created_at,updated_at) VALUES('x7',%s,%s,'en','zh','d','l','pending',3,1,2,NOW(6),NOW(6))", (uid, fid), "constraint")
    ok &= expect_fail("计数-book failed_units 负数", "INSERT INTO book(id,owner_id,task_id,name,src_lang,tgt_lang,failed_units,created_at) VALUES('x8',%s,%s,'n','en','zh',-1,NOW(6))", (uid, tid), "constraint")
    ok &= expect_fail("大小-upload_file 负数", "INSERT INTO upload_file(id,owner_id,original_name,storage_ref,ext,size_bytes,sha256,created_at) VALUES('x9',%s,'n','r','.txt',-5,%s,NOW(6))", (uid, "b" * 64), "constraint")
    ok &= expect_fail("大小-book_file 负数", "INSERT INTO book_file(id,book_id,format,storage_ref,size_bytes,generated_at) VALUES('x10',%s,'epub','r',-1,NOW(6))", (bid,), "constraint")
    ok &= expect_fail("举报-对象双空", "INSERT INTO report(id,reporter_id,reason,status,created_at) VALUES('r1',%s,'r','pending',NOW(6))", (uid,), "constraint")
    ok &= expect_fail("举报-对象双设", "INSERT INTO report(id,reporter_id,reported_user_id,book_id,reason,status,created_at) VALUES('r2',%s,%s,%s,'r','pending',NOW(6))", (uid, uid2, bid), "constraint")
    try:
        ins("INSERT INTO report(id,reporter_id,book_id,reason,status,created_at) VALUES('r3',%s,%s,'r','pending',NOW(6))", (uid, bid))
        print("[TEST] 举报-对象=书籍（恰一非空）: 成功（符合预期）")
    except Exception as e:
        print(f"[TEST] 举报-对象=书籍: 意外失败 {str(e)[:120]} -> FAIL")
        ok = False
    return ok


def _with_connection_close(conn, fn):
    try:
        return fn(conn)
    finally:
        conn.close()


def _with_rollback(conn, fn):
    conn.autocommit(False)
    try:
        return fn(conn.cursor())
    finally:
        conn.rollback()
        conn.autocommit(True)


def run_selftest() -> int:
    """离线替身测试：证明错误库名/端点在连接前拒绝、错误版本在 DDL 前拒绝、异常路径关闭连接、测试事务 finally 回滚。"""
    fails = []

    def check(name, cond):
        print(f"[SELFTEST] {name}: {'PASS' if cond else 'FAIL'}")
        if not cond:
            fails.append(name)

    for bad in ("yiban_api_dev", "yiban_api_test", "mysql", "information_schema"):
        try:
            require_db_name(bad)
            check(f"拒绝库名 {bad}", False)
        except ValueError:
            check(f"拒绝库名 {bad}", True)
    try:
        require_db_name(ALLOWED_DB)
        check("接受合法库名", True)
    except ValueError:
        check("接受合法库名", False)

    for bad in (("127.0.0.1", 3306), ("127.0.0.1", 3308), ("localhost", 3307)):
        try:
            require_endpoint(*bad)
            check(f"拒绝端点 {bad}", False)
        except ValueError:
            check(f"拒绝端点 {bad}", True)
    try:
        require_endpoint(ALLOWED_HOST, ALLOWED_PORT)
        check("接受合法端点", True)
    except ValueError:
        check("接受合法端点", False)

    for bad in ("8.0.36", "5.7.44", "8.3.0", "9.0.0"):
        try:
            require_version(bad)
            check(f"拒绝版本 {bad}", False)
        except ValueError:
            check(f"拒绝版本 {bad}", True)
    try:
        require_version("8.4.13")
        check("接受版本 8.4.13", True)
    except ValueError:
        check("接受版本 8.4.13", False)

    class FakeConn:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

        def cursor(self):
            raise RuntimeError("boom")

    fc = FakeConn()
    try:
        _with_connection_close(fc, lambda c: c.cursor())
    except RuntimeError:
        pass
    check("异常路径关闭连接", fc.closed)

    class FakeConn2:
        def __init__(self):
            self.rolled = False
            self.auto = True

        def cursor(self):
            return self

        def execute(self, *a, **k):
            raise RuntimeError("insert failed")

        def autocommit(self, v):
            self.auto = v

        def rollback(self):
            self.rolled = True

    fc2 = FakeConn2()
    try:
        _with_rollback(fc2, lambda cur: cur.execute("INSERT ..."))
    except RuntimeError:
        pass
    check("测试事务 finally 回滚", fc2.rolled)
    check("测试事务恢复 autocommit=True", fc2.auto is True)

    print(f"[SELFTEST] {'PASS' if not fails else 'FAIL'}（{len(fails)} 项失败）")
    return 1 if fails else 0


def main() -> int:
    args = sys.argv[1:]
    if "--selftest" in args:
        return run_selftest()
    readonly = "--readonly" in args
    env_path = ""
    if "--env-file" in args:
        i = args.index("--env-file")
        if i + 1 < len(args):
            env_path = args[i + 1]
    password = _load_env_file(env_path)
    if not password:
        print("[FAIL] 未从 --env-file 读到 MYSQL_ROOT_PASSWORD（凭据须经本机私有配置注入，不打印）")
        return 1

    # 硬保护：连接前校验端点与库名
    try:
        require_endpoint(ALLOWED_HOST, ALLOWED_PORT)
        require_db_name(ALLOWED_DB)
    except ValueError as e:
        print(f"[FAIL] {e}")
        return 1

    print(f"[INFO] 连接 {ALLOWED_USER}@{ALLOWED_HOST}:{ALLOWED_PORT}（库未指定）")
    try:
        conn = pymysql.connect(host=ALLOWED_HOST, port=ALLOWED_PORT, user=ALLOWED_USER,
                               password=password, connect_timeout=8, autocommit=True, charset="utf8mb4")
    except Exception as e:
        print(f"[FAIL] 连接失败：{type(e).__name__} {str(e)[:160]}（不含凭据）")
        return 1

    try:
        cur = conn.cursor()
        cur.execute("SELECT VERSION(), @@hostname, @@port")
        ver, hostname, srv_port = cur.fetchone()
        print(f"[INFO] 服务器版本={ver} 主机={hostname} 服务器port={srv_port}")
        # 版本必须在任何 DDL 前确认
        try:
            require_version(ver)
        except ValueError as e:
            print(f"[FAIL] {e}")
            return 1

        model = parse_schema(SCHEMA_SQL)
        print(f"[INFO] schema.sql 解析：{len(model)} 张表（来源 {SCHEMA_SQL.name}，固定不可改写）")

        cur.execute("SHOW DATABASES")
        existing = {r[0] for r in cur.fetchall()}
        db_exists = ALLOWED_DB in existing

        if readonly:
            if not db_exists:
                print(f"[FAIL] 只读模式：库 {ALLOWED_DB} 不存在，无法核对（只读不建库）")
                return 1
            cur.execute(f"USE `{ALLOWED_DB}`")
            print(f"[INFO] 只读模式：对已存在库 {ALLOWED_DB} 做深度元数据核对（不建表/不删数据）")
            rc = deep_check(conn, model)
            print(f"[RESULT] {'PASS' if rc == 0 else 'FAIL'}（只读深度核对）")
            return rc

        # 写模式：目标库必须为空；非空则停止（禁止自动 DROP/TRUNCATE）
        if db_exists:
            cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s", (ALLOWED_DB,))
            n = cur.fetchone()[0]
            if n > 0:
                print(f"[FAIL] 目标库 {ALLOWED_DB} 已存在且含 {n} 张表；停止（不 DROP/TRUNCATE/覆盖；复验请用 --readonly）")
                return 1
            print(f"[CHECK] 目标库 {ALLOWED_DB} 已存在且为空，复用")
        else:
            cur.execute(f"CREATE DATABASE `{ALLOWED_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
            print(f"[CHECK] 已创建独立库 {ALLOWED_DB}")

        # 执行 schema.sql（DDL，MySQL 隐式提交，不依赖事务回滚）
        sql_text = SCHEMA_SQL.read_text(encoding="utf-8")
        stmts = []
        for raw in sql_text.split(";"):
            body = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("--"))
            if body.strip():
                stmts.append(body)
        cur.execute(f"USE `{ALLOWED_DB}`")
        created = 0
        for st in stmts:
            cur.execute(st)
            if st.lstrip().upper().startswith("CREATE TABLE"):
                created += 1
        print(f"[CHECK] 已执行 {created} 条 CREATE TABLE（DDL 隐式提交）")

        rc = deep_check(conn, model)
        if rc != 0:
            print("[RESULT] FAIL（元数据深度核对不一致）")
            return rc

        ok = _with_rollback(conn, _constraint_cases)
        print("[INFO] 合成测试数据已回滚（DDL 已隐式提交，不在回滚范围）")
        if not ok:
            print("[RESULT] FAIL（存在未按预期拒绝的用例）")
            return 1
        print(f"[RESULT] PASS：{ALLOWED_DB} 深度核对通过，{created} 表约束用例通过并回滚")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
