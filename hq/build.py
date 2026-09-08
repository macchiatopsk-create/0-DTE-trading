from pathlib import Path
import shutil,sys

src=Path(__file__).resolve().parent
out=Path(sys.argv[1] if len(sys.argv)>1 else '_site')/'hq'
out.mkdir(parents=True,exist_ok=True)

html=(src/'v21.html').read_text(encoding='utf-8')
html=html.replace('manifest.webmanifest?v=21','manifest.webmanifest?v=22')
html=html.replace('icon-192.png?v=21','icon-192.png?v=22')
html=html.replace('icon-180.png?v=21','icon-180.png?v=22')
html=html.replace('</body>','<script src="./swipe-v22.js?v=22"></script></body>')
(out/'index.html').write_text(html,encoding='utf-8')
for name in ('manifest.webmanifest','icon-180.png','icon-192.png','icon-512.png','swipe-v22.js'):
    shutil.copyfile(src/name,out/name)
print('HQ v22 holographic Korean console with swipe built',out)
