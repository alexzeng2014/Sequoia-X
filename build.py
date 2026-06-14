"""Sequoia-X V2 打包脚本 — 打包为单文件 exe"""

import subprocess
import sys


def main():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "Sequoia-X",
        "--clean",
        # 包含整个 sequoia_x 包
        "--hidden-import", "sequoia_x",
        "--hidden-import", "sequoia_x.core.config",
        "--hidden-import", "sequoia_x.core.logger",
        "--hidden-import", "sequoia_x.data.engine",
        "--hidden-import", "sequoia_x.strategy.base",
        "--hidden-import", "sequoia_x.strategy.turtle_trade",
        "--hidden-import", "sequoia_x.strategy.ma_volume",
        "--hidden-import", "sequoia_x.strategy.high_tight_flag",
        "--hidden-import", "sequoia_x.strategy.limit_up_shakeout",
        "--hidden-import", "sequoia_x.strategy.uptrend_limit_down",
        "--hidden-import", "sequoia_x.strategy.rps_breakout",
        "--hidden-import", "sequoia_x.strategy.private_placement",
        "--hidden-import", "sequoia_x.notify.feishu",
        # 包含数据文件
        "--add-data", "data;data",
        "--add-data", ".env;.",
        "--add-data", ".env.example;.",
        # 收集 customtkinter 数据
        "--collect-data", "customtkinter",
        # 入口
        "gui.py",
    ]

    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
