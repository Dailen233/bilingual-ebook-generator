# v4 资源来源与许可

## 字体（本地自托管，页面不请求任何境外资源）

| 文件 | 源字体 | 许可 | 用途 |
|---|---|---|---|
| `assets/fonts/lxgw-wenkai-mark.woff2` | 霞鹜文楷 LXGW WenKai Regular | SIL OFL 1.1 | 字标方案一（「译伴」+ 拉丁副名子集，约 2.4 KB） |
| `assets/fonts/mashanzheng-mark.woff2` | Ma Shan Zheng（马善政毛笔楷书） | SIL OFL 1.1 | 字标方案二子集，约 3.0 KB |
| `assets/fonts/mashanzheng-title.woff2` | Ma Shan Zheng | SIL OFL 1.1 | 主标题「一纸书文／两境言说」子集 |
| `assets/fonts/zhimangxing-title.woff2` | Zhi Mang Xing（志莽行书） | SIL OFL 1.1 | 主标题对照方案 |
| `assets/fonts/noto-serif-sc-semibold.woff2` | Noto Serif CJK SC SemiBold | SIL OFL 1.1 | 界面衬线（含字标回退） |
| `assets/fonts/noto-sans-sc-regular.woff2` | Noto Sans CJK SC Regular | SIL OFL 1.1 | 界面正文 |

### 官方来源

- 霞鹜文楷 LXGW WenKai：https://github.com/lxgw/LxgwWenKai
  - 下载：releases `v1.520/LXGWWenKai-Regular.ttf`
  - 许可：`assets/licenses/OFL-LXGWWenKai.txt`
  - 附加许可（重要）：OFL 的 ADDITIONAL PERMISSION 明确允许**子集化或转换为 WOFF/WOFF2
    用于网页字体分发**，条件是不以可安装桌面字体的形式再分发。本项目仅自托管 woff2 子集，符合该条件。
- Ma Shan Zheng：https://github.com/google/fonts/tree/main/ofl/mashanzheng
  - 许可：`assets/licenses/OFL-MaShanZheng.txt`
- Zhi Mang Xing：https://github.com/google/fonts/tree/main/ofl/zhimangxing
  - 许可：`assets/licenses/OFL-ZhiMangXing.txt`
- Noto CJK：https://github.com/notofonts/noto-cjk
  - 许可全文：https://scripts.sil.org/OFL

### 字形覆盖核对（fontTools cmap 实测）

- 霞鹜文楷：`译` `伴` 均在 cmap 中（另有拉丁 `BilingualPress`）。
- Ma Shan Zheng：`译` `伴` 均在 cmap 中；标题 8 字 `一纸书文两境言说` 全覆盖，无缺字。
- 页面另有运行时检查：`document.fonts.check` 逐字验证 + canvas 位图指纹与纯回退栈比对，
  两项都通过才判定为「由目标字体绘制」（避免中文同宽导致的宽度误判）。

### 子集生成

- 字标：`python3 assets/build_wordmark_fonts.py`（输出 `wordmark-chars.txt`）
- 标题：`python3 assets/build_title_fonts.py`（输出 `title-chars.txt`）
- 界面：`python3 assets/build_fonts.py`（输出 `subset-chars.txt`）
- 依赖：`pip install fonttools brotli`

### 回退策略

字标与标题的 CSS 字体栈依次为：子集字体 → `BP Serif SC`（Noto Serif CJK SC）→ 系统衬线。
字体加载失败时字形完整可读、不出现缺字方框，实验页设有专门的回退演示区块。

## 图像与插画

- 未使用任何位图、摄影或第三方插画；所有视觉元素由 CSS 绘制。

## 文案

- 双语示例（英文原文与中文译文）为本原型自编的占位示例，非引用他人作品。

## 参考的设计方法（未复制其素材、图片、品牌或文案）

- Reedsy Studio https://reedsy.com/studio/ —— 首屏结构：短标题 + 一句副标 + CTA，
  下方以产品成品画面作为视觉主角。
