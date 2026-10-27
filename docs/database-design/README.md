# 数据库设计检查版（目标模型 · MySQL 8.4）

> 本文档是「数据库设计」考核材料，供老师顺序检查。它把既有《数据库逻辑模型草案》从**逻辑层**落到**物理目标模型**，并**与 yiban-api 实际源码/迁移对齐**（截至 2026-10-27 核对）。
> 性质：**目标模型验证稿**，不是运行库迁移；不改写 yiban-api 已验收的 alembic 0001/0002；不对开发库/测试库执行建表。

## 文件导航（按此顺序阅读）

| 文件 | 内容 |
|---|---|
| [README.md](README.md)（本页） | 范围、状态分类、与既有文档关系、差异与待决 |
| [01-er.md](01-er.md) / [01-er.mmd](01-er.mmd) | ER 图 mermaid 源（网页可直接渲染）+ 关系基数 + 约束摘要；**SVG 待补**（导出命令见 01-er.md 顶部） |
| [02-字段字典.md](02-字段字典.md) | 逐表字段字典（类型/空/默认/键/说明）+ 状态合法值 |
| [03-页面数据对应表.md](03-页面数据对应表.md) | 页面→实体→写入角色/触发时机→实现状态；持久化/计算/展示 |
| [schema.sql](schema.sql) | 目标模型设计 SQL（含表/列 COMMENT，MySQL 8.4） |

## 范围与实现状态

| 表 | 说明 | 状态 |
|---|---|---|
| `user` | 用户账号（含管理员角色） | ✅ 已实现（alembic 0001） |
| `user_session` | 用户会话（JWT jti + 撤销） | ✅ 已实现（alembic 0002） |
| `upload_file` | 上传文件（私有、属主隔离） | ✍ 本次拟定（上传方案仍在评审） |
| `task` | 任务 + 配置快照 + 进度计数 | ✍ 本次拟定 |
| `chapter` / `paragraph` / `translation_unit` | 章节/段落/翻译单元 | ✍ 本次拟定 |
| `book` / `book_file` | 书籍成果 + 文件记录 | ✍ 本次拟定 |
| `audit_log` | 管理留痕（管理员查看私有内容） | ❓ 设计建议（待确认） |

- **已实现**：以 yiban-api `models/user.py`、`models/user_session.py`、`alembic/versions/0001`、`0002` 为准，本设计与其逐列一致。
- **本次拟定**：依据已确认需求（FR-01~16、G11、NFR-03）与 v4 原型流程形成；落库前需经评审与迁移批次。
- **仍待确认**：`audit_log` 是否纳入首版（首版管理端仅「任务/失败只读查看」，查看私有内容留痕是否强制待定）；`stage`/`fail_reason` 是否持久化（见下）。

## 与既有文档的关系（相互引用）

| 既有文档 | 关系 |
|---|---|
| 需求分析与设计文档说明.md §3.5 / FR-01~16 | 需求来源与范围依据 |
| 数据库逻辑模型草案.md | 逻辑模型原件；本文档是其物理目标模型落地，逻辑关系与唯一约束保持一致 |
| 任务状态机与进度口径草案.md | `task.status/stage` 与计数语义来源（done 判定、重试=新建 task） |
| 任务接口契约草案.md / 书库与成果接口契约草案.md | 字段与读写口径来源（属主校验、进度展示、下载条件） |

## 与既有草案的差异与推荐修订（记录，不擅自改已确认需求）

> 以下差异来自「逻辑草案 → 物理目标模型」的落地，以及「真实后端已实现」的对照；均已标注依据，**不悄悄改动需求文档**。

| # | 差异点 | 既有表述 | 目标模型 | 依据 / 推荐 |
|---|---|---|---|---|
| 1 | 主键类型 | 逻辑草案 `id string PK`（自增/UUID 待决） | `VARCHAR(36)` UUID 字符串 | yiban-api `user` 已用 UUID；推荐其余表一致 |
| 2 | 枚举落地 | 逻辑草案 `enum('user','admin')` 等 | `VARCHAR(16)` + 应用层校验 | yiban-api 决策：避免 MySQL ENUM 的 ALTER 成本 |
| 3 | 会话表 | 逻辑草案未含会话表 | 新增 `user_session` | yiban-api 0002 已实现；补齐双端会话 |
| 4 | 时间类型 | 逻辑草案 `timestamp` | `DATETIME(6)` 无时区 UTC | yiban-api `models/types.py` 约定 |
| 5 | `stage`/`fail_reason` | 逻辑草案标「建议增补/待决」 | 暂列 `stage`/`fail_reason` 字段 | 仍待确认是否首版持久化（状态机草案 §8） |
| 6 | 软删除 | 逻辑草案 §7.12 待决 | 不应用（`user` 未用 SoftDeleteMixin） | 保留待决，不预加 `is_deleted` |

## 关键约束（与状态机/接口草案一致，详见 01/02）

- 属主一致：`task.owner_id == upload_file.owner_id`、`book.owner_id == task.owner_id`（服务端强制，非 FK 自动保证）。
- 幂等入库：`book.task_id` 唯一；`translation_unit(paragraph_id,seq_no)` 唯一；`book_file(book_id,format)` 唯一（防重复行，不解决物理文件一致性）。
- 重试：`task.retry_of_task_id` 唯一 → 一个 failed task 最多一个直接子任务；重试=新建 task。
- 计数：`0 ≤ failed_units ≤ done_units ≤ total_units`。

## 待决 / 待技术设计

1. 上传方案仍在 yiban-api 分支评审（`docs/upload-foundation-plan`），`upload_file` 字段随其定稿微调。
2. `stage`/`fail_reason` 是否首版持久化。
3. `audit_log` 是否纳入首版。
4. 物理文件与 `book_file` 记录的一致性（孤儿文件清理）——属文件存储设计，数据库唯一约束不解决。
5. 后续在独立设计验证库核验方法（见发布说明），不对开发库/测试库执行本 SQL。
