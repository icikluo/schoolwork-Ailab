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


def 转换(输入, 输出js, 变量名, 贴图边=1024, 去骨骼=False):
    gltf, bin数据 = 读glb(输入)
    mesh = gltf["meshes"][0]
    prims = mesh["primitives"]
    assert len(prims) == 1, "暂只支持单 primitive 模型"
    pr = prims[0]
    at = pr["attributes"]

    有骨骼 = ("JOINTS_0" in at and "WEIGHTS_0" in at and bool(gltf.get("skins")))
    保留骨骼 = 有骨骼 and not 去骨骼

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
    转换(sys.argv[1], sys.argv[2], sys.argv[3], 去骨骼=("--去骨骼" in sys.argv))
