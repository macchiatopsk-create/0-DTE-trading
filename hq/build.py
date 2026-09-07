"""Build Last Wall HQ v12. Private snapshot remains encrypted; UI is vector/CSS based."""
from pathlib import Path
import shutil, sys

src = Path(__file__).resolve().parent
out = Path(sys.argv[1] if len(sys.argv) > 1 else '_site') / 'hq'
out.mkdir(parents=True, exist_ok=True)
html = (src / 'index.html').read_text(encoding='utf-8')
html = html.replace("script-src 'unsafe-inline'", "script-src 'self' 'unsafe-inline'")
html = html.replace("style-src 'unsafe-inline'", "style-src 'self' 'unsafe-inline'")
html = html.replace("connect-src 'self';", "connect-src 'self' https://nutfgkxaddvidqrcnvyj.supabase.co;")
head = '<link rel="manifest" href="./manifest.webmanifest?v=12"><link rel="icon" href="./icon-192.png?v=12" sizes="192x192" type="image/png"><link rel="apple-touch-icon" href="./icon-180.png?v=12"><link rel="stylesheet" href="./v12.css?v=12">'
html = html.replace('</head>', head + '</head>')
html = html.replace('</body>', '<script src="./v12.js?v=12"></script><script src="./live.js?v=12"></script></body>')
(out / 'index.html').write_text(html, encoding='utf-8')
for name in ('status.enc.json','live.js','v12.css','v12.js','manifest.webmanifest','icon-180.png','icon-192.png','icon-512.png'):
    shutil.copyfile(src / name, out / name)
print('HQ v12 built:', out)
