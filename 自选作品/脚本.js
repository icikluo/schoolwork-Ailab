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

  function 渲染全部() {
    var 全部 = window.食谱数据.slice().sort(function (a, b) {
      return a.id.localeCompare(b.id);
    });
    渲染列表("全部列表", 全部, "加入");
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

    var 目标显示 = 取元素("已摄入").nextElementSibling;
    var 目标文本 = 目标值 === null ? "—" : 目标值;
    取元素("已摄入").nextElementSibling.textContent = "/ 目标 " + 目标文本;

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
  function 添加记录(菜) {
    var 记录 = 读记录();
    记录.push({
      id: 菜.id,
      名称: 菜.名称,
      人群: 菜.人群.slice(),
      卡路里: 菜.卡路里,
      碳水: 菜.碳水,
      脂肪: 菜.脂肪,
      膳食纤维: 菜.膳食纤维,
      蛋白质: 菜.蛋白质
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

    渲染全部();
    刷新所有();
  }

  document.addEventListener("DOMContentLoaded", 初始化);

  // 暴露给测试脚本（第 10 周回归测试会用）
  window.食谱搭配 = {
    计算基础代谢: 计算基础代谢,
    计算目标卡路里: 计算目标卡路里,
    汇总营养: 汇总营养,
    生成推荐: 生成推荐
  };
})();