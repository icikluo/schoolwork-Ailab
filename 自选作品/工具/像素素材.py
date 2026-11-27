# -*- coding: utf-8 -*-
"""把小窝的 AI 生图原稿处理成作品里能直接用的 PNG。

原稿统一是「品红底 + 右下角水印」的 JPG（1920² 或 2560×1440），
本脚本负责四件事，全部在这里做、不在作品代码里做：

  1. 抠品红：把纯品红背景变成透明，边缘像素做去色溢出
  2. 去水印：图标类靠裁内容框顺便排掉，房间图靠裁掉底部一条
  3. 缩放：统一到页面实际要用的像素尺寸（像素图不要留 1920 的大图）
  4. 落盘：数据/房间/、数据/家具图标/

用法（在 自选作品/ 目录下）：

    python 工具/像素素材.py

依赖 Pillow 与 numpy（只在做素材时用，不进作品、不影响双击运行）。
原稿建议先按「临时_」前缀放好，处理完可以删掉。
"""

import os
import sys

import numpy as np
from PIL import Image

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

家具清单 = ["家具-木桌", "家具-绿植", "家具-地毯", "家具-书架", "家具-小沙发", "家具-落地灯"]


def 抠品红(图, 忽略右下=True):
    """品红转透明。返回 (RGBA 图, 内容框)。"""
    像素 = np.asarray(图.convert("RGBA")).astype(np.int16)
    r, g, b = 像素[..., 0], 像素[..., 1], 像素[..., 2]
    # 品红 = 红蓝高、绿低；键值越大越像背景
    键 = (np.minimum(r, b) - g) / 255.0
    透 = np.clip((键 - 0.10) / 0.25, 0.0, 1.0)
    透明 = 透 >= 1.0
    边 = (透 > 0) & ~透明
    # 半透明边缘：把红/蓝压回绿色附近，不然边缘会留一圈品红
    像素[..., 0] = np.where(边, np.minimum(r, g + 50), r)
    像素[..., 2] = np.where(边, np.minimum(b, g + 50), b)
    像素[..., 3] = np.where(透明, 0, 像素[..., 3])
    结果 = Image.fromarray(像素.astype(np.uint8), "RGBA")

    实 = (np.asarray(结果)[..., 3] > 10)
    if 忽略右下:
        # 水印固定在右下角，按比例挖掉，免得被算进内容框
        h, w = 实.shape
        实[int(h * 0.90):, int(w * 0.76):] = False
    if not 实.any():
        raise SystemExit("抠完什么都不剩，检查原稿底色是不是品红")
    行 = np.where(实.any(axis=1))[0]
    列 = np.where(实.any(axis=0))[0]
    return 结果, (int(列[0]), int(行[0]), int(列[-1]) + 1, int(行[-1]) + 1)


def 存(图, 相对路径):
    路径 = os.path.join(根, 相对路径)
    os.makedirs(os.path.dirname(路径), exist_ok=True)
    图.save(路径, optimize=True)
    print("  写出 %-34s %s" % (相对路径, "%dx%d %.0fKB" % (
        图.width, 图.height, os.path.getsize(路径) / 1024)))


def 找原稿(名):
    候选 = [名 + 后缀 for 后缀 in (".jpg", ".png")]
    for 文件 in 候选:
        路径 = os.path.join(根, 文件)
        if os.path.exists(路径):
            return Image.open(路径)
    raise SystemExit("找不到原稿：" + 名 + ".jpg")


def 处理房间():
    图 = 找原稿("数据/房间/临时_房间-2D")
    # 底部 8% 是水印，直接裁掉；剩下的地板还是满的
    图 = 图.crop((0, 0, 图.width, int(图.height * 0.92)))
    图 = 图.resize((1024, round(1024 * 图.height / 图.width)), Image.LANCZOS).convert("RGB")
    存(图, "数据/房间/房间-2D.png")


def 处理贴图():
    for 名 in ("地板", "墙"):
        图 = 找原稿("数据/房间/临时_贴图-" + 名)
        图 = 图.resize((256, 256), Image.LANCZOS).convert("RGB")
        存(图, "数据/房间/贴图-%s.png" % 名)


def 处理家具():
    for 名 in 家具清单:
        图, 框 = 抠品红(找原稿("数据/家具图标/临时_" + 名))
        图 = 图.crop(框)
        # 图标不留透明边：页面按「内容高度」摆位，留白会让每件家具看起来忽大忽小
        if max(图.width, 图.height) > 240:
            比例 = 240 / max(图.width, 图.height)
            图 = 图.resize((max(1, round(图.width * 比例)), max(1, round(图.height * 比例))), Image.LANCZOS)
        存(图, "数据/家具图标/%s.png" % 名)


if __name__ == "__main__":
    if not os.path.isdir(os.path.join(根, "数据")):
        raise SystemExit("请在 自选作品/ 目录下运行：python 工具/像素素材.py")
    print("处理小窝素材：")
    处理房间()
    处理贴图()
    处理家具()
    print("完成。")
