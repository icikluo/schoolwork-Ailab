"""校验数据文件是否符合 schema/*.json 契约（A4 评分点①）

与既有测试的关系：
  - 核对数据.py / 核对动作.py / 核对养成.py 里的字段检查，是**散落在测试代码里**的硬编码。
  - 本脚本把那些检查**提炼成 schema/*.json 声明式契约**，再统一按 schema 校验。
  - 两份并存时，schema 是唯一事实来源；测试脚本里的检查保留作为双保险。

用法：
    python 测试/校验schema.py            # 校验全部 schema
    python 测试/校验schema.py 食谱       # 只校验某一个（按文件名前缀匹配）

退出码 0 = 全部通过；1 = 有违例（逐条打印）。
"""
import json
import re
import sys
from pathlib import Path

根 = Path(r"D:\lab\自选作品")
契约目录 = 根 / "schema"

通过 = 0
失败 = 0
问题 = []


def 检查(名称, 实际, 期望):
    global 通过, 失败
    if 实际 == 期望:
        通过 += 1
        return True
    失败 += 1
    问题.append(f"{名称}：实际 {实际!r}，期望 {期望!r}")
    return False


# ==================== 通用校验原语 ====================


def 校验字段值(值, 规则, 位置, 上下文):
    """按单字段规则校验一个值，违例写入 问题。"""
    类型 = 规则.get("类型")

    if 类型 == "string":
        if not isinstance(值, str):
            问题.append(f"{位置} 应为字符串，实际 {type(值).__name__}")
            return
        if 规则.get("非空") and not 值.strip():
            问题.append(f"{位置} 不能为空字符串")
        if "格式" in 规则 and 值 and not re.fullmatch(规则["格式"], 值):
            问题.append(f"{位置} 不符合格式 {规则['格式']}：{值}")
        for 禁止 in 规则.get("禁止子串", []):
            if 禁止 in 值:
                问题.append(f"{位置} 含禁止子串 {禁止!r}")
        if 规则.get("本地路径") and 值:
            if 值.startswith(("http://", "https://")):
                问题.append(f"{位置} 必须是本地路径，不能是外链：{值}")
            elif not (根 / 值).exists():
                问题.append(f"{位置} 文件不存在：{值}")
            elif "最小字节" in 规则 and (根 / 值).stat().st_size < 规则["最小字节"]:
                问题.append(f"{位置} 文件过小（{规则['最小字节']} 字节下限）：{值}")

    elif 类型 == "integer":
        if not isinstance(值, int) or isinstance(值, bool):
            问题.append(f"{位置} 应为整数，实际 {type(值).__name__}")
            return
        if "最小" in 规则 and 值 < 规则["最小"]:
            问题.append(f"{位置} 小于下限 {规则['最小']}：{值}")
        if "最大" in 规则 and 值 > 规则["最大"]:
            问题.append(f"{位置} 超过上限 {规则['最大']}：{值}")
        if "枚举数值" in 规则 and 值 not in 规则["枚举数值"]:
            问题.append(f"{位置} 取值必须是 {规则['枚举数值']}，实际 {值}")

    elif 类型 == "number":
        if not isinstance(值, (int, float)) or isinstance(值, bool):
            问题.append(f"{位置} 应为数字，实际 {type(值).__name__}")
            return
        if "最小" in 规则 and 值 < 规则["最小"]:
            问题.append(f"{位置} 小于下限 {规则['最小']}：{值}")
        if "小数位最多" in 规则:
            小数位 = len(str(值).split(".")[1]) if "." in str(值) else 0
            if round(值, 规则["小数位最多"]) != 值:
                问题.append(f"{位置} 小数位超过 {规则['小数位最多']} 位：{值}")

    elif 类型 == "boolean":
        if not isinstance(值, bool):
            问题.append(f"{位置} 应为布尔，实际 {type(值).__name__}")

    elif 类型 == "array":
        校验数组(值, 规则, 位置, 上下文)

    elif 类型 == "object":
        校验对象(值, 规则, 位置, 上下文)

    elif 类型 == "object|null":
        if 值 is None:
            return
        校验对象(值, 规则, 位置, 上下文)

    elif 类型 == "any":
        pass

    else:
        问题.append(f"{位置} 出现未知类型规则：{类型}")


