"""基准商店 · A3 双分支方案决斗的统一基准测试（两分支共用）

课程第 4 周要求：**设计统一基准测试输入，对比两分支的执行结果与代码清晰度**。

本脚本做三件事：
  1. 静态统计：读 自选作品/养成商店.js，算净代码行数、嵌套深度、圈复杂度
  2. 语义翻译：按 A3-方案选型标准.md 的 JS 语义子集，把分支实现翻译成 Python
  3. 穷举对拍：金币 0–50 × 每道具已购 0–上限 × 全部道具（含非法）共 150 条，
     与 契约期望() 逐条比对；并测 3000 次调用的耗时

时间口径：脚本只测 Python 翻译后的行为，不测浏览器里的真实 JS 耗时。
这一点写进报告，避免把"Python 复刻更快"当成"JS 更快"。

用法：
    python 测试/基准商店.py            # 对比当前工作区版本
    python 测试/基准商店.py --方案 a    # 只跑当前分支并打标签 a
"""
import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

根 = Path(r"D:\lab\自选作品")
实装文件 = 根 / "养成商店.js"


# ==================== 1. 静态统计 ====================

def 取实现块(源码):
    """去掉文件头注释与 IIFE 外壳，只保留「实现本体」用于统计。"""
    开始 = 源码.find("function 结算购买")
    if 开始 == -1:
        raise SystemExit("【失败】养成商店.js 里找不到 结算购买()")
    结束 = 源码.find("\n  window.养成系统", 开始)
    if 结束 == -1:
        结束 = len(源码)
    return 源码[开始:结束]


def 静态统计(源码):
    块 = 取实现块(源码)
    行 = [l for l in 块.splitlines() if l.strip()]
    净行 = len(行)
    # 嵌套深度：按大括号层级算最大深度（去掉字符串内的大括号影响较小，本用例可接受）
    深度 = 当前 = 0
    for 字 in 块:
        if 字 == "{":
            当前 += 1
            深度 = max(深度, 当前)
        elif 字 == "}":
            当前 -= 1
    # 圈复杂度：分支点计数 + 1
    分支 = len(re.findall(r"\bif\b|\belse if\b|\bfor\b|\bwhile\b|\bcase\b|\?|&&|\|\|", 块))
    return {"净代码行": 净行, "最大嵌套深度": 深度, "圈复杂度": 分支 + 1}


# ==================== 2. JS 语义子集翻译 ====================

class 不支持(Exception):
    pass


def 分词(源码):
    """极简分词：字符串、数字、标识符、运算符。"""
    词表 = []
    i = 0
    while i < len(源码):
        字 = 源码[i]
        if 字.isspace():
            i += 1
            continue
        if 源码.startswith("//", i):
            j = 源码.find("\n", i)
            i = len(源码) if j == -1 else j
            continue
        if 源码.startswith("/*", i):
            j = 源码.find("*/", i)
            i = len(源码) if j == -1 else j + 2
            continue
        if 字 in "\"'":
            引号 = 字
            j = i + 1
            while j < len(源码) and 源码[j] != 引号:
                if 源码[j] == "\\":
                    j += 1
                j += 1
            词表.append(("str", 源码[i + 1:j]))
            i = j + 1
            continue
        m = re.match(r"-?\d+(\.\d+)?", 源码[i:])
        if m:
            文 = m.group(0)
            词表.append(("num", float(文) if "." in 文 else int(文)))
            i += len(文)
            continue
        m = re.match(r"[A-Za-z_$\u4e00-\u9fff][A-Za-z0-9_$\u4e00-\u9fff]*", 源码[i:])
        if m:
            词 = m.group(0)
            i += len(词)
            # 与 Python 关键字的碰撞只影响 "function"（JS 关键字，Python 也保留），
            # 其余 JS 关键字不会误伤；统一改写成不冲突的名字。
            词 = {"function": "function_"}.get(词, 词)
            词表.append(("id", 词))
            continue
        for 符号 in ("===", "!==", "++", "--", "+=", "-=", "&&", "||", ">=", "<=", "=>"):
            if 源码.startswith(符号, i):
                词表.append(("op", 符号))
                i += len(符号)
                break
        else:
            词表.append(("op", 字))
            i += 1
    return 词表


