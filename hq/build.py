"""Build Last Wall HQ with the v11 portrait-office interface. Private snapshot remains encrypted."""
from pathlib import Path
import shutil, sys

src = Path(__file__).resolve().parent
out = Path(sys.argv[1] if len(sys.argv) > 1 else '_site') / 'hq'
out.mkdir(parents=True, exist_ok=True)
html = (src / 'index.html').read_text(encoding='utf-8')
html = html.replace("script-src 'unsafe-inline'", "script-src 'self' 'unsafe-inline'")
html = html.replace("style-src 'unsafe-inline'", "style-src 'self' 'unsafe-inline'")
html = html.replace("connect-src 'self';", "connect-src 'self' https://nutfgkxaddvidqrcnvyj.supabase.co;")
head = '<link rel="manifest" href="./manifest.webmanifest?v=11"><link rel="icon" href="./icon-192.png?v=11" sizes="192x192" type="image/png"><link rel="apple-touch-icon" href="./icon-180.png?v=11"><link rel="stylesheet" href="./v10.css?v=11"><link rel="stylesheet" href="./v11.css?v=11">'
if 'v11.css?v=11' not in html:
    html = html.replace('</head>', head + '</head>')
scripts = '<script src="./live.js?v=11"></script><script src="./presence-v10.js?v=11"></script>'
if 'presence-v10.js?v=11' not in html:
    html = html.replace('</body>', scripts + '</body>')
if html.count('presence-v10.js?v=11') != 1:
    raise ValueError('v11 presence extension must load exactly once')
(out / 'index.html').write_text(html, encoding='utf-8')
for name in ('office-art.avif','status.enc.json','live.js','v10.css','v11.css','presence-v10.js','manifest.webmanifest','icon-180.png','icon-192.png'):
    shutil.copyfile(src / name, out / name)
print('HQ v11 built:', out)