def 校验数组(值, 规则, 位置, 上下文):
    if not isinstance(值, list):
        问题.append(f"{位置} 应为数组，实际 {type(值).__name__}")
        return
    if 规则.get("非空数组") and not 值:
        问题.append(f"{位置} 不能是空数组")
    if "最少条数" in 规则 and len(值) < 规则["最少条数"]:
        问题.append(f"{位置} 条数不足，最少 {规则['最少条数']}，实际 {len(值)}")
    if "最多条数" in 规则 and len(值) > 规则["最多条数"]:
        问题.append(f"{位置} 条数超限，最多 {规则['最多条数']}，实际 {len(值)}")
    if "条数" in 规则 and len(值) != 规则["条数"]:
        问题.append(f"{位置} 条数必须为 {规则['条数']}，实际 {len(值)}")
    if 规则.get("唯一"):
        seen = set()
        for 项 in 值:
            if 项 in seen:
                问题.append(f"{位置} 出现重复值：{项}")
            seen.add(项)
    if "枚举" in 规则:
        for 项 in 值:
            if 项 not in 规则["枚举"]:
                问题.append(f"{位置} 含非法元素 {项!r}，允许 {规则['枚举']}")
    if "枚举元素" in 规则:
        for 项 in 值:
            if 项 not in 规则["枚举元素"]:
                问题.append(f"{位置} 含非法元素 {项!r}，允许 {规则['枚举元素']}")
    if "元素类型" in 规则:
        元素规则 = {"类型": 规则["元素类型"]}
        if 规则.get("非空"):
            元素规则["非空"] = True
        for i, 项 in enumerate(值):
            校验字段值(项, 元素规则, f"{位置}[{i}]", 上下文)


def 校验对象(值, 规则, 位置, 上下文):
    if not isinstance(值, dict):
        问题.append(f"{位置} 应为对象，实际 {type(值).__name__}")
        return
    字段规则 = 规则.get("字段", {})
    for 名, 子规则 in 字段规则.items():
        if 名 not in 值:
            问题.append(f"{位置} 缺少字段 {名}")
            continue
        校验字段值(值[名], 子规则, f"{位置}.{名}", 上下文)
    # 元素级字段（数组里每个对象）
    if "元素字段顺序" in 规则 and "元素字段" in 规则:
        pass


def 校验记录数组(数据, schema, 名称前缀):
    """校验「对象数组」形态的数据文件（食谱 / 动作 / 家具 / 商店道具）"""
    global 通过

    if "条数" in schema:
        检查(f"{名称前缀} 条数", len(数据), schema["条数"])
    if "最少条数" in schema:
        检查(f"{名称前缀} 不少于 {schema['最少条数']} 条", len(数据) >= schema["最少条数"], True)

    字段顺序 = schema.get("字段顺序") or schema.get("元素字段顺序") or []
    字段规则 = schema.get("字段", {}) or schema.get("元素字段", {})

    for i, 记录 in enumerate(数据):
        位置 = f"{名称前缀}[{i}]"
        if 字段顺序 and list(记录.keys()) != 字段顺序:
            问题.append(f"{位置} 字段名或顺序不符：{list(记录.keys())}")
        for 名, 规则 in 字段规则.items():
            if 名 not in 记录:
                问题.append(f"{位置} 缺少字段 {名}")
                continue
            校验字段值(记录[名], 规则, f"{位置}.{名}", schema)

    # 唯一性
    for 名, 规则 in 字段规则.items():
        if 规则.get("唯一"):
            值表 = [记录.get(名) for 记录 in 数据]
            if len(set(值表)) != len(值表):
                问题.append(f"{名称前缀} 字段 {名} 存在重复值")
            else:
                通过 += 1

    # 分类最少条数（动作的部位覆盖）
    for 名, 规则 in 字段规则.items():
        if "分类最少条数" in 规则:
            for 类 in 规则.get("枚举", []):
                数量 = sum(1 for r in 数据 if r.get(名) == 类)
                检查(f"{名称前缀} 分类「{类}」至少 {规则['分类最少条数']} 条",
                     数量 >= 规则["分类最少条数"], True)


# ==================== 各数据文件的解析 ====================


def 解析JS数据(路径, 变量名):
    源 = 路径.read_text(encoding="utf-8")
    m = re.search(r"window\." + 变量名 + r"\s*=\s*([\[{].*[\]}]);", 源, re.S)
    if not m:
        raise SystemExit(f"【失败】{路径.name} 里找不到 window.{变量名}")
    原文 = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    原文 = re.sub(r"^\s*//.*$", "", 原文, flags=re.M)
    return json.loads(原文)


def 校验食谱():
    schema = json.loads((契约目录 / "食谱.schema.json").read_text(encoding="utf-8"))
    数据 = json.loads((根 / schema["路径"]).read_text(encoding="utf-8"))
    校验记录数组(数据, schema, "食谱")
    # 食谱与 食谱.js 同构（两份数据必须一致）
    js数据 = 解析JS数据(根 / "数据" / "食谱.js", "食谱数据")
    检查("食谱.json 与 食谱.js 条数一致", len(js数据), len(数据))
    检查("食谱.json 与 食谱.js 首条一致", js数据[0], 数据[0])