def 翻译(源码, 函数名="结算购买"):
    # 顶层：跳过 "function <函数名>(...)" 头。
    词表 = 分词(源码)
    位置 = [0]
    写模式 = [False]

    # 跳过开头的 function_ / 函数名，进入参数表
    if 位置[0] < len(词表) and 词表[位置[0]][1] == "function_":
        位置[0] += 1
    if 位置[0] < len(词表) and 词表[位置[0]][1] == 函数名:
        位置[0] += 1

    def 取():
        if 位置[0] >= len(词表):
            raise 不支持("源码意外结束")
        词 = 词表[位置[0]]
        位置[0] += 1
        return 词

    def 看():
        return 词表[位置[0]] if 位置[0] < len(词表) else (None, None)

    def 期待(值):
        种类, 词 = 取()
        if 词 != 值:
            raise 不支持(f"期待 {值!r}，实际 {词!r}")
        return 词

    def 取值(变量):
        return 变量

    def 标识符(名):
        return 名

    def 表达式(变量):
        return 或表达式(变量)

    def 或表达式(变量):
        左 = 与表达式(变量)
        while 看() == ("op", "||"):
            取()
            右 = 与表达式(变量)
            左 = f"({左} if {左} else {右})"
        return 左

    def 与表达式(变量):
        左 = 比较表达式(变量)
        while 看() == ("op", "&&"):
            取()
            右 = 比较表达式(变量)
            左 = f"({右} if {左} else {左})"
        return 左

    def 比较表达式(变量):
        左 = 加减表达式(变量)
        映射 = {"===": "==", "!==": "!=", ">=": ">=", "<=": "<=", "==": "==", "!=": "!=", ">": ">", "<": "<"}
        while 看()[0] == "op" and 看()[1] in 映射:
            符 = 取()[1]
            右 = 加减表达式(变量)
            左 = f"({左} {映射[符]} {右})"
        return 左

    def 加减表达式(变量):
        左 = 项(变量)
        while 看()[0] == "op" and 看()[1] in ("+", "-"):
            符 = 取()[1]
            右 = 项(变量)
            左 = f"({左} {符} {右})"
        return 左

    def 项(变量):
        左 = 一元(变量)
        while 看()[0] == "op" and 看()[1] in ("*", "/", "%"):
            符 = 取()[1]
            右 = 一元(变量)
            左 = f"({左} {符} {右})"
        return 左

    def 一元(变量):
        if 看() == ("op", "!"):
            取()
            return f"(not {一元(变量)})"
        if 看() == ("op", "-"):
            取()
            return f"(-{一元(变量)})"
        return 基本值(变量)

    def 基本值(变量):
        种类, 词 = 看()
        if (种类, 词) == ("op", "("):
            取()
            值 = 表达式(变量)
            期待(")")
            return f"({值})"
        if 种类 == "id":
            # 注意：这段分支必须放在「(」分组之前被命中，且不能依赖位置比较；
            # 早期版本把 ( 分支放前面、又只在末尾处理 id，导致函数调用解析失败。
            取()
            if 词 in ("true", "false", "null", "undefined"):
                return {"true": "True", "false": "False", "null": "None", "undefined": "None"}[词]
            if 词 == "new":
                raise 不支持("new 表达式")
            if 看() == ("op", "("):
                取()
                参 = []
                if 看() != ("op", ")"):
                    while True:
                        参.append(表达式(变量))
                        if 看() == ("op", ","):
                            取()
                            continue
                        break
                期待(")")
                return 后缀(f"{词}({', '.join(参)})", 变量)
            return 后缀(标识符(词), 变量)
        if (种类, 词) == ("op", "["):
            取()
            项列表 = []
            if 看() != ("op", "]"):
                while True:
                    项列表.append(表达式(变量))
                    if 看() == ("op", ","):
                        取()
                        continue
                    break
            期待("]")
            return "[" + ", ".join(项列表) + "]"
        if (种类, 词) == ("op", "{"):
            取()
            对列表 = []
            if 看() != ("op", "}"):
                while True:
                    键类, 键 = 取()
                    if 键类 not in ("str", "num", "id"):
                        raise 不支持(f"对象键不合法：{键!r}")
                    期待(":")
                    值 = 表达式(变量)
                    对列表.append(f"{键!r}: {值}")
                    if 看() == ("op", ","):
                        取()
                        continue
                    break
            期待("}")
            return "{" + ", ".join(对列表) + "}"
        if 种类 == "num":
            取()
            return repr(词)
        if 种类 == "str":
            取()
            return repr(词)
        if 种类 == "id":
            # 注意：这段分支必须放在「(」分组之前被命中，否则函数调用会被当成括号表达式。
            取()
            if 词 in ("true", "false", "null", "undefined"):
                return {"true": "True", "false": "False", "null": "None", "undefined": "None"}[词]
            if 词 == "new":
                raise 不支持("new 表达式")
            if 看() == ("op", "("):
                取()
                参 = []
                if 看() != ("op", ")"):
                    while True:
                        参.append(表达式(变量))
                        if 看() == ("op", ","):
                            取()
                            continue
                        break
                期待(")")
                return 后缀(f"{词}({', '.join(参)})", 变量)
            return 后缀(标识符(词), 变量)
        raise 不支持(f"无法解析的表达式起始：{词!r}")

    def 后缀(已生成, 变量):
        while True:
            # 「类」是外层 set 变量，绝对不能用它兜住 token 类型
            种类, 词 = 看()
            if (种类, 词) == ("op", "["):
                取()
                键 = 表达式(变量)
                期待("]")
                已生成 = f"{已生成}[{键}]" if 写模式[0] else f"_取({已生成}, {键})"
            elif (种类, 词) == ("op", "."):
                取()
                类2, 名 = 取()
                if 类2 != "id":
                    raise 不支持("属性名不是标识符")
                # JS 属性访问在 Python 侧：后面紧跟 '(' 才是方法调用（obj.m()），
                # 其余属性按属性名生成（对象用点号；list 的 .length 由 _列 提供）。
                后面是调用 = (看() == ("op", "("))
                已生成 = f"{已生成}.{名}" if 后面是调用 else f"{已生成}.{名}" if 名 == "length" else f"{已生成}[{名!r}]"
            elif (种类, 词) == ("op", "("):
                # 方法调用：obj.m(...) → 记录求值后生成的 Python 表达式也要能调用
                取()
                实参 = []
                if 看() != ("op", ")"):
                    while True:
                        实参.append(表达式(变量))
                        if 看() == ("op", ","):
                            取()
                            continue
                        break
                期待(")")
                已生成 = f"{已生成}({', '.join(实参)})"
            else:
                return 已生成

    标点词 = {"var", "let", "const", "return", "if", "else", "throw", "for", "while", "function", "function_"}

    def 语句(变量, 缩进):
        行 = []
        # 注意：不能写 `类, 词 = 看()`——那会把外层的 set 变量「类」重新绑成字符串，
        # 之后所有同类比较（"id" == 类）全部失效，错误会伪装成「无法解析的语句起始」。
        # 「类」改为「种类」：类 是外层 set 变量，任何分支里写 `类, 词 = ...`
        # 都会把它重新绑成字符串，让后面的 类x/词x 判断全部错位（本次自检踩到两次）。
        # 前置自增/自减（i++、i--）先单独处理：它们不是表达式的一部分。
        种类, 词 = 看()
        if 种类 == "id" and 位置[0] + 1 < len(词表) and 词表[位置[0] + 1] in (("op", "++"), ("op", "--")):
            运算符 = 词表[位置[0] + 1][1]
            位置[0] += 2
            return [" " * 缩进 + f"{词} += 1" if 运算符 == "++" else " " * 缩进 + f"{词} -= 1"], 变量
        if 种类 == "id" and 位置[0] + 2 < len(词表) and 词表[位置[0] + 1] == ("op", "+") \
                and 词表[位置[0] + 2] == ("op", "="):
            位置[0] += 3
            return [" " * 缩进 + f"{词} = {词} + {表达式(变量)}"], 变量
        # if/return/var 的括号由各自分支处理，不能落进下面的「函数调用语句」。
        # 这里不再需要额外前置判断——见函数末尾的 dispatch。
        if 词 in ("var", "let", "const"):
            取()
            while True:
                类2, 名 = 取()
                if 类2 != "id":
                    raise 不支持("声明处不是标识符")
                变量.add(名)
                if 看() == ("op", "="):
                    取()
                    行.append(" " * 缩进 + f"{名} = {表达式(变量)}")
                else:
                    行.append(" " * 缩进 + f"{名} = None")
                if 看() == ("op", ","):
                    取()
                    continue
                break
            期待(";") if 看() == ("op", ";") else None
            return 行, 变量
        if 词 == "for":
            # 只支持 C 风格 for (初始化; 条件; 步进) { ... }，翻译成 while
            取()
            期待("(")
            初值 = []
            while 看() != ("op", ";"):
                种类x, 词x = 取()
                if 词x in ("var", "let", "const"):
                    continue
                变量.add(词x)
                期待("=")
                初值.append(f"{词x} = {表达式(变量)}")
                取() if 看() == ("op", ",") else None
            期待(";")
            条件 = 表达式(变量) if 看() != ("op", ";") else "True"
            期待(";")
            # 步进：i++ / i-- / i += n / i -= n / 普通赋值
            种类s, 词s = 看()
            if 种类s == "id" and 位置[0] + 1 < len(词表) and 词表[位置[0] + 1][1] in ("++", "--"):
                运算符 = 词表[位置[0] + 1][1]
                位置[0] += 2
                步进 = f"{词s} += 1" if 运算符 == "++" else f"{词s} -= 1"
            elif 种类s == "id" and 位置[0] + 1 < len(词表) and 词表[位置[0] + 1][1] in ("+=", "-="):
                运算符 = 词表[位置[0] + 1][1]
                位置[0] += 2
                步进 = f"{词s} {运算符} {表达式(变量)}"
            else:
                步进 = 表达式(变量)
            期待(")")
            内部 = []
            取块(内部, 变量, 缩进 + 4)
            行.extend(" " * 缩进 + s for s in 初值)
            行.append(" " * 缩进 + f"while {条件}:")
            体 = list(内部) or [" " * (缩进 + 4) + "pass"]
            体.append(" " * (缩进 + 4) + 步进)
            行.extend(体)
            return 行, 变量
        if 词 == "return":
            取()
            if 看() == ("op", ";"):
                取()
                return [" " * 缩进 + "return"], 变量
            值 = 表达式(变量)
            if 看() == ("op", ";"):
                取()
            return [" " * 缩进 + f"return {值}"], 变量
        if 词 == "throw":
            取()
            表达式(变量)
            期待(";")
            return [" " * 缩进 + "raise RuntimeError('实现抛出异常')"], 变量
        if 词 == "if":
            取()
            if 看() == ("op", "("):
                取()
                条件 = 表达式(变量)
                期待(")")
            else:
                条件 = 表达式(变量)
            内部 = []
            if 看() == ("op", "{"):
                取块(内部, 变量, 缩进 + 4)
            else:
                # 单行 if（不带花括号）：只解析一条语句
                子, 变量 = 语句(变量, 缩进 + 4)
                内部.extend(子)
            行.append(" " * 缩进 + f"if {条件}:")
            行.extend(内部 or [" " * (缩进 + 4) + "pass"])
            类2, 词2 = 看()
            if 词2 == "else":
                取()
                类3, 词3 = 看()
                if 词3 == "if":
                    子, 变量 = 语句(变量, 缩进)   # 递归处理 else if
                    行.extend(子)
                    return 行, 变量
                内部2 = []
                取块(内部2, 变量, 缩进 + 4)
                行.append(" " * 缩进 + "else:")
                行.extend(内部2 or [" " * (缩进 + 4) + "pass"])
            return 行, 变量
        # 赋值语句：x = ... / obj.k = ... / obj[k] = ...
        if 种类 == "id":
            # 左值不能用 _取 包装（那是读语义）——临时切到「写」模式再恢复
            写模式[0] = True
            左式 = 标识符(词)
            取()
            左式 = 后缀(左式, 变量)
            写模式[0] = False
            if 看() == ("op", "="):
                取()
                行.append(" " * 缩进 + f"{左式} = {表达式(变量)}")
                取() if 看() == ("op", ";") else None
                return 行, 变量
            # 不是赋值 → 回退为函数调用语句（后缀解析已经消费掉 name(...)）
            行.append(" " * 缩进 + 左式)
            取() if 看() == ("op", ";") else None
            return 行, 变量
        # 表达式语句（函数调用），如 合并写(...); / 画宠物();
        # 注意：这里不能再解包到「类」——它是外层 set 变量，解包会污染后续判断。
        if 种类 == "id" and 词 not in 标点词:
            值 = 表达式(变量)
            取() if 看() == ("op", ";") else None
            return [" " * 缩进 + 值], 变量
        raise 不支持(f"无法解析的语句起始：{词!r}")

    def 取块(行, 变量, 缩进):
        期待("{")
        while True:
            类y, 词y = 看()
            if 词y == "}":
                取()
                return
            子, 变量 = 语句(变量, 缩进)
            行.extend(子)

    # 顶层：函数头（function_ 与函数名）已在上面跳过，这里直接解析参数表
    期待("(")
    参名 = []
    if 看() != ("op", ")"):
        while True:
            种类, 词 = 取()
            if 种类 != "id":
                raise 不支持("参数名不是标识符")
            参名.append(词)
            if 看() == ("op", ","):
                取()
                continue
            break
    期待(")")
    # 注意：变量集合不能叫「变量」，否则会遮住外层 表达式(变量) 的参数名，
    # 导致函数内部把 set 当成函数调用（曾在自检时踩到）。
    已知变量 = set(参名)
    体 = []
    取块(体, 已知变量, 4)
    return 参名, "\n".join(体)


