"""将霞鹜文楷子集化到登录页欢迎语与点睛文字。
输出: prototype/v4/assets/fonts/lxgw-wenkai-login.woff2
许可: SIL OFL 1.1（官方 OFL.txt 已存 assets/licenses/OFL-LXGWWenKai.txt）"""
import pathlib, subprocess, sys
from fontTools.ttLib import TTFont

KICKER = '双语阅读伴侣'
WELCOME = '让每一页，都有另一门语言陪伴。'
TEXT = KICKER + WELCOME + '登录'
HERE = pathlib.Path(__file__).resolve().parent
FONTS = HERE / 'fonts'
FONTS.mkdir(exist_ok=True)
textfile = HERE / 'login-chars.txt'
textfile.write_text(TEXT + '\n', encoding='utf-8')

src = '/tmp/gf/LXGWWenKai-Regular.ttf'
f = TTFont(src)
cmap = f.getBestCmap()
missing = [c for c in TEXT if ord(c) not in cmap]
assert not missing, missing
dest = FONTS / 'lxgw-wenkai-login.woff2'
r = subprocess.run([sys.executable, '-m', 'fontTools.subset', src,
                    '--text-file=' + str(textfile), '--flavor=woff2',
                    '--no-hinting', '--desubroutinize',
                    '--output-file=' + str(dest)],
                   capture_output=True, text=True)
print('lxgw-wenkai-login ->', dest.stat().st_size if dest.exists() else 'FAIL', 'rc', r.returncode, 'missing', missing)
