# -*- coding: utf-8 -*-
"""
桌宠 Desktop Pet
============================================================
一只会自己吃饭、唱歌、睡觉，可以被摸头、分身、拖拽的桌面宠物。

技术说明（非常重要）：
- 本程序只使用 Python 自带的标准库 tkinter，不含任何外部依赖，
  因此不需要安装任何第三方库，直接双击"启动桌宠.bat"即可运行。
- 桌宠形象默认由程序用 Canvas 自己绘制（一只可爱的小猫/精灵），
  你也可以用自己的图片替换 —— 见 README.md 和 sprites/ 目录。
- 透明、无边框、置顶窗口。可用鼠标拖拽移动。

功能：
  左键单击 1 次      ->  摸头（开心动画 + 爱心）
  左键快速连点 3 次  ->  分身（复制出一只新的桌宠）
  按住左键拖动       ->  拖动桌宠到屏幕任意位置
  自主行为           ->  随机吃饭 / 唱歌跳舞 / 睡觉 / 发呆 / 散步
============================================================
"""

import math
import os
import random
import tkinter as tk
import sys
import time

# 配置（你也可以在这个文件里直接改，或编辑 pet_config.py）
from pet_config import (
    PET_SIZE, PET_COLOR, PET_BELLY, PET_EAR_INNER, PET_CHEEK,
    SB_SIZE, SB_X, SB_Y, SB_BG, SB_HIT,
    CLICK_WINDOW_SECS, CLICK_THRESHOLD_CLICKS,
    SELECT_GRACE_SECS,
    STATE_TIMINGS, DRAG_DEAD_ZONE,
    USE_IMAGE, IMAGE_PATH,
)

# 图片状态映射：状态名 -> 期望的 png 文件名（放在 sprites/ 下）
IMAGE_STATE_FILES = {
    "idle":     "idle.png",
    "mopping":  "mopping.png",
    "eating":   "eating.png",
    "singing":  "singing.png",
    "sleeping": "sleeping.png",
    "walking":  "idle.png",  # 散步复用 idle
}
_SPRITE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sprites")

# ------------------------------------------------------------------
# 定时刷新：把帧率限制在 30 FPS，避免 CPU 空转。
# ------------------------------------------------------------------
FRAME_MS = 33  # 约 30 FPS

# 分身上限：同一时刻最多允许存在的桌宠数量（含本体）
MAX_PETS = 3
# 全局存活桌宠计数
_ALIVE = 0
# 全局存活桌宠实例注册表（用于“靠近自动合并”）
_ALL_PETS = set()
# 两个桌宠中心距离小于该值（px）时自动合并；被合并的关闭并入本体
MERGE_DIST = 70

# 隐藏时右下角小图标的尺寸
HIDDEN_ICON_SIZE = (64, 64)


