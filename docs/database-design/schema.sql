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
--      （models/types.py 的 UTCDateTime），不在 SQL 层用 CURRENT_TIMESTAMP，
--      以免依赖 MySQL session time_zone；
--   4) 密码仅存 bcrypt 哈希；user_session 只存 JWT 的 jti，不存原始 JWT；
--   5) 已验收迁移 0001(user)、0002(user_session) 不含列 COMMENT；本验证稿按
--      老师检查要求补齐 COMMENT，作为后续新增迁移时的规范，不改写既有迁移。
--
-- 实现状态标记（配合 docs/database-design/README.md）：
--   [已实现]     user / user_session（对应 alembic 0001/0002）
--   [本次拟定]   upload_file / task / chapter / paragraph / translation_unit
--                / book / book_file（上传方案仍在 yiban-api 分支评审，见 §待决）
--   [设计建议]   audit_log（管理员查看私有内容留痕，待确认）
-- ============================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- 1. user 用户账号 [已实现 → alembic 0001]
-- 来源：需求 FR-14（注册/登录/属主）、G11（角色服务端校验）。
-- ---------------------------------------------------------------------------
CREATE TABLE `user` (
    `id`            VARCHAR(36)  NOT NULL COMMENT '用户唯一标识（UUID 字符串，服务端生成）',
    `email`         VARCHAR(255) NOT NULL COMMENT '登录邮箱（入库前 strip+lower 规范化，唯一）',
    `password_hash` VARCHAR(255) NOT NULL COMMENT '密码哈希（bcrypt，绝不明文）',
    `display_name`  VARCHAR(100) NOT NULL COMMENT '显示名/昵称',
    `role`          VARCHAR(16)  NOT NULL DEFAULT 'user' COMMENT '角色：user/admin（应用层校验合法值）',
    `created_at`    DATETIME(6)  NOT NULL COMMENT '注册时间（无时区 UTC）',
    `updated_at`    DATETIME(6)  NOT NULL COMMENT '更新时间（无时区 UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_user_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户账号（含管理员角色）';

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
-- 3. upload_file 上传文件 [本次拟定；上传方案待评审]
-- 来源：FR-01（上传/校验）、NFR-03（文件私有 + 访问控制）、DB 逻辑草案 §3.2。
-- ---------------------------------------------------------------------------
CREATE TABLE `upload_file` (
    `id`            VARCHAR(36)  NOT NULL COMMENT '文件记录唯一标识（UUID）',
    `owner_id`      VARCHAR(36)  NOT NULL COMMENT '属主（FK → user.id；上传时服务端写入=当前用户）',
    `original_name` VARCHAR(255) NOT NULL COMMENT '原始文件名（展示用，不参与唯一性）',
    `storage_ref`   VARCHAR(512) NOT NULL COMMENT '存储引用（对象存储键/磁盘路径；不暴露给前端）',
    `ext`           VARCHAR(16)  NOT NULL COMMENT '扩展名（首版仅 txt；epub/pdf 输入为后续扩展）',
    `size_bytes`    BIGINT UNSIGNED NOT NULL COMMENT '文件大小（字节）',
    `sha256`        CHAR(64)     NULL COMMENT '内容摘要（校验/去重，64 位十六进制）',
    `created_at`    DATETIME(6)  NOT NULL COMMENT '上传时间（UTC）',
    PRIMARY KEY (`id`),
    KEY `ix_upload_file_owner_id` (`owner_id`),
    CONSTRAINT `fk_upload_file_user` FOREIGN KEY (`owner_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='上传文件（私有，属主隔离）';

-- ---------------------------------------------------------------------------
-- 4. task 任务 + 配置快照 [本次拟定]
-- 来源：FR-03/05/09/16、状态机草案（status/stage/counters）、DB 逻辑草案 §3.3。
-- ---------------------------------------------------------------------------
CREATE TABLE `task` (
    `id`                VARCHAR(36)  NOT NULL COMMENT '任务唯一标识（UUID）',
    `owner_id`          VARCHAR(36)  NOT NULL COMMENT '属主（服务端派生自 upload_file.owner_id，创建时校验一致）',
    `file_id`           VARCHAR(36)  NOT NULL COMMENT '来源文件（FK → upload_file.id）',
    `retry_of_task_id`  VARCHAR(36)  NULL COMMENT '重试来源：指向被重试的旧 task；唯一，保证一个 failed task 最多一个直接子任务',
    `src_lang`          VARCHAR(16)  NOT NULL COMMENT '原文语言（首版 en）',
    `tgt_lang`          VARCHAR(16)  NOT NULL COMMENT '目标语言（首版 zh）',
    `svc_key`           VARCHAR(64)  NOT NULL COMMENT '翻译服务标识（快照，FR-16，新任务必填）',
    `svc_name`          VARCHAR(128) NULL COMMENT '翻译服务名称（快照，展示）',
    `model_key`         VARCHAR(64)  NULL COMMENT '模型标识（快照；仅服务提供模型参数时非空）',
    `model_name`        VARCHAR(128) NULL COMMENT '模型名称（快照，展示）',
    `style_key`         VARCHAR(64)  NOT NULL COMMENT '翻译风格标识（快照，新任务必填）',
    `style_name`        VARCHAR(128) NULL COMMENT '翻译风格名称（快照，展示）',
    `status`            VARCHAR(16)  NOT NULL DEFAULT 'pending' COMMENT '任务状态：pending/running/done/failed（done/failed 为不可变终态）',
    `stage`             VARCHAR(16)  NULL COMMENT '处理阶段：extract/align/translate/layout/export（是否持久化待定）',
    `fail_reason`       VARCHAR(255) NULL COMMENT '失败原因（提取/切分/翻译/导出），仅 status=failed 时非空',
    `total_units`       INT          NOT NULL DEFAULT 0 COMMENT '翻译单元总数（align 阶段确定，此后不变）',
    `done_units`        INT          NOT NULL DEFAULT 0 COMMENT '已终态单元数（translated + failed）',
    `failed_units`      INT          NOT NULL DEFAULT 0 COMMENT '失败单元数（保留原文，结果页展示）',
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
    CONSTRAINT `fk_task_retry`  FOREIGN KEY (`retry_of_task_id`) REFERENCES `task` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='翻译任务（含配置快照与进度计数）';

-- ---------------------------------------------------------------------------
-- 5. chapter 章节 [本次拟定]
-- 来源：FR-02（正文提取/章节结构）、DB 逻辑草案 §3.4。
-- ---------------------------------------------------------------------------
CREATE TABLE `chapter` (
    `id`      VARCHAR(36)  NOT NULL COMMENT '章节唯一标识（UUID）',
    `task_id` VARCHAR(36)  NOT NULL COMMENT '归属任务（FK → task.id）',
    `seq_no`  INT          NOT NULL COMMENT '章节在全书内的顺序（1 起）',
    `title`   VARCHAR(255) NULL COMMENT '章节标题（如 Chapter 1）；无标题纯文本归入 title 为空的默认章节',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_chapter_task_seq` (`task_id`, `seq_no`),
    CONSTRAINT `fk_chapter_task` FOREIGN KEY (`task_id`) REFERENCES `task` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='正文提取出的章节（保序）';

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
    CONSTRAINT `fk_paragraph_chapter` FOREIGN KEY (`chapter_id`) REFERENCES `chapter` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='原文段落（还原段落结构）';

-- ---------------------------------------------------------------------------
-- 7. translation_unit 翻译单元 [本次拟定]
-- 来源：FR-04（切分）/FR-05（失败回退原文）、DB 逻辑草案 §3.6。
-- ---------------------------------------------------------------------------
CREATE TABLE `translation_unit` (
    `id`           VARCHAR(36) NOT NULL COMMENT '单元唯一标识（UUID）',
    `paragraph_id` VARCHAR(36) NOT NULL COMMENT '归属段落（FK → paragraph.id）',
    `seq_no`       INT         NOT NULL COMMENT '单元在段落内的顺序（1 起，失败不使邻位错序）',
    `source_text`  TEXT        NOT NULL COMMENT '单元原文（句子或整段）',
    `target_text`  TEXT        NULL COMMENT '译文；失败单元回退为原文（保留原文）',
    `status`       VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '单元状态：pending/translated/failed（条件更新，不回退）',
    `retry_count`  INT         NOT NULL DEFAULT 0 COMMENT '重试次数（达上限置 failed）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_unit_paragraph_seq` (`paragraph_id`, `seq_no`),
    CONSTRAINT `fk_unit_paragraph` FOREIGN KEY (`paragraph_id`) REFERENCES `paragraph` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='翻译单元（句子或段落级，含失败状态）';

-- ---------------------------------------------------------------------------
-- 8. book 书籍成果 [本次拟定]
-- 来源：FR-07/09/10（成果/幂等入库）、DB 逻辑草案 §3.7。
-- ---------------------------------------------------------------------------
CREATE TABLE `book` (
    `id`           VARCHAR(36)  NOT NULL COMMENT '书唯一标识（UUID；可由 task 幂等派生，见 uk_book_task_id）',
    `owner_id`     VARCHAR(36)  NOT NULL COMMENT '属主（服务端派生自 task.owner_id，写入同事务一致）',
    `task_id`      VARCHAR(36)  NOT NULL COMMENT '来源任务（唯一 = 幂等入库，一个任务最多一本书）',
    `name`         VARCHAR(255) NOT NULL COMMENT '书名快照（无唯一约束，同名不同配置可分别成书）',
    `src_lang`     VARCHAR(16)  NOT NULL COMMENT '原文语言快照',
    `tgt_lang`     VARCHAR(16)  NOT NULL COMMENT '目标语言快照',
    `svc_name`     VARCHAR(128) NULL COMMENT '翻译服务名称快照（展示）',
    `model_name`   VARCHAR(128) NULL COMMENT '模型名称快照（展示）',
    `style_name`   VARCHAR(128) NULL COMMENT '风格名称快照（展示）',
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
    `size_bytes`   BIGINT UNSIGNED NULL COMMENT '文件大小（字节）',
    `sha256`       CHAR(64)     NULL COMMENT '摘要（重新下载一致性校验）',
    `generated_at` DATETIME(6)  NOT NULL COMMENT '生成时间（UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_book_file_book_format` (`book_id`, `format`),
    CONSTRAINT `fk_book_file_book` FOREIGN KEY (`book_id`) REFERENCES `book` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='书籍成果文件记录（EPUB/PDF）';

-- ============================================================================
-- 10. audit_log 操作留痕 [设计建议，待确认]
-- 来源：NFR-03/G11（管理员查看私有文件内容须条件 + 留痕）、FR-15（M2）。
-- 说明：首版管理端仅「任务/失败只读查看」不强制此表；本表为「管理员查看用户
--      私有内容」场景的留痕设计建议，是否纳入首版由用户确认。
-- ============================================================================
-- CREATE TABLE `audit_log` (
--     `id`         VARCHAR(36)  NOT NULL COMMENT '留痕唯一标识（UUID）',
--     `actor_id`   VARCHAR(36)  NOT NULL COMMENT '操作者（FK → user.id，管理员）',
--     `action`     VARCHAR(64)  NOT NULL COMMENT '动作（如 view_private_file）',
--     `target_type`VARCHAR(32)  NOT NULL COMMENT '目标类型（upload_file/book 等）',
--     `target_id`  VARCHAR(36)  NOT NULL COMMENT '目标标识',
--     `detail`     VARCHAR(512) NULL COMMENT '附加说明',
--     `created_at` DATETIME(6)  NOT NULL COMMENT '发生时间（UTC）',
--     PRIMARY KEY (`id`),
--     KEY `ix_audit_log_actor` (`actor_id`),
--     KEY `ix_audit_log_target` (`target_type`, `target_id`)
-- ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='管理操作留痕（设计建议）';
