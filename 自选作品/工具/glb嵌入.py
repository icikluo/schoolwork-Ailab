# -*- coding: utf-8 -*-
"""
glb嵌入.py —— 把 GLB 模型转成「数据/xxx.js」（base64 内嵌），供零依赖页面使用。

做了什么：
  1. 默认**保留骨骼**（JOINTS_0 / WEIGHTS_0 / skins / inverseBindMatrices + 节点层级），
     可以绑定姿势、做动作；加 --去骨骼 才剥离，省约 45% 体积；
  2. 贴图缩到 1024（需 Pillow）——4096 贴图对网页展示是浪费；
  3. 重建一个最小 GLB（只留渲染必需的数据 + 贴图）；
  4. base64 后写成 数据/<名>.js：window.<变量名> = { 名, b64, 顶点数, 三角形数, 骨骼数, 包围盒 }

用法：
  python 工具/glb嵌入.py 美术/男孩玩偶3d模型.glb 数据/角色模型.js 角色模型
  python 工具/glb嵌入.py 美术/男孩玩偶3d模型.glb 数据/角色模型.js 角色模型 --去骨骼
  python 工具/glb嵌入.py 美术/迷你客厅3d模型.glb 数据/房间模型.js 房间模型

注意：产物是「构建产物」，由 Python 离线生成；网页运行时不再依赖任何转换工具。
"""
import struct
import json
import base64
import sys
import io
import os
import copy

try:
    from PIL import Image
except ImportError:
    Image = None

组件大小 = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
类型分量 = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def 读glb(路径):
    data = open(路径, "rb").read()
    magic, version, 总长 = struct.unpack("<III", data[:12])
    assert magic == 0x46546C67, "不是 GLB 文件"
    jlen, jtype = struct.unpack("<II", data[12:20])
    assert jtype == 0x4E4F534A
    gltf = json.loads(data[20:20 + jlen])
    off = 20 + jlen
    bin数据 = b""
    if off < 总长:
        blen, btype = struct.unpack("<II", data[off:off + 8])
        assert btype == 0x004E4942
        bin数据 = data[off + 8:off + 8 + blen]
    return gltf, bin数据


def 取访问器字节(gltf, bin数据, 序号):
    ac = gltf["accessors"][序号]
    bv = gltf["bufferViews"][ac["bufferView"]]
    起 = bv.get("byteOffset", 0) + ac.get("byteOffset", 0)
    单元 = 组件大小[ac["componentType"]] * 类型分量[ac["type"]]
    长 = ac["count"] * 单元
    assert not bv.get("byteStride"), "暂不支持交错布局"
    return bin数据[起:起 + 长], ac


def 读数组(gltf, bin数据, 序号):
    """把 accessor 读成「扁平数组」（list[float/int]），能处理 byteStride 交错布局。

    直接切字节的老做法只在「紧凑排列」时成立；Tripo 的部分导出把 POSITION 的
    byteStride 写成 12（=3×float，其实是紧凑的），也有写成 16/24 的真交错，
    那种必须按 stride 逐元素拷。
    """
    import array as _array
    ac = gltf["accessors"][序号]
    bv = gltf["bufferViews"][ac["bufferView"]]
    起 = bv.get("byteOffset", 0) + ac.get("byteOffset", 0)
    分量 = 类型分量[ac["type"]]
    单元字节 = 组件大小[ac["componentType"]]
    紧凑 = 单元字节 * 分量
    stride = bv.get("byteStride") or 紧凑
    格式 = {5126: "f", 5125: "I", 5123: "H", 5121: "B"}[ac["componentType"]]
    n = ac["count"]
    if stride == 紧凑:
        return list(_array.array(格式, bin数据[起:起 + n * 紧凑]))
    出 = []
    单元素 = _array.array(格式)
    for i in range(n):
        o = 起 + i * stride
        单元素 = _array.array(格式, bin数据[o:o + 紧凑])
        出.extend(单元素)
    return 出


