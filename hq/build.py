from pathlib import Path
import shutil,sys
src=Path(__file__).resolve().parent
out=Path(sys.argv[1] if len(sys.argv)>1 else '_site')/'hq'
out.mkdir(parents=True,exist_ok=True)
shutil.copyfile(src/'v14.html',out/'index.html')
for name in ('manifest.webmanifest','icon-180.png','icon-192.png','icon-512.png','office-v15.jpg','meeting-v15.jpg'):
    shutil.copyfile(src/name,out/name)
print('HQ v15 built with JPEG scenes',out)