JS_工具函数 = r"""
import copy
import json

class _JSON:
    @staticmethod
    def parse(s):
        return s
    @staticmethod
    def stringify(v):
        return copy.deepcopy(v)

JSON = _JSON()

class _列(list):
    # 让 JS 的 .length 在 Python 侧可用
    @property
    def length(self):
        return len(self)

def _列表(值):
    return _列(值)

def _深拷(值):
    if isinstance(值, dict):
        return {k: _深拷(v) for k, v in 值.items()}
    if isinstance(值, list):
        return [_深拷(v) for v in 值]
    return 值

def _取(容器, 键):
    # 复刻 JS 语义：读不存在的键返回 undefined（Python 用 None），不抛 KeyError
    try:
        return 容器[键]
    except (KeyError, TypeError, IndexError):
        return None
"""

def 取辅助函数(源码):
    """提取「结算购买」之前、同级的普通函数（如 查道具），一并翻译。

    两分支都可能写辅助函数，基准必须能把它们一起翻译出来，
    否则会因「找不到函数」而误判某方案失败。
    """
    实现块 = 取实现块(源码)
    头 = 源码[:源码.find("function 结算购买")]
    结果 = []
    for 名 in ["查道具"]:
        m = re.search(r"function " + 名 + r"\s*\([^)]*\)\s*\{", 头)
        if not m:
            continue
        i = m.end()
        深 = 1
        while i < len(头) and 深 > 0:
            if 头[i] == "{":
                深 += 1
            elif 头[i] == "}":
                深 -= 1
            i += 1
        结果.append((名, 头[m.start():i]))
    return 结果


