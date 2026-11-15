"""契约检查：脚本里 取元素("id") 引用的 id，必须在 index.html 中存在。

对应课程标准 U3「概念完整性 / 接口契约断裂」：
HTML 与 JS 各自独立运行都正常，但 id 对不上就会在运行期崩溃。
"""
import re
import sys
from pathlib import Path

根 = Path(r"D:\lab\自选作品")
html = (根 / "index.html").read_text(encoding="utf-8")
脚本 = (根 / "脚本.js").read_text(encoding="utf-8")

页面ids = set(re.findall(r'id="([^"]+)"', html))
脚本ids = re.findall(r'取元素\("([^"]+)"\)', 脚本)
被引用 = sorted(set(脚本ids))

缺失 = [i for i in 被引用 if i not in 页面ids]

print(f"页面 id 共 {len(页面ids)} 个")
print(f"脚本引用 id 共 {len(被引用)} 个")
print()

for i in 被引用:
    print(("  OK   " if i in 页面ids else "  缺失 ") + i)

print()
if 缺失:
    print(f"【失败】脚本引用了 {len(缺失)} 个页面中不存在的 id：{缺失}")
    sys.exit(1)
print("【通过】所有 取元素() 引用都能在页面中找到对应元素")

# 反向检查：页面上的 id 是否都被用到（允许有未用到的，仅提示）
未用 = sorted(页面ids - set(被引用))
if 未用:
    print(f"\n提示：页面中以下 id 未被脚本引用（可能正常）：{未用}")
sys.exit(0)