class Pet:
    """
    一只桌宠。
    - id: 唯一编号（分身时递增）
    - root: 独立的、置顶的、无边框透明窗口
    - 每个 Pet 有自己独立的状态机：mopping(摸头) / eating(吃饭) /
      singing(唱歌) / sleeping(睡觉) / idle(发呆) / walking(散步)
    """

    _counter = 0

    def __init__(self, x=None, y=None):
        global _ALIVE, _ALL_PETS
        Pet._counter += 1
        self.pid = Pet._counter
        _ALIVE += 1
        self._merged_away = False  # 是否已被合并掉（用于跳过自动合并逻辑）
        self._birth_grace = 0.0    # 出生后的短暂免合并时间（无人合并时置 0）
        _ALL_PETS.add(self)

        self.root = tk.Tk()
        self.root.title(f"桌宠 {self.pid}")
        # 置顶
        self.root.attributes("-topmost", True)
        # 去标题栏和边框
        self.root.overrideredirect(True)
        # 透明背景色（该颜色处的像素视为完全透明）
        self.root.config(bg=SB_BG)
        self.root.attributes("-transparentcolor", SB_BG)

        self.w = SB_SIZE[0]
        self.h = SB_SIZE[1]
        self.root.geometry(f"{self.w}x{self.h}")

        # 主画布，背景用透明色
        self.canvas = tk.Canvas(
            self.root,
            width=self.w, height=self.h,
            bg=SB_BG, bd=0, highlightthickness=0,
        )
        self.canvas.pack()

        # 桌宠在画布中的位置（以中心为基准），画布内部坐标
        self.cx = SB_X
        self.cy = SB_Y

        # 位置（屏幕坐标）
        if x is None or y is None:
            x = self._random_screen_pos()
            y = self._random_screen_pos()
        self.screen_x = x
        self.screen_y = y
        self.root.geometry(f"{self.w}x{self.h}+{x}+{y}")

        # 状态机
        self.state = "idle"
        self.phase = 0.0          # 动画相位（随时间前进）
        self.state_timer = 0.0    # 距上次状态切换/喂食等的计时
        self.next_behavior_in = 0.0  # 下一次自主行为的倒计时

        # 摸头/分身的点击检测
        self._click_n = 0            # 当前一轮内的连击次数
        self._last_release_t = -1e9  # 上次左键释放的时刻（用于判定连击/单击）

        # 爱心特效
        self.hearts = []          # [(x, y, life)] 生命值递减

        # 说话气泡
        self.say = None           # (text, life)
        self.say_until = 0.0

        # 图片模式素材
        self._img_refs = []       # 防止图片被 gc
        self._images = self._load_images()

        # 拖拽相关
        self._drag = None         # None 或 (offset_x, offset_y, start_time)
        self._pressed = False

        # 绑定事件
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        # 右键退出菜单（方便调试 / 关闭）
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="退出本桌宠", command=self.close)
        self.canvas.bind("<Button-3>", self._on_right)

        # 悬停选项面板 + 隐藏/唤回
        self._hovering = False    # 鼠标是否在桌宠上
        self._hidden = False      # 是否已隐藏（右下角小图标）
        self._restore_pos = None  # 隐藏前的位置，用于唤回
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)

        # 主循环
        self._last_t = time.monotonic()
        self._schedule_next()

    # ---------------- 图片模式 ----------------
    def _load_images(self):
        """图片模式：从 sprites/（或 IMAGE_PATH）加载各状态图片。"""
        if not USE_IMAGE:
            return None
        loaded = {}
        candidates = []
        if IMAGE_PATH:
            candidates.append(IMAGE_PATH)
        candidates.append(os.path.join(_SPRITE_DIR, "idle.png"))
        # 主图（第一个可用文件）用于所有状态
        main = None
        for p in candidates:
            if os.path.exists(p):
                main = self._load_image(p)
                break
        if main is None:
            return None
        for state, fname in IMAGE_STATE_FILES.items():
            p = os.path.join(_SPRITE_DIR, fname)
            if os.path.exists(p) and os.path.abspath(p) != os.path.abspath(
                    # 状态图与主图不同文件才单独加载
                    IMAGE_PATH or os.path.join(_SPRITE_DIR, "idle.png")):
                img = self._load_image(p)
                loaded[state] = img if img else main
            else:
                loaded[state] = main
        return loaded

    def _load_image(self, path):
        """用 PIL 解码成 tk.PhotoImage（PIL 可用时），否则退回绘制模式。"""
        try:
            # tkinter 不内置 png 解码（除 GIF/PGM 外），这里尽量用 PIL
            from PIL import Image, ImageTk
            im = Image.open(path).convert("RGBA")
            # 缩放到画布内合适大小
            scale = 1.0
            box = (int(SB_SIZE[0] * 0.9), int(SB_SIZE[1] * 0.9))
            if im.width > box[0] or im.height > box[1]:
                scale = min(box[0] / im.width, box[1] / im.height)
            im = im.resize((max(1, int(im.width * scale)),
                            max(1, int(im.height * scale))),
                           Image.LANCZOS)
            photo = ImageTk.PhotoImage(im)
            self._img_refs.append(photo)
            return photo
        except Exception:
            return None

    def _image_for_state(self, state):
        if not self._images:
            return None
        return self._images.get(state) or self._images.get("idle")

    # ---------------- 屏幕定位工具 ----------------
    def _random_screen_pos(self):
        # 用根窗口尺寸估算屏幕大小
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            margin = 80
            return random.randint(margin, max(margin + 1, sw - self.w - margin))
        except Exception:
            return 200

    # ---------------- 事件处理 ----------------
    def _on_press(self, event):
        # 记录按下起点，用于区分"点击"与"拖拽"
        self._pressed = True
        self._press_x = event.x_root
        self._press_y = event.y_root
        self._win_x = self.screen_x
        self._win_y = self.screen_y
        self._press_t = time.monotonic()

    def _on_motion(self, event):
        if not self._pressed:
            return
        # 移动超过阈值 -> 视为拖拽
        dx = event.x_root - self._press_x
        dy = event.y_root - self._press_y
        if (abs(dx) > DRAG_DEAD_ZONE[0] or abs(dy) > DRAG_DEAD_ZONE[1]) \
                and time.monotonic() - self._press_t > 0.05:
            self._drag = True
        if self._drag:
            nx = self._win_x + dx
            ny = self._win_y + dy
            self.screen_x = nx
            self.screen_y = ny
            self.root.geometry(f"{self.w}x{self.h}+{nx}+{ny}")
            # 拖拽时会打断睡觉等长时间行为
            if self.state in ("sleeping",):
                self._set_state("idle")

    def _on_release(self, event):
        """判定点击/拖拽：单击=摸头，窗口内连点3次=分身；点击面板按钮执行对应动作。"""
        was_drag = bool(self._drag)
        self._pressed = False
        self._drag = None
        if was_drag:
            return  # 拖拽结束，不当作点击

        # 隐藏状态下：点击角落小图标 -> 唤回
        if self._hidden:
            self._do_restore()
            self._click_n = 0
            return

        # 点击了选项面板上的按钮 -> 隐藏 / 关闭
        btn = self._panel_hit(event.x, event.y)
        if btn == "hide":
            self._do_hide()
            self._click_n = 0
            return
        if btn == "close":
            self._do_close()
            return

        now = time.monotonic()
        # 超过判定窗口 -> 开启新一轮点击
        if now - self._last_release_t > CLICK_WINDOW_SECS:
            self._click_n = 0
        self._click_n += 1
        self._last_release_t = now

        if self._click_n >= CLICK_THRESHOLD_CLICKS:
            self._spawn_clone()
            self._click_n = 0          # 分身完成后清空本轮
        elif self._click_n == 1:
            # 当前是"首个单击"：立即摸头。
            # 若用户随后快速补点成连击，第 2 击会进入 else 分支等待，
            # 而只有当达到阈值时才会分身覆盖这次摸头（见 _spawn_clone 处）。
            # 这样既保证单击立刻摸头，也不会让连击被摸头打断多次。
            self._do_pet()
        # _click_n == 2：属连击中间，暂不动作，等待第 3 击。

    def _on_right(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # ---------------- 悬停选项面板（画在画布身体右侧）+ 隐藏/唤回 ----------------
    def _on_enter(self, event):
        self._hovering = True

    def _on_leave(self, event):
        self._hovering = False
        self._destroy_panel()

    def _panel_button_rects(self):
        """计算身体右侧、画布边缘内的两个按钮区域（隐藏 / 关闭）。"""
        # 画布宽 220，身体中心 cx≈110。按钮放在身体右侧、画布右缘之前，
        # 紧贴身体，方便鼠标从身体横移过去点，不用跨很大距离。
        bw = 54
        bh = 28
        bgap = 5
        # 右边留 8px 边距，按钮右缘固定在画布右缘
        canvas_right = SB_SIZE[0]
        third_margin = 6
        x1 = canvas_right - third_margin
        x0 = x1 - bw
        # 垂直：与身体中心对齐，两个按钮上下排列
        hide_y0 = self.cy - bh - bgap // 2
        hide_y1 = self.cy - bgap // 2
        close_y0 = self.cy + bgap // 2
        close_y1 = self.cy + bgap // 2 + bh
        # 裁剪：保证都在画布内
        hide_y0 = max(0, hide_y0)
        close_y1 = min(SB_SIZE[1], close_y1)
        return [
            ("hide", (x0, hide_y0, x1, hide_y1)),
            ("close", (x0, close_y0, x1, close_y1)),
        ]

    def _panel_hit(self, x, y):
        """返回 (x, y) 落在哪个按钮上：'hide' / 'close' / None。"""
        if self._hidden:
            return None
        for name, (x0, y0, x1, y1) in self._panel_button_rects():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return name
        return None

    def _destroy_panel(self):
        """（保留空实现）面板现在画在画布内，无需销毁独立窗口。"""
        pass

    def _do_hide(self):
        """隐藏：收进屏幕右下角的小图标，点击可唤回。"""
        self._destroy_panel()
        self._hidden = True
        self._restore_pos = (self.screen_x, self.screen_y)
        # 缩到右下角小图标
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
        except Exception:
            sw, sh = 1920, 1080
        self._dock_w = HIDDEN_ICON_SIZE[0]
        self._dock_h = HIDDEN_ICON_SIZE[1]
        dx = sw - self._dock_w - 40
        dy = sh - self._dock_h - 60
        self.screen_x, self.screen_y = dx, dy
        self._set_geometry(self._dock_w, self._dock_h, dx, dy)
        self._say("我藏起来啦，戳角落图标能回来~", seconds=1.6)

    def _do_restore(self):
        """点击右下角小图标，唤回。"""
        self._hidden = False
        rx, ry = self._restore_pos or (self.screen_x, self.screen_y)
        self._restore_pos = None
        self.screen_x, self.screen_y = rx, ry
        self._set_geometry(self.w, self.h, rx, ry)
        self._say("回来啦！", seconds=1.6)

    def _set_geometry(self, w, h, x, y):
        try:
            self.root.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _do_close(self):
        """彻底关闭这只桌宠。"""
        self.close()

    # ---------------- 交互动作 ----------------
    def _do_pet(self):
        """摸头：开心动画 + 冒爱心 + 气泡。"""
        self._set_state("mopping", force=True)
        # 冒爱心
        self.hearts.append([self.cx, self.cy - PET_SIZE[1] * 0.4, 1.0])
        self._say("好开心~（づ￣3￣）づ")

    def _spawn_clone(self):
        """分身：在附近新建一只新桌宠。数量超过上限则提示不再分身。"""
        global _ALIVE
        if _ALIVE >= MAX_PETS:
            self._say(f"已经满 {MAX_PETS} 只啦，不能更多了~")
            return
        # 分身要离本体足够远（> 合并距离），否则刚出生就会被立刻并入
        ox, oy = self._center()
        nx, ny = ox, oy
        tries = 0
        while ((nx - ox) ** 2 + (ny - oy) ** 2) <= (MERGE_DIST + 50) ** 2 and tries < 30:
            nx = self.screen_x + random.randint(-160, 160)
            ny = self.screen_y + random.randint(-120, 120)
            tries += 1
        p = Pet(nx, ny)
        p._birth_grace = time.monotonic() + 0.8  # 出生后短暂不参与合并
        p._say("我是分身！喵~")
        self._say("分身来啦！")

    # ---------------- 自主行为状态机 ----------------
    def _set_state(self, state, force=False):
        if state == self.state and not force:
            return
        self.state = state
        self.phase = 0.0
        self.state_timer = 0.0

    def _update_state_machine(self, dt):
        self.state_timer += dt

        # 各状态对应的最长持续时间（秒），到时自动回到 idle
        limits = STATE_TIMINGS
        if self.state in limits:
            if self.state_timer >= limits[self.state]:
                self._set_state("idle")
                return

        # 只有在 idle 时才计划下一次自主行为
        if self.state == "idle":
            self.next_behavior_in -= dt
            if self.next_behavior_in <= 0:
                self._start_random_behavior()

    def _start_random_behavior(self):
        r = random.random()
        if r < 0.30:
            self._set_state("eating", force=True)
            self._say("吃饭饭啦~ 🍜")
        elif r < 0.55:
            self._set_state("singing", force=True)
            self._say("♪♪ 啦啦啦～♪♪")
        elif r < 0.75:
            self._set_state("sleeping", force=True)
            self._say("困了……晚安 Zzz")
        elif r < 0.90:
            self._set_state("walking", force=True)
        else:
            self._set_state("idle", force=True)

        self.next_behavior_in = random.randint(4, 10)

    # ---------------- 动画绘制 ----------------
    def _draw(self):
        c = self.canvas
        c.delete("all")

        # 隐藏状态：只画一个右下角的可爱小图标
        if self._hidden:
            self._draw_hidden_icon(c)
            return

        # 时间相位：随状态推进
        self.phase += 1.0 / 6.0  # 每帧约 0.05（相对帧时间 33ms）
        t = self.phase

        # 图片模式：直接用图片 + 轻微动画
        if self._images and USE_IMAGE:
            self._draw_image_mode(c, t)
            self._update_hearts(c)
            self._draw_speech(c)
            self._draw_hover_panel(c)
            return

        # 各状态的不同绘制
        if self.state == "sleeping":
            self._draw_sleeping(c, t)
        elif self.state == "eating":
            self._draw_eating(c, t)
        elif self.state == "singing":
            self._draw_singing(c, t)
        elif self.state == "walking":
            self._draw_walking(c, t)
        elif self.state == "mopping":
            self._draw_mopping(c, t)
        else:
            self._draw_idle(c, t)

        # 爱心特效
        self._update_hearts(c)

        # 说话气泡
        self._draw_speech(c)

        # 悬停时右下侧显示选项面板
        self._draw_hover_panel(c)

    def _draw_image_mode(self, c, t):
        """图片模式：把当前状态对应的图放到画布中央，做轻微缩放/翻转动画。"""
        img = self._image_for_state(self.state)
        if not img:
            # 没有图片则退回绘制模式
            return self._draw_canvas_mode_only(c, t)
        w, h = img.width(), img.height()
        x = self.cx - w / 2
        y = self.cy - h / 2
        # 轻微上下浮动，让静态图也有生命感
        bob = math.sin(t * 2.2) * 4
        if self.state == "sleeping":
            bob = math.sin(t * 1.5) * 3
        elif self.state == "mopping":
            bob = abs(math.sin(t * 6)) * 8
        c.create_image(x, y + bob, image=img, anchor="nw")

    def _draw_canvas_mode_only(self, c, t):
        """图片模式异常时退回绘制模式。"""
        if self.state == "sleeping":
            self._draw_sleeping(c, t)
        elif self.state == "eating":
            self._draw_eating(c, t)
        elif self.state == "singing":
            self._draw_singing(c, t)
        elif self.state == "walking":
            self._draw_walking(c, t)
        elif self.state == "mopping":
            self._draw_mopping(c, t)
        else:
            self._draw_idle(c, t)

    def _draw_hover_panel(self, c):
        """悬停时在身体右侧绘制选项面板：隐藏 / 关闭。"""
        if self._hidden or not self._hovering:
            return
        for name, (x0, y0, x1, y1) in self._panel_button_rects():
            # 圆角按钮底色（浅白 + 细边框）
            fill = "#ffe9d6" if name == "hide" else "#ffe0e0"
            c.create_rectangle(x0, y0, x1, y1,
                               fill=fill, outline="#d9a077", width=1)
            text = "隐藏" if name == "hide" else "关闭"
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=text,
                          fill=SB_HIT, font=("Microsoft YaHei UI", 10))

    def _draw_hidden_icon(self, c):
        """隐藏状态下右下角的小图标：一颗迷你猫头。"""
        w = HIDDEN_ICON_SIZE[0]
        h = HIDDEN_ICON_SIZE[1]
        cx, cy = 14, 16
        min_r = 9
        # 迷你猫头（耳朵 + 圆脸 + 眼睛）
        c.create_polygon(cx - 12, cy - 4, cx - 6, cy - 10, cx - 3, cy - 5,
                         fill=PET_COLOR, outline="")
        c.create_polygon(cx + 3, cy - 5, cx + 6, cy - 10, cx + 12, cy - 4,
                         fill=PET_COLOR, outline="")
        c.create_oval(cx - min_r, cy - min_r, cx + min_r, cy + min_r,
                      fill=PET_COLOR, outline="")
        c.create_oval(cx - 4, cy - 2, cx - 1, cy + 1, fill=SB_HIT, outline="")
        c.create_oval(cx + 1, cy - 2, cx + 4, cy + 1, fill=SB_HIT, outline="")
        c.create_arc(cx - 2, cy + 2, cx + 2, cy + 5, start=0, extent=180,
                     style="arc", outline=SB_HIT, width=2)
        # 提示小字
        c.create_text(cx, h - 2, text="点我", fill=SB_HIT,
                      font=("Microsoft YaHei UI", 7))

    # 通用身体绘制基座（躯干 + 肚皮 + 耳朵 + 脸）
    def _draw_body(self, c, t, body_wobble=0.0, ear_angles=(0, 0),
                   face_shift=(0, 0), eye_shape="open", mouth="smile",
                   eyes_closed=False, blush=False):
        cx, cy = self.cx, self.cy + body_wobble
        # 单位尺寸
        w = PET_SIZE[0]
        h = PET_SIZE[1]

        # 耳朵
        e1 = math.radians(65 + ear_angles[0])
        e2 = math.radians(70 + ear_angles[1])
        ear_l = w * 0.16
        ear_w = w * 0.14
        # 左耳
        lx0, ly0 = cx - w * 0.18, cy - h * 0.30
        lx1 = lx0 - ear_l * math.cos(e1)
        ly1 = ly0 - ear_l * math.sin(e1)
        c.create_polygon(lx0, ly0, lx0 + ear_w, ly0 - h * 0.10,
                         lx1 - ear_w * 0.4, ly1 + ear_w * 0.4,
                         fill=PET_COLOR, outline="", smooth=True)
        # 右耳
        rx0, ry0 = cx + w * 0.18, cy - h * 0.30
        rx1 = rx0 + ear_l * math.cos(e2)
        ry1 = ry0 - ear_l * math.sin(e2)
        c.create_oval(rx1 - ear_w, ry1 - ear_w * 0.4,
                      rx1 + ear_w, ry1 + ear_w * 1.4,
                      fill=PET_COLOR, outline="")

        # 头/身体（一个大圆）
        body_r = w * 0.34
        c.create_oval(cx - body_r + face_shift[0],
                      cy - h * 0.30 + face_shift[1],
                      cx + body_r + face_shift[0],
                      cy + h * 0.34 + face_shift[1],
                      fill=PET_COLOR, outline="")

        # 肚皮（身体下方浅色椭圆）
        belly_rx = w * 0.20
        belly_ry = h * 0.11
        c.create_oval(cx - belly_rx, cy + h * 0.05,
                      cx + belly_rx, cy + h * 0.05 + belly_ry * 2,
                      fill=PET_BELLY, outline="")

        # 眼睛
        eye_y = cy - h * 0.12 + face_shift[1]
        el = cx - w * 0.11 + face_shift[0]
        er = cx + w * 0.11 + face_shift[0]
        eye_r = w * 0.045
        if eyes_closed:
            # 闭眼 = 开心弧线
            c.create_line(el - eye_r, eye_y + 2, el + eye_r, eye_y + 6,
                          fill=SB_HIT, width=3, capstyle="round")
            c.create_line(er - eye_r, eye_y + 6, er + eye_r, eye_y + 2,
                          fill=SB_HIT, width=3, capstyle="round")
        else:
            c.create_oval(el - eye_r, eye_y - eye_r,
                          el + eye_r, eye_y + eye_r,
                          fill=SB_HIT, outline="")
            c.create_oval(er - eye_r, eye_y - eye_r,
                          er + eye_r, eye_y + eye_r,
                          fill=SB_HIT, outline="")
            # 高光
            hl = eye_r * 0.35
            c.create_oval(el + hl, eye_y - eye_r * 0.6,
                          el + eye_r * 1.2, eye_y - eye_r * 0.1,
                          fill="white", outline="")
            c.create_oval(er - eye_r * 1.2, eye_y - eye_r * 0.6,
                          er - hl, eye_y - eye_r * 0.1,
                          fill="white", outline="")

        # 腮红
        if blush:
            c.create_oval(cx - w * 0.24, cy - h * 0.10,
                          cx - w * 0.14, cy - h * 0.04,
                          fill=PET_CHEEK, outline="")
            c.create_oval(cx + w * 0.14, cy - h * 0.10,
                          cx + w * 0.24, cy - h * 0.04,
                          fill=PET_CHEEK, outline="")

        # 嘴巴
        mx, my = cx + face_shift[0], cy - h * 0.02 + face_shift[1]
        if mouth == "smile":
            c.create_arc(mx - w * 0.05, my - w * 0.02,
                         mx + w * 0.05, my + w * 0.05,
                         start=0, extent=180, style="arc", outline=SB_HIT, width=2)
        elif mouth == "open":  # 唱歌 / 吃饭张开嘴
            c.create_oval(mx - w * 0.03, my - 2, mx + w * 0.03, my + w * 0.06,
                          fill=SB_HIT, outline="")
        elif mouth == "sleep":
            c.create_line(mx - w * 0.05, my + 2, mx + w * 0.05, my + 2,
                          fill=SB_HIT, width=2, capstyle="round")

    # ---------------- 各状态动画 ----------------
    def _draw_idle(self, c, t):
        wobble = math.sin(t * 1.2) * 3
        self._draw_body(c, t, body_wobble=wobble, face_shift=(0, wobble * 0.3))

    def _draw_mopping(self, c, t):
        # 摸头：身体弹跳 + 闭眼笑 + 腮红
        bounce = abs(math.sin(t * 6)) * 14
        self._draw_body(c, t, body_wobble=-bounce, eyes_closed=True,
                        blush=True, face_shift=(0, -bounce * 0.2))

    def _draw_eating(self, c, t):
        # 吃饭：点头 + 张嘴巴 + 手里/嘴边出现饭团
        bob = math.sin(t * 4) * 8
        shift = (0, bob * 0.4)
        self._draw_body(c, t, body_wobble=0, face_shift=shift,
                        mouth="open",
                        blush=True)
        cx, cy = self.cx, self.cy
        # 食物小球在嘴边进进出出
        bite = math.sin(t * 4)
        fx = cx + 0.30 * PET_SIZE[0]
        fy = cy - 0.10 * PET_SIZE[1] - bite * 6
        self._draw_food(c, fx, fy)

    def _draw_singing(self, c, t):
        bounce = math.sin(t * 2.2) * 6
        mouth = "open" if (math.sin(t * 4) > -0.2) else "smile"
        self._draw_body(c, t, body_wobble=bounce,
                        face_shift=(0, bounce * 0.2), mouth=mouth,
                        eyes_closed=(math.sin(t * 2) > 0.6))
        # 音符特效
        cx, cy = self.cx, self.cy
        for i, (xn, yn, start) in enumerate(
                [(1.2, -0.6, 0.0), (1.4, -0.8, 0.35), (1.1, -1.0, 0.7)]):
            dy = ((t + start * 4) % 2)
            y = cy - yn * PET_SIZE[1] - dy * 22
            x = cx + xn * PET_SIZE[0]
            if 0 <= y <= self.h:
                self._draw_note(c, x, y)

    def _draw_sleeping(self, c, t):
        # 睡觉：起伏呼吸 + Zzz
        breath = abs(math.sin(t * 1.5)) * 6
        self._draw_body(c, t, body_wobble=-breath, eyes_closed=True,
                        mouth="sleep", blush=True)
        # Zzz
        cx, cy = self.cx, self.cy
        for i in range(3):
            zy = cy - 0.35 * PET_SIZE[1] - i * 18 - (t * 12 % 1) * 14
            zx = cx + 0.3 * PET_SIZE[0] + math.sin(t * 2 + i) * 4
            if 0 <= zy <= self.h:
                c.create_text(zx, zy, text="Z", fill=SB_HIT,
                              font=("Microsoft YaHei UI", 14 - i * 2, "bold"))

    def _draw_walking(self, c, t):
        # 散步：左右晃动 + 左右移动
        sway = math.sin(t * 4) * 5
        self._draw_body(c, t, body_wobble=sway * 0.2,
                        face_shift=(math.sin(t * 4) * 2, sway * 0.3))

    # ---------------- 特效小工具 ----------------
    def _draw_food(self, c, x, y):
        r = PET_SIZE[0] * 0.06
        c.create_oval(x - r, y - r, x + r, y + r, fill="#E8C36B", outline="")
        c.create_oval(x - r * 0.4, y - r * 0.3, x, y, fill="#F7DEA0", outline="")

    def _draw_note(self, c, x, y):
        # 一个八分音符
        c.create_oval(x, y, x + 8, y + 6, fill=SB_HIT, outline="")
        c.create_line(x + 8, y + 2, x + 8, y - 12, fill=SB_HIT, width=2)
        c.create_arc(x - 2, y - 16, x + 10, y - 8, start=0, extent=180,
                     style="arc", outline=SB_HIT, width=2)

    def _update_hearts(self, c):
        cx, cy = self.cx, self.cy
        dy = 1.4  # 每帧上升像素
        keep = []
        for hx, hy, life in self.hearts:
            new = (hx, hy - dy, life - 0.04)
            if new[2] > 0:
                keep.append(new)
            size = PET_SIZE[0] * 0.09 * (1.0 + (1.0 - new[2]))
            col = "#FF6B81" if new[2] > 0.5 else "#FFA0B0"
            c.create_text(hx, hy, text="♥", fill=col,
                          font=("Microsoft YaHei UI", int(10 + size * 0.4)))
        self.hearts = keep

    def _say(self, text, seconds=2.6):
        self.say = text
        self.say_until = time.monotonic() + seconds

    def _draw_speech(self, c):
        if not self.say:
            return
        if time.monotonic() > self.say_until:
            self.say = None
            return
        x, y = self.cx, self.cy - PET_SIZE[1] * 0.62
        c.create_oval(x - 60, y - 18, x + 60, y + 18,
                      fill="white", outline="#CCCCCC", width=2)
        c.create_text(x, y, text=self.say, fill=SB_HIT,
                      font=("Microsoft YaHei UI", 10))

    # ---------------- 主循环 ----------------
    def _schedule_next(self):
        now = time.monotonic()
        dt = now - self._last_t
        self._last_t = now
        dt = max(0.0, min(dt, 0.2))  # 防止卡顿跳帧过大

        self._update_state_machine(dt)
        self._merge_if_touching()
        self._draw()
        self.root.after(FRAME_MS, self._schedule_next)

    def run(self):
        self.root.mainloop()

    def close(self):
        global _ALIVE, _ALL_PETS
        try:
            _ALIVE = max(0, _ALIVE - 1)
            _ALL_PETS.discard(self)
        except Exception:
            pass
        self._destroy_panel()
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------------- 靠近自动合并 ----------------
    def _center(self):
        """屏幕上的身体中心坐标。"""
        return (self.screen_x + self.cx, self.screen_y + self.cy)

    def _merge_if_touching(self):
        """若桌上还有其他分身靠近到一定距离，则合并（自己并入最早那/主桌宠）。
        主桌宠（pid 最小）负责驱赶合并：其它分身靠近主桌宠时把自己关闭。"""
        global _ALL_PETS
        if self._merged_away:
            return
        # 只有一个桌宠，无需合并
        if len(_ALL_PETS) < 2:
            return
        # 只有主桌宠（最早创建的那只）负责发起合并，避免多只同时互并
        if self.pid != min(p.pid for p in _ALL_PETS if not p._merged_away):
            return
        mex, mey = self._center()
        for other in list(_ALL_PETS):
            if other is self or other._merged_away:
                continue
            # 刚出生的分身给一点时间，避免一出来就被并回去
            if other._birth_grace and time.monotonic() < other._birth_grace:
                continue
            ox, oy = other._center()
            if (ox - mex) ** 2 + (oy - mey) ** 2 <= MERGE_DIST ** 2:
                # 找到的重叠分身并入本体
                other._merged_away = True  # 避免它自己再被重复处理
                other.close()
                self._say("合体！我们又更强大啦~")
                self._trigger_merge_effect()
                return  # 一次合并一只，避免循环里互相干扰

    def _trigger_merge_effect(self):
        """合体时的闪光动画（简单的心/光环）。"""
        self._set_state("singing", force=True)
        for _ in range(6):
            self.hearts.append([self.cx, self.cy - 20 - (len(self.hearts) * 2), 1.0])


def main():
    # 支持从命令行传入初始位置
    x = y = None
    if len(sys.argv) >= 3:
        try:
            x, y = int(sys.argv[1]), int(sys.argv[2])
        except Exception:
            pass
    pet = Pet(x, y)
    # 一启动先打个招呼
    pet._say("你好呀~ 我是你的桌宠！")
    pet.run()


if __name__ == "__main__":
    main()