# 数据库设计检查版（目标模型 · MySQL 8.4）

> 本文档是「数据库设计」考核材料，供老师顺序检查。它把既有《数据库逻辑模型草案》从**逻辑层**落到**物理目标模型**，并**与 yiban-api 实际源码/迁移对齐**（截至 2026-10-27 核对）。
> 性质：**目标模型验证稿**，不是运行库迁移；不改写 yiban-api 已验收的 alembic 0001/0002；不对开发库/测试库执行建表。

## 文件导航（按此顺序阅读）

| 文件 | 内容 |
|---|---|
| [README.md](README.md)（本页） | 范围、状态分类、与既有文档关系、差异与待决 |
| [01-er.md](01-er.md) / [01-er.mmd](01-er.mmd) | ER 图 mermaid 源（网页可直接渲染）+ 关系基数 + 约束摘要 |
| [er.svg](er.svg) / [er-overview.svg](er-overview.svg) | 全字段 / 关键字段概览 ER 图（由 `../scripts/render_database_er.py` 从 schema.sql 生成，已与 SQL 逐表逐列核对） |
| [02-字段字典.md](02-字段字典.md) | 逐表字段字典（类型/空/默认/键/说明）+ 状态合法值 + 删除规则 |
| [03-页面数据对应表.md](03-页面数据对应表.md) | 页面→实体→写入角色/触发时机→实现状态；持久化/计算/展示 |
| [schema.sql](schema.sql) | 目标模型设计 SQL（含表/列 COMMENT，MySQL 8.4） |

## 范围与实现状态（14 表）

| 表 | 说明 | 状态 |
|---|---|---|
| `user` | 用户账号（含管理员角色与启停） | ✅ 已实现（0001）；`status/disabled_*` 为 ⬜ 计划扩展 M2 |
| `user_session` | 用户会话（JWT jti + 撤销） | ✅ 已实现（alembic 0002） |
| `upload_file` | 上传文件（私有、属主隔离） | ✍ 本次拟定（对齐 yiban-api 4e3c762，上传方案仍待评审） |
| `task` | 任务 + 配置快照 + 进度计数 | ✍ 本次拟定 |
| `chapter` / `paragraph` / `translation_unit` | 章节 / 段落 / 翻译单元 | ✍ 本次拟定 |
| `book` / `book_file` | 书籍成果 + 文件记录 | ✍ 本次拟定 |
| `report` / `disposition` / `audit_log` | 举报审核 + 处置记录 + 管理留痕 | ⬜ 计划扩展（M2） |
| `bookmark` / `reading_progress` | 书签 + 阅读位置/继续阅读 | ⬜ 计划扩展（M4） |

- **已实现**：以 yiban-api `models/user.py`、`models/user_session.py`、`alembic/versions/0001`、`0002` 为准，本设计与其逐列一致；`user.status/disabled_reason/disabled_at` 为后续里程碑新增列，**不标为已实现**。
- **本次拟定**：依据已确认需求（FR-01~16、G11、NFR-03）与 v4 原型流程形成；落库前需经评审与迁移批次。
- **计划扩展**：`report`/`disposition`/`audit_log`（M2 管理端）、`bookmark`/`reading_progress`（M4 阅读体验）、`user.status/disabled_*` 与 `book.status`（M2）——均为后续里程碑目标设计；承载方式见 02-字段字典（事件记录 / 关联实体），**资源用量由聚合查询承载、不单独建表**（待确认展示口径）。
- **社区扩展方向（不建表、不覆盖）**：社区发布 / 授权分享仅列为**后续待评估方向**；发布/授权信息应与私有书籍（`book`）与审核状态（`report`/`disposition`）区分，具体模型留后续评审。**本 14 表目标模型不覆盖社区发布/评论/点赞/关注**；个人书库默认私有。

## 与既有文档的关系（相互引用）

| 既有文档 | 关系 |
|---|---|
| 需求分析与设计文档说明.md §3.5 / FR-01~16 | 需求来源与范围依据（FR-12/13 阅读、FR-15 管理端） |
| 数据库逻辑模型草案.md | 逻辑模型原件；本文档是其物理目标模型落地，逻辑关系与唯一约束保持一致 |
| 任务状态机与进度口径草案.md | `task.status/stage` 与计数语义来源（done 判定、重试=新建 task、单元级 vs 任务级失败） |
| 任务接口契约草案.md / 书库与成果接口契约草案.md | 字段与读写口径来源（属主校验、进度展示、下载条件） |

## 与既有草案的差异与推荐修订（记录，不擅自改已确认需求）

> 以下差异来自「逻辑草案 → 物理目标模型」的落地，以及「真实后端已实现 / 上传方案待评审」的对照；均已标注依据，**不悄悄改动需求文档**。