def 生成Python(源码):
    """把分支实现翻译成一个可执行的 Python 模块，并注入 JS 语义辅助函数。

    注意：这里必须先 取实现块()——整份文件开头是 IIFE 的 (function(){...})，
    直接分词会让 翻译() 从 IIFE 的括号开始解析（本次自检踩到）。
    若实现调用了同级辅助函数（如 查道具），这些函数也要一并翻译出来；
    「只允许用契约子集」由 测试/核对商店.py 的 B 组扫描。
    """
    辅助 = 取辅助函数(源码)
    参名, 体 = 翻译(取实现块(源码))

    辅助代码 = ""
    for 名, 文本 in 辅助:
        子参, 子体 = 翻译(文本, 名)
        辅助代码 += f"\n\ndef {名}({', '.join(子参)}):\n{子体 or '    pass'}\n"

    # 商店表注入：JS 里读 window.商店数据，Python 侧给一个同构的对象
    商店 = json.loads(re.search(r"window\.商店数据\s*=\s*(\{.*\});",
                               (根 / "数据" / "商店.js").read_text(encoding="utf-8"), re.S).group(1))
    辅助代码 += ("\n\nclass _窗口(dict):\n    def __getattr__(self, 名):\n        return self[名]\n"
            "window = _窗口()\n"
            "window['商店数据'] = {'道具': _列表([dict(d) for d in " + repr(商店["道具"]) + "])}\n")

    return JS_工具函数 + 辅助代码 + f"""

def 结算购买({', '.join(参名)}):
{体 or '    pass'}
"""


