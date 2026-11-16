"""契约检查（多页版）：脚本里 取元素("id") 引用的 id，必须在某个页面中存在。

对应课程标准 U3「概念完整性 / 接口契约断裂」：
HTML 与 JS 各自独立运行都正常，但 id 对不上就会在运行期崩溃。

v0.5 起页面拆成 6 个 HTML，共用一份 脚本.js。脚本里引用的是「所有页面的 id 并集」，
缺失元素由 取元素() 的哑元素兜底；本脚本同时检查每页的侧栏导航是否一致、
data-页面 是否与导航项对应，避免换页后链接或高亮对不上。
"""
import re
import sys
from pathlib import Path

根 = Path(r"D:\lab\自选作品")
页面文件 = ["index.html", "目标.html", "食谱.html", "计划.html", "记录.html", "训练.html"]
导航文件 = {
    "总览": "index.html",
    "目标": "目标.html",
    "食谱": "食谱.html",
    "计划": "计划.html",
    "记录": "记录.html",
    "训练": "训练.html",
}

页面文本 = {}
for 名 in 页面文件:
    路径 = 根 / 名
    if not 路径.exists():
        print(f"【失败】缺少页面文件：{名}")
        sys.exit(1)
    页面文本[名] = 路径.read_text(encoding="utf-8")

脚本 = (根 / "脚本.js").read_text(encoding="utf-8")

页面ids = set()
for 名, 文本 in 页面文本.items():
    页面ids |= set(re.findall(r'id="([^"]+)"', 文本))
脚本ids = re.findall(r'取元素\("([^"]+)"\)', 脚本)
被引用 = sorted(set(脚本ids))

print(f"6 个页面 id 并集共 {len(页面ids)} 个")
print(f"脚本引用 id 共 {len(被引用)} 个")
print()
for i in 被引用:
    print(("  OK   " if i in 页面ids else "  缺失 ") + i)

缺失 = [i for i in 被引用 if i not in 页面ids]
print()
if 缺失:
    print(f"【失败】脚本引用了 {len(缺失)} 个所有页面都不存在的 id：{缺失}")
    sys.exit(1)

# 页面结构契约：每页的 data-页面、侧栏、导航链接、目标值 id 都要齐全
结构问题 = []
for 名, 文本 in 页面文本.items():
    页键 = re.search(r'<body data-页面="([^"]+)">', 文本)
    if not 页键 or 页键.group(1) not in 导航文件 or 导航文件[页键.group(1)] != 名:
        结构问题.append(f"{名}：body 的 data-页面 与文件名不匹配")
    if any(标记 not in 文本 for 标记 in
           ['class="侧栏"', 'id="侧栏目标"', 'id="侧栏今日"', 'id="顶栏目标"']):
        结构问题.append(f"{名}：缺少侧栏 / 侧栏目标 / 侧栏今日 / 顶栏目标")
    for 键, 文件 in 导航文件.items():
        if f'href="{文件}" data-页="{键}"' not in 文本:
            结构问题.append(f"{名}：侧栏缺少指向 {文件}（{键}）的导航项")

if 结构问题:
    print("【失败】页面结构契约不一致：")
    for 条 in 结构问题:
        print("  - " + 条)
    sys.exit(1)
print("【通过】所有 取元素() 引用都能在页面中找到对应元素")
print("【通过】6 个页面的 data-页面 / 侧栏导航 / 目标值 id 全部一致")

# 反向检查：页面上的 id 是否都被用到（允许有未用到的，仅提示）
未用 = sorted(页面ids - set(被引用))
if 未用:
    print(f"\n提示：页面中以下 id 未被脚本引用（可能正常）：{未用}")
sys.exit(0)