| # | 差异点 | 既有表述 | 目标模型 | 依据 / 推荐 |
|---|---|---|---|---|
| 1 | 主键类型 | 逻辑草案 `id string PK`（自增/UUID 待决） | `VARCHAR(36)` UUID 字符串 | yiban-api `user` 已用 UUID；推荐其余表一致 |
| 2 | 枚举落地 | 逻辑草案 `enum('user','admin')` 等 | `VARCHAR(16)` + 应用层校验 | yiban-api 决策：避免 MySQL ENUM 的 ALTER 成本 |
| 3 | 会话表 | 逻辑草案未含会话表 | 新增 `user_session` | yiban-api 0002 已实现；补齐双端会话 |
| 4 | 时间类型 | 逻辑草案 `timestamp` | `DATETIME(6)` 无时区 UTC | yiban-api `models/types.py` 约定 |
| 5 | `stage`/`fail_reason` | 逻辑草案标「建议增补/待决」 | 暂列 `stage`/`fail_reason` 字段 | 仍待确认是否首版持久化（状态机草案 §8） |
| 6 | 软删除 | 逻辑草案 §7.12 待决 | 不应用（`user` 未用 SoftDeleteMixin） | 保留待决，不预加 `is_deleted` |
| 7 | `upload_file` 字段口径 | storage_ref 512 且无唯一、sha256 可空、ext 无点约定 | `storage_ref` VARCHAR(255) UNIQUE、`sha256` NOT NULL（不加唯一）、`ext` 小写含点 ".txt" | **对齐 yiban-api 4e3c762**（上传方案，仍待评审）；`size_bytes` 用 `BIGINT`（4e3c762 用 BIGINT，与本稿一致） |
| 8 | 管理/阅读扩展 | 逻辑草案未覆盖 | 新增 `report`/`disposition`/`audit_log`/`bookmark`/`reading_progress` + `user.status` | FR-12/13/15、G11；M2/M4 计划扩展，非首版 |

## 关键约束（与状态机/接口草案一致，详见 01/02）

- 属主一致：`task.owner_id == upload_file.owner_id`、`book.owner_id == task.owner_id`（服务端强制，非 FK 自动保证）。
- 幂等入库：`book.task_id` 唯一；`translation_unit(paragraph_id,seq_no)` 唯一；`book_file(book_id,format)` 唯一（防重复行，不解决物理文件一致性）。
- 重试：`task.retry_of_task_id` 唯一 → 一个 failed task 最多一个直接子任务；重试=新建 task。
- 计数：`0 ≤ failed_units ≤ done_units ≤ total_units`（`total_units/done_units/failed_units` 均 ≥0，已落 CHECK）；`book.failed_units ≥ 0`；`size_bytes ≥ 0`；单元级失败保留原文、不使任务 failed。
- 完成顺序：成果文件就绪后同一事务内 `book → book_file → task.status=done`，不先标 done 再补记录。
- 删除规则：外键默认 `RESTRICT`；用户 `status=disabled` 停用、书籍 `status=blocked/removed` 逻辑移除（不物理删除）；`disposition`/`audit_log` append-only，`report` 为可受控状态更新的状态实体。
- 举报对象：`report` 用户或书籍二选一（`chk_report_target` 恰一非空）。
- 处置落点：`disposition.action` block/delete 同事务落到 `user.status='disabled'` 或 `book.status='blocked/removed'`；approve/reject 仅推进 `report.status`。
- 审核留痕：`audit_log.report_id` 结构化关联举报（成功查看私有内容可追溯具体审核事项）；无上下文拒绝日志为空。
- 书签/阅读位置服务端一致性（外键不足以保证）：用户有权访问该书且段落经 chapter/task 确属该书。

## 待决 / 待技术设计

1. 上传方案仍在 yiban-api 分支评审（`tasks/upload-foundation-plan.md`，4e3c762）；`storage_ref/sha256/ext` 已对齐，其余随定稿微调（如 20 MiB 上限、是否加 `PAYLOAD_TOO_LARGE` 响应码）。
2. `stage`/`fail_reason` 是否首版持久化（状态机草案 §8）。
3. `report`/`disposition`/`audit_log`（M2）与 `bookmark`/`reading_progress`（M4）在各自里程碑内的落地批次【待确认】；审核事项已定「不单独建表（report 队列态视图）」、书签锚点已定「段落级」，如需整章书签再评估。
4. 资源用量展示口径（实时聚合 vs 缓存汇总表）【待确认】。
5. 物理文件与 `book_file` 记录的一致性（孤儿文件清理）——属文件存储设计，数据库唯一约束不解决。
6. 后续在独立设计验证库核验方法（见发布说明），不对开发库/测试库执行本 SQL。
