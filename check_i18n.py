import re
from pathlib import Path

root = Path(r'C:\Users\dell\Desktop\LuckyPatcher-PC\src\ui')
keys = set()
for py in root.rglob('*.py'):
    text = py.read_text(encoding='utf-8')
    for m in re.finditer(r't\([\'"]([\w.]+)[\'"]', text):
        keys.add(m.group(1))
for k in sorted(keys):
    print(k)