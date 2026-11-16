/* 养成反馈层（M1 任务区 M3）
 * 把 养成.js 的纯函数接到真实页面上。
 *
 * 职责边界：
 *   · 读写 4 个存储键（存档 / 每日 / 流水 / 场景）
 *   · 换天归一（每日清零，等级与金币在存档里不动）
 *   · 侧栏经验块、今日任务区、手机胶囊、打卡浮层（全部由本文件自建自销）
 *   · 对外的打卡入口：餐后结算(餐次, 强制) —— 三餐来自记录页，喝水/运动来自任务区按钮
 *
 * 设计约束：
 *   · 页面 HTML 不写任何养成相关结构，只引脚本；渲染失败不会让页面变空。
 *   · 唯一的外部挂载点是 脚本.js 的 添加记录()，且外面套了 try/catch —— 养成系统
 *     出错绝不能影响记账主链路。
 *   · 本文件不做游戏规则判断，规则一律问 养成系统（纯函数，已被 105 项对拍覆盖）。
 */
(function () {
  "use strict";

  var 键 = {
    存档: "食谱搭配-养成存档",
    每日: "食谱搭配-养成每日",
    流水: "食谱搭配-养成流水",
    场景: "食谱搭配-养成场景"
  };
  var 流水上限 = 30;

  // ============ 存储 ============
  function 读(键名) {
    try {
      var 原文 = localStorage.getItem(键名);
      return 原文 ? JSON.parse(原文) : null;
    } catch (e) { return null; }
  }
  function 写(键名, 值) {
    try { localStorage.setItem(键名, JSON.stringify(值)); } catch (e) { /* 隐私模式忽略 */ }
  }

  function 今日串() {
    var d = new Date();
    return d.getFullYear() + "-" +
      ("0" + (d.getMonth() + 1)).slice(-2) + "-" +
      ("0" + d.getDate()).slice(-2);
  }
  function 时分串() {
    var d = new Date();
    return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
  }

  function 读存档() {
    var a = 读(键.存档);
    if (!a || typeof a !== "object" || !a.版本) return null;
    return a;
  }
  function 读每日() {
    var d = 读(键.每日);
    if (!d || typeof d !== "object" || !d.日期) return null;
    return d;
  }
  function 读流水() {
    var l = 读(键.流水);
    return Array.isArray(l) ? l : [];
  }
  function 读场景() {
    var s = 读(键.场景);
    return (s && typeof s === "object") ? s : null;
  }

  function 追加流水(获得, 来源, 日期) {
    var 流水 = 读流水();
    流水.unshift({
      "时间": 日期 + " " + 时分串(),
      "来源": 来源,
      "经验": 获得.经验,
      "金币": 获得.金币
    });
    写(键.流水, 流水.slice(0, 流水上限));
  }

  // 今日获得经验一律从流水求和（R7：不存冗余字段，避免和流水漂移）
  function 今日获得(日期) {
    var 前缀 = (日期 || 今日串()) + " ";
    var 总 = { 经验: 0, 金币: 0 };
    读流水().forEach(function (条) {
      if (条 && typeof 条.时间 === "string" && 条.时间.indexOf(前缀) === 0) {
        总.经验 += Number(条.经验) || 0;
        总.金币 += Number(条.金币) || 0;
      }
    });
    return 总;
  }

  // ============ 结算（不碰 DOM，便于对拍） ============
  /**
   * 选项：{ 今天, 小时, 强制, 存档, 每日 }
   * 传入 存档/每日/今天/小时 是为了测试可重复；页面调用时不传，取真实时间与存储。
   */
  function 结算(来源, 选项) {
    var o = 选项 || {};
    var 今天 = o.今天 || 今日串();
    var 存 = o.存档 || 读存档() || 养成系统.默认存档();
    var 每 = o.每日 || 读每日();
    // 换天：昨天的三餐/喝水清零，等级、金币、形象、宠物都在存档里，不受影响
    if (!每 || 每.日期 !== 今天) 每 = 养成系统.默认每日(今天);

    var 结果 = 养成系统.结算打卡(存, 每, 来源, {
      "今天": 今天,
      "强制": !!o.强制,
      "小时": typeof o.小时 === "number" ? o.小时 : new Date().getHours(),
      "家具加成": 养成系统.场景加成(读场景(), window.家具数据)
    });

    // 把「加餐兜底成晚」这类归一化结果带出来，浮层文案才说得对
    var 归 = 养成系统.归一化来源(来源, 每, {});
    结果.来源 = 归.结果 ? 来源 : 归.来源;

    // 关键：结算打卡的「结果」在新打卡成功时同样是 "已完成"，不能拿它判断成败。
    // 唯一可靠的信号是「本次有没有真的得分」——重复打卡、上限、未到餐点都给 0。
    结果.得分 = (结果.获得.经验 > 0 || 结果.获得.金币 > 0);
    // 每日是「今天做了什么」的事实，任何时候都要跟着日历走：
    // 换天后的第一次操作即使没得分（重复/未到餐点），也不能把昨天的三餐留在存储里。
    写(键.每日, 结果.每日);
    if (结果.得分) {
      写(键.存档, 结果.存档);
      追加流水(结果.获得, 结果.来源 || 来源, 今天);
    }
    return 结果;
  }

  // ============ 任务区（M3） ============

  // 展示用的每日：换了天但今天还没有任何操作时，存储里仍是昨天的进度，
  // 任务区直接按「全空」画（不落盘——写入只在 结算 里发生，见 M1 的教训）。
  function 展示每日() {
    var d = 读每日();
    var 今天 = 今日串();
    if (!d || d.日期 !== 今天) return 养成系统.默认每日(今天);
    return d;
  }

  function 任务状态() {
    var d = 展示每日();
    var 目 = 养成系统.每日目标, 限 = 养成系统.每日上限;
    var 三餐 = d.三餐 || [];
    function 有(餐) { return 三餐.indexOf(餐) !== -1; }
    return {
      "日期": d.日期,
      "早": 有("早"), "午": 有("午"), "晚": 有("晚"),
      "三餐数": 三餐.length, "三餐目标": 目.三餐,
      "喝水": d.喝水 || 0, "喝水目标": 目.喝水, "喝水上限": 限.喝水,
      "运动": d.运动 || 0, "运动目标": 目.运动, "运动上限": 限.运动,
      "已达标": !!d.达标
    };
  }

  function 造行() {
    var 行 = document.createElement("div");
    行.className = "任务行";
    return 行;
  }

  // 三餐卡：进度是早/午/晚三个圆片，打卡入口在记录页（记录一餐就自动结算）
  function 画三餐行(容器, s) {
    var 行 = 造行();
    行.innerHTML =
      '<span class="任务图标" aria-hidden="true">🍚</span>' +
      '<span class="任务名">三餐</span>';
    var 点 = document.createElement("span");
    点.className = "餐点";
    点.setAttribute("aria-label", "三餐 " + s.三餐数 + "/" + s.三餐目标);
    ["早", "午", "晚"].forEach(function (餐) {
      var i = document.createElement("i");
      if (s[餐]) i.className = "完成";
      i.textContent = 餐;
      点.appendChild(i);
    });
    行.appendChild(点);
    var 数 = document.createElement("span");
    数.className = "任务数";
    数.textContent = s.三餐数 + "/" + s.三餐目标;
    行.appendChild(数);
    if (location.pathname.indexOf("记录.html") === -1) {
      var 链 = document.createElement("a");
      链.className = "任务链接";
      链.href = "记录.html";
      链.title = "在记录页写一餐就自动打卡";
      链.textContent = "记一餐";
      行.appendChild(链);
    }
    容器.appendChild(行);
  }

  // 喝水 / 运动卡：目标线达标即可，上限前按钮一直可用（R3：达标线低于上限）
  function 画计数行(容器, s, 键, 图标, 名, 钮文, 达标提示) {
    var 数 = s[键], 目标 = s[键 + "目标"], 上限 = s[键 + "上限"];
    var 满 = 数 >= 上限, 达 = 数 >= 目标;
    var 行 = 造行();
    if (满) 行.className += " 满";
    行.innerHTML =
      '<span class="任务图标" aria-hidden="true">' + 图标 + '</span>' +
      '<span class="任务名">' + 名 + '</span>';
    var 条 = document.createElement("span");
    条.className = "任务条";
    条.setAttribute("role", "progressbar");
    条.setAttribute("aria-label", 名 + "进度");
    var 填 = document.createElement("i");
    填.style.width = Math.min(100, Math.round(数 / 目标 * 100)) + "%";
    条.appendChild(填);
    行.appendChild(条);
    var 数字 = document.createElement("span");
    数字.className = "任务数";
    数字.textContent = 满 ? 数 + "/" + 上限 : (达 ? 目标 + "/" + 目标 + " ✓" : 数 + "/" + 目标);
    行.appendChild(数字);
    var 钮 = document.createElement("button");
    钮.type = "button";
    钮.className = "任务钮";
    钮.textContent = 满 ? "已满" : 钮文;
    钮.disabled = 满;
    if (达 && !满) 钮.title = 达标提示;
    if (满) 钮.title = "今天到上限了，明天再来";
    钮.setAttribute("aria-label", 名 + "打卡");
    钮.addEventListener("click", function () { 餐后结算(键, false); });
    行.appendChild(钮);
    容器.appendChild(行);
  }

  function 画任务区(容器) {
    if (!容器) return;
    var s = 任务状态();
    容器.innerHTML = "";
    var 头 = document.createElement("div");
    头.className = "任务头";
    头.innerHTML =
      '<span class="任务头名">今日任务</span>' +
      '<span class="任务徽章' + (s.已达标 ? " 亮" : "") + '">🏅 今日达标</span>';
    容器.appendChild(头);
    画三餐行(容器, s);
    画计数行(容器, s, "喝水", "💧", "喝水", "+1 杯", "已达目标，多喝还有经验，8 杯封顶");
    画计数行(容器, s, "运动", "🏃", "运动", "+1 次", "已达目标，多练还有经验，3 次封顶");
  }

  // ============ 视图 ============
  function 取元素(id) { return document.getElementById(id); }

  function 造经验块() {
    var 块 = document.createElement("div");
    块.className = "侧栏养成";
    块.id = "养成经验块";
    块.innerHTML =
      '<div class="养成头">' +
        '<b class="养成等级" id="养成等级">Lv.1</b>' +
        '<span class="养成星" id="养成星"></span>' +
        '<span class="养成金币" id="养成金币">0 金币</span>' +
      '</div>' +
      '<div class="养成条" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-label="升级进度">' +
        '<i id="养成进度"></i>' +
      '</div>' +
      '<div class="养成注" id="养成注">今天还没有打卡</div>';
    return 块;
  }

  function 造胶囊() {
    var 钮 = document.createElement("button");
    钮.type = "button";
    钮.className = "养成胶囊";
    钮.id = "养成胶囊";
    钮.innerHTML = '<span id="胶囊等级">Lv.1</span>' +
      '<span class="胶囊分隔">·</span><span id="胶囊进度">0/100</span>' +
      '<span class="胶囊分隔">·</span><span id="胶囊金币">0 币</span>';
    钮.title = "今日任务 · 点开快速打卡";
    钮.setAttribute("aria-expanded", "false");
    return 钮;
  }

  // 手机任务板：胶囊点开弹出，内容与侧栏任务区同一份 画任务区
  function 开任务板(开) {
    var 板 = 取元素("养成任务板"), 钮 = 取元素("养成胶囊");
    if (!板) return;
    if (开) 画任务区(板.querySelector(".任务区"));
    板.classList.toggle("开", 开);
    if (钮) 钮.setAttribute("aria-expanded", 开 ? "true" : "false");
  }

  function 造任务板() {
    var 板 = document.createElement("div");
    板.className = "任务板 任务浅";
    板.id = "养成任务板";
    板.innerHTML = '<div class="任务区"></div>' +
      '<div class="任务板底">' +
        '<a href="养成.html">去小窝看看 →</a>' +
        '<button type="button" class="任务板关">收起</button>' +
      '</div>';
    板.querySelector(".任务板关").addEventListener("click", function () { 开任务板(false); });
    return 板;
  }

  function 注入() {
    var 侧栏 = document.querySelector(".侧栏");
    // 小窝页的任务区在正文里（手机质感的组件），侧栏不再重复放一份
    var 在小窝页 = document.body.getAttribute("data-页面") === "小窝";
    if (侧栏 && !取元素("养成经验块")) {
      var 块 = 造经验块();
      var 目标块 = 侧栏.querySelector(".侧栏目标");
      if (目标块 && 目标块.nextSibling) 侧栏.insertBefore(块, 目标块.nextSibling);
      else 侧栏.appendChild(块);
    }
    if (侧栏 && !在小窝页 && !取元素("养成任务块")) {
      var 任务 = document.createElement("div");
      任务.className = "侧栏养成 任务块";
      任务.id = "养成任务块";
      var 经验块 = 取元素("养成经验块");
      if (经验块 && 经验块.nextSibling) 侧栏.insertBefore(任务, 经验块.nextSibling);
      else 侧栏.appendChild(任务);
    }
    if (!取元素("养成胶囊")) {
      var 胶囊 = 造胶囊();
      胶囊.addEventListener("click", function (事件) {
        事件.stopPropagation();
        开任务板(!取元素("养成任务板").classList.contains("开"));
      });
      document.body.appendChild(胶囊);
    }
    if (!取元素("养成任务板")) document.body.appendChild(造任务板());
    // 点到任务板外面就收起（胶囊自己的点击已 stopPropagation）
    if (!注入.已挂外点) {
      注入.已挂外点 = true;
      document.addEventListener("click", function (事件) {
        var 板 = 取元素("养成任务板");
        if (板 && 板.classList.contains("开") && !板.contains(事件.target)) 开任务板(false);
      });
    }
  }

  function 刷新任务区() {
    var 块 = 取元素("养成任务块");
    if (块) 画任务区(块);
    // 小窝页正文里的手机组件（生成养成页.py 放的静态容器）
    var 窝 = 取元素("小窝任务区");
    if (窝) 画任务区(窝);
    var 板 = 取元素("养成任务板");
    if (板 && 板.classList.contains("开")) 画任务区(板.querySelector(".任务区"));
  }

  function 刷新经验块() {
    注入();
    var 存 = 读存档();
    var 经验 = 存 ? (Number(存.经验) || 0) : 0;
    var 金币 = 存 ? (Number(存.金币) || 0) : 0;
    var 级 = 养成系统.由经验算等级(经验);
    var 百分比 = 级.是否满级 ? 100
      : Math.max(0, Math.min(100, 级.级内经验 / 级.升级需要 * 100));
    var 进度文本 = 级.是否满级
      ? "满级 · ★" + 级.星星
      : 级.级内经验 + " / " + 级.升级需要;

    var 等级 = 取元素("养成等级");
    if (等级) 等级.textContent = "Lv." + 级.等级;
    var 星 = 取元素("养成星");
    if (星) 星.textContent = 级.是否满级 ? "★ " + 级.星星 : "";
    var 金 = 取元素("养成金币");
    if (金) 金.textContent = 金币 + " 金币";
    var 条 = 取元素("养成进度");
    if (条) 条.style.width = 百分比 + "%";
    var 条框 = document.querySelector(".养成条");
    if (条框) 条框.setAttribute("aria-valuenow", Math.round(百分比));

    var 今日 = 今日获得();
    var 注 = 取元素("养成注");
    if (注) {
      注.textContent = 今日.经验 > 0
        ? "今日 +" + 今日.经验 + " 经验 · 连签 " + (存 ? (存.连续天数 || 0) : 0) + " 天"
        : "今天还没有打卡 · 连签 " + (存 ? (存.连续天数 || 0) : 0) + " 天";
    }

    var 胶级 = 取元素("胶囊等级");
    if (胶级) 胶级.textContent = "Lv." + 级.等级;
    var 胶进 = 取元素("胶囊进度");
    if (胶进) 胶进.textContent = 进度文本;
    var 胶金 = 取元素("胶囊金币");
    if (胶金) 胶金.textContent = 金币 + " 币";

    刷新任务区();
  }

  // ============ 浮层 ============
  function 取浮层() {
    var 层 = 取元素("养成浮层");
    if (!层) {
      层 = document.createElement("div");
      层.id = "养成浮层";
      层.className = "养成浮层";
      层.setAttribute("role", "status");
      层.setAttribute("aria-live", "polite");
      document.body.appendChild(层);
    }
    return 层;
  }

  function 弹提示(标题, 副文, 类型) {
    var 条 = document.createElement("div");
    条.className = "养成提示" + (类型 ? " " + 类型 : "");
    var 标 = document.createElement("b");
    标.textContent = 标题;
    条.appendChild(标);
    if (副文) {
      var 副 = document.createElement("span");
      副.textContent = 副文;
      条.appendChild(副);
    }
    取浮层().appendChild(条);
    setTimeout(function () { 条.classList.add("淡出"); }, 2200);
    setTimeout(function () {
      if (条.parentNode) 条.parentNode.removeChild(条);
    }, 2700);
  }

  function 来源文案(餐次) {
    if (餐次 === "早") return "早餐打卡成功，一天的好开头";
    if (餐次 === "午") return "午餐打卡成功，继续保持";
    if (餐次 === "晚") return "晚餐打卡成功，今天圆满了";
    if (餐次 === "喝水") return "喝水打卡成功";
    if (餐次 === "运动") return "运动打卡成功";
    return "打卡成功";
  }

  // ============ 对外：打卡入口 ============
  /**
   * 餐次：早 / 午 / 晚 / 加餐（脚本.js 判定餐次）/ 喝水 / 运动
   * 强制：来自计划页「标记已吃」时为 true，需通过餐次时间窗校验（R2）
   */
  function 餐后结算(餐次, 强制) {
    var 结果 = 结算(餐次, { 强制: 强制 });
    刷新经验块();

    if (!结果.得分) {
      if (结果.结果 === "已上限") {
        弹提示("今天这项到上限了", "多喝水不算经验，但身体还是受益的", "淡");
      } else if (结果.结果 === "未到餐点") {
        弹提示("还没到这个餐点", "到点再标记，经验才算数", "淡");
      } else if (结果.结果 === "不打卡") {
        return 结果;   // 21 点后的第二顿加餐：静默，不打扰
      } else {
        弹提示("这一餐已经打过卡啦", "一天只算一次，明天继续", "淡");
      }
    } else {
      弹提示("+" + 结果.获得.经验 + " 经验 · +" + 结果.获得.金币 + " 金币",
             来源文案(结果.来源 || 餐次), "好");
      if (结果.是否刚达标) {
        弹提示("今天三项都做到了！", "达标奖励 +50 经验 · +20 金币", "喜");
      }
      if (结果.升了几级 > 0) {
        弹提示("升级！Lv." + 养成系统.由经验算等级(结果.存档.经验).等级,
               "新等级可以解锁更多装扮", "喜");
      }
    }
    return 结果;
  }

  // 供测试读取内部状态（只读）
  function 快照() {
    var 存 = 读存档();
    return {
      "存档": 存,
      "每日": 读每日(),
      "流水": 读流水(),
      "等级": 养成系统.由经验算等级(存 ? 存.经验 : 0),
      "今日获得": 今日获得()
    };
  }

  function 启动() {
    注入();
    刷新经验块();
    // 同一浏览器的另一个标签页打卡了，本页跟着更新
    window.addEventListener("storage", function (事件) {
      if (事件.key && 事件.key.indexOf("食谱搭配-养成") === 0) 刷新经验块();
    });
    // 跨零点：页面长时间开着也要在新一天第一次操作时正确换天（渲染时判断即可）
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) 刷新经验块();
    });
  }

  window.养成反馈 = {
    "键": 键,
    "结算": 结算,
    "餐后结算": 餐后结算,
    "刷新经验块": 刷新经验块,
    "弹提示": 弹提示,
    "今日获得": 今日获得,
    "快照": 快照,
    "启动": 启动,
    "任务状态": 任务状态,
    "画任务区": 画任务区,
    "刷新任务区": 刷新任务区,
    "开任务板": 开任务板,
    "注入": 注入
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", 启动);
  } else {
    启动();
  }
})();
