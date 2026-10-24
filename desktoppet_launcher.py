# -*- coding: utf-8 -*-
"""
桌宠入口 / 启动器
============================================================
用法（在命令行里）：
    python desktoppet_launcher.py              # 启动 1 只桌宠
    python desktoppet_launcher.py -multi 3     # 一次启动 3 只（热闹些）

也可以直接双击“启动桌宠.bat”。
============================================================
"""
import sys

from desktop_pet import Pet


def main():
    argv = sys.argv[1:]
    n = 1
    if "-multi" in argv:
        i = argv.index("-multi")
        try:
            n = int(argv[i + 1])
        except Exception:
            n = 1
    for _ in range(max(1, n)):
        Pet().run()


if __name__ == "__main__":
    main()