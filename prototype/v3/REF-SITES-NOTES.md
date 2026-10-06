# 参考网站实际观察记录（2026-09-25，替代此前 Lulu/Paperturn 推断）

方法：web_fetch 抓页面文本 + 无头 Chrome 截图（桌面 1440px / 手机 390px UA）。
截图位于 /tmp/refshots/，共 8 张，文件名与网站一一对应（已逐张核对）：

- reedsy_desktop.png / reedsy_mobile.png → Reedsy Studio
- bookfusion_desktop.png / bookfusion_mobile.png → BookFusion
- immerse_desktop.png / immerse_mobile.png → 沉浸式翻译
- readwise_desktop.png / readwise_mobile.png → Readwise

局限：只截首屏（非整页长截图）；沉浸式翻译官网对 web_fetch 返回 403，headless Chrome 可正常渲染。

## 1. Reedsy Studio（桌面+手机均查看）
- 深色蓝绿底，Hero 内嵌真实编辑器截图（章节侧栏 + 正文 + 右侧统计面板）。
- 衬线体大标题「Every writer needs a Studio」，副标 plan / draft / edit / typeset。
- 滚动叙事（全文抓取）：词典式定义 → Write → Plan → Revise → Export → 评价 → FAQ，CTA 重复。
- 成品书视觉：用「编辑器排版预览」表达成品，而非封面图。
- 手机首屏：编辑器截图压缩成窄条，标题换行，CTA 并排。

## 2. BookFusion（桌面+手机均查看）
- 深蓝星空插画风，主标题「Make the Most of Your Reading!」，副标强调多设备、任意时间地点阅读。
- Hero 下嵌真实 App 书架截图：封面卡 + Continue 续读按钮、统计环。
- 叙事（全文）：Hero → 评价墙 → 三场景 → 功能网格 → 下载 CTA。手机同构，插画环绕标题。
- 未展示双语对照能力。

## 3. 沉浸式翻译（immersetranslate.com，桌面+手机均查看）
- 中文站，浅蓝渐变底。主标题「沉浸式翻译：AI 网页翻译、PDF 翻译、视频字幕翻译」。
- 副标：免费双语对照 AI 翻译工具，网页/PDF（保留排版）/视频字幕/图片翻译一体；内置 20+ 翻译引擎，支持 100+ 语言互译，适配 Chrome/Edge/Safari 及 iOS/Android。
- CTA：「安装到 Chrome」+「手机 App」下拉；下方平台下载矩阵（浏览器扩展/手机平板/桌面端）。
- 手机首屏：导航折叠为「文本/文档/视频/图片」四个 Tab，CTA 变为单按钮「下载」。
- 借鉴点：引擎/语言数量是信任要素；多端矩阵化展示。

## 4. Readwise（桌面+手机均查看）
- 暖橙渐变底，衬线大标题「Get the most out of what you read」，副标强调回顾高亮与批注。
- Hero 内嵌桌面 Library 书架截图 + 手机阅读卡片（封面、881 条高亮计数）。
- 叙事：Hero → 功能区块（回顾/导出/同步）→ 评价 → CTA。单 CTA「Get Started For Free」。
- 借鉴点：高亮/批注作为核心价值主张前置；产品截图即首屏主视觉。

## 对 v3 的借鉴（只借鉴方法，不复制素材/文案，G12）
- 首屏主视觉用产品界面截图（而非装饰插画），与「对照阅读」核心能力直接相关。
- 单 CTA 纪律：每区块一个主按钮；次要动作降级为文字链接。
- 语言/引擎数量是信任要素：六语 30 方向语言对矩阵要醒目呈现。
- 手机首屏降级：导航折叠、CTA 收敛为单按钮、截图压缩为窄条。
