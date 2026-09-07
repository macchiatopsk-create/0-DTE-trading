"""Build Last Wall HQ with the v10 visual/presence overlay. Source snapshot remains private and encrypted."""
from pathlib import Path
import shutil, sys

src = Path(__file__).resolve().parent
out = Path(sys.argv[1] if len(sys.argv) > 1 else '_site') / 'hq'
out.mkdir(parents=True, exist_ok=True)
html = (src / 'index.html').read_text(encoding='utf-8')
html = html.replace("script-src 'unsafe-inline'", "script-src 'self' 'unsafe-inline'")
html = html.replace("style-src 'unsafe-inline'", "style-src 'self' 'unsafe-inline'")
html = html.replace("connect-src 'self';", "connect-src 'self' https://nutfgkxaddvidqrcnvyj.supabase.co;")
head = '<link rel="manifest" href="./manifest.webmanifest?v=10"><link rel="icon" href="./icon-192.png?v=10" sizes="192x192" type="image/png"><link rel="apple-touch-icon" href="./icon-180.png?v=10"><link rel="stylesheet" href="./v10.css?v=10">'
if 'v10.css?v=10' not in html:
    html = html.replace('</head>', head + '</head>')
scripts = '<script src="./live.js?v=10"></script><script src="./presence-v10.js?v=10"></script>'
if 'presence-v10.js?v=10' not in html:
    html = html.replace('</body>', scripts + '</body>')
if html.count('presence-v10.js?v=10') != 1:
    raise ValueError('v10 presence extension must load exactly once')
(out / 'index.html').write_text(html, encoding='utf-8')
for name in ('office-art.avif','status.enc.json','live.js','v10.css','presence-v10.js','manifest.webmanifest','icon-180.png','icon-192.png'):
    shutil.copyfile(src / name, out / name)
print('HQ v10 built:', out)
