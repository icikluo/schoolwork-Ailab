/* 食谱搭配 —— 主逻辑
 * 数据源：window.食谱数据（见 数据/食谱.js）
 * 记录存储：localStorage，键名 "食谱搭配-今日记录"，值为 [{ id, 名称, ... }]
 */

(function () {
  "use strict";

  // ============ 固定参数（见 PRD.md） ============
  var 记录存储键 = "食谱搭配-今日记录";
  var 目标存储键 = "食谱搭配-今日目标";
  var 最低目标 = 1200;          // 安全下限，低于则上调
  var 取整步长 = 10;           // 结果取整到 10 kcal
  var 推荐数量 = 3;            // 每次推荐 3 道
  var 人群系数 = {
    减脂: 0.8,
    增肌: 1.1,
    控糖: 1.0,
    均衡: 1.0
  };
  var 推荐优先级 = {
    减脂: "蛋白高、脂肪低",
    增肌: "蛋白高、碳水足",
    控糖: "碳水低、纤维高",
    均衡: "营养均衡"
  };
  var 营养字段 = ["卡路里", "碳水", "脂肪", "膳食纤维", "蛋白质"];

  // 功能增强（v0.4.1）
  var 食谱分区键 = "食谱搭配-食谱分区";   // 专区上次选择的分区
  var 历史存储键 = "食谱搭配-历史记录";   // 近 7 天记录（纯文字回看）
  var 记录日期键 = "食谱搭配-记录日期";   // 今日记录对应的日期戳
  var 历史保留天数 = 7;
  var 推荐偏移 = 0;             // 「换一批」在排序候选里的起点
  var 当前搜索词 = "";          // 食谱专区搜索
  var 当前排序 = "默认";        // 食谱专区排序

  // 宏量营养目标供能比（借鉴 CookHero 的目标管理，按人群给三项目标）
  // 蛋白质 / 脂肪 / 碳水 三项供能比之和为 1
  var 宏量供能比 = {
    减脂: { 蛋白质: 0.30, 脂肪: 0.25, 碳水: 0.45 },
    增肌: { 蛋白质: 0.25, 脂肪: 0.25, 碳水: 0.50 },
    控糖: { 蛋白质: 0.25, 脂肪: 0.35, 碳水: 0.40 },
    均衡: { 蛋白质: 0.20, 脂肪: 0.30, 碳水: 0.50 }
  };
  var 供能系数 = { 蛋白质: 4, 脂肪: 9, 碳水: 4 };  // 每克供能 kcal

  function 计算宏量目标(目标卡路里, 人群) {
    var 比 = 宏量供能比[人群] || 宏量供能比["均衡"];
    var 结果 = {};
    ["蛋白质", "脂肪", "碳水"].forEach(function (字段) {
      结果[字段] = Math.round(目标卡路里 * 比[字段] / 供能系数[字段]);
    });
    return 结果;
  }

  // 按当前时间自动归入餐次（早 / 午 / 晚 / 加餐）
  function 判定餐次(时刻) {
    var 小时 = (时刻 || new Date()).getHours();
    if (小时 < 10) return "早";
    if (小时 < 15) return "午";
    if (小时 < 21) return "晚";
    return "加餐";
  }

  // ============ 工具 ============
  function 取元素(id) {
    return document.getElementById(id);
  }

  function 保留一位小数(x) {
    return Math.round(x * 10) / 10;
  }

  // 份量折算：整份（1）或半份（0.5），卡路里取整、克数保留 1 位小数
  function 折算份量(菜, 份量) {
    份量 = 份量 === 0.5 ? 0.5 : 1;
    return {
      卡路里: Math.round(菜.卡路里 * 份量),
      碳水: 保留一位小数(菜.碳水 * 份量),
      脂肪: 保留一位小数(菜.脂肪 * 份量),
      膳食纤维: 保留一位小数(菜.膳食纤维 * 份量),
      蛋白质: 保留一位小数(菜.蛋白质 * 份量)
    };
  }

  // 「换一批」用：从排序后的候选里按偏移循环取一段（到尾自动回到开头）
  function 按偏移取段(列表, 偏移, 数量) {
    if (!列表.length) return [];
    var 段 = [];
    for (var i = 0; i < 数量; i++) {
      段.push(列表[(偏移 + i) % 列表.length]);
    }
    return 段;
  }

  // ============ 目标卡路里三步计算 ============
  // 第一步：基础代谢 BMR（Mifflin-St Jeor）
  function 计算基础代谢(性别, 体重, 身高, 年龄) {
    var 基数 = 10 * 体重 + 6.25 * 身高 - 5 * 年龄;
    return 性别 === "男" ? 基数 + 5 : 基数 - 161;
  }

  // 第二步：乘以活动系数得到每日消耗 TDEE
  function 计算每日消耗(基础代谢, 活动系数) {
    return 基础代谢 * 活动系数;
  }

  // 第三步：按人群系数调整 -> 取整到 10 -> 低于 1200 上调
  function 计算目标卡路里(性别, 体重, 身高, 年龄, 活动系数, 人群) {
    var 基础代谢 = 计算基础代谢(性别, 体重, 身高, 年龄);
    var 每日消耗 = 计算每日消耗(基础代谢, 活动系数);
    var 调整后 = 每日消耗 * (人群系数[人群] || 1);

    var 取整后 = Math.round(调整后 / 取整步长) * 取整步长;
    var 是否上调 = 取整后 < 最低目标;
    var 目标 = 是否上调 ? 最低目标 : 取整后;

    return {
      基础代谢: 保留一位小数(基础代谢),
      每日消耗: 保留一位小数(每日消耗),
      调整后: 保留一位小数(调整后),
      目标: 目标,
      是否上调: 是否上调
    };
  }

  // ============ 记录读写 ============
  function 读记录() {
    try {
      var 原文 = localStorage.getItem(记录存储键);
      return 原文 ? JSON.parse(原文) : [];
    } catch (e) {
      return [];
    }
  }

  function 写记录(记录) {
    localStorage.setItem(记录存储键, JSON.stringify(记录));
  }

  function 读目标() {
    try {
      var 原文 = localStorage.getItem(目标存储键);
      return 原文 ? JSON.parse(原文) : null;
    } catch (e) {
      return null;
    }
  }

  function 写目标(数据) {
    localStorage.setItem(目标存储键, JSON.stringify(数据));
  }

  // ============ 营养汇总 ============
  function 汇总营养(记录) {
    var 合计 = { 卡路里: 0, 碳水: 0, 脂肪: 0, 膳食纤维: 0, 蛋白质: 0 };
    记录.forEach(function (条目) {
      营养字段.forEach(function (字段) {
        合计[字段] += Number(条目[字段]) || 0;
      });
    });
    合计.卡路里 = Math.round(合计.卡路里);
    ["碳水", "脂肪", "膳食纤维", "蛋白质"].forEach(function (字段) {
      合计[字段] = 保留一位小数(合计[字段]);
    });
    return 合计;
  }

  function 按id查找(id) {
    for (var i = 0; i < window.食谱数据.length; i++) {
      if (window.食谱数据[i].id === id) return window.食谱数据[i];
    }
    return null;
  }

  // ============ 推荐逻辑 ============
  // 规则：
  //   1) 只从当前人群标签中挑选
  //   2) 根据剩余卡路里额度，优先选择接近额度一半的（早中晚各一道）
  //   3) 已记录过的今天不再重复推荐
  //   4) 额度不足时提示，不再硬推
  //   5) 偏移用于「换一批」：同一排序里往后翻 3 道，到尾回绕
  function 生成推荐(人群, 剩余卡路里, 已记录ids, 偏移) {
    var 候选 = window.食谱数据.filter(function (菜) {
      return 菜.人群.indexOf(人群) !== -1 && 已记录ids.indexOf(菜.id) === -1;
    });

    if (剩余卡路里 <= 100) {
      return { 列表: [], 说明: "今日已达目标额度，明天再吃吧。", 候选数: 0 };
    }

    // 每餐预算 ≈ 剩余 / 3，在预算 60%~140% 之间优先
    var 餐预算 = 剩余卡路里 / 3;
    var 计算得分 = function (菜) {
      var 差 = Math.abs(菜.卡路里 - 餐预算) / (餐预算 || 1);
      var 得分 = 差;
      // 同人群的加分项：减脂看蛋白/脂肪比，增肌看蛋白，控糖看碳水低 + 纤维高
      if (人群 === "减脂") 得分 -= (菜.蛋白质 / Math.max(菜.脂肪, 1)) * 0.02;
      if (人群 === "增肌") 得分 -= 菜.蛋白质 / 100;
      if (人群 === "控糖") 得分 -= 菜.膳食纤维 / 20 + (30 / Math.max(菜.碳水, 1)) * 0.1;
      if (人群 === "均衡") 得分 -= 菜.膳食纤维 / 40;
      return 得分;
    };

    候选.sort(function (a, b) {
      return 计算得分(a) - 计算得分(b);
    });

    var 列表 = 按偏移取段(候选, 偏移 || 0, 推荐数量);
    var 说明 = "按「" + 人群 + "」优先" + 推荐优先级[人群] + "，结合剩余 " +
      剩余卡路里 + " kcal 挑出以下 " + 列表.length + " 道。";
    if (候选.length === 0) {
      说明 = "今天的食谱都记录过了，明天可以换个吃法。";
    }
    return { 列表: 列表, 说明: 说明, 候选数: 候选.length };
  }

  // ============ 渲染 ============
  function 创建菜单项(菜, 按钮区) {
    var li = document.createElement("li");
    li.className = "食谱项";

    var 菜名盒 = document.createElement("div");
    菜名盒.className = "菜名";

    // 今日已记录列表：显示该条属于哪一餐（早 / 午 / 晚 / 加餐）
    if (按钮区 === "移除" && 菜.餐次) {
      var 餐次标记 = document.createElement("span");
      餐次标记.className = "记录餐次";
      餐次标记.textContent = 菜.餐次;
      菜名盒.appendChild(餐次标记);
    }

    var 名字 = document.createElement("div");
    名字.className = "名字";
    // 半份记录在菜名后标注，直观看出这不是整份的营养
    名字.textContent = 菜.名称 + (菜.份量 === 0.5 ? "（半份）" : "");
    菜名盒.appendChild(名字);

    var 标签行 = document.createElement("div");
    菜.人群.forEach(function (人群名) {
      var 标签 = document.createElement("span");
      标签.className = "人群标签";
      标签.textContent = 人群名;
      标签行.appendChild(标签);
    });
    菜名盒.appendChild(标签行);

    var 明细 = document.createElement("div");
    明细.className = "营养明细";
    明细.textContent = "碳水 " + 菜.碳水.toFixed(1) + "g · 脂肪 " + 菜.脂肪.toFixed(1) +
      "g · 膳食纤维 " + 菜.膳食纤维.toFixed(1) + "g · 蛋白质 " + 菜.蛋白质.toFixed(1) + "g";
    菜名盒.appendChild(明细);
    li.appendChild(菜名盒);

    var 热量盒 = document.createElement("div");
    热量盒.className = "热量";
    热量盒.innerHTML = "<b>" + 菜.卡路里 + "</b> <small>kcal</small>";
    li.appendChild(热量盒);

    if (按钮区 === "加入") {
      // 份量选择：整份 / 半份，记录时按比例折算营养
      var 份量选择 = 创建份量选择(菜.名称);
      li.appendChild(份量选择);

      var 加入 = document.createElement("button");
      加入.type = "button";
      加入.className = "加入按钮";
      加入.textContent = "记录";
      加入.addEventListener("click", function () {
        添加记录(菜, null, Number(份量选择.value));
      });
      li.appendChild(加入);
    } else if (按钮区 === "移除") {
      var 移除 = document.createElement("button");
      移除.type = "button";
      移除.className = "移除按钮";
      移除.textContent = "移除";
      移除.addEventListener("click", function () {
        移除记录(菜);
      });
      li.appendChild(移除);
    }
    return li;
  }

  function 渲染列表(容器id, 列表, 按钮区) {
    var 容器 = 取元素(容器id);
    容器.innerHTML = "";
    列表.forEach(function (菜) {
      容器.appendChild(创建菜单项(菜, 按钮区));
    });
  }

  // 整份 / 半份下拉（搜索结果与推荐行共用）
  function 创建份量选择(菜名) {
    var 选择 = document.createElement("select");
    选择.className = "份量选择";
    选择.setAttribute("aria-label", 菜名 + " 份量");
    [["1", "整份"], ["0.5", "半份"]].forEach(function (项) {
      var 选项 = document.createElement("option");
      选项.value = 项[0];
      选项.textContent = 项[1];
      选择.appendChild(选项);
    });
    return 选择;
  }

  // ============ 食谱专区：按人群分区 + 搜索 + 排序 ============
  var 当前分区 = "全部";
  var 合法分区 = ["全部", "减脂", "增肌", "控糖", "均衡"];

  function 分区列表() {
    var 分区 = ["全部"].concat(Object.keys(人群系数));
    return 分区.map(function (名称) {
      var 数量 = 名称 === "全部"
        ? window.食谱数据.length
        : window.食谱数据.filter(function (菜) {
            return 菜.人群.indexOf(名称) !== -1;
          }).length;
      return { 名称: 名称, 数量: 数量 };
    });
  }

  // 创建带图片位的食谱卡（图片暂缺时用占位块，见 PRD 功能进度表）
  function 创建食谱卡(菜) {
    var 卡 = document.createElement("div");
    卡.className = "食谱卡";

    var 图区 = document.createElement("div");
    图区.className = "食谱图";
    if (菜.图片) {
      var img = document.createElement("img");
      img.src = 菜.图片;
      img.alt = 菜.名称;
      img.loading = "lazy";
      img.addEventListener("error", function () {
        图区.innerHTML = "";
        图区.appendChild(创建占位图(菜.名称));
      });
      图区.appendChild(img);
    } else {
      图区.appendChild(创建占位图(菜.名称));
    }
    卡.appendChild(图区);

    var 内容 = document.createElement("div");
    内容.className = "食谱卡内容";

    var 名字 = document.createElement("div");
    名字.className = "名字";
    名字.textContent = 菜.名称;
    内容.appendChild(名字);

    var 标签行 = document.createElement("div");
    菜.人群.forEach(function (人群名) {
      var 标签 = document.createElement("span");
      标签.className = "人群标签";
      标签.textContent = 人群名;
      标签行.appendChild(标签);
    });
    内容.appendChild(标签行);

    var 明细 = document.createElement("div");
    明细.className = "营养明细";
    明细.textContent = "碳水 " + 菜.碳水.toFixed(1) + "g · 脂肪 " + 菜.脂肪.toFixed(1) +
      "g · 膳食纤维 " + 菜.膳食纤维.toFixed(1) + "g · 蛋白质 " + 菜.蛋白质.toFixed(1) + "g";
    内容.appendChild(明细);

    // 食材与做法详情（默认收起，点「做法」展开）
    var 详情 = document.createElement("div");
    详情.className = "食谱详情";
    详情.hidden = true;
    if (菜.食材) {
      var 食材行 = document.createElement("p");
      食材行.className = "详情食材";
      食材行.textContent = "食材：" + 菜.食材;
      详情.appendChild(食材行);
    }
    if (菜.步骤 && 菜.步骤.length) {
      var 步骤表 = document.createElement("ol");
      步骤表.className = "详情步骤";
      菜.步骤.forEach(function (一步) {
        var li = document.createElement("li");
        li.textContent = 一步;
        步骤表.appendChild(li);
      });
      详情.appendChild(步骤表);
    }
    内容.appendChild(详情);

    var 底部 = document.createElement("div");
    底部.className = "食谱卡底部";

    var 热量盒 = document.createElement("div");
    热量盒.className = "热量";
    热量盒.innerHTML = "<b>" + 菜.卡路里 + "</b> <small>kcal</small>";
    底部.appendChild(热量盒);

    var 按钮组 = document.createElement("div");
    按钮组.className = "卡按钮组";

    // 展开「食材与做法」（数据来自食谱字段 食材 / 步骤）
    if (菜.食材 || (菜.步骤 && 菜.步骤.length)) {
      var 做法按钮 = document.createElement("button");
      做法按钮.type = "button";
      做法按钮.className = "做法按钮";
      做法按钮.textContent = "做法";
      做法按钮.setAttribute("aria-expanded", "false");
      做法按钮.addEventListener("click", function () {
        详情.hidden = !详情.hidden;
        做法按钮.classList.toggle("展开", !详情.hidden);
        做法按钮.setAttribute("aria-expanded", 详情.hidden ? "false" : "true");
      });
      按钮组.appendChild(做法按钮);
    }

    var 份量选择 = 创建份量选择(菜.名称);
    按钮组.appendChild(份量选择);

    var 按钮 = document.createElement("button");
    按钮.type = "button";
    按钮.className = "加入按钮";
    按钮.textContent = "记录";
    按钮.addEventListener("click", function () {
      添加记录(菜, null, Number(份量选择.value));
    });
    按钮组.appendChild(按钮);

    底部.appendChild(按钮组);

    内容.appendChild(底部);
    卡.appendChild(内容);
    return 卡;
  }

  function 创建占位图(菜名) {
    var 占位 = document.createElement("div");
    占位.className = "占位";
    // 占位块只显示 🍽 图标，菜名已在卡片标题显示，避免重复
    var 图标 = document.createElement("span");
    图标.textContent = "🍽";
    图标.style.cssText = "font-size:28px;opacity:0.55";
    占位.appendChild(图标);
    占位.setAttribute("aria-label", 菜名 + " 暂无图片");
    return 占位;
  }

  function 渲染专区() {
    var 导航 = 取元素("分区导航");
    导航.innerHTML = "";

    分区列表().forEach(function (项) {
      var 按钮 = document.createElement("button");
      按钮.type = "button";
      按钮.className = "分区按钮" + (项.名称 === 当前分区 ? " 选中" : "");
      按钮.setAttribute("role", "tab");
      按钮.setAttribute("aria-selected", 项.名称 === 当前分区 ? "true" : "false");
      按钮.innerHTML = 项.名称 + '<span class="计数">' + 项.数量 + "</span>";
      按钮.addEventListener("click", function () {
        当前分区 = 项.名称;
        try {
          localStorage.setItem(食谱分区键, 项.名称);   // 记住上次分区
        } catch (e) { /* 隐私模式忽略 */ }
        渲染专区();
      });
      导航.appendChild(按钮);
    });

    var 内容 = 取元素("分区内容");
    内容.innerHTML = "";

    var 待显示 = 当前分区 === "全部"
      ? window.食谱数据.slice()
      : window.食谱数据.filter(function (菜) {
          return 菜.人群.indexOf(当前分区) !== -1;
        });

    // 关键词过滤（按菜名包含匹配）
    if (当前搜索词) {
      待显示 = 待显示.filter(function (菜) {
        return 菜.名称.indexOf(当前搜索词) !== -1;
      });
    }

    // 排序：默认按 id；热量升 / 降按卡路里，同热量按 id 稳定排序
    if (当前排序 === "热量升") {
      待显示.sort(function (a, b) {
        return a.卡路里 - b.卡路里 || a.id.localeCompare(b.id);
      });
    } else if (当前排序 === "热量降") {
      待显示.sort(function (a, b) {
        return b.卡路里 - a.卡路里 || a.id.localeCompare(b.id);
      });
    } else {
      待显示.sort(function (a, b) {
        return a.id.localeCompare(b.id);
      });
    }

    if (待显示.length === 0) {
      var 空 = document.createElement("p");
      空.className = "空分区";
      空.textContent = 当前搜索词
        ? "没有找到「" + 当前搜索词 + "」相关的菜，换个关键词或分区试试。"
        : "这个分类下暂时还没有食谱。";
      内容.appendChild(空);
      return;
    }

    var 网格 = document.createElement("div");
    网格.className = "食谱网格";
    待显示.forEach(function (菜) {
      网格.appendChild(创建食谱卡(菜));
    });
    内容.appendChild(网格);
  }

  // ============ 一周食谱计划（只做 7 天） ============
  var 计划存储键 = "食谱搭配-一周计划";
  var 计划天数 = 7;          // 固定 7 天；不做 30 天，见 PRD 三不原则第 3 条
  var 每日餐次 = ["早", "午", "晚"];

  function 读计划() {
    try {
      var 原文 = localStorage.getItem(计划存储键);
      return 原文 ? JSON.parse(原文) : null;
    } catch (e) {
      return null;
    }
  }

  function 写计划(计划) {
    if (计划 === null) {
      localStorage.removeItem(计划存储键);
    } else {
      localStorage.setItem(计划存储键, JSON.stringify(计划));
    }
  }

  // 生成 7 天计划：逐日扣减额度，同一周内不重复推荐
  // 两条硬约束：
  //   1) 同一天内不重复同一道菜
  //   2) 单餐卡路里不得超过当日剩余额度（否则会出现"预算 40 却推 160 的菜"）
  function 生成一周计划(人群, 每日目标) {
    var 已用ids = [];
    var 天数 = [];

    for (var d = 0; d < 计划天数; d++) {
      var 当日餐 = [];
      var 当日卡路里 = 0;
      var 当日已用 = [];

      for (var m = 0; m < 每日餐次.length; m++) {
        var 剩余额度 = 每日目标 - 当日卡路里;
        if (剩余额度 <= 100) break;

        var 餐预算 = 剩余额度 / (每日餐次.length - m);

        // 候选：本人群 + 本周未用过 + 今天未用过 + 单餐不超剩余额度
        var 候选 = window.食谱数据.filter(function (菜) {
          return 菜.人群.indexOf(人群) !== -1 &&
                 已用ids.indexOf(菜.id) === -1 &&
                 当日已用.indexOf(菜.id) === -1 &&
                 菜.卡路里 <= 剩余额度;
        });

        if (候选.length === 0) {
          // 本周可选项用尽：允许跨天重复，但同一天内仍不重复
          候选 = window.食谱数据.filter(function (菜) {
            return 菜.人群.indexOf(人群) !== -1 &&
                   当日已用.indexOf(菜.id) === -1 &&
                   菜.卡路里 <= 剩余额度;
          });
          if (候选.length === 0) break;
        }

        候选.sort(function (a, b) {
          return Math.abs(a.卡路里 - 餐预算) - Math.abs(b.卡路里 - 餐预算);
        });

        var 选中 = 候选[0];
        当日餐.push({
          餐次: 每日餐次[m],
          id: 选中.id,
          名称: 选中.名称,
          卡路里: 选中.卡路里
        });
        当日已用.push(选中.id);
        已用ids.push(选中.id);
        当日卡路里 += 选中.卡路里;
      }

      天数.push({
        序号: d + 1,
        名称: "第 " + (d + 1) + " 天",
        餐: 当日餐,
        卡路里合计: Math.round(当日卡路里)
      });
    }

    return {
      人群: 人群,
      每日目标: 每日目标,
      天数: 天数
    };
  }

  function 渲染计划() {
    var 容器 = 取元素("计划结果");
    var 说明 = 取元素("计划说明");
    var 范围说明 = 取元素("计划范围说明");
    容器.innerHTML = "";

    范围说明.textContent = "固定 " + 计划天数 + " 天，不提供 30 天计划。";

    var 目标 = 读目标();
    if (!目标) {
      说明.textContent = "设置每日目标后，可生成连续 7 天的食谱安排。";
      取元素("生成计划按钮").disabled = true;
      return;
    }
    取元素("生成计划按钮").disabled = false;

    var 计划 = 读计划();
    if (!计划) {
      说明.textContent = "点击「生成一周计划」，按「" + 目标.人群 + "」为你排出 7 天三餐。";
      取元素("偏差说明").hidden = true;
      return;
    }

    说明.textContent = "按「" + 计划.人群 + "」生成，每日目标 " + 计划.每日目标 + " kcal。";

    var 表 = document.createElement("div");
    表.className = "计划表";

    计划.天数.forEach(function (日) {
      var 是今天 = 日.序号 === 1;
      var 日块 = document.createElement("div");
      // 今天（第 1 天）默认展开并高亮；其余 6 天折叠，点标题行切换
      日块.className = "计划日" + (是今天 ? " 今天" : " 收起");

      var 头 = document.createElement("div");
      头.className = "计划日头";
      头.addEventListener("click", function () {
        日块.classList.toggle("收起");
      });

      var 名 = document.createElement("div");
      名.className = "计划日名";
      名.textContent = 是今天 ? "今天（第 1 天）" : 日.名称;

      var 统计 = document.createElement("div");
      统计.className = "计划日统计" + (日.卡路里合计 > 计划.每日目标 ? " 超额度" : "");
      统计.textContent = 日.卡路里合计 + " / " + 计划.每日目标 + " kcal";

      头.appendChild(名);
      头.appendChild(统计);
      日块.appendChild(头);

      if (日.餐.length === 0) {
        var 空 = document.createElement("p");
        空.className = "提示";
        空.textContent = "该人群食谱不足，无法排出三餐。";
        日块.appendChild(空);
      } else {
        日.餐.forEach(function (餐) {
          var 行 = document.createElement("div");
          行.className = "计划餐";

          var 标签 = document.createElement("span");
          标签.className = "餐次标签";
          标签.textContent = 餐.餐次;

          var 菜名 = document.createElement("span");
          菜名.className = "菜名";
          菜名.textContent = 餐.名称;

          var 热量 = document.createElement("span");
          热量.className = "热量";
          热量.textContent = 餐.卡路里 + " kcal";

          行.appendChild(标签);
          行.appendChild(菜名);
          行.appendChild(热量);

          // 第 1 天视为今天：可一键「标记已吃」转入今日记录
          if (日.序号 === 1) {
            var 已吃 = 计划.已吃 || [];
            if (已吃.indexOf(已吃键(日.序号, 餐.餐次)) !== -1) {
              var 徽章 = document.createElement("span");
              徽章.className = "已吃徽章";
              徽章.textContent = "已吃 ✓";
              行.appendChild(徽章);
            } else {
              var 标记按钮 = document.createElement("button");
              标记按钮.type = "button";
              标记按钮.className = "标记已吃按钮";
              标记按钮.textContent = "标记已吃";
              标记按钮.addEventListener("click", function () {
                标记计划已吃(日.序号, 餐);
              });
              行.appendChild(标记按钮);
            }
          }

          日块.appendChild(行);
        });
      }
      表.appendChild(日块);
    });

    容器.appendChild(表);

    // 计划 vs 实际：第 1 天视为今天，用一句话文字说明偏差（不做图表，见三不原则第 2 条）
    var 偏差说明 = 取元素("偏差说明");
    偏差说明.hidden = false;
    var 首日 = 计划.天数[0];
    var 实际 = 汇总营养(读记录()).卡路里;
    var 偏差文本 = "今天（第 1 天）计划合计 " + 首日.卡路里合计 + " kcal，实际已记录 " + 实际 + " kcal";
    if (实际 === 0) {
      偏差文本 += "，还没开始记录。";
    } else {
      var 差值 = 实际 - 首日.卡路里合计;
      if (差值 > 0) 偏差文本 += "，比计划多约 " + 差值 + " kcal。";
      else if (差值 < 0) 偏差文本 += "，比计划少约 " + (-差值) + " kcal。";
      else 偏差文本 += "，与计划一致。";
    }
    偏差说明.textContent = 偏差文本;
  }

  function 生成计划() {
    var 目标 = 读目标();
    if (!目标) return;
    var 计划 = 生成一周计划(目标.人群, 目标.目标);
    计划.已吃 = [];   // 已吃标记，键为 "天序号-餐次"
    写计划(计划);
    渲染计划();
  }

  function 清除计划() {
    写计划(null);
    渲染计划();
  }

  // 「标记已吃」：把计划中的一餐转入今日记录（借鉴 CookHero 的 计划 → 记录 闭环）
  function 已吃键(天序号, 餐次) {
    return 天序号 + "-" + 餐次;
  }

  function 标记计划已吃(天序号, 餐) {
    var 计划 = 读计划();
    if (!计划) return;
    var 菜 = 按id查找(餐.id);
    if (!菜) return;
    添加记录(菜, 餐.餐次);
    计划.已吃 = 计划.已吃 || [];
    var 键 = 已吃键(天序号, 餐.餐次);
    if (计划.已吃.indexOf(键) === -1) 计划.已吃.push(键);
    写计划(计划);
    渲染计划();
  }

  function 渲染记录() {
    var 记录 = 读记录();
    渲染列表("记录列表", 记录, "移除");
    取元素("记录空提示").hidden = 记录.length > 0;
  }

  function 渲染进度() {
    var 记录 = 读记录();
    var 合计 = 汇总营养(记录);
    var 目标 = 读目标();
    var 目标值 = 目标 ? 目标.目标 : null;

    取元素("已摄入").textContent = 合计.卡路里;

    // 顶栏常驻目标值（滚动到哪都能看到自己的额度）
    取元素("顶栏目标").textContent = 目标值 === null ? "—" : 目标值;

    // 直接按 id 取，不再依赖 nextElementSibling 的 DOM 顺序。
    // 结构一改就崩，这正是第 5 周要讲的"隐式契约"问题。
    var 目标文本 = 目标值 === null ? "—" : 目标值;
    取元素("目标对照").textContent = "/ 目标 " + 目标文本;

    var 填充 = 取元素("进度填充");
    if (目标值 === null) {
      填充.style.width = "0%";
      填充.classList.remove("超出");
    } else {
      var 比例 = 合计.卡路里 / 目标值;
      填充.style.width = Math.min(比例, 1) * 100 + "%";
      填充.classList.toggle("超出", 合计.卡路里 > 目标值);
    }

    取元素("总碳水").textContent = 合计.碳水.toFixed(1);
    取元素("总脂肪").textContent = 合计.脂肪.toFixed(1);
    取元素("总纤维").textContent = 合计.膳食纤维.toFixed(1);
    取元素("总蛋白质").textContent = 合计.蛋白质.toFixed(1);

    // 宏量营养目标（按人群换算），无目标时只显示单位
    var 宏量 = 目标值 === null ? null : 计算宏量目标(目标值, 目标.人群);
    取元素("碳水目标").textContent = 宏量 ? "g / 目标 " + 宏量.碳水 : "g";
    取元素("脂肪目标").textContent = 宏量 ? "g / 目标 " + 宏量.脂肪 : "g";
    取元素("蛋白目标").textContent = 宏量 ? "g / 目标 " + 宏量.蛋白质 : "g";

    // 空状态引导：没设目标时给一句去哪设置的指引
    取元素("今日引导").hidden = 目标值 !== null;

    return { 合计: 合计, 目标值: 目标值 };
  }

  function 渲染推荐() {
    var 目标 = 读目标();
    var 记录 = 读记录();
    var 说明 = 取元素("推荐说明");

    if (!目标) {
      说明.textContent = "设置目标后开始推荐";
      取元素("推荐列表").innerHTML = "";
      取元素("换一批按钮").disabled = true;
      return;
    }

    var 营养 = 汇总营养(记录);
    var 剩余 = Math.max(目标.目标 - 营养.卡路里, 0);
    var 已记录ids = 记录.map(function (菜) { return 菜.id; });
    var 结果 = 生成推荐(目标.人群, 剩余, 已记录ids, 推荐偏移);

    说明.textContent = 结果.说明;
    // 候选不够 3 道时「换一批」翻不出新内容，直接禁用
    取元素("换一批按钮").disabled = 结果.候选数 <= 推荐数量;
    渲染列表("推荐列表", 结果.列表, "加入");
  }

  function 刷新所有() {
    推荐偏移 = 0;   // 记录或目标变了，推荐从头排
    渲染进度();
    渲染记录();
    渲染推荐();
  }

  // ============ 事件 ============
  // 添加记录：份量（整份 1 / 半份 0.5）按比例折算营养；
  // 记录id 为每条记录的唯一键，同一道菜记两次也能分别移除。
  function 添加记录(菜, 指定餐次, 份量) {
    var 记录 = 读记录();
    var 营养 = 折算份量(菜, 份量);
    记录.push({
      记录id: Date.now() + "-" + Math.floor(Math.random() * 10000),
      id: 菜.id,
      名称: 菜.名称,
      人群: 菜.人群.slice(),
      卡路里: 营养.卡路里,
      碳水: 营养.碳水,
      脂肪: 营养.脂肪,
      膳食纤维: 营养.膳食纤维,
      蛋白质: 营养.蛋白质,
      份量: 份量 === 0.5 ? 0.5 : 1,
      餐次: 指定餐次 || 判定餐次()
    });
    写记录(记录);
    刷新所有();
  }

  // 移除记录：优先按唯一键 记录id 删单条；旧存档没有 记录id 时回退按菜品 id 删
  function 移除记录(条目) {
    var 记录 = 读记录();
    if (条目.记录id) {
      记录 = 记录.filter(function (t) { return t.记录id !== 条目.记录id; });
    } else {
      记录 = 记录.filter(function (t) { return t.id !== 条目.id; });
    }
    写记录(记录);
    刷新所有();
  }

  // ============ 近 7 天记录（纯文字回看，不做图表） ============
  function 今日日期串() {
    var d = new Date();
    return d.getFullYear() + "-" +
      ("0" + (d.getMonth() + 1)).slice(-2) + "-" +
      ("0" + d.getDate()).slice(-2);
  }

  function 读历史() {
    try {
      var 原文 = localStorage.getItem(历史存储键);
      var 历史 = 原文 ? JSON.parse(原文) : {};
      return 历史 && typeof 历史 === "object" ? 历史 : {};
    } catch (e) {
      return {};
    }
  }

  function 写历史(历史) {
    localStorage.setItem(历史存储键, JSON.stringify(历史));
  }

  // 只保留最近 N 天（日期字符串排序即时间序）
  function 截断历史(历史, 天数) {
    var 键集 = Object.keys(历史).sort();
    while (键集.length > 天数) {
      delete 历史[键集.shift()];
    }
    return 历史;
  }

  // 换天结转：上次记录的日期不是今天 → 把当时的今日记录存入历史并清空
  function 结转历史() {
    var 今日 = 今日日期串();
    var 存日期 = null;
    try {
      存日期 = localStorage.getItem(记录日期键);
    } catch (e) { /* 忽略 */ }

    if (!存日期) {
      // 旧版本存档没有日期戳：视为今天的记录，不结转，只补日期
      try { localStorage.setItem(记录日期键, 今日); } catch (e) { /* 忽略 */ }
      return;
    }
    if (存日期 === 今日) return;

    var 记录 = 读记录();
    if (记录.length > 0) {
      var 历史 = 读历史();
      历史[存日期] = 记录;
      写历史(截断历史(历史, 历史保留天数));
    }
    写记录([]);
    try { localStorage.setItem(记录日期键, 今日); } catch (e) { /* 忽略 */ }
  }

  function 渲染历史() {
    var 容器 = 取元素("历史内容");
    容器.innerHTML = "";
    var 历史 = 读历史();
    var 日期集 = Object.keys(历史).sort().reverse();   // 最近在前

    取元素("历史空提示").hidden = 日期集.length > 0;

    日期集.forEach(function (日期) {
      var 条目 = 历史[日期];
      var 合计 = 汇总营养(条目);
      var 部 = 日期.split("-");

      var 日块 = document.createElement("div");
      日块.className = "历史日 收起";

      var 头 = document.createElement("div");
      头.className = "历史日头";
      头.addEventListener("click", function () {
        日块.classList.toggle("收起");
      });

      var 名 = document.createElement("span");
      名.className = "历史日名";
      名.textContent = Number(部[1]) + " 月 " + Number(部[2]) + " 日";

      var 统计 = document.createElement("span");
      统计.className = "历史日统计";
      统计.textContent = 条目.length + " 条 · " + 合计.卡路里 + " kcal";

      头.appendChild(名);
      头.appendChild(统计);
      日块.appendChild(头);

      条目.forEach(function (条) {
        var 行 = document.createElement("div");
        行.className = "历史条目";

        var 餐次 = document.createElement("span");
        餐次.className = "餐次标签";
        餐次.textContent = 条.餐次 || "·";

        var 菜名 = document.createElement("span");
        菜名.className = "菜名";
        菜名.textContent = 条.名称 + (条.份量 === 0.5 ? "（半份）" : "");

        var 热量 = document.createElement("span");
        热量.className = "热量";
        热量.textContent = 条.卡路里 + " kcal";

        行.appendChild(餐次);
        行.appendChild(菜名);
        行.appendChild(热量);
        日块.appendChild(行);
      });

      容器.appendChild(日块);
    });
  }

  // 设置卡片：折叠交互（目标设好后收起表单，只留摘要，低频操作不占首屏）
  function 更新设置摘要(目标) {
    取元素("设置摘要").textContent = 目标
      ? 目标.人群 + " · 目标 " + 目标.目标 + " kcal · "
        + (目标.性别 === "男" ? "男" : "女") + " " + 目标.年龄 + " 岁"
      : "先填身体数据，算出每日目标。";
  }

  function 折叠设置(收起) {
    取元素("设置主体").hidden = 收起;
    取元素("设置开关").textContent = 收起 ? "修改" : "收起";
  }

  function 设置目标(事件) {
    事件.preventDefault();

    var 性别 = 取元素("性别").value;
    var 年龄 = Number(取元素("年龄").value);
    var 身高 = Number(取元素("身高").value);
    var 体重 = Number(取元素("体重").value);
    var 活动系数 = Number(取元素("活动量").value);
    var 人群 = 取元素("人群").value;

    var 结果 = 计算目标卡路里(性别, 体重, 身高, 年龄, 活动系数, 人群);
    写目标({
      性别: 性别,
      年龄: 年龄,
      身高: 身高,
      体重: 体重,
      活动量: 活动系数,
      人群: 人群,
      目标: 结果.目标
    });

    显示目标结果(结果);
    更新设置摘要(读目标());
    折叠设置(true);
    刷新所有();
    // 目标变了，计划区需要刷新：解锁「生成计划」按钮并更新提示。
    // 否则设置目标后按钮仍处于 disabled 状态，用户点不动。
    渲染计划();
  }

  function 显示目标结果(结果) {
    var 盒子 = 取元素("目标结果");
    盒子.hidden = false;
    取元素("目标值").textContent = 结果.目标;

    var 文本 = "基础代谢 " + 结果.基础代谢 + " kcal → 每日消耗 " +
      结果.每日消耗 + " kcal → 调整后 " + 结果.调整后 + " kcal";
    if (结果.是否上调) {
      文本 += "；低于安全下限，已上调至 " + 最低目标 + " kcal";
    }
    取元素("目标提示").textContent = 文本;
  }

  function 回填目标表单(目标) {
    if (!目标) return;
    取元素("性别").value = 目标.性别;
    取元素("年龄").value = 目标.年龄;
    取元素("身高").value = 目标.身高;
    取元素("体重").value = 目标.体重;
    取元素("活动量").value = String(目标.活动量);
    取元素("人群").value = 目标.人群;
  }

  // ============ 健身动作教程（按部位分区） ============
  var 动作部位 = ["全部", "上肢", "下肢", "核心", "全身"];
  var 当前部位 = "全部";

  function 部位列表() {
    return 动作部位.map(function (名称) {
      var 数量 = 名称 === "全部"
        ? window.动作数据.length
        : window.动作数据.filter(function (a) {
            return a.部位 === 名称;
          }).length;
      return { 名称: 名称, 数量: 数量 };
    });
  }

  // 无图动作的 SVG 简笔示意图（用姿态剪影区分部位）
  function 画示意图(动作) {
    var 图 = {
      上肢: '<circle cx="60" cy="26" r="8"/><line x1="60" y1="34" x2="60" y2="62"/><line x1="60" y1="42" x2="34" y2="52"/><line x1="60" y1="42" x2="86" y2="52"/><line x1="60" y1="62" x2="48" y2="86"/><line x1="60" y1="62" x2="72" y2="86"/>',
      下肢: '<circle cx="60" cy="24" r="8"/><line x1="60" y1="32" x2="60" y2="56"/><line x1="60" y1="40" x2="44" y2="50"/><line x1="60" y1="40" x2="76" y2="50"/><line x1="60" y1="56" x2="42" y2="80"/><line x1="42" y1="80" x2="42" y2="90"/><line x1="60" y1="56" x2="78" y2="80"/><line x1="78" y1="80" x2="78" y2="90"/>',
      核心: '<circle cx="34" cy="60" r="7"/><line x1="41" y1="60" x2="72" y2="44"/><line x1="72" y1="44" x2="92" y2="76"/><line x1="92" y1="76" x2="104" y2="78"/><line x1="55" y1="52" x2="52" y2="76"/><line x1="52" y1="76" x2="64" y2="80"/>',
      全身: '<circle cx="60" cy="22" r="8"/><line x1="60" y1="30" x2="60" y2="58"/><line x1="60" y1="36" x2="36" y2="26"/><line x1="60" y1="36" x2="84" y2="26"/><line x1="60" y1="58" x2="44" y2="86"/><line x1="60" y1="58" x2="76" y2="86"/>'
    };
    var 路径 = 图[动作.部位] || 图.全身;
    var svg = '<svg viewBox="0 0 120 100" width="150" height="125" ' +
      'fill="none" stroke="#3B6D11" stroke-width="3.2" stroke-linecap="round" ' +
      'aria-label="' + 动作.名称 + ' 示意图" role="img">' + 路径 + '</svg>';

    var 盒 = document.createElement("div");
    盒.className = "示意";
    盒.innerHTML = svg;
    return 盒;
  }

  function 创建动作卡(动作) {
    var 卡 = document.createElement("div");
    卡.className = "动作卡";

    var 图区 = document.createElement("div");
    图区.className = "动作图";
    if (动作.图片) {
      var img = document.createElement("img");
      img.src = 动作.图片;
      img.alt = 动作.名称;
      img.loading = "lazy";
      img.addEventListener("error", function () {
        图区.innerHTML = "";
        图区.appendChild(画示意图(动作));
      });
      图区.appendChild(img);
    } else {
      图区.appendChild(画示意图(动作));
    }
    卡.appendChild(图区);

    var 内容 = document.createElement("div");
    内容.className = "动作内容";

    var 头 = document.createElement("div");
    头.className = "动作头";
    var 名 = document.createElement("span");
    名.className = "动作名";
    名.textContent = 动作.名称;
    var 建议 = document.createElement("span");
    建议.className = "动作建议";
    建议.textContent = 动作.建议;
    头.appendChild(名);
    头.appendChild(建议);
    内容.appendChild(头);

    var 肌群 = document.createElement("div");
    肌群.className = "动作肌群";
    肌群.textContent = "目标： " + 动作.目标肌群;
    内容.appendChild(肌群);

    var 要点标题 = document.createElement("div");
    要点标题.className = "动作小节标题";
    要点标题.textContent = "动作要点";
    内容.appendChild(要点标题);

    var 要点 = document.createElement("ul");
    要点.className = "动作要点";
    动作.要点.forEach(function (条) {
      var li = document.createElement("li");
      li.textContent = 条;
      要点.appendChild(li);
    });
    内容.appendChild(要点);

    if (动作.常见错误 && 动作.常见错误.length) {
      var 错标题 = document.createElement("div");
      错标题.className = "动作小节标题";
      错标题.textContent = "常见错误";
      内容.appendChild(错标题);

      var 错误 = document.createElement("ul");
      错误.className = "动作错误";
      动作.常见错误.forEach(function (条) {
        var li = document.createElement("li");
        li.textContent = 条;
        错误.appendChild(li);
      });
      内容.appendChild(错误);
    }

    卡.appendChild(内容);
    return 卡;
  }

  function 渲染动作() {
    if (typeof window.动作数据 === "undefined") return;

    var 导航 = 取元素("部位导航");
    导航.innerHTML = "";

    部位列表().forEach(function (项) {
      var 按钮 = document.createElement("button");
      按钮.type = "button";
      按钮.className = "分区按钮" + (项.名称 === 当前部位 ? " 选中" : "");
      按钮.setAttribute("role", "tab");
      按钮.innerHTML = 项.名称 + '<span class="计数">' + 项.数量 + "</span>";
      按钮.addEventListener("click", function () {
        当前部位 = 项.名称;
        渲染动作();
      });
      导航.appendChild(按钮);
    });

    var 内容 = 取元素("动作内容");
    内容.innerHTML = "";

    var 待显示 = 当前部位 === "全部"
      ? window.动作数据.slice()
      : window.动作数据.filter(function (a) {
          return a.部位 === 当前部位;
        });

    if (待显示.length === 0) {
      var 空 = document.createElement("p");
      空.className = "空分区";
      空.textContent = "这个部位暂时还没有动作。";
      内容.appendChild(空);
      return;
    }

    var 网格 = document.createElement("div");
    网格.className = "动作网格";
    待显示.forEach(function (动作) {
      网格.appendChild(创建动作卡(动作));
    });
    内容.appendChild(网格);
  }

  // ============ 主功能分区切换 ============
  var 主分区键 = "食谱搭配-主分区";
  var 当前主分区 = "饮食";

  function 切换主分区(名称) {
    当前主分区 = 名称;
    ["饮食", "训练"].forEach(function (名) {
      var 区 = 取元素("分区-" + 名);
      if (区) 区.hidden = 名 !== 名称;
    });
    var 按钮集 = document.querySelectorAll(".主导航按钮");
    for (var i = 0; i < 按钮集.length; i++) {
      var 是选中 = 按钮集[i].getAttribute("data-分区") === 名称;
      按钮集[i].classList.toggle("选中", 是选中);
      按钮集[i].setAttribute("aria-selected", 是选中 ? "true" : "false");
    }
    try {
      localStorage.setItem(主分区键, 名称);
    } catch (e) { /* 隐私模式可能写入失败，忽略 */ }
  }

  function 初始化主分区() {
    var 保存 = null;
    try {
      保存 = localStorage.getItem(主分区键);
    } catch (e) { /* 忽略 */ }
    if (保存 === "训练" || 保存 === "饮食") 当前主分区 = 保存;

    var 按钮集 = document.querySelectorAll(".主导航按钮");
    for (var i = 0; i < 按钮集.length; i++) {
      (function (按钮) {
        按钮.addEventListener("click", function () {
          切换主分区(按钮.getAttribute("data-分区"));
        });
      })(按钮集[i]);
    }
    切换主分区(当前主分区);
  }

  function 初始化() {
    // 自检：数据文件缺失时给出明确提示，避免页面"看起来正常但完全不可用"。
    // 见 作业/A1/A1-运行证据.md 实验 C。
    if (typeof window.食谱数据 === "undefined") {
      var 提示 = document.createElement("p");
      提示.style.cssText = "padding:48px 24px;text-align:center;font-size:16px;color:#d64545";
      提示.textContent = "数据文件未加载，请确认 数据/食谱.js 存在。";
      document.body.innerHTML = "";
      document.body.appendChild(提示);
      return;
    }

    var 目标 = 读目标();
    回填目标表单(目标);

    // 换天结转：把昨天的记录存进历史，今天从空记录开始（近 7 天可回看）
    结转历史();

    if (目标) {
      // 用当前系数重新计算并回写，保证顶部目标与"今日摄入"用的是同一个值。
      // 否则改了 人群系数 后刷新页面，顶部按新代码算、进度栏读旧存档，两处数字会打架。
      var 结果 = 计算目标卡路里(
        目标.性别, 目标.体重, 目标.身高, 目标.年龄, 目标.活动量, 目标.人群
      );
      if (结果.目标 !== 目标.目标) {
        目标.目标 = 结果.目标;
        写目标(目标);
      }
      显示目标结果(结果);
    }

    // 首屏日期（今日餐盘右上角）
    var 今 = new Date();
    取元素("今日日期").textContent =
      (今.getMonth() + 1) + " 月 " + 今.getDate() + " 日 · 周" +
      "日一二三四五六".charAt(今.getDay());

    // 设置卡片：已有目标则折叠为摘要，未设置则展开表单引导填写
    更新设置摘要(目标);
    折叠设置(Boolean(目标));
    取元素("设置开关").addEventListener("click", function () {
      折叠设置(!取元素("设置主体").hidden);
    });

    取元素("设置表单").addEventListener("submit", 设置目标);
    取元素("清空按钮").addEventListener("click", function () {
      写记录([]);
      刷新所有();
    });
    取元素("生成计划按钮").addEventListener("click", 生成计划);
    取元素("清空计划按钮").addEventListener("click", 清除计划);

    // 功能增强：换一批 / 搜索 / 排序 / 分区记忆
    取元素("换一批按钮").addEventListener("click", function () {
      推荐偏移 += 推荐数量;
      渲染推荐();
    });
    取元素("搜索输入").addEventListener("input", function () {
      当前搜索词 = this.value.trim();
      渲染专区();
    });
    取元素("排序选择").addEventListener("change", function () {
      当前排序 = this.value;
      渲染专区();
    });
    try {
      var 存分区 = localStorage.getItem(食谱分区键);
      if (合法分区.indexOf(存分区) !== -1) 当前分区 = 存分区;
    } catch (e) { /* 忽略 */ }

    渲染专区();
    渲染计划();
    渲染动作();
    渲染历史();
    刷新所有();
    初始化主分区();
  }

  document.addEventListener("DOMContentLoaded", 初始化);

  // 暴露给测试脚本（第 10 周回归测试会用）
  window.食谱搭配 = {
    计算基础代谢: 计算基础代谢,
    计算目标卡路里: 计算目标卡路里,
    计算宏量目标: 计算宏量目标,
    判定餐次: 判定餐次,
    汇总营养: 汇总营养,
    生成推荐: 生成推荐,
    按偏移取段: 按偏移取段,
    折算份量: 折算份量,
    截断历史: 截断历史,
    生成一周计划: 生成一周计划,
    计划天数: 计划天数,
    动作部位: 动作部位
  };
})();