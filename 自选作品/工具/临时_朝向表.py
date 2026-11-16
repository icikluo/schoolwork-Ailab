# 临时：每件家具四个方向各渲染一次，用来判断「正面」朝哪。
from pathlib import Path

根 = Path(r"D:\lab\自选作品")
核心 = "\n".join((根 / "测试" / "真房间合成.html").read_text(encoding="utf-8").splitlines()[37:221])
核心 = 核心.replace(
    'var ibv = g.bufferViews[g.images[0].bufferView], 图起 = ibv.byteOffset || 0;',
    'var 图 = g.images && g.images[0] ? g.images[0] : null;\n'
    '    var ibv = 图 ? g.bufferViews[图.bufferView] : null, 图起 = ibv ? (ibv.byteOffset || 0) : 0;')
核心 = 核心.replace(
    '图字节: bin.subarray(图起, 图起 + ibv.byteLength), 图类型: g.images[0].mimeType };',
    '图字节: ibv ? bin.subarray(图起, 图起 + ibv.byteLength) : null, 图类型: 图 ? 图.mimeType : "" };')

模型 = ["木桌", "椅子", "书架", "转角桌", "矮架", "落地灯", "盆栽", "坐垫堆", "便当盒"]
脚本 = "\n".join(f'<script src="../数据/模型/{m}.js"></script>' for m in 模型)

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>家具朝向表</title>
<style>
  body {{ margin:0; background:#F6F1E8; font-family:"Microsoft YaHei",sans-serif; color:#3C4A2E; }}
  h1 {{ font-size:14px; margin:8px 16px 4px; }}
  .排 {{ display:flex; flex-wrap:wrap; gap:8px; padding:0 12px 12px; }}
  .格 {{ background:#fff; border:1px solid #D8CFB8; border-radius:10px; padding:5px; }}
  canvas {{ display:block; }}
  .名 {{ font-size:11.5px; margin:3px 2px 0; font-family:Consolas,monospace; }}
</style></head>
<body>
<h1>每格四象限：左上=从 +Z 看（正面？） 右上=从 −Z 看 左下=从 +X 看 右下=俯视 +Y</h1>
<div class="排" id="排"></div>
{脚本}
<script>
"use strict";
(function () {{
{核心}

  var 名单 = [{",".join('"' + m + '"' for m in 模型)}];
  var 排 = document.getElementById("排");
  var 宽 = 300, 高 = 300;

  function 画一个(数据, 标题) {{
    var 盒 = document.createElement("div"); 盒.className = "格";
    var 布 = document.createElement("canvas"); 布.width = 宽; 布.height = 高;
    盒.appendChild(布);
    var 名 = document.createElement("div"); 名.className = "名"; 名.textContent = 标题;
    盒.appendChild(名); 排.appendChild(盒);

    var gl = 布.getContext("webgl2", {{ antialias: true, alpha: false }});
    gl.enable(gl.DEPTH_TEST); gl.clearColor(0.98, 0.97, 0.94, 1);

    var 模 = 解析GLB(解b64(数据.b64));
    var 数 = 模.位置.length / 3;
    var 交错 = new Float32Array(数 * 8);
    for (var i = 0; i < 数; i++) {{
      交错[i*8] = 模.位置[i*3]; 交错[i*8+1] = 模.位置[i*3+1]; 交错[i*8+2] = 模.位置[i*3+2];
      交错[i*8+3] = 模.法线[i*3]; 交错[i*8+4] = 模.法线[i*3+1]; 交错[i*8+5] = 模.法线[i*3+2];
      交错[i*8+6] = 模.uv[i*2]; 交错[i*8+7] = 模.uv[i*2+1];
    }}
    var vb = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, vb);
    gl.bufferData(gl.ARRAY_BUFFER, 交错, gl.STATIC_DRAW);
    var ib = gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, 模.索引, gl.STATIC_DRAW);

    var 小 = [1e9,1e9,1e9], 大 = [-1e9,-1e9,-1e9];
    for (var k = 0; k < 数; k++) for (var a = 0; a < 3; a++) {{
      var v = 模.位置[k*3+a];
      if (v < 小[a]) 小[a] = v; if (v > 大[a]) 大[a] = v;
    }}
    var 心 = [(小[0]+大[0])/2, (小[1]+大[1])/2, (小[2]+大[2])/2];
    var 径 = Math.max(大[0]-小[0], 大[1]-小[1], 大[2]-小[2]) * 0.5 || 1;
    var 距 = 径 * 3.2;

    var 程 = 建程序(gl, 贴图顶点, 贴图片元);
    var 纹理 = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, 纹理);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);

    var 就绪 = 数据.有贴图
      ? createImageBitmap(new Blob([模.图字节], {{ type: 模.图类型 }}))
      : Promise.resolve(null);
    就绪.then(function (位图) {{
      if (位图) gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, 位图);
      else gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, 1, 1, 0, gl.RGB, gl.UNSIGNED_BYTE,
                         new Uint8Array([214, 199, 178]));

      var 视角 = [
        {{ 眼: [心[0], 心[1] + 径*0.25, 心[2] + 距], 标: "+Z" }},
        {{ 眼: [心[0], 心[1] + 径*0.25, 心[2] - 距], 标: "-Z" }},
        {{ 眼: [心[0] + 距, 心[1] + 径*0.25, 心[2]], 标: "+X" }},
        {{ 眼: [心[0] + 径*0.01, 心[1] + 距, 心[2] + 径*0.01], 标: "俯" }}
      ];
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      视角.forEach(function (视, i) {{
        var x = (i % 2) * (宽/2), y = (i < 2) ? (高/2) : 0;
        gl.viewport(x, y, 宽/2, 高/2);
        gl.useProgram(程);
        var 绑 = function (nm, 位, 分) {{
          var l = gl.getAttribLocation(程, nm); if (l < 0) return;
          gl.enableVertexAttribArray(l);
          gl.vertexAttribPointer(l, 分, gl.FLOAT, false, 32, 位);
        }};
        gl.bindBuffer(gl.ARRAY_BUFFER, vb);
        绑("aPosition", 0, 3); 绑("aNormal", 12, 3); 绑("aUV", 24, 2);
        gl.uniformMatrix4fv(gl.getUniformLocation(程, "uProj"), false, 透视(0.80, 1, 距*0.05, 距*4));
        gl.uniformMatrix4fv(gl.getUniformLocation(程, "uView"), false, 观察(视.眼, 心, [0,1,0]));
        gl.uniformMatrix4fv(gl.getUniformLocation(程, "uModel"), false, 单位());
        gl.uniformMatrix3fv(gl.getUniformLocation(程, "uNormalMat"), false, 法线阵3());
        gl.uniform1i(gl.getUniformLocation(程, "uTex"), 0);
        gl.drawElements(gl.TRIANGLES, 模.索引.length,
          (模.索引 instanceof Uint32Array) ? gl.UNSIGNED_INT : gl.UNSIGNED_SHORT, 0);
      }});
      名.textContent = 标题 + " | " + 数据.三角形数.toLocaleString() + "面 | "
        + (大[0]-小[0]).toFixed(2) + "×" + (大[1]-小[1]).toFixed(2) + "×" + (大[2]-小[2]).toFixed(2);
    }}).catch(function (e) {{ 名.textContent = 标题 + " 失败 " + e.message; }});
  }}

  名单.forEach(function (n) {{
    var 数据 = window[n];
    if (!数据) {{ 排.innerHTML += "<div>" + n + " 未加载</div>"; return; }}
    画一个(数据, n);
  }});
}})();
</script>
</body></html>
"""
(根 / "测试" / "临时_朝向表.html").write_text(html, encoding="utf-8")
print("生成 测试/临时_朝向表.html", len(html))
