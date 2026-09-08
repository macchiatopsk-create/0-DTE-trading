from pathlib import Path
import shutil,sys
src=Path(__file__).resolve().parent
out=Path(sys.argv[1] if len(sys.argv)>1 else '_site')/'hq'
out.mkdir(parents=True,exist_ok=True)
html=(src/'v14.html').read_text(encoding='utf-8')
old="onerror=\"this.style.display='none';this.parentElement.style.background='linear-gradient(#0b1218,#182531)'\""
new="onerror=\"if(!this.dataset.fallback){this.dataset.fallback='1';this.src='./office-art.avif?v=14'}else{this.style.display='none';this.parentElement.style.background='linear-gradient(#0b1218,#182531)'}\""
html=html.replace(old,new)
(out/'index.html').write_text(html,encoding='utf-8')
for name in ('manifest.webmanifest','icon-180.png','icon-192.png','icon-512.png','office-v13.webp','meeting-v13.webp','office-art.avif'):
    shutil.copyfile(src/name,out/name)
print('HQ v14 built with verified visual fallback',out)