# ==================== 3. 穷举对拍 + 计时 ====================

def 载入契约():
    数据 = json.loads(re.search(r"window\.商店数据\s*=\s*(\{.*\});",
                               (根 / "数据" / "商店.js").read_text(encoding="utf-8"), re.S).group(1))
    道具 = 数据["道具"]
    价格 = {d["id"]: d["价格"] for d in 道具}
    上限 = {d["id"]: d["每日上限"] for d in 道具}

    def 期望(币, 已购, 道具id):
        if 道具id not in 价格:
            return {"结果": "无此道具", "剩余金币": 币, "价格": 0}
        if 已购 >= 上限[道具id]:
            return {"结果": "已达上限", "剩余金币": 币, "价格": 价格[道具id]}
        if 币 < 价格[道具id]:
            return {"结果": "金币不足", "剩余金币": 币, "价格": 价格[道具id]}
        return {"结果": "已购买", "剩余金币": 币 - 价格[道具id], "价格": 价格[道具id]}

    return 价格, 上限, 期望


def 造用例(价格, 上限):
    用例 = []
    for 币 in range(0, 51):
        for 道具id in list(价格) + ["蛋糕"]:
            for 已购 in range(0, 上限.get(道具id, 1) + 1):
                用例.append((币, 已购, 道具id))
    return 用例


