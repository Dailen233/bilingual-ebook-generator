"""字标字体子集：霞鹜文楷（LXGW WenKai）与马善政毛笔楷书（Ma Shan Zheng）。
许可均为 SIL OFL 1.1；霞鹜文楷 OFL 附加许可明确允许子集化为 woff2 用于网页字体分发。
输出: assets/fonts/{lxgw-wenkai-mark,mashanzheng-mark}.woff2
"""
import pathlib, subprocess, sys
from fontTools.ttLib import TTFont

CHARS = '译伴BilingualPress'
HERE = pathlib.Path(__file__).resolve().parent
FONTS = HERE / 'fonts'
FONTS.mkdir(exist_ok=True)
tf = HERE / 'wordmark-chars.txt'
tf.write_text(CHARS + '\n', encoding='utf-8')

JOBS = [('/tmp/gf/LXGWWenKai-Regular.ttf', 'lxgw-wenkai-mark'),
        ('/tmp/gf/MaShanZheng-Regular.ttf', 'mashanzheng-mark')]

for src, out in JOBS:
    f = TTFont(src)
    cmap = f.getBestCmap()
    for c in '译伴':
        print(out, c, 'covered' if ord(c) in cmap else 'MISSING')
    dest = FONTS / (out + '.woff2')
    r = subprocess.run([sys.executable, '-m', 'fontTools.subset', src,
                        '--text-file=' + str(tf), '--flavor=woff2',
                        '--layout-features=*', '--no-hinting', '--desubroutinize',
                        '--output-file=' + str(dest)], capture_output=True, text=True)
    print('  ->', dest.stat().st_size if dest.exists() else 'FAIL', r.returncode)
