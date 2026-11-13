"""检查 脚本.js 括号配对（剔除注释与字符串后再计数）。

v0.3 升级：旧版先剔注释再剔字符串，遇到字符串里含 "https://" 这类文本时，
"//" 会被误当成注释起点，连闭合引号一起删掉，导致后续字符串剥离错乱。
现改为单趟状态机：代码 / 行注释 / 块注释 / 单引号串 / 双引号串 五个状态，
互不误伤。脚本内正则字面量不含 "//"，不会被误判为注释。
"""
import sys
from pathlib import Path

s = Path(r"D:\lab\自选作品\脚本.js").read_text(encoding="utf-8")

状态 = "代码"
输出 = []
i = 0
while i < len(s):
    c = s[i]
    下一个 = s[i + 1] if i + 1 < len(s) else ""

    if 状态 == "代码":
        if c == "/" and 下一个 == "/":
            状态 = "行注释"
            i += 2
            continue
        if c == "/" and 下一个 == "*":
            状态 = "块注释"
            i += 2
            continue
        if c == "'":
            状态 = "单引号串"
        elif c == '"':
            状态 = "双引号串"
        输出.append(c)
        i += 1
        continue

    if 状态 == "行注释":
        if c == "\n":
            状态 = "代码"
            输出.append(c)
        i += 1
        continue

    if 状态 == "块注释":
        if c == "*" and 下一个 == "/":
            状态 = "代码"
            i += 2
            continue
        i += 1
        continue

    # 字符串内：转义跳两格；闭合引号回到代码态。字符串内容整体丢弃。
    if c == "\\":
        i += 2
        continue
    if (状态 == "单引号串" and c == "'") or (状态 == "双引号串" and c == '"'):
        状态 = "代码"
    i += 1

t = "".join(输出)

ok = 状态 == "代码"
if 状态 != "代码":
    print(f"  [失败] 文件结束时仍处于未闭合状态：{状态}")

for a, b, n in [("{", "}", "花括号"), ("(", ")", "圆括号"), ("[", "]", "方括号")]:
    good = t.count(a) == t.count(b)
    ok = ok and good
    print(f"  {n}: {t.count(a)} / {t.count(b)} -> {'OK' if good else 'MISMATCH'}")

sys.exit(0 if ok else 1)