def 校验动作():
    schema = json.loads((契约目录 / "动作.schema.json").read_text(encoding="utf-8"))
    数据 = 解析JS数据(根 / schema["路径"], "动作数据")
    校验记录数组(数据, schema, "动作")


def 校验家具():
    schema = json.loads((契约目录 / "家具.schema.json").read_text(encoding="utf-8"))
    数据 = 解析JS数据(根 / schema["路径"], "家具数据")
    校验记录数组(数据, schema, "家具")
    加成合计 = round(sum(d["加成"] for d in 数据), 10)
    检查("家具加成合计", 加成合计, schema["约束"]["加成合计"])
    检查("家具加成合计不超过上限", 加成合计 <= schema["约束"]["加成合计上限"], True)


def 校验商店():
    schema = json.loads((契约目录 / "商店.schema.json").read_text(encoding="utf-8"))
    数据 = 解析JS数据(根 / schema["路径"], "商店数据")
    道具规则 = schema["字段"]["道具"]
    校验记录数组(数据["道具"], 道具规则, "道具")
    检查("商店 id 唯一", len({d["id"] for d in 数据["道具"]}), len(数据["道具"]))


def 校验装扮():
    global 通过
    schema = json.loads((契约目录 / "装扮.schema.json").read_text(encoding="utf-8"))
    数据 = 解析JS数据(根 / schema["路径"], "装扮数据")
    检查("装扮分类齐全", sorted(数据.keys()), sorted(schema["分类"]))
    全部id = []
    合计 = 0
    for 分类, 件列表 in 数据.items():
        合计 += len(件列表)
        for i, 件 in enumerate(件列表):
            位置 = f"装扮[{分类}][{i}]"
            for 名, 规则 in schema["字段"].items():
                # 色值 只对肤色分类生效
                if 名 == "色值" and 分类 != "肤色":
                    continue
                if 名 not in 件:
                    问题.append(f"{位置} 缺少字段 {名}")
                    continue
                校验字段值(件[名], 规则, f"{位置}.{名}", schema)
            全部id.append(件.get("id"))
            # 约束：肤色分类全免费
            if 分类 == "肤色" and 件.get("价格") != 0:
                问题.append(f"{位置} 肤色必须免费，实际价格 {件.get('价格')}")
    检查("装扮合计件数", 合计, schema["合计件数"])
    检查("装扮 id 全局唯一", len(set(全部id)), len(全部id))


def 校验存档():
    """存档 schema 是「结构说明」而非实际数据；这里校验它与 养成.js 的默认值一致。"""
    schema = json.loads((契约目录 / "存档.schema.json").read_text(encoding="utf-8"))
    源 = (根 / "养成.js").read_text(encoding="utf-8")
    # 存储键必须与 养成反馈.js 的 键 表一致
    反馈源 = (根 / "养成反馈.js").read_text(encoding="utf-8")
    for 名, 规则 in schema["存储"].items():
        键 = 规则["键"]
        检查(f"存储键「{名}」在 养成反馈.js 中存在", f'"{键}"' in 反馈源, True)
    # 存档默认字段必须齐全
    for 名 in schema["存档结构"].keys():
        检查(f"默认存档包含字段 {名}", f'"{名}"' in 源, True)
    # 不变量：经验不加成 —— 结算打卡 里经验直接取自 奖励表，金币才乘 (1+加成)
    检查("结算打卡经验直接取奖励表（不乘加成）",
         "var 本次经验 = 奖.经验;" in 源, True)
    检查("结算打卡金币乘 (1+加成)",
         "本次金币 = Math.round(奖.金币 * (1 + 加成))" in 源, True)
    # 返回结构字段
    for 字段 in schema["结算购买返回"]["字段顺序"]:
        检查(f"结算购买返回含字段 {字段}", f'"{字段}"' in (根 / "养成商店.js").read_text(encoding="utf-8"), True)


校验器 = {
    "食谱": 校验食谱,
    "动作": 校验动作,
    "家具": 校验家具,
    "商店": 校验商店,
    "装扮": 校验装扮,
    "存档": 校验存档,
}


def main():
    筛选 = sys.argv[1] if len(sys.argv) > 1 else None
    目标 = [名 for 名 in 校验器 if not 筛选 or 筛选 in 名]
    if not 目标:
        print(f"【失败】没有匹配的 schema：{筛选}")
        return 1

    for 名 in 目标:
        print(f"\n【{名}】按 schema/{名}.schema.json 校验")
        前 = 失败
        校验器[名]()
        if 失败 == 前:
            print(f"  ✓ 通过")

    print("\n" + "=" * 44)
    if 问题:
        print(f"【失败】{失败} 项违例：")
        for p in 问题:
            print("  -", p)
        return 1
    print(f"【通过】{通过} 项检查全部符合 schema 契约")
    return 0


if __name__ == "__main__":
    sys.exit(main())