def 算法线(位置, 索引):
    """按面积加权累加面法线再归一化（平滑着色）。虚拟模型常常不带 NORMAL。"""
    法 = [0.0] * len(位置)
    for t in range(0, len(索引), 3):
        a, b, c = 索引[t], 索引[t + 1], 索引[t + 2]
        ax, ay, az = 位置[a * 3], 位置[a * 3 + 1], 位置[a * 3 + 2]
        bx, by, bz = 位置[b * 3], 位置[b * 3 + 1], 位置[b * 3 + 2]
        cx, cy, cz = 位置[c * 3], 位置[c * 3 + 1], 位置[c * 3 + 2]
        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = cx - ax, cy - ay, cz - az
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        for v in (a, b, c):
            法[v * 3] += nx
            法[v * 3 + 1] += ny
            法[v * 3 + 2] += nz
    for v in range(len(法) // 3):
        x, y, z = 法[v * 3], 法[v * 3 + 1], 法[v * 3 + 2]
        l = (x * x + y * y + z * z) ** 0.5
        if l < 1e-12:
            法[v * 3], 法[v * 3 + 1], 法[v * 3 + 2] = 0.0, 1.0, 0.0
        else:
            法[v * 3] /= l
            法[v * 3 + 1] /= l
            法[v * 3 + 2] /= l
    return 法


def 聚类减面(位置, 索引, uv, 目标三角):
    """顶点聚类（grid clustering）减面：把每个格子里的顶点并成一个，落在格子质心。

    对「贴图驱动的粘土小物件」够用：轮廓保留，UV 取格子内平均，接缝会略糊但
    30 万面降到 3 万面时肉眼几乎只在边缘看出来。返回 (位置, 索引, uv, 格边长)。
    """
    小 = [min(位置[i::3]) for i in range(3)]
    大 = [max(位置[i::3]) for i in range(3)]
    对角 = ((大[0] - 小[0]) ** 2 + (大[1] - 小[1]) ** 2 + (大[2] - 小[2]) ** 2) ** 0.5 or 1.0

    def 试(边长):
        桶 = {}
        顶点格 = []
        for v in range(len(位置) // 3):
            kx = int((位置[v * 3] - 小[0]) / 边长)
            ky = int((位置[v * 3 + 1] - 小[1]) / 边长)
            kz = int((位置[v * 3 + 2] - 小[2]) / 边长)
            k = (kx, ky, kz)
            g = 桶.get(k)
            if g is None:
                g = 桶[k] = [len(桶), 0.0, 0.0, 0.0, 0.0, 0.0, 0]
            顶点格.append(g[0])
            g[1] += 位置[v * 3]
            g[2] += 位置[v * 3 + 1]
            g[3] += 位置[v * 3 + 2]
            g[4] += uv[v * 2]
            g[5] += uv[v * 2 + 1]
            g[6] += 1
        新位置 = [0.0] * (len(桶) * 3)
        新uv = [0.0] * (len(桶) * 2)
        for g in 桶.values():
            i, n = g[0], g[6]
            新位置[i * 3] = g[1] / n
            新位置[i * 3 + 1] = g[2] / n
            新位置[i * 3 + 2] = g[3] / n
            新uv[i * 2] = g[4] / n
            新uv[i * 2 + 1] = g[5] / n
        新索引 = []
        for t in range(0, len(索引), 3):
            a, b, c = 顶点格[索引[t]], 顶点格[索引[t + 1]], 顶点格[索引[t + 2]]
            if a == b or b == c or a == c:
                continue          # 三个角落进同一格 → 退化三角形，丢掉
            新索引.extend((a, b, c))
        return 新位置, 新索引, 新uv, len(新索引) // 3

    低, 高 = 对角 / 400.0, 对角 / 4.0
    for _ in range(14):
        中 = (低 + 高) / 2
        试结果 = 试(中)
        if 试结果[3] > 目标三角:
            低 = 中
        else:
            高 = 中
    新位置, 新索引, 新uv, 三角数 = 试(高)
    return 新位置, 新索引, 新uv, 高


def 静态转换(输入, 输出js, 变量名, 贴图边=1024, 目标三角=0, 落地=False):
    """静态（无骨骼）模型：焊接顶点 → 补法线 → 可选减面 → 重建 GLB。

    相比老路径多做三件事，都是被这批模型逼出来的：
      1. 无索引（三角面汤）→ 顺序索引，再按位置焊接压缩顶点；
      2. 无 NORMAL → 面积加权累加后归一化，得到平滑法线；
      3. 面数过大 → 聚类减面到目标三角形数（默认不启用）。
    """
    gltf, bin数据 = 读glb(输入)
    pr = gltf["meshes"][0]["primitives"][0]
    at = pr["attributes"]
    位置 = [float(v) for v in 读数组(gltf, bin数据, at["POSITION"])]
    源顶点 = len(位置) // 3

    有索引 = "indices" in pr and pr["indices"] is not None
    if 有索引:
        索原始 = [int(v) for v in 读数组(gltf, bin数据, pr["indices"])]
    else:
        索原始 = list(range(源顶点))

    if "TEXCOORD_0" in at:
        uv原始 = [float(v) for v in 读数组(gltf, bin数据, at["TEXCOORD_0"])]
    else:
        uv原始 = [0.0] * (源顶点 * 2)

    # ---- 焊接：同位置顶点合并（三角面汤能压掉 3/4 顶点）----
    表 = {}
    顶点映射 = [0] * 源顶点
    位置2 = []
    uv2 = []
    for v in range(源顶点):
        k = (round(位置[v * 3], 6), round(位置[v * 3 + 1], 6), round(位置[v * 3 + 2], 6))
        j = 表.get(k)
        if j is None:
            j = 表[k] = len(位置2) // 3
            位置2.extend(k)
            uv2.extend((uv原始[v * 2], uv原始[v * 2 + 1]))
        顶点映射[v] = j
    索引2 = [顶点映射[t] for t in 索原始]

    # 丢掉退化三角形
    索引2 = [i for t in range(0, len(索引2), 3)
             for i in (索引2[t], 索引2[t + 1], 索引2[t + 2])
             if not (索引2[t] == 索引2[t + 1] or 索引2[t + 1] == 索引2[t + 2] or 索引2[t] == 索引2[t + 2])]

    减面说明 = ""
    if 目标三角 and len(索引2) // 3 > 目标三角:
        原三角 = len(索引2) // 3
        位置2, 索引2, uv2, 边长 = 聚类减面(位置2, 索引2, uv2, 目标三角)
        减面说明 = f"，聚类减面 {原三角:,} → {len(索引2) // 3:,} 三角形（格 {边长:.4f}）"

    # ---- 落地归一化：底面 y=0、水平中心落在原点 ----
    # Tripo 导出常把模型摆在「以原点为中心」的位置（y 从 -1 到 1），直接往场景里放
    # 会一半埋进地板。统一搬到「脚踩 y=0、站在原点」，页面就只需关心 x/z 与朝向。
    归一说明 = ""
    if 落地:
        小0 = [min(位置2[i::3]) for i in range(3)]
        大0 = [max(位置2[i::3]) for i in range(3)]
        移 = [-(小0[0] + 大0[0]) / 2, -小0[1], -(小0[2] + 大0[2]) / 2]
        for v in range(len(位置2) // 3):
            位置2[v * 3] += 移[0]
            位置2[v * 3 + 1] += 移[1]
            位置2[v * 3 + 2] += 移[2]
        归一说明 = f"，落地归一（位移 {移[0]:.2f},{移[1]:.2f},{移[2]:.2f}）"

    法线 = 算法线(位置2, 索引2)
    顶点数 = len(位置2) // 3
    三角形数 = len(索引2) // 3

    # ---- 打包 ----
    段列表 = []
    视图表 = []
    访问器 = []

    def 加段(字节, ac, 名):
        视图表.append({"buffer": 0,
                       "byteOffset": sum(len(对齐4(b)) for b in 段列表),
                       "byteLength": len(字节)})
        段列表.append(字节)
        新 = {"bufferView": len(视图表) - 1,
              "componentType": ac["componentType"],
              "count": ac["count"], "type": ac["type"]}
        if "min" in ac:
            新["min"] = ac["min"]
        if "max" in ac:
            新["max"] = ac["max"]
        访问器.append(新)
        return len(访问器) - 1

    import array as _array
    pos_bytes = _array.array("f", 位置2).tobytes()
    nor_bytes = _array.array("f", 法线).tobytes()
    uv_bytes = _array.array("f", uv2).tobytes()
    if 顶点数 <= 65535:
        idx_bytes = _array.array("H", 索引2).tobytes()
        idx_ct = 5123
    else:
        idx_bytes = _array.array("I", 索引2).tobytes()
        idx_ct = 5125

    小 = [min(位置2[i::3]) for i in range(3)]
    大 = [max(位置2[i::3]) for i in range(3)]
    位 = 加段(pos_bytes, {"componentType": 5126, "count": 顶点数, "type": "VEC3",
                         "min": 小, "max": 大}, "pos")
    法 = 加段(nor_bytes, {"componentType": 5126, "count": 顶点数, "type": "VEC3"}, "nor")
    uv = 加段(uv_bytes, {"componentType": 5126, "count": 顶点数, "type": "VEC2"}, "uv")
    索 = 加段(idx_bytes, {"componentType": idx_ct, "count": len(索引2), "type": "SCALAR"}, "idx")

    # ---- 贴图（可有可无）----
    有图 = bool(gltf.get("images")) and "bufferView" in gltf["images"][0]
    if 有图:
        图 = gltf["images"][0]
        bv = gltf["bufferViews"][图["bufferView"]]
        起 = bv.get("byteOffset", 0)
        原图 = bin数据[起:起 + bv["byteLength"]]
        新图, 贴图说明 = 缩贴图(原图, 贴图边)
        图视图 = len(视图表)
        视图表.append({"buffer": 0,
                       "byteOffset": sum(len(对齐4(b)) for b in 段列表),
                       "byteLength": len(新图)})
        新bin = b"".join(对齐4(b) for b in 段列表) + 对齐4(新图)
        材质 = {"name": "主材质", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0}, "metallicFactor": 0.0, "roughnessFactor": 0.9}}
        扩展 = {"textures": [{"source": 0, "sampler": 0}],
              "samplers": [{"magFilter": 9729, "minFilter": 9987,
                            "wrapS": 10497, "wrapT": 10497}],
              "images": [{"name": "贴图.jpg", "mimeType": "image/jpeg", "bufferView": 图视图}]}
    else:
        新图 = b""
        贴图说明 = "无贴图（纯色）"
        新bin = b"".join(对齐4(b) for b in 段列表)
        材质 = {"name": "主材质", "pbrMetallicRoughness": {
            "baseColorFactor": [0.86, 0.80, 0.72, 1.0],
            "metallicFactor": 0.0, "roughnessFactor": 0.9}}
        扩展 = {}

    新gltf = {
        "asset": {"version": "2.0",
                  "generator": "glb嵌入.py（静态：焊接+补法线" + ("+减面" if 减面说明 else "") + "）"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": 变量名, "mesh": 0}],
        "meshes": [{"name": 变量名, "primitives": [{
            "attributes": {"POSITION": 位, "NORMAL": 法, "TEXCOORD_0": uv},
            "indices": 索, "material": 0, "mode": 4}]}],
        "materials": [材质],
        "accessors": 访问器,
        "bufferViews": 视图表,
        "buffers": [{"byteLength": len(新bin)}],
    }
    新gltf.update(扩展)

    j = json.dumps(新gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    j += b" " * ((4 - len(j) % 4) % 4)
    总长 = 12 + 8 + len(j) + 8 + len(新bin)
    新glb = (struct.pack("<III", 0x46546C67, 2, 总长)
             + struct.pack("<II", len(j), 0x4E4F534A) + j
             + struct.pack("<II", len(新bin), 0x004E4942) + 新bin)

    b64 = base64.b64encode(新glb).decode("ascii")
    js = ("// 本文件由 工具/glb嵌入.py 生成，请勿手改。\n"
          "// 源模型：" + os.path.basename(输入) + "（静态，焊接+补法线，无骨骼）\n"
          "window." + 变量名 + " = {\n"
          "  名: " + json.dumps(变量名, ensure_ascii=False) + ",\n"
          "  顶点数: " + str(顶点数) + ",\n"
          "  三角形数: " + str(三角形数) + ",\n"
          "  骨骼数: 0,\n"
          "  有贴图: " + ("true" if 有图 else "false") + ",\n"
          "  包围盒: " + json.dumps({"min": 小, "max": 大}) + ",\n"
          "  b64: \"" + b64 + "\"\n"
          "};\n")
    open(输出js, "w", encoding="utf-8").write(js)

    原大小 = os.path.getsize(输入)
    print(f"完成：{os.path.basename(输入)}")
    print(f"  顶点 {顶点数:,} / 三角形 {三角形数:,}{减面说明}{归一说明}")
    print(f"  贴图 {贴图说明}")
    print(f"  体积 {原大小/1048576:.1f}MB → GLB {len(新glb)/1048576:.1f}MB"
          f" → JS {len(js)/1048576:.1f}MB（{len(js)*100//原大小}%）")
    print(f"  输出 {输出js}（window.{变量名}）")
    return {"顶点数": 顶点数, "三角形数": 三角形数, "最小": 小, "最大": 大}


def 缩贴图(jpeg字节, 目标边=1024, 质量=85):
    if Image is None:
        print("  ! 未安装 Pillow，贴图保持原尺寸")
        return jpeg字节, "原尺寸"
    im = Image.open(io.BytesIO(jpeg字节)).convert("RGB")
    原 = im.size
    if max(原) > 目标边:
        im.thumbnail((目标边, 目标边), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=质量)
    return buf.getvalue(), f"{原[0]}x{原[1]} → {im.size[0]}x{im.size[1]}"


def 对齐4(b):
    补 = (4 - len(b) % 4) % 4
    return b + b"\x00" * 补


def 转换(输入, 输出js, 变量名, 贴图边=1024, 去骨骼=False, 目标三角=0, 落地=False):
    gltf, bin数据 = 读glb(输入)
    mesh = gltf["meshes"][0]
    prims = mesh["primitives"]
    assert len(prims) == 1, "暂只支持单 primitive 模型"
    pr = prims[0]
    at = pr["attributes"]

    有骨骼 = ("JOINTS_0" in at and "WEIGHTS_0" in at and bool(gltf.get("skins")))
    保留骨骼 = 有骨骼 and not 去骨骼

    if not 保留骨骼:
        # 静态模型走新路径：能处理无索引 / 无法线 / 交错 stride / 需要减面
        return 静态转换(输入, 输出js, 变量名, 贴图边=贴图边, 目标三角=目标三角, 落地=落地)

    # ---- 逐段收集字节，同时登记 bufferView / accessor ----
    段列表 = []
    访问器 = []
    视图表 = []

    def 加段(名, 字节, ac):
        视图表.append({"buffer": 0,
                       "byteOffset": sum(len(对齐4(b)) for _, b in 段列表),
                       "byteLength": len(字节)})
        段列表.append((名, 字节))
        新 = {"bufferView": len(视图表) - 1,
              "componentType": ac["componentType"],
              "count": ac["count"], "type": ac["type"]}
        if "min" in ac: 新["min"] = ac["min"]
        if "max" in ac: 新["max"] = ac["max"]
        访问器.append(新)
        return len(访问器) - 1

    位 = 加段("pos", *取访问器字节(gltf, bin数据, at["POSITION"]))
    法 = 加段("nor", *取访问器字节(gltf, bin数据, at["NORMAL"]))
    uv = 加段("uv", *取访问器字节(gltf, bin数据, at["TEXCOORD_0"]))
    索 = 加段("idx", *取访问器字节(gltf, bin数据, pr["indices"]))
    idx_ac = gltf["accessors"][pr["indices"]]
    pos_ac = gltf["accessors"][at["POSITION"]]
    assert idx_ac["componentType"] in (5123, 5125), "索引类型异常"

    新属性 = {"POSITION": 位, "NORMAL": 法, "TEXCOORD_0": uv}
    骨数 = 0
    if 保留骨骼:
        骨数 = len(gltf["skins"][0]["joints"])
        新属性["JOINTS_0"] = 加段("jt", *取访问器字节(gltf, bin数据, at["JOINTS_0"]))
        新属性["WEIGHTS_0"] = 加段("wt", *取访问器字节(gltf, bin数据, at["WEIGHTS_0"]))
        存骨骼矩阵 = 加段("ibm", *取访问器字节(gltf, bin数据,
                                             gltf["skins"][0]["inverseBindMatrices"]))

    # ---- 贴图 ----
    图 = gltf["images"][0]
    bv = gltf["bufferViews"][图["bufferView"]]
    起 = bv.get("byteOffset", 0)
    原图 = bin数据[起:起 + bv["byteLength"]]
    新图, 贴图说明 = 缩贴图(原图, 贴图边)
    图视图 = len(视图表)
    视图表.append({"buffer": 0,
                   "byteOffset": sum(len(对齐4(b)) for _, b in 段列表),
                   "byteLength": len(新图)})

    新bin = b"".join(对齐4(b) for _, b in 段列表) + 对齐4(新图)

    顶点数 = pos_ac["count"]
    三角形数 = idx_ac["count"] // 3

    新gltf = {
        "asset": {"version": "2.0",
                  "generator": "glb嵌入.py（贴图缩放" + ("，保留骨骼" if 保留骨骼 else "，去骨骼") + "）"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": 变量名, "mesh": 0}],
        "meshes": [{"name": 变量名, "primitives": [{
            "attributes": 新属性, "indices": 索, "material": 0, "mode": 4}]}],
        "materials": [{"name": "主材质", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0},
            "metallicFactor": 0.0, "roughnessFactor": 0.9}}],
        "textures": [{"source": 0, "sampler": 0}],
        "samplers": [{"magFilter": 9729, "minFilter": 9987,
                      "wrapS": 10497, "wrapT": 10497}],
        "images": [{"name": "贴图.jpg", "mimeType": "image/jpeg", "bufferView": 图视图}],
        "accessors": 访问器,
        "bufferViews": 视图表,
        "buffers": [{"byteLength": len(新bin)}],
    }

    if 保留骨骼:
        # 节点树原样保留（骨骼名与层级），mesh / skin 索引重映射到 0
        节点 = []
        for n in gltf["nodes"]:
            m = copy.deepcopy(n)
            if "mesh" in m: m["mesh"] = 0
            if "skin" in m: m["skin"] = 0
            节点.append(m)
        新gltf["nodes"] = 节点
        新gltf["scenes"] = [{"nodes": gltf.get("scenes", [{}])[0].get("nodes", [0])}]
        新gltf["skins"] = [{"joints": gltf["skins"][0]["joints"],
                            "inverseBindMatrices": 存骨骼矩阵}]
        if "skeleton" in gltf["skins"][0]:
            新gltf["skins"][0]["skeleton"] = gltf["skins"][0]["skeleton"]

    # ---- 组 GLB ----
    j = json.dumps(新gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    j += b" " * ((4 - len(j) % 4) % 4)
    总长 = 12 + 8 + len(j) + 8 + len(新bin)
    新glb = (struct.pack("<III", 0x46546C67, 2, 总长)
             + struct.pack("<II", len(j), 0x4E4F534A) + j
             + struct.pack("<II", len(新bin), 0x004E4942) + 新bin)

    b64 = base64.b64encode(新glb).decode("ascii")
    包围 = {"min": pos_ac.get("min"), "max": pos_ac.get("max")}
    js = ("// 本文件由 工具/glb嵌入.py 生成，请勿手改。\n"
          "// 源模型：" + os.path.basename(输入) + ("（保留骨骼）" if 保留骨骼 else "（去骨骼）") + "\n"
          "window." + 变量名 + " = {\n"
          "  名: " + json.dumps(变量名, ensure_ascii=False) + ",\n"
          "  顶点数: " + str(顶点数) + ",\n"
          "  三角形数: " + str(三角形数) + ",\n"
          "  骨骼数: " + str(骨数) + ",\n"
          "  包围盒: " + json.dumps(包围) + ",\n"
          "  b64: \"" + b64 + "\"\n"
          "};\n")
    open(输出js, "w", encoding="utf-8").write(js)

    原大小 = os.path.getsize(输入)
    print(f"完成：{os.path.basename(输入)}")
    print(f"  顶点 {顶点数:,} / 三角形 {三角形数:,}" + (f" / 骨骼 {骨数}" if 骨数 else " / 无骨骼"))
    print(f"  贴图 {贴图说明}")
    print(f"  体积 {原大小/1048576:.1f}MB → GLB {len(新glb)/1048576:.1f}MB"
          f" → JS {len(js)/1048576:.1f}MB（{len(js)*100//原大小}%）")
    print(f"  输出 {输出js}（window.{变量名}）")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    目标 = 0
    for 参 in sys.argv:
        if 参.startswith("--三角="):
            目标 = int(参.split("=", 1)[1])
    转换(sys.argv[1], sys.argv[2], sys.argv[3],
         去骨骼=("--去骨骼" in sys.argv), 目标三角=目标, 落地=("--落地" in sys.argv))
