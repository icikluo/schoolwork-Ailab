# -*- coding: utf-8 -*-
"""
glb嵌入.py —— 把 GLB 模型转成「数据/xxx.js」（base64 内嵌），供零依赖页面使用。

做了什么：
  1. 剥离骨骼数据（JOINTS_0 / WEIGHTS_0 / skins / inverseBindMatrices）——
     当前只静态展示，不播骨骼动画，可省约 45% 体积；
  2. 贴图缩到 1024（需 Pillow）——4096 贴图对网页展示是浪费；
  3. 重建一个最小 GLB（只留 POSITION / NORMAL / TEXCOORD_0 / indices / 贴图）；
  4. base64 后写成 数据/<名>.js：window.<变量名> = { 名, b64, 顶点数, 三角形数, ... }

用法：
  python 工具/glb嵌入.py 美术/男孩玩偶3d模型.glb 数据/角色模型.js 角色模型
  python 工具/glb嵌入.py 美术/迷你客厅3d模型.glb 数据/房间模型.js 房间模型

注意：产物是「构建产物」，由 Python 离线生成；网页运行时不再依赖任何转换工具。
"""
import struct
import json
import base64
import sys
import io
import os

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


def 转换(输入, 输出js, 变量名, 贴图边=1024):
    gltf, bin数据 = 读glb(输入)
    mesh = gltf["meshes"][0]
    prims = mesh["primitives"]
    assert len(prims) == 1, "暂只支持单 primitive 模型"
    pr = prims[0]
    at = pr["attributes"]

    pos字节, pos_ac = 取访问器字节(gltf, bin数据, at["POSITION"])
    nor字节, _ = 取访问器字节(gltf, bin数据, at["NORMAL"])
    uv字节, _ = 取访问器字节(gltf, bin数据, at["TEXCOORD_0"])
    idx字节, idx_ac = 取访问器字节(gltf, bin数据, pr["indices"])
    assert idx_ac["componentType"] == 5125, "索引不是 u32"

    # 贴图
    图 = gltf["images"][0]
    bv = gltf["bufferViews"][图["bufferView"]]
    起 = bv.get("byteOffset", 0)
    原图 = bin数据[起:起 + bv["byteLength"]]
    新图, 贴图说明 = 缩贴图(原图, 贴图边)

    # 组装新 BIN（顺序：pos / nor / uv / idx / img，各 4 字节对齐）
    段 = []
    偏移 = {}
    游标 = 0
    for 名, 字节 in [("pos", pos字节), ("nor", nor字节), ("uv", uv字节),
                     ("idx", idx字节), ("img", 新图)]:
        偏移[名] = 游标
        段.append(对齐4(字节))
        游标 += len(对齐4(字节))
    新bin = b"".join(段)

    顶点数 = pos_ac["count"]
    三角形数 = idx_ac["count"] // 3

    新gltf = {
        "asset": {"version": "2.0", "generator": "glb嵌入.py（精简：去骨骼/缩贴图）"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": 变量名, "mesh": 0}],
        "meshes": [{"name": 变量名, "primitives": [{
            "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
            "indices": 3, "material": 0, "mode": 4}]}],
        "materials": [{"name": "主材质", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0},
            "metallicFactor": 0.0, "roughnessFactor": 0.9}}],
        "textures": [{"source": 0, "sampler": 0}],
        "samplers": [{"magFilter": 9729, "minFilter": 9987,
                      "wrapS": 10497, "wrapT": 10497}],
        "images": [{"name": "贴图.jpg", "mimeType": "image/jpeg", "bufferView": 4}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 顶点数,
             "type": "VEC3",
             "min": pos_ac.get("min"), "max": pos_ac.get("max")},
            {"bufferView": 1, "componentType": 5126, "count": 顶点数, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": 顶点数, "type": "VEC2"},
            {"bufferView": 3, "componentType": 5125, "count": idx_ac["count"],
             "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 偏移["pos"], "byteLength": len(pos字节)},
            {"buffer": 0, "byteOffset": 偏移["nor"], "byteLength": len(nor字节)},
            {"buffer": 0, "byteOffset": 偏移["uv"], "byteLength": len(uv字节)},
            {"buffer": 0, "byteOffset": 偏移["idx"], "byteLength": len(idx字节)},
            {"buffer": 0, "byteOffset": 偏移["img"], "byteLength": len(新图)},
        ],
        "buffers": [{"byteLength": len(新bin)}],
    }

    # 组 GLB
    j = json.dumps(新gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    j += b" " * ((4 - len(j) % 4) % 4)
    总长 = 12 + 8 + len(j) + 8 + len(新bin)
    新glb = (struct.pack("<III", 0x46546C67, 2, 总长)
             + struct.pack("<II", len(j), 0x4E4F534A) + j
             + struct.pack("<II", len(新bin), 0x004E4942) + 新bin)

    b64 = base64.b64encode(新glb).decode("ascii")
    包围 = {"min": pos_ac.get("min"), "max": pos_ac.get("max")}
    js = ("// 本文件由 工具/glb嵌入.py 生成，请勿手改。\n"
          "// 源模型：" + os.path.basename(输入) + "\n"
          "window." + 变量名 + " = {\n"
          "  名: " + json.dumps(变量名, ensure_ascii=False) + ",\n"
          "  顶点数: " + str(顶点数) + ",\n"
          "  三角形数: " + str(三角形数) + ",\n"
          "  包围盒: " + json.dumps(包围) + ",\n"
          "  b64: \"" + b64 + "\"\n"
          "};\n")
    open(输出js, "w", encoding="utf-8").write(js)

    原大小 = os.path.getsize(输入)
    print(f"完成：{输入}")
    print(f"  顶点 {顶点数:,} / 三角形 {三角形数:,}")
    print(f"  贴图 {贴图说明}")
    print(f"  体积 {原大小/1048576:.1f}MB → GLB {len(新glb)/1048576:.1f}MB"
          f" → JS {len(js)/1048576:.1f}MB（{len(js)*100//原大小}%）")
    print(f"  输出 {输出js}（window.{变量名}）")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    转换(sys.argv[1], sys.argv[2], sys.argv[3])
