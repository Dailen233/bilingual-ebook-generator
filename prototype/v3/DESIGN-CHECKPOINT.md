# v3 设计检查点（2026-09-25）

## 1. 参考网站分析（仅借鉴方法，不复制素材/文案，G12）

### Lulu（自出版平台，lulu.com）
- 观察到的设计方法：
  - **浅色干净底 + 大留白**：产品/书封卡片是视觉主角，导航极简，一屏一个信息焦点。
  - **流程化表达**：把"出版一本书"拆成 3–4 步图示（上传稿件 → 设计封面 → 出版），降低理解成本。
  - **模板/成品画廊**：直接展示成品样书，用户"先看结果再操作"。
  - **强 CTA 单一化**：每个区块只有一个主按钮，次要动作用文字链接。
- 借鉴到 v3：
  1. 首页保持"成品对照书卡"为 Hero 主角（v2 已有），压缩文字区块密度，强化留白与层级。
  2. "上传 → 选语言 → 在线阅读/下载"三步流程独立成区块并编号图示。
  3. 语言对矩阵（6 语 × 15 组合 × 30 方向，G5）用可点击的"语言对卡片"展示，替代纯表格。
  4. 每区块只保留一个主 CTA，次要动作降级为 ghost/文字链接。

### Paperturn（PDF → HTML5 翻页书）
- 观察到的设计方法：
  - **阅读即产品**：首页核心是阅读器 demo（3D 翻书），而非功能列表。
  - **阅读控制外置**：翻页/目录/缩放等控制集中在顶部窄条，正文区最大化。
  - **进度可感知**：章节/页码进度常驻可见。
  - **响应式降级**：窄屏从"双页摊开"降级为"单页"，而非横向挤压。
- 借鉴到 v3：
  1. 阅读页顶部控制条（书名 + 视图切换 + 字号 + 进度），正文区最大化（v2 已有雏形，v3 增加视图/字号控制）。
  2. 双语对照支持**并排 / 上下堆叠**两种视图：桌面默认并排，手机默认堆叠（v2 只做了 CSS 降级，v3 做显式切换 + 记忆）。
  3. 段落滚动同步（并排视图下原文/译文对齐高亮），模拟"翻页对齐"体验。
  4. 阅读进度（第 n/m 段）常驻控制条。

## 2. v3 页面方案（保留 v2 全部 12 个页面与完整流程，不缩减范围）

| 页面 | v3 改动 |
|---|---|
| index.html | 重排：Hero 对照书卡（微交互）+ 三步流程 + 语言对矩阵卡片 + 功能卡 + 单 CTA 纪律 |
| new-task.html | 上传/选语言/提交；识别修正交互保留；提交后进入任务详情 |
| dashboard.html | 统计 + 进行中任务（可见进度，G4/P1）+ 历史入口 |
| task-detail.html | 进度条 + 阶段时间线 + 结果/失败两态；模拟进度推进 |
| reader.html | **核心升级**：并排/堆叠视图切换、字号调节、段落同步高亮、进度计数；移动端默认堆叠（G10） |
| library.html | 书库列表 + 状态筛选；空态；重下载入口（G3） |
| login.html / register.html | 分屏登录/注册，保留模拟态声明 |
| admin-login.html | 独立入口声明（G11），服务端校验说明保留 |
| admin.html / admin-tasks.html / admin-reviews.html | 管理端深色体系微调；审核留痕交互保留（G11/P13 假设） |

**v3 视觉基线（增量，不重写 v2 类名）**
- 新增 design tokens：阴影 3 级、字号阶梯（--fs-*）、动效时长、聚焦环。
- 卡片/按钮：更克制的圆角与阴影分层；hover 微位移（2px）；聚焦环统一。
- 首页语言对矩阵：`.lang-grid` / `.lang-pair`（新增类）。
- 阅读器：`.reader-tools`、`.view-toggle`、`.font-ctl`、同步高亮 `.hl`（新增类）。
- 进度环（任务详情）：`.ring`（conic-gradient 实现）。
- 动效纪律：仅 transform/opacity，≤200ms，尊重 `prefers-reduced-motion`。

**PWA（G10 可安装）**
- `manifest.webmanifest` + `sw.js`（shell 缓存，cache-first + 网络回退）+ 64/512 图标。
- 每页 head 注入 manifest 链接；`app.js` 注入 SW 注册（生产域名才启用逻辑保留注释）。

## 3. 分批实施计划

| 批 | 内容 | 文件 |
|---|---|---|
| 1 | 视觉基线：styles.css tokens/组件增强；app.js 扩展（阅读偏好、进度环工具）；PWA manifest + sw.js + 图标；12 页注入 manifest | styles.css, app.js, manifest.webmanifest, sw.js, icons/*, *.html(head) |
| 2 | 首页重排 | index.html |
| 3 | 核心流程页：new-task / dashboard / task-detail | 3 个 html |
| 4 | 阅读器升级：reader.html（视图/字号/同步/进度）+ library.html | 2 个 html |
| 5 | 认证 + 管理端微调：login / register / admin-login / admin / admin-tasks / admin-reviews | 6 个 html |

每批完成即验证：浏览器可打开（无控制台报错）、类名兼容 v2（不删改已有类）、流程闭环（登录→创建→进度→阅读→书库→管理端）。

## 5. 批次完成记录（2026-09-25 全部完成）

| 批 | 状态 | 交付 |
|---|---|---|
| 1 | ✅ | styles.css（521 行，v3 组件全量）、app.js（V3 命名空间 + SW 注册）、manifest.webmanifest、sw.js、icons/（192/512）、12 页注入 manifest |
| 2 | ✅ | index.html：Hero 书卡微动效、语言对矩阵（15 组合）、三步流程卡片化、单 CTA 纪律、顶栏 PWA 安装按钮 |
| 3 | ✅ | new-task.html 阶段指示条；task-detail.html 进度环 + 四阶段时间线；dashboard.html 统计卡 hover |
| 4 | ✅ | reader.html 视图切换/字号档位/段落联动高亮/进度（偏好持久化）；library.html 搜索 + 语言筛选 + 双空态 |
| 5 | ✅ | login/register 表单校验错误态；admin 卡 hover；admin-tasks 状态筛选 + 无匹配提示；admin-login 校验 |

**最终验证（自动脚本）**：12 页 HTML 标签配对 ✅；全部内联 JS `node --check` ✅；本地引用（href/src）文件存在 ✅；CSS 自定义变量无未定义引用 ✅；manifest JSON ✅；sw.js/app.js 语法 ✅。

**手工验证建议（需浏览器）**：
1. 登录 → 创建任务（示例文件选 high-conf）→ 任务详情观察进度环/阶段点亮 → 完成进入书库
2. 阅读页：并排/上下切换、字号 A−/A＋、点击段落联动高亮，刷新后偏好保持
3. 书库：按书名搜索、按语言筛选、清除筛选
4. 管理端：独立登录 → 任务表状态筛选（选"失败"应剩 2 行）
5. 断网测试（DevTools Offline）：已访问页可离线打开，导航回退到 index
6. 注意：PWA 安装与 SW 需在 http(s) 下（如 `python3 -m http.server`）才生效，file:// 下静默跳过

## 4. 约束备忘
- 不删 v2 任何页面/流程；v3 是 v2 的视觉 + 交互升级层。
- 所有模拟能力保留 sim-bar/sim-tag 声明（登录、权限、生成结果、审核均为模拟）。
- 不复制 Lulu/Paperturn 素材与文案。
- 已读文件（不再重读）：styles.css、app.js、admin-login.html、admin-reviews.html、README.md。
