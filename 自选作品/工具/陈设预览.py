# 临时：只加载家具（不加载 23MB 玩偶）的陈设预览台。
# 陈设表直接从 养成.html 里抠出来，保证预览和正式页是同一份数据。
import json
import re
from pathlib import Path

根 = Path(r"D:\lab\自选作品")
核心 = "\n".join((根 / "测试" / "真房间合成.html").read_text(encoding="utf-8").splitlines()[37:249])
核心 = 核心.replace(
    'var ibv = g.bufferViews[g.images[0].bufferView], 图起 = ibv.byteOffset || 0;',
    'var 图0 = g.images && g.images[0] ? g.images[0] : null;\n'
    '    var ibv = 图0 ? g.bufferViews[图0.bufferView] : null, 图起 = ibv ? (ibv.byteOffset || 0) : 0;')
核心 = 核心.replace(
    '图字节: bin.subarray(图起, 图起 + ibv.byteLength), 图类型: g.images[0].mimeType };',
    '图字节: ibv ? bin.subarray(图起, 图起 + ibv.byteLength) : null, 图类型: 图0 ? 图0.mimeType : "" };')

页 = (根 / "养成.html").read_text(encoding="utf-8")
m = re.search(r"    var 陈设 = \[.*?\n    \];", 页, re.S)
assert m, "养成.html 里没找到陈设表"
陈设 = m.group(0)
m2 = re.search(r"    var 偶位 = \{[^}]*\};", 页)
偶位 = m2.group(0) if m2 else "var 偶位 = { x: 0.34, z: -0.26, 缩放: 0.98, 朝向: -0.72 };"

名 = re.findall(r'名: "([^"]+)"', 陈设)
色表 = json.loads((根 / "测试" / "临时_平均色.json").read_text(encoding="utf-8"))
贴 = json.loads((根 / "测试" / "临时_贴图256.json").read_text(encoding="utf-8"))
贴JS = "{" + ",".join('"%s":"%s"' % (k, v) for k, v in 贴.items()) + "}"
色JS = "{" + ",".join(
    '"%s":[%s]' % (k, ",".join(str(round(x * 255)) for x in v)) if v else '"%s":[214,201,182]' % k
    for k, v in 色表.items()) + "}"
