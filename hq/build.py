"""Build the existing office plus its local live extension. No private data rewriting."""
from pathlib import Path
import shutil
import sys

def build(destination: str) -> None:
    src = Path(__file__).resolve().parent
    out = Path(destination) / 'hq'
    out.mkdir(parents=True, exist_ok=True)
    html = (src / 'index.html').read_text(encoding='utf-8')
    html = html.replace("script-src 'unsafe-inline'", "script-src 'self' 'unsafe-inline'")
    html = html.replace("connect-src 'self';", "connect-src 'self' https://nutfgkxaddvidqrcnvyj.supabase.co;")
    if './live.js?v=9' not in html:
        html = html.replace('</body>', '<script src="./live.js?v=9"></script></body>')
    if html.count('src="./live.js?v=9"') != 1:
        raise ValueError('Live extension must be loaded exactly once')
    (out / 'index.html').write_text(html, encoding='utf-8')
    for name in ('office-art.avif', 'status.enc.json', 'live.js'):
        shutil.copyfile(src / name, out / name)

if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else '_site')
