# -*- coding: utf-8 -*-
"""把「真房间合成」验证页里的渲染器，装配成正式的 养成.html。

为什么单独一个生成脚本：渲染器（561 行 WebGL）已经在验证页里调稳定了，
正式页只需要换外壳 + 加染色/宠物/存档/懒加载，不该把那 561 行复制一遍
然后在两个文件里各自演进。

用法：python 工具/生成养成页.py
输入：测试/真房间合成.html（渲染器来源）
输出：养成.html
"""
import io
import os
import sys

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
源 = os.path.join(根, "测试", "真房间合成.html")
出 = os.path.join(根, "养成.html")


def 提取渲染器(path):
    src = open(path, encoding="utf-8").read()
    a = src.index('"use strict";')
    b = src.rindex("})();") + len("})();")
    return src[a:b]


def 改(js, old, new):
    assert old in js, "未找到片段：" + old[:70]
    return js.replace(old, new, 1)


def 装配(js):
    # ---------- 顶部：去自检面板，改成进度回调 ----------
    js = 改(js, '''  var 画布 = document.getElementById("画布"), 自检 = document.getElementById("自检");
  var 行 = [];
  function 记(s) { 行.push(s); 自检.innerHTML = 行.join("\\n"); }''',
            '''  var 画布 = document.getElementById("画布");
  // 渲染器内部的过程信息只进控制台：生产页面上不该出现「骨骼定位」这类字眼
  function 记(s) { if (window.console && console.debug) console.debug("[小窝]", s); }''')

    # ---------- 启动签名 ----------
    js = 改(js, '''  async function 启动() {
    var t0 = performance.now();
    if (!window.房间模型 || !window.角色模型) throw new Error("模型数据未加载");

    var 画 = 画布.getContext("webgl2", { antialias: true, alpha: true });
    if (!画) { 自检.innerHTML = '<span class="失败">此页需要 WebGL2（蒙皮着色器用了动态索引）</span>'; return; }
    记("WebGL2：创建成功");''',
            '''  var 染 = {};                 // { 上衣:#hex, 裤子:#hex, 鞋:#hex }，缺省键表示保持原色
  async function 启动(选项) {
    var t0 = performance.now();
    染 = (选项 && 选项.染色) || {};
    if (!window.房间模型 || !window.角色模型) throw new Error("模型数据未加载");
    if (!document.createElement("canvas").getContext("webgl2")) throw new Error("NO_WEBGL2");

    var 画 = 画布.getContext("webgl2", { antialias: true, alpha: true });
    if (!画) throw new Error("NO_WEBGL2");''')

    # ---------- 蒙皮着色器：把模型空间的 y 传下去 ----------
    js = 改(js, '''    "uniform mat4 uBone[30];",
    "out vec3 vN; out vec2 vUV;",''',
            '''    "uniform mat4 uBone[30];",
    "out vec3 vN; out vec2 vUV; out float vY;",''')
    js = 改(js, '''    " vN = uNormalMat * n; vUV = aUV;",''',
            '''    " vY = aPosition.y; vN = uNormalMat * n; vUV = aUV;",''')

    # ---------- 蒙皮片元：按「高度带 + 底色」判定衣物后染色 ----------
    # 注意：着色器里的标识符必须是纯 ASCII。GLSL 不接受中文变量名，
    # 编译时报的是 "0:5: '?' : syntax error"，看不出跟中文有关——第三次踩这个坑了。
    js = 改(js, '''  var 蒙皮片元 = 贴图片元;''',
            '''  var 蒙皮片元 = 头 + [
    "in vec3 vN; in vec2 vUV; in float vY;",
    "uniform sampler2D uTex;",
    "uniform vec3 uTintTop, uTintPants, uTintShoes;",
    "uniform float uOnTop, uOnPants, uOnShoes;",
    "out vec4 o;",
    "void main(){",
    " vec3 base = texture(uTex, vUV).rgb;",
    " float lum = dot(base, vec3(0.299, 0.587, 0.114));",
    " float hi = max(max(base.r, base.g), base.b);",
    " float lo = min(min(base.r, base.g), base.b);",
    " float sat = (hi - lo) / max(hi, 0.001);",
    " vec3 tint = base; float w = 0.0;",
    // 鞋在最下面；牛仔裤是唯一明显偏蓝的色块；上衣是上身那片近白低饱和区域
    " if (uOnShoes > 0.5 && vY < 0.13 && lum > 0.50 && sat < 0.30) { tint = uTintShoes; w = 1.0; }",
    " else if (uOnPants > 0.5 && vY < 0.58 && base.b > base.r + 0.03 && sat > 0.10) { tint = uTintPants; w = 1.0; }",
    " else if (uOnTop > 0.5 && vY > 0.26 && lum > 0.56 && sat < 0.20) { tint = uTintTop; w = 1.0; }",
    // 用原贴图亮度当明暗系数，褶皱和阴影才不会被抹平
    " vec3 t = mix(base, tint * (0.50 + 0.60 * lum), w);",
    " vec3 n = normalize(vN);",
    " float hemi = n.y*0.5+0.5;",
    " vec3 amb = mix(vec3(0.60,0.56,0.52), vec3(1.02,0.99,0.94), hemi);",
    " float diff = max(dot(n, normalize(vec3(0.5,0.9,0.55))), 0.0);",
    " float fill = max(dot(n, normalize(vec3(-0.55,0.25,0.5))), 0.0);",
    " vec3 c = t * (amb*0.72 + vec3(1.0,0.95,0.86)*diff*0.40 + vec3(0.9,0.95,1.0)*fill*0.10);",
    " o = vec4(clamp(c,0.0,1.0), 1.0); }"
  ].join("\\n");''')

    # ---------- uniform 表 ----------
    js = 改(js, '''        uBone: 画.getUniformLocation(p, "uBone")''',
            '''        uBone: 画.getUniformLocation(p, "uBone"),
        uTintTop: 画.getUniformLocation(p, "uTintTop"),
        uTintPants: 画.getUniformLocation(p, "uTintPants"),
        uTintShoes: 画.getUniformLocation(p, "uTintShoes"),
        uOnTop: 画.getUniformLocation(p, "uOnTop"),
        uOnPants: 画.getUniformLocation(p, "uOnPants"),
        uOnShoes: 画.getUniformLocation(p, "uOnShoes")''')

    # ---------- 姿势：日常呼吸，挥手按需 ----------
    js = 改(js, '''    var 时间 = 0;
    function 画一帧() {''',
            '''    var 时间 = 0, 挥起 = -99, 挥到 = -1;
    function 缓入(x) { x = x < 0 ? 0 : x > 1 ? 1 : x; return x * x * (3 - 2 * x); }
    // 挥手为什么长这样：这只玩偶「肩到手」只有 0.26 长，而脑袋半宽 0.27、下颌在
    // y=0.52 —— 手一旦抬过肩高就整只钻进头里，画面上直接消失（试过 -1.9/-2.2 都是
    // 只剩一条断臂）。所以抬手只到侧平举，靠前臂+手腕上下扇 + 歪头来演「招手」。
    function 算姿势(t) {
      var 姿势 = {};
      if (脊 >= 0) 姿势[脊] = { 绕Z: Math.sin(t * 1.05) * 0.016 };
      if (头 >= 0) 姿势[头] = { 绕Y: Math.sin(t * 0.65) * 0.11, 绕Z: 0.02 };
      var 余 = 挥到 - t;
      if (余 > 0) {
        // 抬手 0.3s、落手 0.5s，两头都缓入缓出，手不会「啪」地跳起来
        var 幅 = 缓入(Math.min((t - 挥起) / 0.30, 余 / 0.50));
        var 摆 = Math.sin(t * 8.6);
        // 侧平举略偏前（绕Z 0.15），手才落在脸颊外面而不是贴到脸上
        if (右上臂 >= 0) 姿势[右上臂] = { 绕X: (-0.60 + 摆 * 0.15) * 幅, 绕Z: 0.15 * 幅 };
        if (右前臂 >= 0) 姿势[右前臂] = { 绕X: (0.06 + 摆 * 0.10) * 幅 };
        if (右手 >= 0) 姿势[右手] = { 绕X: 摆 * 0.30 * 幅 };
        if (头 >= 0) {
          姿势[头].绕X = 0.12 * 幅;      // 头歪向挥手那一侧
          姿势[头].绕Y += 0.13 * 幅;     // 顺势看过去
        }
        if (脊 >= 0) 姿势[脊].绕X = 0.04 * 幅 * Math.sin(t * 3.1);
      }
      return 姿势;
    }
    window.小窝操作 = {
      // 连点不打断：已经举起来了就只延长，不再从零抬一次（否则手会抽一下）
      "挥手": function () { if (时间 >= 挥到) 挥起 = 时间; 挥到 = 时间 + 2.6; },
      "复位": function () { 场景.偏航 = 0.52; 场景.俯仰 = 0.24; 场景.距离 = 5.6; 画一帧(); },
      "设色": function (新染) { 染 = 新染 || {}; 画一帧(); }
    };
    function 画一帧() {''')

    # 挥手要用到手腕，补一个关节名（Tripo 只保留了 Twist 骨，R_Hand 在关节表里存在）
    js = 改(js, '''    var 右上臂 = 关节位("R_Clavicle"), 右前臂 = 关节位("R_ForearmTwist01"),
        头 = 关节位("Head"), 脊 = 关节位("Spine02");''',
            '''    var 右上臂 = 关节位("R_Clavicle"), 右前臂 = 关节位("R_ForearmTwist01"),
        右手 = 关节位("R_Hand"),
        头 = 关节位("Head"), 脊 = 关节位("Spine02");''')

    js = 改(js, '''      var 摆 = Math.sin(时间 * 2.2);
      var 姿势 = {};
      // 诊断阶段：先确认蒙皮链路通不通 —— 头部明显转头 + 手臂尝试不同轴
      // 世界轴：X 轴抬高/放下手臂（Y-Z 平面），Y 轴转头
      if (右上臂 >= 0) 姿势[右上臂] = { 绕X: 0.95 + 摆 * 0.10 };
      if (右前臂 >= 0) 姿势[右前臂] = { 绕X: 0.55 + 摆 * 0.20 };
      if (头 >= 0) 姿势[头] = { 绕Y: 摆 * 0.10, 绕Z: 0.05 };
      if (脊 >= 0) 姿势[脊] = { 绕Z: 摆 * 0.02 };
      画.uniformMatrix4fv(uP[2].uBone, false, 算骨骼(姿势));''',
            '''      画.uniformMatrix4fv(uP[2].uBone, false, 算骨骼(算姿势(时间)));

      // 染色开关：缺省全关，画面与原始贴图完全一致
      画.uniform3fv(uP[2].uTintTop, 染.上衣 ? 颜色(染.上衣) : [1, 1, 1]);
      画.uniform3fv(uP[2].uTintPants, 染.裤子 ? 颜色(染.裤子) : [0.29, 0.43, 0.60]);
      画.uniform3fv(uP[2].uTintShoes, 染.鞋 ? 颜色(染.鞋) : [0.94, 0.94, 0.94]);
      画.uniform1f(uP[2].uOnTop, 染.上衣 ? 1 : 0);
      画.uniform1f(uP[2].uOnPants, 染.裤子 ? 1 : 0);
      画.uniform1f(uP[2].uOnShoes, 染.鞋 ? 1 : 0);''')

    # ---------- 舞台站位：家具与玩偶整体右移，填掉右下角的空地 ----------
    js = 改(js, '''    var 偶位 = { x: 0.52, y: 0.02, z: -0.15, 缩放: 0.95, 朝向: -0.72 };
    var 家位 = { x: -0.05, y: 0.0, z: -1.45, 缩放: 2.30, 朝向: 0 };''',
            '''    var 偶位 = { x: 0.34, y: 0.02, z: -0.26, 缩放: 0.98, 朝向: -0.72 };
    var 家位 = { x: 0.22, y: 0.0, z: -1.38, 缩放: 2.34, 朝向: 0 };''')
    js = 改(js, '''      眼目标: [0, 0.82, -0.35]''', '''      眼目标: [0.10, 0.84, -0.32]''')

    # ---------- 取景：宽画布下把镜头推近，避免两侧大片空地 ----------
    js = 改(js, '''      var cp = Math.cos(场景.俯仰);
      var 眼 = [场景.眼目标[0] + 场景.距离*cp*Math.sin(场景.偏航),
                场景.眼目标[1] + 场景.距离*Math.sin(场景.俯仰),
                场景.眼目标[2] + 场景.距离*cp*Math.cos(场景.偏航)];''',
            '''      // 垂直视角固定时，画布越宽两侧越多空地。按宽高比把镜头推近，
      // 让房间在 16:9 的舞台上也能填满，而窄屏保持原距离。
      var 比 = w / h;
      var 距 = 场景.距离 * (比 > 1.45 ? Math.max(0.80, 1.45 / 比 * 1.06) : 1);
      var cp = Math.cos(场景.俯仰);
      var 眼 = [场景.眼目标[0] + 距*cp*Math.sin(场景.偏航),
                场景.眼目标[1] + 距*Math.sin(场景.俯仰),
                场景.眼目标[2] + 距*cp*Math.cos(场景.偏航)];''')

    # ---------- 删掉诊断块 ----------
    i0 = js.index("    // ---- 诊断：蒙皮到底有没有作用到手臂 ----")
    i1 = js.index('    var 静帧 = location.search.indexOf("静帧") >= 0;')
    js = js[:i0] + js[i1:]

    # ---------- 尾部：导出接口，不自动启动 ----------
    js = 改(js, '''    记("首帧：" + Math.round(performance.now() - t0) + " ms" + (静帧 ? "（静帧模式）" : ""));
''', "")
    js = 改(js, '''    记("自检结果：通过 ✅（玩偶由骨骼驱动）");
  }

  启动().catch(function (e) {
    自检.innerHTML = '<span class="失败">失败：' + (e && e.message) + "</span>";
    console.error(e);
  });''',
           '''    if (window.小窝就绪) window.小窝就绪();
  }

  window.启动小窝 = function (选项) {
    return 启动(选项).catch(function (e) {
      if (window.小窝失败) window.小窝失败(e && e.message);
      console.error(e);
    });
  };''')
    return js


