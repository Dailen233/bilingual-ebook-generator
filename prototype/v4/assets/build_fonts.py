"""从本地 Noto CJK（OFL）生成页面子集字体 woff2。
用法：python3 assets/build_fonts.py
"""
import re, pathlib, subprocess, sys
from fontTools.ttLib import TTCollection

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'assets'
FONTS = ASSETS / 'fonts'
FONTS.mkdir(exist_ok=True)

html = (ROOT / 'index.html').read_text(encoding='utf-8')
text = re.sub(r'<[^>]+>', '', html)
chars = set(text)
chars |= set('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
chars |= set('，。、；：？！·—…《》「」（）/.,;:?!-—"\' ')
charset = ''.join(sorted(chars))
(ASSETS / 'subset-chars.txt').write_text(charset + '\n', encoding='utf-8')
print('charset size:', len(charset))

JOBS = [
    ('/usr/share/fonts/opentype/noto/NotoSerifCJK-SemiBold.ttc', 'Noto Serif CJK SC', 'noto-serif-sc-semibold'),
    ('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 'Noto Sans CJK SC', 'noto-sans-sc-regular'),
]

for path, want, out in JOBS:
    ttc = TTCollection(path)
    idx = None
    for i, f in enumerate(ttc.fonts):
        name = f['name'].getDebugName(1)
        if name and name.startswith(want):
            idx = i
            break
    if idx is None:
        print('MISS', want, file=sys.stderr)
        continue
    dest = FONTS / (out + '.woff2')
    cmd = [sys.executable, '-m', 'fontTools.subset', path,
           '--font-number=%d' % idx,
           '--text-file=' + str(ASSETS / 'subset-chars.txt'),
           '--flavor=woff2',
           '--output-file=' + str(dest),
           '--layout-features=*', '--no-hinting', '--desubroutinize']
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(out, '->', dest.stat().st_size if dest.exists() else 'FAIL', r.returncode)
    if r.returncode != 0:
        print(r.stderr[-500:], file=sys.stderr)
