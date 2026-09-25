"""将 Ma Shan Zheng / Zhi Mang Xing 子集化到标题固定文案字符。
输出: prototype/v4/assets/fonts/{mashanzheng,zhimangxing}-title.woff2
许可: SIL OFL 1.1（官方 OFL.txt 已存 assets/licenses/）
"""
import pathlib, subprocess, sys
from fontTools.ttLib import TTFont

TITLE = '一纸书文，两境言说。'
HERE = pathlib.Path(__file__).resolve().parent
FONTS = HERE / 'fonts'
FONTS.mkdir(exist_ok=True)
textfile = HERE / 'title-chars.txt'
textfile.write_text(TITLE + '\n', encoding='utf-8')

JOBS = [
    ('/tmp/gf/MaShanZheng-Regular.ttf', 'mashanzheng-title'),
    ('/tmp/gf/ZhiMangXing-Regular.ttf', 'zhimangxing-title'),
]
for src, out in JOBS:
    f = TTFont(src)
    cmap = f.getBestCmap()
    missing = [c for c in TITLE if ord(c) not in cmap]
    assert not missing, (out, missing)
    dest = FONTS / (out + '.woff2')
    r = subprocess.run([sys.executable, '-m', 'fontTools.subset', src,
                        '--text-file=' + str(textfile), '--flavor=woff2',
                        '--no-hinting', '--desubroutinize',
                        '--output-file=' + str(dest)],
                       capture_output=True, text=True)
    print(out, '->', dest.stat().st_size if dest.exists() else 'FAIL', r.returncode)