页头 = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>我的小窝 · 食谱搭配</title>
  <link rel="stylesheet" href="样式.css">
  <style>
    /* ---------- 我的小窝（M2） ---------- */
    .小窝卡片 { padding: 0; overflow: hidden; }
    .小窝舞台 {
      position: relative;
      height: clamp(400px, 64vh, 660px);
      background: radial-gradient(circle at 50% 26%, #FFFDF6 0%, #F2E8D5 62%, #E7DBC2 100%);
    }
    .小窝舞台 canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; touch-action: none; }
    .小窝遮罩 {
      position: absolute; inset: 0; display: flex; flex-direction: column;
      align-items: center; justify-content: center; gap: 10px;
      background: rgba(252, 249, 240, 0.94); transition: opacity .35s ease-out;
    }
    .小窝遮罩[data-隐="1"] { opacity: 0; pointer-events: none; }
    .小窝遮罩 p { margin: 0; font-size: 13px; color: var(--文字-淡); }
    .小窝进度 { width: 168px; height: 5px; border-radius: 99px; background: var(--绿-浅); overflow: hidden; }
    .小窝进度 i { display: block; height: 100%; width: 12%; border-radius: 99px;
                  background: linear-gradient(90deg, var(--绿-中), #F2C75C); transition: width .4s ease-out; }
    .小窝小字 { font-size: 11.5px; color: var(--文字-淡); opacity: .82; }
    .小窝失败 { max-width: 320px; text-align: center; line-height: 1.75; font-size: 13px; color: var(--文字-淡); }
    .小窝操作 { position: absolute; right: 12px; bottom: 12px; display: flex; gap: 6px; }
    .小窝操作 .文字按钮 { background: rgba(255,255,255,.92); border: 1px solid var(--边框); padding: 5px 11px; font-size: 12px; }

    .小窝网格 { display: grid; grid-template-columns: repeat(auto-fit, minmax(258px, 1fr)); gap: 16px; margin-top: 16px; }
    .换装行 { display: flex; align-items: center; gap: 9px; margin-top: 11px; flex-wrap: wrap; }
    .换装行:first-child { margin-top: 4px; }
    .换装名 { width: 44px; font-size: 13px; color: var(--文字-淡); flex: none; }
    .色点 {
      width: 26px; height: 26px; border-radius: 50%; cursor: pointer; padding: 0;
      border: 1px solid var(--边框-深); position: relative; flex: none;
    }
    .色点[data-选="1"] { box-shadow: 0 0 0 2px var(--卡白), 0 0 0 3.5px var(--绿-中); }
    .色点.原色::after {
      content: "原"; position: absolute; inset: 0; display: grid; place-items: center;
      font-size: 11px; color: var(--文字-淡); background: repeating-linear-gradient(45deg, #fff 0 3px, #EDE9DC 3px 6px);
      border-radius: 50%;
    }
    .宠物空 { font-size: 13px; color: var(--文字-淡); line-height: 1.75; margin: 0; }
    .领养组 { display: flex; gap: 8px; margin-top: 12px; }
    .领养组 button { flex: 1; padding: 9px 0; border-radius: var(--圆角-小); cursor: pointer;
                     border: 1px solid var(--绿-边); background: var(--绿-浅); color: var(--绿-深); font: inherit; font-size: 13px; }
    .领养组 button:hover { background: #DFEEC9; }
    .宠物头 { display: flex; align-items: center; gap: 8px; }
    .宠物头像 { font-size: 30px; line-height: 1; }
    .宠物名 { font: inherit; font-size: 15px; font-weight: 600; color: var(--绿-深);
              border: 1px solid transparent; border-radius: 6px; padding: 2px 5px; width: 108px; background: transparent; }
    .宠物名:hover, .宠物名:focus { border-color: var(--边框-深); background: var(--卡白); outline: none; }
    .宠物注 { font-size: 12px; color: var(--文字-淡); margin: 9px 0 0; line-height: 1.7; }
    .存档区 textarea {
      width: 100%; height: 78px; margin-top: 10px; padding: 8px 10px; resize: vertical;
      font-family: ui-monospace, Consolas, monospace; font-size: 11px; line-height: 1.5;
      border: 1px solid var(--边框); border-radius: var(--圆角-小); color: var(--文字-淡); background: #FCFBF6;
    }
    .存档按钮 { display: flex; gap: 8px; margin-top: 8px; }
    .存档按钮 button { padding: 7px 14px; border-radius: var(--圆角-小); cursor: pointer; font: inherit; font-size: 12.5px;
                        border: 1px solid var(--绿-边); background: var(--绿-浅); color: var(--绿-深); }
    .存档按钮 button:hover { background: #DFEEC9; }
    .存档回执 { font-size: 12px; color: var(--绿-主); margin: 8px 0 0; min-height: 17px; }
    @media (max-width: 900px) {
      .小窝舞台 { height: 46vh; min-height: 300px; }
    }
  </style>
</head>
'''

侧栏 = '''<body data-页面="小窝">
  <aside class="侧栏">
    <div class="侧栏品牌">
      <a class="品牌名" href="index.html">食谱搭配</a>
      <span class="品牌副">吃练一体 · 纯离线</span>
    </div>
    <div class="侧栏目标">
      <span class="侧栏目标标签">每日目标</span>
      <div class="侧栏目标值"><b id="侧栏目标">—</b><small> kcal</small></div>
      <div class="侧栏今日" id="侧栏今日">今日 0 道 · 0 kcal</div>
    </div>
    <nav class="侧栏导航" aria-label="主导航">
      <p class="导航组名">饮食管理</p>
      <a class="导航项" href="index.html" data-页="总览"><span class="导航图标">🥗</span>今日总览</a>
      <a class="导航项" href="目标.html" data-页="目标"><span class="导航图标">🎯</span>我的目标</a>
      <a class="导航项" href="食谱.html" data-页="食谱"><span class="导航图标">📖</span>食谱专区</a>
      <a class="导航项" href="计划.html" data-页="计划"><span class="导航图标">🗓</span>一周计划</a>
      <a class="导航项" href="记录.html" data-页="记录"><span class="导航图标">🕘</span>记录与回看</a>
      <p class="导航组名">训练</p>
      <a class="导航项" href="训练.html" data-页="训练"><span class="导航图标">💪</span>动作库</a>
      <p class="导航组名">养成</p>
      <a class="导航项 选中" href="养成.html" data-页="小窝" aria-current="page"><span class="导航图标">🏠</span>我的小窝</a>
    </nav>
    <div class="侧栏底注">记录与目标存在本机浏览器<br>换页、刷新都不会丢</div>
  </aside>
'''

主体 = '''  <div class="主体">
    <header class="页面顶栏">
      <div class="页面标题组">
        <h1>我的小窝</h1>
        <p>每天好好吃饭喝水运动，小窝就一点点变好</p>
      </div>
      <div class="顶栏目标" id="顶栏等级">Lv.<b>—</b> <small id="顶栏金币">0 币</small></div>
    </header>

    <main class="容器">
      <section class="卡片 小窝卡片">
        <div class="小窝舞台" id="舞台">
          <canvas id="画布"></canvas>
          <div class="小窝遮罩" id="遮罩">
            <div class="小窝进度"><i id="进度条"></i></div>
            <p id="遮罩文字">正在搭你的小窝…</p>
            <p class="小窝小字" id="遮罩小字">第一次打开要读两个模型，稍等一下</p>
          </div>
          <div class="小窝操作">
            <button type="button" class="文字按钮" id="挥手按钮">挥个手</button>
            <button type="button" class="文字按钮" id="复位按钮">复位视角</button>
          </div>
        </div>
      </section>

      <div class="小窝网格">
        <section class="卡片">
          <h2>换装</h2>
          <p class="宠物注" style="margin-top:0">颜色实时生效，直接存进存档。款式要等低模服装包，先玩配色。</p>
          <div id="换装区"></div>
          <p class="宠物注" id="换装提示">当前：全部保持原色</p>
        </section>

        <section class="卡片">
          <h2>宠物</h2>
          <div id="宠物区"></div>
        </section>

        <section class="卡片">
          <h2>存档</h2>
          <p class="宠物注" style="margin-top:0">存档只在这台电脑的浏览器里。换电脑或清缓存前，先导出备份。</p>
          <div class="存档区">
            <textarea id="存档文本" spellcheck="false" placeholder="点「导出」把存档变成一段文本，复制走存好"></textarea>
            <div class="存档按钮">
              <button type="button" id="导出按钮">导出</button>
              <button type="button" id="导入按钮">导入</button>
            </div>
            <p class="存档回执" id="存档回执"></p>
          </div>
        </section>
      </div>
    </main>
  </div>

  <script src="养成.js"></script>
  <script src="养成反馈.js"></script>
'''

逻辑 = r'''  <script>
  /* ---------- 小窝页面逻辑：存储、换装、宠物、存档、懒加载 ---------- */
  (function () {
    "use strict";
    var 键 = window.养成反馈 ? 养成反馈.键 : {
      存档: "食谱搭配-养成存档", 每日: "食谱搭配-养成每日",
      流水: "食谱搭配-养成流水", 场景: "食谱搭配-养成场景"
    };

    function 读(名, 兜底) {
      try { var s = localStorage.getItem(名); return s ? JSON.parse(s) : 兜底; }
      catch (e) { return 兜底; }
    }
    function 写(名, 值) {
      try { localStorage.setItem(名, JSON.stringify(值)); return true; }
      catch (e) { return false; }
    }

    // 本页内存里有一份存档副本。如果用户在别的页面刚打卡赚了经验，
    // 这里直接把自己的副本写回去就会把那笔经验覆盖掉。
    // 所以任何写入都先重读、再合并、最后落盘。
    function 合并写(改动) {
      var 最新 = Object.assign({}, 默认, 读(键.存档, {}) || {});
      最新.形象 = Object.assign({}, 默认.形象, 最新.形象 || {});
      改动(最新);
      写(键.存档, 最新);
      存档 = 最新;
      刷新顶栏();
      return 最新;
    }

    var 系统 = window.养成系统;
    var 默认 = 系统.默认存档();
    var 存档 = Object.assign({}, 默认, 读(键.存档, {}) || {});
    存档.形象 = Object.assign({}, 默认.形象, 存档.形象 || {});
    var 染色 = 存档.形象.染色 || {};

    function 刷新顶栏() {
      var 级 = 系统.由经验算等级(存档.经验 || 0);
      var 等 = document.getElementById("顶栏等级");
      if (等) 等.innerHTML = "Lv.<b>" + 级.等级 + "</b> <small id=\"顶栏金币\">" +
        (存档.金币 || 0) + " 币</small>";
    }

    // ---------- 换装（染色） ----------
    var 款式表 = [
      { 键: "上衣", 名: "上衣", 色: [["#FFFFFF", "白"], ["#E4574C", "红"], ["#F2C75C", "黄"],
                                     ["#7FAE6A", "绿"], ["#5B84B8", "蓝"], ["#3A3A3A", "深灰"]] },
      { 键: "裤子", 名: "裤子", 色: [["#4A6D9A", "牛仔"], ["#C9B79C", "米"], ["#8A8A80", "灰"],
                                     ["#3A3A3A", "黑"], ["#6E8B5E", "军绿"], ["#B4674E", "棕"]] },
      { 键: "鞋",   名: "鞋",   色: [["#FFFFFF", "白"], ["#3A3A3A", "黑"], ["#E4574C", "红"],
                                     ["#C9B79C", "米"]] }
    ];

    function 画换装() {
      var 区 = document.getElementById("换装区");
      区.innerHTML = "";
      款式表.forEach(function (款) {
        var 行 = document.createElement("div");
        行.className = "换装行";
        var 名 = document.createElement("span");
        名.className = "换装名";
        名.textContent = 款.名;
        行.appendChild(名);

        var 原 = document.createElement("button");
        原.type = "button";
        原.className = "色点 原色";
        原.title = "保持原色";
        原.setAttribute("aria-label", 款.名 + "保持原色");
        if (!染色[款.键]) 原.dataset.选 = "1";
        原.addEventListener("click", function () { 设色(款.键, null); });
        行.appendChild(原);

        款.色.forEach(function (对) {
          var 点 = document.createElement("button");
          点.type = "button";
          点.className = "色点";
          点.style.background = 对[0];
          点.title = 对[1];
          点.setAttribute("aria-label", 款.名 + 对[1]);
          if (染色[款.键] === 对[0]) 点.dataset.选 = "1";
          点.addEventListener("click", function () { 设色(款.键, 对[0]); });
          行.appendChild(点);
        });
        区.appendChild(行);
      });

      var 已 = 款式表.filter(function (款) { return 染色[款.键]; })
        .map(function (款) { return 款.名; });
      document.getElementById("换装提示").textContent =
        已.length ? "当前：已改 " + 已.join(" / ") : "当前：全部保持原色";
    }

    function 设色(键名, 值) {
      if (值) 染色[键名] = 值; else delete 染色[键名];
      合并写(function (存) { 存.形象.染色 = 染色; });
      画换装();
      if (window.小窝操作) 小窝操作.设色(染色);
    }

    // ---------- 宠物 ----------
    var 宠物款 = { "猫": "🐱", "狗": "🐶", "兔": "🐰" };

    function 今天() {
      var d = new Date();
      return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2);
    }

    function 画宠物() {
      var 区 = document.getElementById("宠物区");
      var 宠 = 存档.宠物;

      if (!宠) {
        区.innerHTML = '<p class="宠物空">还没有伙伴。领养一只，它会跟着你的打卡状态变心情。</p>' +
                      '<div class="领养组">' +
                      Object.keys(宠物款).map(function (k) {
                        return '<button type="button" data-领养="' + k + '">' + 宠物款[k] + " " + k + "</button>";
                      }).join("") + "</div>";
        区.querySelectorAll("[data-领养]").forEach(function (b) {
          b.addEventListener("click", function () {
            合并写(function (存) {
              存.宠物 = { 种类: b.dataset.领养, 名字: "小" + b.dataset.领养,
                          亲密度: 0, 领养日: 今天(), 上次喂食日: null };
            });
            画宠物();
          });
        });
        return;
      }

      var 心 = 系统.宠物心情(读(键.每日, 系统.默认每日()), 存档, {});
      区.innerHTML =
        '<div class="宠物头"><span class="宠物头像">' + (宠物款[宠.种类] || "🐾") + "</span>" +
        '<input class="宠物名" id="宠物名" maxlength="8" value="' + (宠.名字 || "") + '" aria-label="宠物名字">' +
        '<span class="宠物注" style="margin:0">' + 心.心情 + " · 亲密度 " + 心.亲密度 + "</span></div>" +
        '<p class="宠物注">' + 宠.种类 + " · 领养于 " + (宠.领养日 || "—") +
        "。名字最多 8 个字，改完点一下空白处就存好。</p>";

      var 输入 = document.getElementById("宠物名");
      输入.addEventListener("change", function () {
        var 新 = (输入.value || "").trim().slice(0, 8);
        if (!新) { 输入.value = 宠.名字; return; }
        合并写(function (存) { if (存.宠物) 存.宠物.名字 = 新; });
      });
    }

    // ---------- 存档导出 / 导入 ----------
    function 导出() {
      var 包 = { 版本: 1, 导出日: 今天() };
      [["存档", 键.存档], ["每日", 键.每日], ["流水", 键.流水], ["场景", 键.场景]].forEach(function (对) {
        var v = 读(对[1], null);
        if (v !== null) 包[对[0]] = v;
      });
      var 文 = JSON.stringify(包);
      var 框 = document.getElementById("存档文本");
      框.value = 文;
      框.select();
      document.getElementById("存档回执").textContent =
        "已导出 " + Math.round(文.length / 1024) + "KB，复制这段文本存好即可。";
    }

    function 导入() {
      var 回 = document.getElementById("存档回执");
      var 文 = (document.getElementById("存档文本").value || "").trim();
      if (!文) { 回.textContent = "先把导出的文本粘进来。"; return; }
      var 包;
      try { 包 = JSON.parse(文); }
      catch (e) { 回.textContent = "这段文本不是存档（解析失败），没有改动任何东西。"; return; }
      if (!包 || typeof 包 !== "object" || !包.存档) { 回.textContent = "缺少「存档」字段，拒绝导入。"; return; }
      if (包.版本 !== 1) { 回.textContent = "存档版本不是 1，拒绝导入。"; return; }

      写(键.存档, 包.存档);
      if (包.每日) 写(键.每日, 包.每日);
      if (包.流水) 写(键.流水, 包.流水);
      if (包.场景) 写(键.场景, 包.场景);
      回.textContent = "导入完成，正在重新载入…";
      setTimeout(function () { location.reload(); }, 400);
    }

    // ---------- 模型懒加载 ----------
    var 遮罩 = document.getElementById("遮罩"), 进度条 = document.getElementById("进度条");
    function 进度(文字, 百分比) {
      document.getElementById("遮罩文字").textContent = 文字;
      if (百分比) 进度条.style.width = 百分比 + "%";
    }
    window.小窝进度 = function (s) { 进度(s, 68); };
    window.小窝就绪 = function () {
      进度条.style.width = "100%";
      遮罩.dataset.隐 = "1";
      // 直接摘掉，不依赖 CSS 过渡是否跑完：模型解码是长任务，
      // 过渡可能刚开始就被下一次绘制截断，留下一层半透明薄膜。
      遮罩.style.display = "none";
    };
    window.小窝失败 = function (原因) {
      if (原因 === "NO_WEBGL2") {
        遮罩.innerHTML = '<p class="小窝失败">这台电脑的浏览器没开 WebGL2，小窝暂时显示不了。<br>' +
          '换成新版 Chrome 或 Edge 再打开就好，打卡和换装数据都不受影响。</p>';
      } else {
        遮罩.innerHTML = '<p class="小窝失败">小窝没能加载出来：' + 原因 + '<br>' +
          '打卡、换装、宠物都还能正常用，刷新一次再试试。</p>';
      }
    };

    function 载脚本(路径, 完成后) {
      var s = document.createElement("script");
      s.src = 路径;
      s.onload = 完成后;
      s.onerror = function () { window.小窝失败("找不到模型文件 " + 路径); };
      document.head.appendChild(s);
    }

    function 开始加载() {
      if (!document.createElement("canvas").getContext("webgl2")) { window.小窝失败("NO_WEBGL2"); return; }
      进度("正在读取房间模型…", 18);
      载脚本("数据/房间模型.js", function () {
        进度("正在读取角色模型…", 42);
        载脚本("数据/角色模型.js", function () {
          进度("正在拼装小窝…", 66);
          setTimeout(function () {
            if (window.启动小窝) window.启动小窝({ 染色: 染色 });
            else window.小窝失败("渲染器未就绪");
          }, 30);
        });
      });
    }

    document.getElementById("挥手按钮").addEventListener("click", function () {
      if (window.小窝操作) 小窝操作.挥手();
    });
    document.getElementById("复位按钮").addEventListener("click", function () {
      if (window.小窝操作) 小窝操作.复位();
    });
    document.getElementById("导出按钮").addEventListener("click", 导出);
    document.getElementById("导入按钮").addEventListener("click", 导入);

    刷新顶栏();
    画换装();
    画宠物();
    开始加载();
  })();
  </script>
</body>
</html>
'''


def main():
    js = 装配(提取渲染器(源))
    html = 页头 + 侧栏 + 主体 + "  <script>\n" + js + "\n  </script>\n\n" + 逻辑
    with io.open(出, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("养成.html 已生成：%d 行，%.2f MB" % (len(html.splitlines()), len(html.encode("utf-8")) / 1048576))


if __name__ == "__main__":
    main()
