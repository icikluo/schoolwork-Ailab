"""校验健身动作数据的字段契约（对应 PRD 5.8）。

字段：id / 名称 / 部位 / 器械 / 目标肌群 / 要点 / 常见错误 / 建议 / 图片
"""
import json
import re
import sys
from pathlib import Path

根 = Path(r"D:\lab\自选作品")

# 从 动作.js 中提取数据（该文件以 window.动作数据 = [...] 形式保存）
源 = (根 / "数据" / "动作.js").read_text(encoding="utf-8")
匹配 = re.search(r"window\.动作数据\s*=\s*(\[.*\]);\s*$", 源, re.S)
if not 匹配:
    print("[失败] 无法从 动作.js 中解析出动作数据")
    sys.exit(1)

原文 = 匹配.group(1)
# 去掉块注释与行注释（仅剥注释，不动字符串内容）
原文 = re.sub(r"/\*.*?\*/", "", 原文, flags=re.S)
原文 = re.sub(r"^\s*//.*$", "", 原文, flags=re.M)

try:
    数据 = json.loads(原文)
except json.JSONDecodeError as e:
    print(f"[失败] 动作数据不是合法 JSON: {e}")
    sys.exit(1)

字段 = ["id", "名称", "部位", "器械", "目标肌群", "要点", "常见错误", "建议", "图片"]
部位允许 = {"上肢", "下肢", "核心", "全身"}
器械允许 = {"自重", "哑铃", "壶铃", "杠铃", "健身房器械"}
错误 = []
ids = set()

for i, 动作 in enumerate(数据):
    位置 = f"第{i+1}条({动作.get('名称', '?')})"

    # 字段名与顺序
    if list(动作.keys()) != 字段:
        错误.append(f"{位置} 字段名或顺序不符: {list(动作.keys())}")

    # id 唯一
    if 动作.get("id") in ids:
        错误.append(f"{位置} id 重复: {动作.get('id')}")
    if not re.fullmatch(r"e\d{3}", str(动作.get("id", ""))):
        错误.append(f"{位置} id 格式应为 e+三位数字")
    ids.add(动作.get("id"))

    # 名称非空
    if not 动作.get("名称"):
        错误.append(f"{位置} 名称为空")

    # 部位取值
    if 动作.get("部位") not in 部位允许:
        错误.append(f"{位置} 部位非法: {动作.get('部位')}")

    # 器械取值
    if 动作.get("器械") not in 器械允许:
        错误.append(f"{位置} 器械非法: {动作.get('器械')}（允许值: {sorted(器械允许)}）")

    # 目标肌群非空
    if not 动作.get("目标肌群"):
        错误.append(f"{位置} 目标肌群为空")

    # 要点 3-5 条
    要点 = 动作.get("要点")
    if not isinstance(要点, list):
        错误.append(f"{位置} 要点不是数组")
    elif not (3 <= len(要点) <= 5):
        错误.append(f"{位置} 要点应为 3-5 条，实际 {len(要点)} 条")
    elif any(not isinstance(x, str) or not x.strip() for x in 要点):
        错误.append(f"{位置} 要点存在空项")

    # 常见错误 1-3 条
    常见错误 = 动作.get("常见错误")
    if not isinstance(常见错误, list):
        错误.append(f"{位置} 常见错误不是数组")
    elif not (1 <= len(常见错误) <= 3):
        错误.append(f"{位置} 常见错误应为 1-3 条，实际 {len(常见错误)} 条")

    # 建议非空
    if not 动作.get("建议"):
        错误.append(f"{位置} 建议为空")

    # 图片：本地路径或空串
    图片 = 动作.get("图片")
    if not isinstance(图片, str):
        错误.append(f"{位置} 图片必须是字符串")
    elif 图片:
        if 图片.startswith(("http://", "https://")):
            错误.append(f"{位置} 图片必须是本地文件: {图片}")
        elif not (根 / 图片).exists():
            错误.append(f"{位置} 图片文件不存在: {图片}")

# 部位覆盖统计
print(f"动作总数: {len(数据)}")
for p in ["上肢", "下肢", "核心", "全身"]:
    数量 = sum(1 for a in 数据 if a["部位"] == p)
    print(f"  {p}: {数量} 个动作")
    错误.append(f"{p} 至少需要 2 个动作，实际 {数量}") if 数量 < 2 else None

有图 = sum(1 for a in 数据 if a.get("图片"))
示意 = [a["名称"] for a in 数据 if not a.get("图片")]
print(f"配图: {有图}/{len(数据)} 有照片" + (f"，示意图: {示意}" if 示意 else ""))
器械统计 = {}
for a in 数据:
    器械统计[a["器械"]] = 器械统计.get(a["器械"], 0) + 1
print("器械分布:", 器械统计)

if 错误:
    print("\n[发现错误]")
    for e in 错误:
        print(" -", e)
    sys.exit(1)

print("\n[通过] 全部动作符合字段契约")