from pypdf import PdfReader
from pathlib import Path
import sys

p = next(Path('.').glob('*.pdf'), None)
print('PDF:', p)
if not p:
    sys.exit('No PDF')
reader = PdfReader(str(p))
print('Pages:', len(reader.pages))
for i in range(min(3, len(reader.pages))):
    text = reader.pages[i].extract_text() or ''
    print(f'Page {i+1} text length:', len(text))
    print(text[:200])

# check tiktoken
try:
    import tiktoken
    print('tiktoken version:', getattr(tiktoken, '__version__', 'n/a'))
    enc = tiktoken.get_encoding('cl100k_base')
    print('cl100k_base encoding loaded, sample name:', getattr(enc,'name', 'n/a'))
except Exception as e:
    print('tiktoken load error:', repr(e))