def 跑方案(模块, 用例, 期望):
    结算 = 模块["结算购买"]  # exec 得到的是 dict 命名空间，不能按模块属性取
    错例 = []
    耗时 = []
    for 币, 已购, 道具id in 用例:
        存档 = {"金币": 币, "宠物": {"物品": {}}}
        每日 = {"日期": "2026-11-17", "购买": {道具id: 已购}}
        存档快照 = json.dumps(存档, sort_keys=True, ensure_ascii=False)
        起 = time.perf_counter()
        try:
            结果 = 结算(存档, 每日, 道具id, {})
        except Exception as e:  # 实现抛异常也算错
            raise SystemExit(f"【失败】结算购买 抛出异常：{type(e).__name__}: {e}")
        耗时.append((time.perf_counter() - 起) * 1000)
        期望值 = 期望(币, 已购, 道具id)
        实际 = {"结果": 结果.get("结果"), "剩余金币": 结果.get("剩余金币"), "价格": 结果.get("价格")}
        if 实际 != 期望值:
            错例.append((币, 已购, 道具id, 实际, 期望值))
        if json.dumps(存档, sort_keys=True, ensure_ascii=False) != 存档快照:
            错例.append((币, 已购, 道具id, "修改了入参存档", "不得修改入参"))
    耗时.sort()
    P95 = 耗时[int(len(耗时) * 0.95) - 1]
    return 错例, {"用例数": len(用例), "P95毫秒": round(P95, 6),
                  "中位毫秒": round(statistics.median(耗时), 6)}


def main():
    解析 = argparse.ArgumentParser()
    解析.add_argument("--方案", default="当前", help="a / b / 当前")
    参 = 解析.parse_args()

    源码 = 实装文件.read_text(encoding="utf-8")
    静态 = 静态统计(源码)
    价格, 上限, 期望 = 载入契约()
    用例 = 造用例(价格, 上限)

    翻译源码 = 生成Python(源码)
    命名空间 = {}
    exec(compile(翻译源码, "<分支实现>", "exec"), 命名空间)

    错例, 性能 = 跑方案(命名空间, 用例, 期望)

    结果 = {
        "方案": 参.方案,
        "正确性": f"{性能['用例数'] - len(错例)}/{性能['用例数']}",
        "通过率": round((性能["用例数"] - len(错例)) / 性能["用例数"] * 100, 2),
        "净代码行": 静态["净代码行"],
        "最大嵌套深度": 静态["最大嵌套深度"],
        "圈复杂度": 静态["圈复杂度"],
        "P95毫秒": 性能["P95毫秒"],
        "中位毫秒": 性能["中位毫秒"],
        "错例数": len(错例),
    }
    print(json.dumps(结果, ensure_ascii=False, indent=2))
    if 错例:
        print(f"\n【不通过】前 3 条错例：")
        for 币, 已购, 道具id, 实际, 期望值 in 错例[:3]:
            print(f"  金币={币} 已购={已购} 道具={道具id!r}\n    实际 {实际}\n    期望 {期望值}")
        return 1
    print(f"\n【通过】{参.方案} 方案：{性能['用例数']}/{性能['用例数']} 条用例全部正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
