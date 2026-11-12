"""检查 脚本.js 括号配对（剔除注释与字符串后再计数）。"""
import re
import sys
from pathlib import Path

s = Path(r"D:\lab\自选作品\脚本.js").read_text(encoding="utf-8")

t = re.sub(r"//[^\n]*", "", s)
t = re.sub(r"'(?:[^'\\]|\\.)*'", "''", t)
t = re.sub(r'"(?:[^"\\]|\\.)*"', '""', t)

ok = True
for a, b, n in [("{", "}", "花括号"), ("(", ")", "圆括号"), ("[", "]", "方括号")]:
    good = t.count(a) == t.count(b)
    ok = ok and good
    print(f"  {n}: {t.count(a)} / {t.count(b)} -> {'OK' if good else 'MISMATCH'}")

sys.exit(0 if ok else 1)