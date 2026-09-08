from pathlib import Path
import shutil,sys

src=Path(__file__).resolve().parent
out=Path(sys.argv[1] if len(sys.argv)>1 else '_site')/'hq'
out.mkdir(parents=True,exist_ok=True)

html=(src/'v14.html').read_text(encoding='utf-8')
office=(src/'office-v15.b64').read_text(encoding='utf-8').strip()
meeting=(src/'meeting-v15.b64').read_text(encoding='utf-8').strip()

html=html.replace('./office-v15.jpg?v=15', 'data:image/jpeg;base64,'+office)
html=html.replace('./meeting-v15.jpg?v=15', 'data:image/jpeg;base64,'+meeting)
html=html.replace('./office-v13.webp?v=14', 'data:image/jpeg;base64,'+office)
html=html.replace('./meeting-v13.webp?v=14', 'data:image/jpeg;base64,'+meeting)
html=html.replace('manifest.webmanifest?v=14', 'manifest.webmanifest?v=15')
html=html.replace('icon-192.png?v=14', 'icon-192.png?v=15')
html=html.replace('icon-180.png?v=14', 'icon-180.png?v=15')

(out/'index.html').write_text(html,encoding='utf-8')
for name in ('manifest.webmanifest','icon-180.png','icon-192.png','icon-512.png'):
    shutil.copyfile(src/name,out/name)
print('HQ v15 built with inline JPEG scenes',out)
