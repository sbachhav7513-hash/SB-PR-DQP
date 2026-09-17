import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

p = Path(r'c:\Users\SHUBHAM\Downloads\Trading_Bot_Strategy_Review.docx')
print('exists=', p.exists())
if not p.exists():
    raise SystemExit(0)

with zipfile.ZipFile(p) as z:
    xml = z.read('word/document.xml')
    root = ET.fromstring(xml)
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    paras = []
    for node in root.findall('.//w:p', ns):
        texts = []
        for t in node.findall('.//w:t', ns):
            texts.append(t.text or '')
        txt = ''.join(texts)
        if txt.strip():
            paras.append(txt)
    print('---TEXT---')
    for i, line in enumerate(paras[:500], 1):
        print(f'{i}: {line}')
