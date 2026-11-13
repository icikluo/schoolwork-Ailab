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
  function 生成推荐(人群, 剩余卡路里, 已记录ids) {
    var 候选 = window.食谱数据.filter(function (菜) {
      return 菜.人群.indexOf(人群) !== -1 && 已记录ids.indexOf(菜.id) === -1;
    });

    if (剩余卡路里 <= 100) {
      return { 列表: [], 说明: "今日已达目标额度，明天再吃吧。" };
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

    var 列表 = 候选.slice(0, 推荐数量);
    var 说明 = "按「" + 人群 + "」优先" + 推荐优先级[人群] + "，结合剩余 " +
      剩余卡路里 + " kcal 挑出以下 " + 列表.length + " 道。";
    if (候选.length === 0) {
      说明 = "今天的食谱都记录过了，明天可以换个吃法。";
    }
    return { 列表: 列表, 说明: 说明 };
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
    名字.textContent = 菜.名称;
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
      var 加入 = document.createElement("button");
      加入.type = "button";
      加入.className = "加入按钮";
      加入.textContent = "记录";
      加入.addEventListener("click", function () {
        添加记录(菜);
      });
      li.appendChild(加入);
    } else if (按钮区 === "移除") {
      var 移除 = document.createElement("button");
      移除.type = "button";
      移除.className = "移除按钮";
      移除.textContent = "移除";
      移除.addEventListener("click", function () {
        移除记录(菜.id);
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

  // ============ 食谱专区：按人群分区 ============
  var 当前分区 = "全部";

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

    var 按钮 = document.createElement("button");
    按钮.type = "button";
    按钮.className = "加入按钮";
    按钮.textContent = "记录";
    按钮.addEventListener("click", function () {
      添加记录(菜);
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
    待显示.sort(function (a, b) {
      return a.id.localeCompare(b.id);
    });

    if (待显示.length === 0) {
      var 空 = document.createElement("p");
      空.className = "空分区";
      空.textContent = "这个分类下暂时还没有食谱。";
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
      var 日块 = document.createElement("div");
      日块.className = "计划日";

      var 头 = document.createElement("div");
      头.className = "计划日头";

      var 名 = document.createElement("div");
      名.className = "计划日名";
      名.textContent = 日.名称;

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

    return { 合计: 合计, 目标值: 目标值 };
  }

  function 渲染推荐() {
    var 目标 = 读目标();
    var 记录 = 读记录();
    var 说明 = 取元素("推荐说明");

    if (!目标) {
      说明.textContent = "设置目标后开始推荐";
      取元素("推荐列表").innerHTML = "";
      return;
    }

    var 营养 = 汇总营养(记录);
    var 剩余 = Math.max(目标.目标 - 营养.卡路里, 0);
    var 已记录ids = 记录.map(function (菜) { return 菜.id; });
    var 结果 = 生成推荐(目标.人群, 剩余, 已记录ids);

    说明.textContent = 结果.说明;
    渲染列表("推荐列表", 结果.列表, "加入");
  }

  function 刷新所有() {
    渲染进度();
    渲染记录();
    渲染推荐();
  }

  // ============ 事件 ============
  function 添加记录(菜, 指定餐次) {
    var 记录 = 读记录();
    记录.push({
      id: 菜.id,
      名称: 菜.名称,
      人群: 菜.人群.slice(),
      卡路里: 菜.卡路里,
      碳水: 菜.碳水,
      脂肪: 菜.脂肪,
      膳食纤维: 菜.膳食纤维,
      蛋白质: 菜.蛋白质,
      餐次: 指定餐次 || 判定餐次()
    });
    写记录(记录);
    刷新所有();
  }

  function 移除记录(id) {
    var 记录 = 读记录();
    记录 = 记录.filter(function (条目) { return 条目.id !== id; });
    写记录(记录);
    刷新所有();
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
      'fill="none" stroke="#2b6cb0" stroke-width="3.2" stroke-linecap="round" ' +
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

  // ============ AI 助手（v0.3 新增，可选功能，需联网） ============
  // 三条边界（见 PRD 5.13）：
  //   1) 密钥只存浏览器 localStorage，不写进代码、不进仓库、不上传任何服务器（仓库是公开的）。
  //   2) 未配置密钥或网络失败时，AI 功能给出提示并停用；其余功能完全不受影响，仍离线可用。
  //   3) 接口走 OpenAI 兼容 /chat/completions（默认 DeepSeek，可换任何兼容服务）。
  var AI设置存储键 = "食谱搭配-AI设置";
  var AI默认设置 = { 接口地址: "https://api.deepseek.com", 模型: "deepseek-chat", 密钥: "" };
  var 合法餐次表 = ["早", "午", "晚", "加餐"];

  function 读AI设置() {
    var 缺省 = { 接口地址: AI默认设置.接口地址, 模型: AI默认设置.模型, 密钥: "" };
    try {
      var 原文 = localStorage.getItem(AI设置存储键);
      var 存 = 原文 ? JSON.parse(原文) : {};
      if (typeof 存.接口地址 === "string" && 存.接口地址) 缺省.接口地址 = 存.接口地址;
      if (typeof 存.模型 === "string" && 存.模型) 缺省.模型 = 存.模型;
      if (typeof 存.密钥 === "string") 缺省.密钥 = 存.密钥;
    } catch (e) { /* 存档损坏则回退默认 */ }
    return 缺省;
  }

  function 写AI设置(设置) {
    localStorage.setItem(AI设置存储键, JSON.stringify(设置));
  }

  function AI已配置(设置) {
    设置 = 设置 || 读AI设置();
    return 设置.密钥.trim().length > 0;
  }

  function 保存AI设置(事件) {
    事件.preventDefault();
    var 接口 = 取元素("AI接口").value.trim();
    var 模型 = 取元素("AI模型").value.trim();
    var 密钥 = 取元素("AI密钥").value.trim();
    var 状态 = 取元素("AI状态");

    if (接口.indexOf("http://") !== 0 && 接口.indexOf("https://") !== 0) {
      状态.textContent = "接口地址需以 http:// 或 https:// 开头。";
      return;
    }
    if (!模型) {
      状态.textContent = "模型名不能为空。";
      return;
    }
    写AI设置({ 接口地址: 接口, 模型: 模型, 密钥: 密钥 });
    显示AI状态();
  }

  function 显示AI状态() {
    取元素("AI状态").textContent = AI已配置()
      ? "已配置，AI 功能可用（密钥仅保存在本浏览器）。"
      : "未配置密钥：AI 功能暂不可用，页面其余功能不受影响。";
  }

  function 回填AI设置() {
    var 设置 = 读AI设置();
    取元素("AI接口").value = 设置.接口地址;
    取元素("AI模型").value = 设置.模型;
    取元素("AI密钥").value = 设置.密钥;   // type=password，不回显明文
  }

  function 截断(文本, 长度) {
    文本 = String(文本 || "");
    return 文本.length > 长度 ? 文本.slice(0, 长度) + "…" : 文本;
  }

  // 统一的对话请求（OpenAI 兼容）。返回 Promise<string>（正文文本）。
  function 请求AI(消息列表) {
    var 设置 = 读AI设置();
    var 地址 = 设置.接口地址.replace(/\/+$/, "") + "/chat/completions";
    return fetch(地址, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + 设置.密钥
      },
      body: JSON.stringify({
        model: 设置.模型,
        messages: 消息列表,
        temperature: 0.3
      })
    }).then(function (响应) {
      if (!响应.ok) {
        return 响应.text().then(function (错误文本) {
          throw new Error("接口返回 " + 响应.status + "：" + 截断(错误文本, 120));
        });
      }
      return 响应.json();
    }).then(function (数据) {
      var 内容 = 数据 && 数据.choices && 数据.choices[0] &&
        数据.choices[0].message && 数据.choices[0].message.content;
      if (typeof 内容 !== "string" || !内容.trim()) {
        throw new Error("AI 返回内容为空");
      }
      return 内容;
    });
  }

  // 从 AI 回复中提取 JSON（容忍 ```json 围栏与前后废话）。失败返回 null。
  function 从文本提取JSON(文本) {
    var 净 = String(文本 || "").replace(/```json/gi, "").replace(/```/g, "").trim();
    var 首 = 净.indexOf("{");
    var 尾 = 净.lastIndexOf("}");
    if (首 === -1 || 尾 === -1 || 尾 <= 首) return null;
    try {
      return JSON.parse(净.slice(首, 尾 + 1));
    } catch (e) {
      return null;
    }
  }

  // 校验 AI 记录返回的菜品：字段齐全、数值在契约区间。不合法返回 null。
  // 区间与 5.3 食谱契约一致：卡路里 0–3000，克数 0–500。
  function 校验AI菜品(对象) {
    if (!对象 || typeof 对象 !== "object") return null;
    if (typeof 对象.名称 !== "string" || !对象.名称.trim()) return null;

    var 菜 = {
      名称: 对象.名称.trim().slice(0, 20),
      卡路里: Number(对象.卡路里),
      碳水: Number(对象.碳水),
      脂肪: Number(对象.脂肪),
      膳食纤维: Number(对象.膳食纤维),
      蛋白质: Number(对象.蛋白质)
    };
    if (isNaN(菜.卡路里) || 菜.卡路里 < 0 || 菜.卡路里 > 3000) return null;

    var 克数合法 = ["碳水", "脂肪", "膳食纤维", "蛋白质"].every(function (字段) {
      return !isNaN(菜[字段]) && 菜[字段] >= 0 && 菜[字段] <= 500;
    });
    if (!克数合法) return null;

    菜.卡路里 = Math.round(菜.卡路里);
    ["碳水", "脂肪", "膳食纤维", "蛋白质"].forEach(function (字段) {
      菜[字段] = 保留一位小数(菜[字段]);
    });
    return 菜;
  }

  // AI 记录的菜品 id 用 "AI" + 时间戳，与食谱 id（r###）天然不冲突；
  // 人群为空数组（AI 记录不属于任何人群标签），五类营养由 AI 估算。
  function 添加AI记录(菜品, 餐次) {
    var 记录 = 读记录();
    记录.push({
      id: "AI" + Date.now(),
      名称: 菜品.名称,
      人群: [],
      卡路里: 菜品.卡路里,
      碳水: 菜品.碳水,
      脂肪: 菜品.脂肪,
      膳食纤维: 菜品.膳食纤维,
      蛋白质: 菜品.蛋白质,
      来源: "AI",
      餐次: 合法餐次表.indexOf(餐次) !== -1 ? 餐次 : 判定餐次()
    });
    写记录(记录);
    刷新所有();
  }

  // ① AI 记录：一句话描述 → AI 估算营养 → 写入今日记录
  function 处理AI记录(事件) {
    事件.preventDefault();
    var 描述 = 取元素("AI记录输入").value.trim();
    var 提示 = 取元素("AI记录提示");

    if (!描述) { 提示.textContent = "请先描述吃了什么。"; return; }
    if (!AI已配置()) { 提示.textContent = "请先在上方「接口设置」里填入密钥。"; return; }

    提示.textContent = "识别中…（需要联网）";
    var 消息 = [
      { role: "system", content: "你是饮食记录助手。根据用户描述估算这份食物的营养，" +
        "输出严格 JSON（不要任何多余文字）：{\"名称\":\"...\",\"卡路里\":整数,\"碳水\":数字," +
        "\"脂肪\":数字,\"膳食纤维\":数字,\"蛋白质\":数字,\"餐次\":\"早/午/晚/加餐\"}。" +
        "规则：卡路里 0–3000；其余单位为克、0–500；数字不带单位；名称不超过 12 字；" +
        "餐次按描述里的时间推断，没有线索就按用户当前时段。" },
      { role: "user", content: "当前时间 " + new Date().getHours() +
        " 点。用户描述：" + 描述 }
    ];

    请求AI(消息).then(function (回复) {
      var 对象 = 从文本提取JSON(回复);
      var 菜品 = 校验AI菜品(对象);
      if (!菜品) {
        提示.textContent = "AI 返回的数据不合法，没有记录。可以换个说法再试。";
        return;
      }
      添加AI记录(菜品, 对象 && 对象.餐次);
      取元素("AI记录输入").value = "";
      提示.textContent = "已记录：" + 菜品.名称 + "（" + 菜品.卡路里 + " kcal，AI 估算）";
    }).catch(function (错误) {
      提示.textContent = "AI 记录失败（网络或密钥问题）：" + 截断(错误.message, 100);
    });
  }

  // ② AI 营养分析：今日记录 + 目标 → 一段文字短评（不构成营养建议）
  function 处理AI分析() {
    var 结果盒 = 取元素("AI分析结果");
    结果盒.hidden = false;

    if (!AI已配置()) {
      结果盒.textContent = "请先在「⑥ AI 助手」的接口设置里填入密钥。";
      return;
    }
    var 记录 = 读记录();
    if (记录.length === 0) {
      结果盒.textContent = "今天还没有记录，先记几道菜再来分析。";
      return;
    }

    结果盒.textContent = "分析中…（需要联网）";
    var 目标 = 读目标();
    var 合计 = 汇总营养(记录);
    var 上下文 = {
      目标: 目标 ? { 人群: 目标.人群, 卡路里: 目标.目标, 宏量目标: 计算宏量目标(目标.目标, 目标.人群) } : null,
      今日已摄入: 合计,
      明细: 记录.map(function (条) {
        return { 名称: 条.名称, 餐次: 条.餐次, 卡路里: 条.卡路里 };
      })
    };
    var 消息 = [
      { role: "system", content: "你是饮食总结助手。用不超过 120 字的中文短评今日摄入与目标的差距：" +
        "先说卡路里，再说蛋白质 / 脂肪 / 碳水的达标情况，最后一句中性观察。" +
        "只用一段文字，不用列表、标题或图表。开头不要客套。这是教学演示，" +
        "不构成营养或医学建议，不要给出医疗性指令。" },
      { role: "user", content: JSON.stringify(上下文) }
    ];

    请求AI(消息).then(function (回复) {
      结果盒.textContent = 截断(回复.trim(), 300);
    }).catch(function (错误) {
      结果盒.textContent = "分析失败（网络或密钥问题）：" + 截断(错误.message, 100);
    });
  }

  // ③ AI 个性化推荐：人群 + 宏量缺口 + 剩余额度 → 从 40 道菜里选 3 道并给理由。
  // 校验不通过的候选项直接丢弃，宁可少推也不硬推。
  function 校验AI推荐(对象, 菜单, 已记录ids, 剩余额度) {
    var 结果 = { 推荐项: [], 总评: "" };
    if (!对象 || typeof 对象 !== "object" || !Array.isArray(对象.推荐)) return 结果;
    if (typeof 对象.总评 === "string") 结果.总评 = 截断(对象.总评.trim(), 60);

    var 见过 = [];
    对象.推荐.forEach(function (项) {
      if (!项 || typeof 项.id !== "string") return;
      if (见过.indexOf(项.id) !== -1) return;

      var 菜 = null;
      for (var i = 0; i < 菜单.length; i++) {
        if (菜单[i].id === 项.id) { 菜 = 菜单[i]; break; }
      }
      if (!菜) return;                                  // id 不在候选菜单里
      if (已记录ids.indexOf(菜.id) !== -1) return;      // 今天已吃过
      if (菜.卡路里 > 剩余额度) return;                  // 超剩余额度

      见过.push(菜.id);
      结果.推荐项.push({
        菜: 菜,
        理由: typeof 项.理由 === "string" ? 截断(项.理由.trim(), 30) : ""
      });
    });
    return 结果;
  }

  function 处理AI推荐() {
    var 说明 = 取元素("AI推荐说明");
    取元素("AI推荐列表").innerHTML = "";

    if (!AI已配置()) { 说明.textContent = "请先在接口设置里填入密钥。"; return; }
    var 目标 = 读目标();
    if (!目标) { 说明.textContent = "先设置每日目标，AI 才知道往哪个方向推荐。"; return; }

    var 记录 = 读记录();
    var 合计 = 汇总营养(记录);
    var 剩余 = Math.max(目标.目标 - 合计.卡路里, 0);
    var 已记录ids = 记录.map(function (条) { return 条.id; });
    if (剩余 <= 100) { 说明.textContent = "今日已达目标额度，AI 也不再推荐。"; return; }

    var 宏量 = 计算宏量目标(目标.目标, 目标.人群);
    var 菜单 = window.食谱数据.map(function (菜) {
      return {
        id: 菜.id, 名称: 菜.名称, 人群: 菜.人群, 卡路里: 菜.卡路里,
        碳水: 菜.碳水, 脂肪: 菜.脂肪, 膳食纤维: 菜.膳食纤维, 蛋白质: 菜.蛋白质
      };
    });
    var 上下文 = {
      目标人群: 目标.人群,
      每日目标: 目标.目标,
      剩余额度: 剩余,
      今日已吃: 记录.map(function (条) { return 条.名称; }),
      宏量缺口: {
        蛋白质: Math.max(宏量.蛋白质 - 合计.蛋白质, 0),
        脂肪: Math.max(宏量.脂肪 - 合计.脂肪, 0),
        碳水: Math.max(宏量.碳水 - 合计.碳水, 0)
      },
      候选菜单: 菜单
    };
    var 消息 = [
      { role: "system", content: "你是食谱推荐助手。只能从候选菜单里按 id 选菜，" +
        "输出严格 JSON（不要任何多余文字）：{\"推荐\":[{\"id\":\"r###\",\"理由\":\"不超过 20 字\"}]," +
        "\"总评\":\"不超过 30 字\"}。规则：最多 3 道；优先选带目标人群标签的；" +
        "优先补宏量缺口大的营养素；单道卡路里不得超过剩余额度；今天已吃过的不要再选。" },
      { role: "user", content: JSON.stringify(上下文) }
    ];

    说明.textContent = "AI 挑选中…（需要联网）";
    请求AI(消息).then(function (回复) {
      var 结果 = 校验AI推荐(从文本提取JSON(回复), 菜单, 已记录ids, 剩余);
      if (结果.推荐项.length === 0) {
        说明.textContent = "AI 没有给出满足约束的推荐，可重试，或看上方规则推荐。";
        return;
      }
      说明.textContent = 结果.总评 ||
        "AI 结合宏量缺口与剩余额度挑了 " + 结果.推荐项.length + " 道。";
      渲染AI推荐(结果.推荐项);
    }).catch(function (错误) {
      说明.textContent = "AI 推荐失败（网络或密钥问题）：" + 截断(错误.message, 100);
    });
  }

  function 渲染AI推荐(推荐项) {
    var 容器 = 取元素("AI推荐列表");
    容器.innerHTML = "";
    推荐项.forEach(function (项) {
      var li = 创建菜单项(项.菜, "加入");
      if (项.理由) {
        var 理由 = document.createElement("p");
        理由.className = "AI理由";
        理由.textContent = "✦ " + 项.理由;
        li.appendChild(理由);
      }
      容器.appendChild(li);
    });
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

    取元素("设置表单").addEventListener("submit", 设置目标);
    取元素("清空按钮").addEventListener("click", function () {
      写记录([]);
      刷新所有();
    });
    取元素("生成计划按钮").addEventListener("click", 生成计划);
    取元素("清空计划按钮").addEventListener("click", 清除计划);

    // AI 助手（可选功能）：设置 / 记录 / 分析 / 推荐
    取元素("AI设置表单").addEventListener("submit", 保存AI设置);
    取元素("AI记录表单").addEventListener("submit", 处理AI记录);
    取元素("AI分析按钮").addEventListener("click", 处理AI分析);
    取元素("AI推荐按钮").addEventListener("click", 处理AI推荐);
    回填AI设置();
    显示AI状态();

    渲染专区();
    渲染计划();
    渲染动作();
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
    生成一周计划: 生成一周计划,
    计划天数: 计划天数,
    动作部位: 动作部位,
    AI默认设置: AI默认设置,
    从文本提取JSON: 从文本提取JSON,
    校验AI菜品: 校验AI菜品,
    校验AI推荐: 校验AI推荐
  };
})();