脚本 = "\n".join(f'<script src="../数据/模型/{n}.js"></script>' for n in 名)

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>陈设预览</title>
<style>
  body {{ margin:0; background:#F6F1E8; font-family:"Microsoft YaHei",sans-serif; color:#3C4A2E; }}
  h1 {{ font-size:14px; margin:8px 16px 2px; }}
  .说明 {{ font-size:12px; color:#8A9070; margin:0 16px 6px; }}
  #画布 {{ display:block; margin:0 16px; width:1080px; height:760px; background:#fff;
          border:1px solid #D8CFB8; border-radius:10px; }}
</style></head>
<body>
<h1>陈设预览（不含玩偶，灰盒子 = 玩偶站位，高 1.0）</h1>
<p class="说明">陈设表取自 养成.html；灰盒子高 1.0、宽 0.5，用来判断家具比例对不对。</p>
<canvas id="画布"></canvas>
{脚本}
<script>
"use strict";
(function () {{
{核心}
  var 画布 = document.getElementById("画布");

  {偶位}
  {陈设}

  var 色表 = {色JS};
  var 贴图像素 = {贴JS};
  function 参数(k, 缺) {{
    // file:// 下 Edge 会把 ?查询串 丢掉，只能走 #片段
    var 串 = decodeURIComponent((location.hash || "") + (location.search || ""));
    var m = 串.match(new RegExp("[#?&]" + k + "=(-?[0-9.]+)"));
    return m ? parseFloat(m[1]) : 缺;
  }}
  var 场景 = {{ 偏航: 参数("偏", 0.52), 俯仰: 参数("俯", 0.24), 距离: 参数("距", 5.6),
               眼目标: [0.10, 0.84, -0.32] }};

  function 启动() {{
    var 画 = 画布.getContext("webgl2", {{ antialias: true, alpha: false }});
    var 贴图 = 建程序(画, 贴图顶点, 贴图片元);
    var 纯色 = 建程序(画, 纯色顶点, 纯色片元);
    画.enable(画.DEPTH_TEST);
    画.enable(画.CULL_FACE);

    // 房间壳（与正式页同一套参数）
    var 壳 = {{ 位: [], 法: [], 色: [] }}, 壳索 = [];
    造盒(壳, 壳索, 0, -0.06, 0, 4.2, 0.12, 4.2, 颜色("#EBD9B8"));
    造盒(壳, 壳索, 0, 1.25, -2.10, 4.2, 2.5, 0.10, 颜色("#F6DFD6"));
    造盒(壳, 壳索, -2.10, 1.25, 0, 0.10, 2.5, 4.2, 颜色("#F1E4CF"));
    造盒(壳, 壳索, 0, 0.012, 0.15, 2.6, 0.024, 1.9, 颜色("#DCE8CF"));
    var 壳vb = 画.createBuffer(); 画.bindBuffer(画.ARRAY_BUFFER, 壳vb);
    画.bufferData(画.ARRAY_BUFFER, new Float32Array(壳.位), 画.STATIC_DRAW);
    var 壳cb = 画.createBuffer(); 画.bindBuffer(画.ARRAY_BUFFER, 壳cb);
    画.bufferData(画.ARRAY_BUFFER, new Float32Array(壳.色), 画.STATIC_DRAW);
    var 壳ib = 画.createBuffer(); 画.bindBuffer(画.ELEMENT_ARRAY_BUFFER, 壳ib);
    画.bufferData(画.ELEMENT_ARRAY_BUFFER, new Uint16Array(壳索), 画.STATIC_DRAW);

    // 玩偶占位盒：高 1.0（= 玩偶身高），宽厚 0.5
    var 盒 = {{ 位: [], 法: [], 色: [] }}, 盒索 = [];
    造盒(盒, 盒索, 偶位.x, 0.5 + 0.02, 偶位.z, 0.5, 1.0, 0.46, 颜色("#C9C2B4"));
    var 盒vb = 画.createBuffer(); 画.bindBuffer(画.ARRAY_BUFFER, 盒vb);
    画.bufferData(画.ARRAY_BUFFER, new Float32Array(盒.位), 画.STATIC_DRAW);
    var 盒cb = 画.createBuffer(); 画.bindBuffer(画.ARRAY_BUFFER, 盒cb);
    画.bufferData(画.ARRAY_BUFFER, new Float32Array(盒.色), 画.STATIC_DRAW);
    var 盒ib = 画.createBuffer(); 画.bindBuffer(画.ELEMENT_ARRAY_BUFFER, 盒ib);
    画.bufferData(画.ELEMENT_ARRAY_BUFFER, new Uint16Array(盒索), 画.STATIC_DRAW);

    // 家具
    var 件 = {{}};
    for (var k = 0; k < 陈设.length; k++) {{
      var 项 = 陈设[k], 数据 = window[项.名];
      document.title = "装 " + k + ":" + 项.名;
      if (!数据) {{ console.warn("缺模型 " + 项.名); continue; }}
      var 模 = 解析GLB(解b64(数据.b64));
      var 数 = 模.位置.length / 3, 交错 = new Float32Array(数 * 8);
      for (var i = 0; i < 数; i++) {{
        交错[i*8]=模.位置[i*3]; 交错[i*8+1]=模.位置[i*3+1]; 交错[i*8+2]=模.位置[i*3+2];
        交错[i*8+3]=模.法线[i*3]; 交错[i*8+4]=模.法线[i*3+1]; 交错[i*8+5]=模.法线[i*3+2];
        交错[i*8+6]=模.uv[i*2]; 交错[i*8+7]=模.uv[i*2+1];
      }}
      var vb = 画.createBuffer(); 画.bindBuffer(画.ARRAY_BUFFER, vb);
      画.bufferData(画.ARRAY_BUFFER, 交错, 画.STATIC_DRAW);
      var ib = 画.createBuffer(); 画.bindBuffer(画.ELEMENT_ARRAY_BUFFER, ib);
      画.bufferData(画.ELEMENT_ARRAY_BUFFER, 模.索引, 画.STATIC_DRAW);
      // 预览台把贴图离线拆成 256² 原始像素塞进来：同步上传，不经过 createImageBitmap，
      // 页面全程无 await，无头截图才等得到「全部装完」那一帧。
      var 纹理 = 画.createTexture(); 画.bindTexture(画.TEXTURE_2D, 纹理);
      var 像素 = 贴图像素[项.名];
      画.pixelStorei(画.UNPACK_ALIGNMENT, 1);
      if (像素) {{
        var 原 = 解b64(像素);
        画.texImage2D(画.TEXTURE_2D, 0, 画.RGB, 256, 256, 0, 画.RGB, 画.UNSIGNED_BYTE, 原);
        画.generateMipmap(画.TEXTURE_2D);
        画.texParameteri(画.TEXTURE_2D, 画.TEXTURE_MIN_FILTER, 画.LINEAR_MIPMAP_LINEAR);
      }} else {{
        var 彩 = 色表[项.名] || [214, 201, 182];
        画.texImage2D(画.TEXTURE_2D, 0, 画.RGB, 1, 1, 0, 画.RGB, 画.UNSIGNED_BYTE, new Uint8Array(彩));
        画.texParameteri(画.TEXTURE_2D, 画.TEXTURE_MIN_FILTER, 画.LINEAR);
      }}
      画.texParameteri(画.TEXTURE_2D, 画.TEXTURE_MAG_FILTER, 画.LINEAR);
      var 盒2 = 数据.包围盒;
      件[项.名] = {{ vb: vb, ib: ib, 数: 模.索引.length, 纹理: 纹理,
        高: Math.max(0.001, 盒2.max[1] - 盒2.min[1]),
        大: (模.索引 instanceof Uint32Array) ? 画.UNSIGNED_INT : 画.UNSIGNED_SHORT }};
    }}

    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = 画布.clientWidth * dpr, h = 画布.clientHeight * dpr;
    画布.width = w; 画布.height = h; 画.viewport(0, 0, w, h);
    画.clearColor(0.98, 0.97, 0.94, 1);
    画.clear(画.COLOR_BUFFER_BIT | 画.DEPTH_BUFFER_BIT);

    var cp = Math.cos(场景.俯仰);
    var 比 = w / h;
    var 距 = 场景.距离 * (比 > 1.45 ? Math.max(0.80, 1.45 / 比 * 1.06) : 1);
    var 眼 = [场景.眼目标[0] + 距*cp*Math.sin(场景.偏航),
              场景.眼目标[1] + 距*Math.sin(场景.俯仰),
              场景.眼目标[2] + 距*cp*Math.cos(场景.偏航)];
    var 投影 = 透视(40*Math.PI/180, 比, 0.1, 60);
    var 视图 = 观察(眼, 场景.眼目标, [0,1,0]);

    function 绑属性(程) {{
      var aP = 画.getAttribLocation(程, "aPosition"), aN = 画.getAttribLocation(程, "aNormal");
      return {{ P: aP, N: aN }};
    }}

    // 房间壳
    画.useProgram(纯色);
    画.uniformMatrix4fv(画.getUniformLocation(纯色, "uProj"), false, 投影);
    画.uniformMatrix4fv(画.getUniformLocation(纯色, "uView"), false, 视图);
    画.uniformMatrix4fv(画.getUniformLocation(纯色, "uModel"), false, 单位());
    画.uniformMatrix3fv(画.getUniformLocation(纯色, "uNormalMat"), false, 法线阵3());
    var aP0 = 画.getAttribLocation(纯色, "aPosition"), aN0 = 画.getAttribLocation(纯色, "aNormal"),
        aC0 = 画.getAttribLocation(纯色, "aColor");
    画.bindBuffer(画.ARRAY_BUFFER, 壳vb);
    画.enableVertexAttribArray(aP0); 画.enableVertexAttribArray(aN0);
    画.vertexAttribPointer(aP0, 3, 画.FLOAT, false, 12, 0);
    画.vertexAttribPointer(aN0, 3, 画.FLOAT, false, 12, 0);
    画.bindBuffer(画.ARRAY_BUFFER, 壳cb);
    画.enableVertexAttribArray(aC0);
    画.vertexAttribPointer(aC0, 3, 画.FLOAT, false, 12, 0);
    画.bindBuffer(画.ELEMENT_ARRAY_BUFFER, 壳ib);
    画.drawElements(画.TRIANGLES, 壳索.length, 画.UNSIGNED_SHORT, 0);

    // 玩偶占位盒
    画.bindBuffer(画.ARRAY_BUFFER, 盒vb);
    画.enableVertexAttribArray(aP0); 画.enableVertexAttribArray(aN0);
    画.vertexAttribPointer(aP0, 3, 画.FLOAT, false, 12, 0);
    画.vertexAttribPointer(aN0, 3, 画.FLOAT, false, 12, 0);
    画.bindBuffer(画.ARRAY_BUFFER, 盒cb);
    画.enableVertexAttribArray(aC0);
    画.vertexAttribPointer(aC0, 3, 画.FLOAT, false, 12, 0);
    画.bindBuffer(画.ELEMENT_ARRAY_BUFFER, 盒ib);
    画.drawElements(画.TRIANGLES, 盒索.length, 画.UNSIGNED_SHORT, 0);

    // 家具
    画.useProgram(贴图);
    画.uniformMatrix4fv(画.getUniformLocation(贴图, "uProj"), false, 投影);
    画.uniformMatrix4fv(画.getUniformLocation(贴图, "uView"), false, 视图);
    画.uniform1i(画.getUniformLocation(贴图, "uTex"), 0);
    var aP1 = 画.getAttribLocation(贴图, "aPosition"), aN1 = 画.getAttribLocation(贴图, "aNormal"),
        aU1 = 画.getAttribLocation(贴图, "aUV");
    画.enableVertexAttribArray(aP1); 画.enableVertexAttribArray(aN1); 画.enableVertexAttribArray(aU1);
    for (var k2 = 0; k2 < 陈设.length; k2++) {{
      var 项2 = 陈设[k2], 网 = 件[项2.名];
      if (!网) continue;
      var 缩 = 项2.高 / 网.高;
      画.bindBuffer(画.ARRAY_BUFFER, 网.vb);
      画.vertexAttribPointer(aP1, 3, 画.FLOAT, false, 32, 0);
      画.vertexAttribPointer(aN1, 3, 画.FLOAT, false, 32, 12);
      画.vertexAttribPointer(aU1, 2, 画.FLOAT, false, 32, 24);
      画.bindBuffer(画.ELEMENT_ARRAY_BUFFER, 网.ib);
      画.activeTexture(画.TEXTURE0); 画.bindTexture(画.TEXTURE_2D, 网.纹理);
      画.uniformMatrix4fv(画.getUniformLocation(贴图, "uModel"), false,
        乘(乘(平移(项2.x, 项2.y || 0, 项2.z), 绕Y(项2.朝向 || 0)), 缩放(缩, 缩, 缩)));
      画.uniformMatrix3fv(画.getUniformLocation(贴图, "uNormalMat"), false,
        法线阵(缩, 缩, 缩, 项2.朝向 || 0));
      画.drawElements(画.TRIANGLES, 网.数, 网.大, 0);
    }}
    document.title = (location.href + " | hash=" + location.hash + " | ") + "就绪 " + Object.keys(件).length + " 偏" + 场景.偏航 + " 俯" + 场景.俯仰 + " 距" + 场景.距离;
  }}

  try {{ 启动(); }} catch (e) {{ document.title = "失败 " + e.message; console.error(e); }}
}})();
</script>
</body></html>
"""
(根 / "测试" / "陈设预览.html").write_text(html, encoding="utf-8")
print("生成 测试/陈设预览.html", len(html), "件数", len(名))
