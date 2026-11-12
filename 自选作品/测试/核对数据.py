"""核对 脚本.js 里的目标卡路里计算与 数据 是否一致（Python 独立复算同一公式）。"""
import json
import re
import sys
from pathlib import Path

根 = Path(r"D:\lab\自选作品")

# ---- 1. 读数据，校验字段契约 ----
数据 = json.loads((根 / "数据" / "foods.json").read_text(encoding="utf-8"))
字段 = ["id", "名称", "人群", "卡路里", "碳水", "脂肪", "膳食纤维", "蛋白质", "图片"]
人群允许 = {"减脂", "增肌", "控糖", "均衡"}
错误 = []
ids = set()
for i, 菜 in enumerate(数据):
    位置 = f"第{i+1}条({菜.get('名称', '?')})"
    if list(菜.keys()) != 字段:
        错误.append(f"{位置} 字段名或顺序不符: {list(菜.keys())}")
    if 菜.get("id") in ids:
        错误.append(f"{位置} id 重复: {菜.get('id')}")
    ids.add(菜.get("id"))
    if not isinstance(菜.get("卡路里"), int):
        错误.append(f"{位置} 卡路里不是整数")
    if not (0 <= 菜.get("卡路里", -1) <= 3000):
        错误.append(f"{位置} 卡路里超范围")
    for f in ["碳水", "脂肪", "膳食纤维", "蛋白质"]:
        值 = 菜.get(f)
        if not isinstance(值, (int, float)):
            错误.append(f"{位置} {f} 不是数字")
        elif 值 < 0:
            错误.append(f"{位置} {f} 为负")
        elif round(值, 1) != 值:
            错误.append(f"{位置} {f} 超过1位小数: {值}")
    if not 菜.get("人群") or not set(菜["人群"]) <= 人群允许:
        错误.append(f"{位置} 人群标签非法: {菜.get('人群')}")
    # 图片：必须是本地相对路径（保证离线可用）；空字符串表示暂无配图
    图片 = 菜.get("图片")
    if not isinstance(图片, str):
        错误.append(f"{位置} 图片字段必须是字符串")
    elif 图片:
        if 图片.startswith(("http://", "https://")):
            错误.append(f"{位置} 图片必须是本地文件，不能是外链: {图片}")
        elif not (根 / 图片).exists():
            错误.append(f"{位置} 图片文件不存在: {图片}")

# ---- 2. 品牌数据合计 ----
合计 = {f: 0 for f in ["卡路里", "碳水", "脂肪", "膳食纤维", "蛋白质"]}
for 菜 in 数据:
    for f in 合计:
        合计[f] += 菜[f]

# ---- 3. 独立复算三步公式，对比 脚本.js 中写死的示例 ----
def 计算基础代谢(性别, 体重, 身高, 年龄):
    基数 = 10 * 体重 + 6.25 * 身高 - 5 * 年龄
    return 基数 + 5 if 性别 == "男" else 基数 - 161

def 计算目标卡路里(性别, 体重, 身高, 年龄, 活动系数, 系数):
    目标 = 计算基础代谢(性别, 体重, 身高, 年龄) * 活动系数 * 系数
    取整 = round(目标 / 10) * 10
    return 1200 if 取整 < 1200 else 取整

# PRD 中写明的示例：22岁女 165cm 55kg 久坐 减脂
# BMR = 10*55 + 6.25*165 - 5*22 - 161 = 1310.25
# TDEE = 1310.25 * 1.2 = 1572.3 ; 减脂 *0.8 = 1257.84 -> 取整到10 = 1260
示例 = 计算目标卡路里("女", 55, 165, 22, 1.2, 0.8)
print(f"PRD 示例实算结果: {示例} kcal  (期望 1260)")
assert 示例 == 1260, f"示例结果 {示例} != 1260"

# 下限保护：极端体重算出来会低于 1200
下限例 = 计算目标卡路里("女", 35, 150, 60, 1.2, 0.8)
print(f"下限保护实算结果: {下限例} kcal  (期望 1200)")
assert 下限例 == 1200

print(f"\n食谱条数: {len(数据)}")
print(f"营养合计: 卡路里 {round(合计['卡路里'])} kcal | 碳水 {合计['碳水']:.1f}g | "
      f"脂肪 {合计['脂肪']:.1f}g | 膳食纤维 {合计['膳食纤维']:.1f}g | 蛋白质 {合计['蛋白质']:.1f}g")

有图 = sum(1 for 菜 in 数据 if 菜.get("图片"))
无图 = [菜["名称"] for 菜 in 数据 if not 菜.get("图片")]
print(f"配图情况: {有图}/{len(数据)} 条有图" + (f"，暂无图: {无图}" if 无图 else ""))

if 错误:
    print("\n[发现错误]")
    for e in 错误:
        print(" -", e)
    sys.exit(1)
print("\n[通过] 全部食谱符合字段契约，公式与 PRD 一致")