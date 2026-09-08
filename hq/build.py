from pathlib import Path
import shutil,sys

src=Path(__file__).resolve().parent
out=Path(sys.argv[1] if len(sys.argv)>1 else '_site')/'hq'
out.mkdir(parents=True,exist_ok=True)

html=(src/'v14.html').read_text(encoding='utf-8')
html=html.replace('./office-v15.jpg?v=15','./office-v17.jpg?v=17')
html=html.replace('./meeting-v15.jpg?v=15','./meeting-v17.jpg?v=17')
html=html.replace('manifest.webmanifest?v=15','manifest.webmanifest?v=17')
html=html.replace('manifest.webmanifest?v=14','manifest.webmanifest?v=17')
html=html.replace('icon-192.png?v=15','icon-192.png?v=17')
html=html.replace('icon-180.png?v=15','icon-180.png?v=17')
html=html.replace('icon-192.png?v=14','icon-192.png?v=17')
html=html.replace('icon-180.png?v=14','icon-180.png?v=17')
html=html.replace('HQ v15 · JPEG scene assets','HQ v17 · direct JPEG scenes')
(out/'index.html').write_text(html,encoding='utf-8')

for src_name,out_name in (
    ('manifest.webmanifest','manifest.webmanifest'),
    ('icon-180.png','icon-180.png'),
    ('icon-192.png','icon-192.png'),
    ('icon-512.png','icon-512.png'),
    ('office-v15.jpg','office-v17.jpg'),
    ('meeting-v15.jpg','meeting-v17.jpg'),
):
    shutil.copyfile(src/src_name,out/out_name)
print('HQ v17 built with direct JPEG scenes',out)
