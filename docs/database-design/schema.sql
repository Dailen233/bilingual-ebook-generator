-- ============================================================================
-- 译伴 · 双语电子书生成系统 —— 目标数据库模型验证稿（MySQL 8.4）
-- ============================================================================
-- 性质：本文件是「数据库设计检查版」的目标模型验证稿，供老师审查与后续在
--      独立设计验证库中核验；【不是】运行库迁移，不替代 yiban-api 已验收的
--      alembic 迁移 0001/0002。请勿对开发库/测试库执行本文件。
--
-- 与真实工程对齐的事实（截至 2026-10-27 核对 yiban-api 源码与迁移）：
--   1) 主键为 VARCHAR(36) 的 UUID 字符串（服务端生成），非自增整型；
--   2) 角色/会话类型/状态等枚举落地为 VARCHAR(16) + 应用层校验，避免
--      MySQL ENUM 后续增删值的 ALTER 成本（与 models/user.py 一致）；
--   3) 时间列统一 DATETIME(6)、无时区、语义为 UTC：由应用层写入 naive UTC
--      （models/types.py 的 UTCDateTime），不在 SQL 层用 CURRENT_TIMESTAMP；
--   4) 密码仅存 bcrypt 哈希；user_session 只存 JWT 的 jti，不存原始 JWT；
--   5) 已验收迁移 0001(user)、0002(user_session) 不含列 COMMENT 与 user 扩展列；
--      本验证稿补齐 COMMENT 与目标列作为「目标模型」，【不改写】既有迁移，新增
--      列/表仅在后续里程碑用新迁移落地。
--
-- 实现状态标记（配合 docs/database-design/README.md）：
--   [已实现]     user（基础列，对应 0001）、user_session（对应 0002）
--   [本次拟定]   upload_file / task / chapter / paragraph / translation_unit
--                / book / book_file（首个里程碑核心处理模型；上传方案待评审）
--   [计划扩展]   user.status/disabled_reason/disabled_at（M2 用户与权限）、
--                report / disposition / audit_log（M2 举报审核与管理留痕）、
--                bookmark / reading_progress（M4 书签与阅读位置）
--   [待确认]     资源用量 = 聚合查询（不单独建表）；audit_log 是否纳入首版最小集
-- ============================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- 1. user 用户账号 [已实现基础列 → alembic 0001；status/disabled_* 为计划扩展 M2]
-- 来源：需求 FR-14（注册/登录/属主）、G11（角色服务端校验）、FR-15（启用/停用）。
-- 说明：0001 仅含 id/email/password_hash/display_name/role/created_at/updated_at；
--       status/disabled_reason/disabled_at 为 M2 计划扩展列，勿标为已实现。
-- ---------------------------------------------------------------------------
CREATE TABLE `user` (
    `id`              VARCHAR(36)  NOT NULL COMMENT '用户唯一标识（UUID 字符串，服务端生成）',
    `email`           VARCHAR(255) NOT NULL COMMENT '登录邮箱（入库前 strip+lower 规范化，唯一）',
    `password_hash`   VARCHAR(255) NOT NULL COMMENT '密码哈希（bcrypt，绝不明文）',
    `display_name`    VARCHAR(100) NOT NULL COMMENT '显示名/昵称',
    `role`            VARCHAR(16)  NOT NULL DEFAULT 'user' COMMENT '角色：user/admin（应用层校验合法值；权限模型首版仅此二值）',
    `status`          VARCHAR(16)  NOT NULL DEFAULT 'active' COMMENT '账号状态：active/disabled（启用/停用；M2 计划扩展列，0001 无此列）',
    `disabled_reason` VARCHAR(255) NULL COMMENT '停用原因（status=disabled 时非空；处置记录留痕）',
    `disabled_at`     DATETIME(6)  NULL COMMENT '停用时间（无时区 UTC）',
    `created_at`      DATETIME(6)  NOT NULL COMMENT '注册时间（无时区 UTC）',
    `updated_at`      DATETIME(6)  NOT NULL COMMENT '更新时间（无时区 UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_user_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户账号（含管理员角色与启停状态）';

-- ---------------------------------------------------------------------------
-- 2. user_session 用户会话 [已实现 → alembic 0002]
-- 来源：FR-14（会话/退出撤销）、G11（双端会话）、后端 core/token + cookies。
-- ---------------------------------------------------------------------------
CREATE TABLE `user_session` (
    `id`           VARCHAR(36) NOT NULL COMMENT '会话唯一标识（UUID）',
    `user_id`      VARCHAR(36) NOT NULL COMMENT '归属用户（FK → user.id）',
    `jti`          VARCHAR(36) NOT NULL COMMENT 'JWT 的 jti（唯一，退出时用于撤销）',
    `session_type` VARCHAR(16) NOT NULL DEFAULT 'user' COMMENT '会话类型：user/admin',
    `expires_at`   DATETIME(6) NOT NULL COMMENT '会话到期时间（与 JWT exp 一致，UTC）',
    `revoked_at`   DATETIME(6) NULL     COMMENT '撤销时间；非空即会话已失效（退出）',
    `created_at`   DATETIME(6) NOT NULL COMMENT '登录时间（UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_user_session_jti` (`jti`),
    KEY `ix_user_session_user_id` (`user_id`),
    CONSTRAINT `fk_user_session_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户会话（仅存 jti 追踪与撤销，不存原始 JWT）';

-- ---------------------------------------------------------------------------
-- 3. upload_file 上传文件 [本次拟定；上传方案待评审（对齐 yiban-api 4e3c762）]
-- 来源：FR-01（上传/校验）、NFR-03（文件私有 + 访问控制）、DB 逻辑草案 §3.2。
-- 口径（对齐 yiban-api tasks/upload-foundation-plan.md，2026-10-27 4e3c762）：
--   storage_ref VARCHAR(255) 唯一（服务端相对引用，防覆盖）；sha256 CHAR(64) 非空
--   （不加唯一约束）；ext 小写含前导点（首版 ".txt"）；size_bytes 为落盘字节数。
-- ---------------------------------------------------------------------------
CREATE TABLE `upload_file` (
    `id`            VARCHAR(36)  NOT NULL COMMENT '文件记录唯一标识（UUID）',
    `owner_id`      VARCHAR(36)  NOT NULL COMMENT '属主（FK → user.id；上传时服务端写入=当前用户）',
    `original_name` VARCHAR(255) NOT NULL COMMENT '原始文件名（仅展示，不参与唯一性/不作磁盘路径）',
    `storage_ref`   VARCHAR(255) NOT NULL COMMENT '存储引用（服务端生成的相对引用，如 {uuid}.txt；不暴露给前端）',
    `ext`           VARCHAR(16)  NOT NULL COMMENT '扩展名（小写、含前导点；首版 ".txt"，epub/pdf 输入为后续扩展）',
    `size_bytes`    BIGINT       NOT NULL COMMENT '文件大小（字节，实际落盘数）',
    `sha256`        CHAR(64)     NOT NULL COMMENT '小写十六进制 SHA-256（完整性校验；不加唯一约束，允许同名/同内容独立上传）',
    `created_at`    DATETIME(6)  NOT NULL COMMENT '上传时间（UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_upload_file_storage_ref` (`storage_ref`),
    KEY `ix_upload_file_owner_id` (`owner_id`),
    CONSTRAINT `fk_upload_file_user` FOREIGN KEY (`owner_id`) REFERENCES `user` (`id`),
    CONSTRAINT `chk_upload_file_size` CHECK (`size_bytes` >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='上传文件（私有，属主隔离）';

-- ---------------------------------------------------------------------------
-- 4. task 任务 + 配置快照 [本次拟定]
-- 来源：FR-03/05/09/16、状态机草案（status/stage/counters）、DB 逻辑草案 §3.3。
-- 说明：svc_name/model_name/style_name 等是「持久化的展示快照」（随任务落库，
--       供任务详情/书库展示），不是不落库的纯展示数据（见 03-页面数据对应表）。
-- ---------------------------------------------------------------------------
CREATE TABLE `task` (
    `id`                VARCHAR(36)  NOT NULL COMMENT '任务唯一标识（UUID）',
    `owner_id`          VARCHAR(36)  NOT NULL COMMENT '属主（服务端派生自 upload_file.owner_id，创建时校验一致）',
    `file_id`           VARCHAR(36)  NOT NULL COMMENT '来源文件（FK → upload_file.id）',
    `retry_of_task_id`  VARCHAR(36)  NULL COMMENT '重试来源：指向被重试的旧 task；唯一，保证一个 failed task 最多一个直接子任务',
    `src_lang`          VARCHAR(16)  NOT NULL COMMENT '原文语言（首版 en）',
    `tgt_lang`          VARCHAR(16)  NOT NULL COMMENT '目标语言（首版 zh）',
    `svc_key`           VARCHAR(64)  NOT NULL COMMENT '翻译服务标识（快照，FR-16，新任务必填）',
    `svc_name`          VARCHAR(128) NULL COMMENT '翻译服务名称（持久化展示快照）',
    `model_key`         VARCHAR(64)  NULL COMMENT '模型标识（快照；仅服务提供模型参数时非空）',
    `model_name`        VARCHAR(128) NULL COMMENT '模型名称（持久化展示快照）',
    `style_key`         VARCHAR(64)  NOT NULL COMMENT '翻译风格标识（快照，新任务必填）',
    `style_name`        VARCHAR(128) NULL COMMENT '翻译风格名称（持久化展示快照）',
    `status`            VARCHAR(16)  NOT NULL DEFAULT 'pending' COMMENT '任务状态：pending/running/done/failed（done/failed 为不可变终态）',
    `stage`             VARCHAR(16)  NULL COMMENT '处理阶段：extract/align/translate/layout/export（是否持久化待定）',
    `fail_reason`       VARCHAR(255) NULL COMMENT '失败原因（提取/切分/翻译/导出），仅 status=failed 时非空',
    `total_units`       INT          NOT NULL DEFAULT 0 COMMENT '翻译单元总数（align 阶段确定，此后不变）',
    `done_units`        INT          NOT NULL DEFAULT 0 COMMENT '已终态单元数（translated + failed；失败单元保留原文也计入）',
    `failed_units`      INT          NOT NULL DEFAULT 0 COMMENT '失败单元数（保留原文，结果页展示；单元级失败不使任务 failed）',
    `completion_key`    VARCHAR(64)  NULL COMMENT '完成回调幂等键（可选，见约束）',
    `created_at`        DATETIME(6)  NOT NULL COMMENT '创建时间（UTC）',
    `started_at`        DATETIME(6)  NULL COMMENT '开始处理时间（UTC）',
    `finished_at`       DATETIME(6)  NULL COMMENT '结束时间（UTC）',
    `updated_at`        DATETIME(6)  NOT NULL COMMENT '更新时间（UTC）',
    PRIMARY KEY (`id`),
    KEY `ix_task_owner_id` (`owner_id`),
    KEY `ix_task_file_id` (`file_id`),
    UNIQUE KEY `uk_task_retry_of` (`retry_of_task_id`),
    UNIQUE KEY `uk_task_completion_key` (`completion_key`),
    CONSTRAINT `fk_task_user`   FOREIGN KEY (`owner_id`) REFERENCES `user` (`id`),
    CONSTRAINT `fk_task_file`   FOREIGN KEY (`file_id`) REFERENCES `upload_file` (`id`),
    CONSTRAINT `fk_task_retry`  FOREIGN KEY (`retry_of_task_id`) REFERENCES `task` (`id`),
    CONSTRAINT `chk_task_counters` CHECK (`failed_units` <= `done_units` AND `done_units` <= `total_units`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='翻译任务（含配置快照与进度计数）';

-- ---------------------------------------------------------------------------
-- 5. chapter 章节 [本次拟定]
-- 来源：FR-02（正文提取/章节结构）、DB 逻辑草案 §3.4。
-- 说明：task_id NOT NULL——每个章节必属一个任务；一个任务可暂时无章节（未提取完）。
-- ---------------------------------------------------------------------------
CREATE TABLE `chapter` (
    `id`      VARCHAR(36)  NOT NULL COMMENT '章节唯一标识（UUID）',
    `task_id` VARCHAR(36)  NOT NULL COMMENT '归属任务（FK → task.id，必填）',
    `seq_no`  INT          NOT NULL COMMENT '章节在全书内的顺序（1 起）',
    `title`   VARCHAR(255) NULL COMMENT '章节标题（如 Chapter 1）；无标题纯文本归入 title 为空的默认章节',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_chapter_task_seq` (`task_id`, `seq_no`),
    CONSTRAINT `fk_chapter_task` FOREIGN KEY (`task_id`) REFERENCES `task` (`id`),
    CONSTRAINT `chk_chapter_seq` CHECK (`seq_no` >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='正文提取出的章节（保序，任务必属）';

-- ---------------------------------------------------------------------------
-- 6. paragraph 原段落 [本次拟定]
-- 来源：FR-02/FR-06（保留段落结构）、DB 逻辑草案 §3.5。
-- ---------------------------------------------------------------------------
CREATE TABLE `paragraph` (
    `id`          VARCHAR(36) NOT NULL COMMENT '段落唯一标识（UUID）',
    `chapter_id`  VARCHAR(36) NOT NULL COMMENT '归属章节（FK → chapter.id）',
    `seq_no`      INT         NOT NULL COMMENT '段落在章节内的顺序（1 起）',
    `source_text` TEXT        NOT NULL COMMENT '原段落完整原文（用于精确还原段落层级）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_paragraph_chapter_seq` (`chapter_id`, `seq_no`),
    CONSTRAINT `fk_paragraph_chapter` FOREIGN KEY (`chapter_id`) REFERENCES `chapter` (`id`),
    CONSTRAINT `chk_paragraph_seq` CHECK (`seq_no` >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='原文段落（还原段落结构）';

-- ---------------------------------------------------------------------------
-- 7. translation_unit 翻译单元 [本次拟定]
-- 来源：FR-04（切分）/FR-05（失败回退原文）、DB 逻辑草案 §3.6。
-- 说明：单元级失败（status='failed'）保留原文、计入 done_units，不使任务 failed；
--       任务级失败由 task.status 表达（见状态机草案 §3/§5）。
-- ---------------------------------------------------------------------------
CREATE TABLE `translation_unit` (
    `id`           VARCHAR(36) NOT NULL COMMENT '单元唯一标识（UUID）',
    `paragraph_id` VARCHAR(36) NOT NULL COMMENT '归属段落（FK → paragraph.id）',
    `seq_no`       INT         NOT NULL COMMENT '单元在段落内的顺序（1 起，失败不使邻位错序）',
    `source_text`  TEXT        NOT NULL COMMENT '单元原文（句子或整段）',
    `target_text`  TEXT        NULL COMMENT '译文；失败单元回退为原文（保留原文）',
    `status`       VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '单元状态：pending/translated/failed（条件更新，不回退；failed=单元级失败）',
    `retry_count`  INT         NOT NULL DEFAULT 0 COMMENT '重试次数（达上限置 failed）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_unit_paragraph_seq` (`paragraph_id`, `seq_no`),
    CONSTRAINT `fk_unit_paragraph` FOREIGN KEY (`paragraph_id`) REFERENCES `paragraph` (`id`),
    CONSTRAINT `chk_unit_seq` CHECK (`seq_no` >= 1),
    CONSTRAINT `chk_unit_retry` CHECK (`retry_count` >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='翻译单元（句子或段落级，含单元级失败状态）';

-- ---------------------------------------------------------------------------
-- 8. book 书籍成果 [本次拟定]
-- 来源：FR-07/09/10（成果/幂等入库）、DB 逻辑草案 §3.7。
-- 说明：完成流程为同一事务内「先写 book，再写 book_file，最后 task.status=done」；
--       不能先标 done 再补成果记录（见状态机草案 §4）。
-- ---------------------------------------------------------------------------
CREATE TABLE `book` (
    `id`           VARCHAR(36)  NOT NULL COMMENT '书唯一标识（UUID；可由 task 幂等派生，见 uk_book_task_id）',
    `owner_id`     VARCHAR(36)  NOT NULL COMMENT '属主（服务端派生自 task.owner_id，写入同事务一致）',
    `task_id`      VARCHAR(36)  NOT NULL COMMENT '来源任务（唯一 = 幂等入库，一个任务最多一本书）',
    `name`         VARCHAR(255) NOT NULL COMMENT '书名快照（无唯一约束，同名不同配置可分别成书）',
    `src_lang`     VARCHAR(16)  NOT NULL COMMENT '原文语言快照',
    `tgt_lang`     VARCHAR(16)  NOT NULL COMMENT '目标语言快照',
    `svc_name`     VARCHAR(128) NULL COMMENT '翻译服务名称快照（持久化展示快照）',
    `model_name`   VARCHAR(128) NULL COMMENT '模型名称快照（持久化展示快照）',
    `style_name`   VARCHAR(128) NULL COMMENT '风格名称快照（持久化展示快照）',
    `failed_units` INT          NOT NULL DEFAULT 0 COMMENT '失败单元数快照（结果页展示）',
    `created_at`   DATETIME(6)  NOT NULL COMMENT '成书时间（UTC）',
    PRIMARY KEY (`id`),
    KEY `ix_book_owner_id` (`owner_id`),
    UNIQUE KEY `uk_book_task_id` (`task_id`),
    CONSTRAINT `fk_book_user` FOREIGN KEY (`owner_id`) REFERENCES `user` (`id`),
    CONSTRAINT `fk_book_task` FOREIGN KEY (`task_id`) REFERENCES `task` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='书籍成果（任务完成幂等入库）';

-- ---------------------------------------------------------------------------
-- 9. book_file 成果文件记录 [本次拟定]
-- 来源：FR-07（EPUB/PDF）、DB 逻辑草案 §3.8。
-- ---------------------------------------------------------------------------
CREATE TABLE `book_file` (
    `id`           VARCHAR(36)  NOT NULL COMMENT '文件记录唯一标识（UUID）',
    `book_id`      VARCHAR(36)  NOT NULL COMMENT '归属书籍（FK → book.id）',
    `format`       VARCHAR(16)  NOT NULL COMMENT '格式：epub/pdf（首版仅 epub，pdf 后续里程碑）',
    `storage_ref`  VARCHAR(512) NOT NULL COMMENT '生成文件存储引用（不暴露给前端）',
    `size_bytes`   BIGINT       NULL COMMENT '文件大小（字节）',
    `sha256`       CHAR(64)     NULL COMMENT '摘要（重新下载一致性校验）',
    `generated_at` DATETIME(6)  NOT NULL COMMENT '生成时间（UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_book_file_book_format` (`book_id`, `format`),
    CONSTRAINT `fk_book_file_book` FOREIGN KEY (`book_id`) REFERENCES `book` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='书籍成果文件记录（EPUB/PDF）';

-- ============================================================================
-- 以下为「计划扩展」模型（后续里程碑 M2/M4 的目标设计，非首版、非已实现）。
-- 每张表说明其承载方式：事件记录 / 关联实体 / 聚合查询（不建表）。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 10. report 举报/审核事项 [计划扩展 M2]
-- 来源：FR-15（举报/审核队列）、G11（人工审核为主）、S8/E-AD1~E-AD3。
-- 承载方式：事件记录。「审核事项」= report 处于 pending/under_review 的行（审核
--           队列为按 status 过滤的视图），不单独建表，避免凑表。
-- 删除规则：举报及其处置默认保留（可追溯）；不物理删除，状态置 resolved/dismissed。
-- ---------------------------------------------------------------------------
CREATE TABLE `report` (
    `id`               VARCHAR(36)  NOT NULL COMMENT '举报唯一标识（UUID）',
    `reporter_id`      VARCHAR(36)  NOT NULL COMMENT '举报人（FK → user.id）',
    `reported_user_id` VARCHAR(36)  NULL COMMENT '被举报用户（FK → user.id；举报用户时非空）',
    `book_id`          VARCHAR(36)  NULL COMMENT '被举报内容/书籍（FK → book.id；举报内容时非空）',
    `reason`           VARCHAR(255) NOT NULL COMMENT '举报原因（用户填写）',
    `status`           VARCHAR(16)  NOT NULL DEFAULT 'pending' COMMENT '审核状态：pending/under_review/resolved/dismissed（pending/under_review 即审核队列）',
    `created_at`       DATETIME(6)  NOT NULL COMMENT '举报时间（UTC）',
    PRIMARY KEY (`id`),
    KEY `ix_report_reporter_id` (`reporter_id`),
    KEY `ix_report_status` (`status`),
    KEY `ix_report_reported_user` (`reported_user_id`),
    KEY `ix_report_book` (`book_id`),
    CONSTRAINT `fk_report_reporter` FOREIGN KEY (`reporter_id`) REFERENCES `user` (`id`),
    CONSTRAINT `fk_report_reported_user` FOREIGN KEY (`reported_user_id`) REFERENCES `user` (`id`),
    CONSTRAINT `fk_report_book` FOREIGN KEY (`book_id`) REFERENCES `book` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='举报/审核事项（审核队列为 status 过滤视图）';

-- ---------------------------------------------------------------------------
-- 11. disposition 处置记录 [计划扩展 M2]
-- 来源：FR-15（处理记录：谁、何时、做了什么）、G11（处置可追溯）。
-- 承载方式：事件记录（append-only）。一次审核可产生一条处置（或多次补充处置）。
-- ---------------------------------------------------------------------------
CREATE TABLE `disposition` (
    `id`         VARCHAR(36)  NOT NULL COMMENT '处置记录唯一标识（UUID）',
    `report_id`  VARCHAR(36)  NOT NULL COMMENT '被处置的举报（FK → report.id）',
    `actor_id`   VARCHAR(36)  NOT NULL COMMENT '处置管理员（FK → user.id）',
    `action`     VARCHAR(16)  NOT NULL COMMENT '处置动作：approve/reject/block/delete（通过/驳回/屏蔽/删除）',
    `note`       VARCHAR(512) NULL COMMENT '处置说明/理由',
    `created_at` DATETIME(6)  NOT NULL COMMENT '处置时间（UTC）',
    PRIMARY KEY (`id`),
    KEY `ix_disposition_report_id` (`report_id`),
    KEY `ix_disposition_actor_id` (`actor_id`),
    CONSTRAINT `fk_disposition_report` FOREIGN KEY (`report_id`) REFERENCES `report` (`id`),
    CONSTRAINT `fk_disposition_actor` FOREIGN KEY (`actor_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='审核处置记录（谁、何时、做了什么）';

-- ---------------------------------------------------------------------------
-- 12. audit_log 管理操作留痕（含私有内容访问）[计划扩展 M2]
-- 来源：FR-15（管理员查看私有文件须留痕）、NFR-03、E-AD3（无上下文访问拒绝并记录）。
-- 承载方式：事件记录（append-only）。target 为多态引用（target_type + target_id），
--           不设外键——留痕对象可能已被删除，且留痕不应阻断对象生命周期。
-- ---------------------------------------------------------------------------
CREATE TABLE `audit_log` (
    `id`          VARCHAR(36)  NOT NULL COMMENT '留痕唯一标识（UUID）',
    `actor_id`    VARCHAR(36)  NOT NULL COMMENT '操作者（FK → user.id，管理员）',
    `action`      VARCHAR(64)  NOT NULL COMMENT '动作（如 view_private_file / access_denied）',
    `target_type` VARCHAR(32)  NOT NULL COMMENT '目标类型（upload_file/book/report 等，多态，不设 FK）',
    `target_id`   VARCHAR(36)  NOT NULL COMMENT '目标标识',
    `detail`      VARCHAR(512) NULL COMMENT '附加说明（如审核上下文 report_id）',
    `created_at`  DATETIME(6)  NOT NULL COMMENT '发生时间（UTC）',
    PRIMARY KEY (`id`),
    KEY `ix_audit_log_actor` (`actor_id`),
    KEY `ix_audit_log_target` (`target_type`, `target_id`),
    CONSTRAINT `fk_audit_log_actor` FOREIGN KEY (`actor_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='管理操作留痕（含管理员查看私有内容；append-only，target 多态不设 FK）';

-- ---------------------------------------------------------------------------
-- 13. bookmark 书签 [计划扩展 M4]
-- 来源：FR-12（书签）、G3（站内阅读）。
-- 承载方式：关联实体（user × book × paragraph，多值，带备注）。
-- 说明：book_id 为直接父引用（书签列表/归属过滤），paragraph_id 为精确阅读锚点；
--       book_id 可由 paragraph→chapter→task→book 推导，此处保留为必要冗余。
-- ---------------------------------------------------------------------------
CREATE TABLE `bookmark` (
    `id`           VARCHAR(36)  NOT NULL COMMENT '书签唯一标识（UUID）',
    `user_id`      VARCHAR(36)  NOT NULL COMMENT '归属用户（FK → user.id）',
    `book_id`      VARCHAR(36)  NOT NULL COMMENT '书籍（FK → book.id）',
    `paragraph_id` VARCHAR(36)  NOT NULL COMMENT '书签所在段落（FK → paragraph.id）',
    `note`         VARCHAR(255) NULL COMMENT '书签备注',
    `created_at`   DATETIME(6)  NOT NULL COMMENT '添加时间（UTC）',
    PRIMARY KEY (`id`),
    KEY `ix_bookmark_user_book` (`user_id`, `book_id`),
    CONSTRAINT `fk_bookmark_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`),
    CONSTRAINT `fk_bookmark_book` FOREIGN KEY (`book_id`) REFERENCES `book` (`id`),
    CONSTRAINT `fk_bookmark_paragraph` FOREIGN KEY (`paragraph_id`) REFERENCES `paragraph` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='书签（FR-12，站内阅读）';

-- ---------------------------------------------------------------------------
-- 14. reading_progress 阅读位置/继续阅读 [计划扩展 M4]
-- 来源：FR-13（阅读位置）、P1（继续阅读，与任务进度是两回事）、G3。
-- 承载方式：关联实体（每人每书一行，upsert）。
-- ---------------------------------------------------------------------------
CREATE TABLE `reading_progress` (
    `id`           VARCHAR(36)  NOT NULL COMMENT '进度唯一标识（UUID）',
    `user_id`      VARCHAR(36)  NOT NULL COMMENT '归属用户（FK → user.id）',
    `book_id`      VARCHAR(36)  NOT NULL COMMENT '书籍（FK → book.id）',
    `paragraph_id` VARCHAR(36)  NOT NULL COMMENT '最后阅读到的段落（FK → paragraph.id）',
    `updated_at`   DATETIME(6)  NOT NULL COMMENT '最近阅读时间（UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_reading_progress_user_book` (`user_id`, `book_id`),
    CONSTRAINT `fk_reading_progress_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`),
    CONSTRAINT `fk_reading_progress_book` FOREIGN KEY (`book_id`) REFERENCES `book` (`id`),
    CONSTRAINT `fk_reading_progress_paragraph` FOREIGN KEY (`paragraph_id`) REFERENCES `paragraph` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='阅读位置/继续阅读（FR-13；每人每书一行）';

-- ============================================================================
-- 资源用量（FR-15「资源用量」）不单独建表，由聚合查询承载：
--   - 全量/单用户：文件数 + Σ upload_file.size_bytes、任务数按 task.status 分组、
--     成果文件 Σ book_file.size_bytes；
--   展示口径（按天/总量、是否缓存为汇总表）待确认，属「待确认策略」而非建表需求。
-- ============================================================================
