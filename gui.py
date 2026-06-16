"""Sequoia-X V2 GUI — Archive风格：奶油纸 × 赤陶橙 × 衬线"""

import multiprocessing
import sys
import threading
from pathlib import Path

import customtkinter as ctk
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

# Archive风格：奶油纸 × 赤陶橙 × 衬线
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# ===== Archive 暖色纸感档案馆配色 =====
# 参考 fanbox warm 主题
COLORS = {
    # 纸张层次
    "bg": "#f5f0e8",           # 奶油纸主背景
    "bg_2": "#faf6ef",         # 更浅背景
    "bg_3": "#ece2d2",         # 第三层背景
    "panel": "#f1ebdf",        # 面板背景
    "sidebar": "#f1ebdf",      # 侧边栏

    # 边框与分隔
    "border": "#e3d9c8",       # 边框
    "rule": "#e3d9c8",         # 分隔线
    "divider": "#d8cdb8",      # 分隔线深色

    # 文字
    "text": "#1a1a18",         # 主文字
    "text_dim": "#6b6355",     # 次要文字
    "text_faint": "#a39882",   # 第三级文字
    "text_white": "#fffaf3",   # 反白文字

    # 强调色 — 赤陶橙
    "accent": "#cc785c",       # 赤陶橙
    "accent_hover": "#d4886a", # 悬停
    "accent_soft": "#cc785c22", # 浅强调
    "accent_ink": "#fffaf3",   # 反白

    # 功能色
    "green": "#7d8a55",        # 苔藓绿
    "green_hover": "#8a9660",  # 悬停绿
    "green_light": "#e8ead8",  # 浅绿背景
    "red": "#b85c4a",          # 赭红
    "red_hover": "#c46a58",    # 悬停红
    "red_light": "#f0e0dc",    # 浅红背景
    "yellow": "#c2893a",       # 琥珀黄

    # 卡片与表格
    "card": "#faf6ef",         # 卡片
    "card_hover": "#f5f0e8",   # 卡片悬停
    "row_even": "#faf6ef",     # 偶数行
    "row_odd": "#f5f0e8",      # 奇数行
    "row_hover": "#ece2d2",    # 行悬停
    "header_bg": "#f1ebdf",    # 表头

    # 图表
    "chart_bg": "#faf6ef",
    "chart_grid": "#ece2d2",
    "kline_up": "#7d8a55",     # 上涨绿
    "kline_down": "#b85c4a",   # 下跌红
    "ma5": "#c2893a",          # MA5琥珀
    "ma20": "#8b7d6b",         # MA20灰褐

    # 阴影
    "shadow": "#5a422a2e",     # 暖色阴影
}

# 字体配置 — 衬线用于标题，无衬线用于UI
FONT_UI = "Microsoft YaHei"
FONT_SERIF = "Georgia"
FONT_MONO = "Consolas"


class StockApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Sequoia-X")
        self.geometry("1320x820")
        self.minsize(1020, 680)
        self.configure(fg_color=COLORS["bg"])
        
        # 设置窗口样式
        self._set_window_style()
        
        self.results: list[str] = []
        self._init_engine()
        self._build_ui()

    def _set_window_style(self):
        """设置窗口样式"""
        try:
            self.attributes("-alpha", 1.0)
        except Exception:
            pass

    def _init_engine(self):
        from sequoia_x.core.config import Settings
        from sequoia_x.data.engine import DataEngine

        class _S(Settings):
            feishu_webhook_url: str = ""

        self.settings = _S()
        self.engine = DataEngine(self.settings)

        from sequoia_x.strategy.high_tight_flag import HighTightFlagStrategy
        from sequoia_x.strategy.limit_up_shakeout import LimitUpShakeoutStrategy
        from sequoia_x.strategy.ma_volume import MaVolumeStrategy
        from sequoia_x.strategy.private_placement import PrivatePlacementStrategy
        from sequoia_x.strategy.rps_breakout import RpsBreakoutStrategy
        from sequoia_x.strategy.turtle_trade import TurtleTradeStrategy
        from sequoia_x.strategy.uptrend_limit_down import UptrendLimitDownStrategy

        self.strategies = {
            "海龟突破": TurtleTradeStrategy,
            "均线放量": MaVolumeStrategy,
            "高窄旗形": HighTightFlagStrategy,
            "涨停洗盘": LimitUpShakeoutStrategy,
            "上升跌停": UptrendLimitDownStrategy,
            "RPS 突破": RpsBreakoutStrategy,
            "定增": PrivatePlacementStrategy,
        }

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── 侧边栏 ──
        sidebar = ctk.CTkFrame(
            self, width=260, corner_radius=0,
            fg_color=COLORS["sidebar"],
            border_width=0,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        # 顶部Logo区域 — 衬线字体
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent", height=80)
        logo_frame.pack(fill="x", padx=24, pady=(28, 0))
        logo_frame.pack_propagate(False)
        
        # Logo图标背景 — 赤陶橙
        logo_icon = ctk.CTkFrame(
            logo_frame, width=42, height=42, corner_radius=10,
            fg_color=COLORS["accent"],
        )
        logo_icon.pack(side="left", padx=(0, 14))
        logo_icon.pack_propagate(False)
        
        ctk.CTkLabel(
            logo_icon, text="S",
            font=ctk.CTkFont(size=20, weight="bold", family=FONT_SERIF),
            text_color=COLORS["text_white"],
        ).place(relx=0.5, rely=0.5, anchor="center")
        
        logo_text_frame = ctk.CTkFrame(logo_frame, fg_color="transparent")
        logo_text_frame.pack(side="left", fill="y")
        
        ctk.CTkLabel(
            logo_text_frame, text="Sequoia-X",
            font=ctk.CTkFont(size=20, weight="bold", family=FONT_SERIF),
            text_color=COLORS["text"],
        ).pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(
            logo_text_frame, text="A股量化选股",
            font=ctk.CTkFont(size=12, family=FONT_UI),
            text_color=COLORS["text_dim"],
        ).pack(anchor="w")

        # 分隔线
        divider = ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["divider"])
        divider.pack(fill="x", padx=24, pady=20)

        # 数据操作区域
        section_label = ctk.CTkLabel(
            sidebar, text="数据操作",
            font=ctk.CTkFont(size=11, weight="bold", family=FONT_UI),
            text_color=COLORS["text_faint"],
        )
        section_label.pack(anchor="w", padx=24, pady=(0, 12))

        # 回填按钮 — 赭红风格
        self.btn_backfill = self._create_archive_button(
            sidebar, text="回填历史数据",
            fg_color=COLORS["red_light"],
            hover_color=COLORS["red"],
            text_color=COLORS["red"],
            hover_text_color=COLORS["text_white"],
            command=self._backfill,
        )
        self.btn_backfill.pack(fill="x", padx=20, pady=(0, 8))

        # 同步按钮
        self.btn_sync = self._create_archive_button(
            sidebar, text="同步最新数据",
            fg_color=COLORS["green_light"],
            hover_color=COLORS["green"],
            text_color=COLORS["green"],
            hover_text_color=COLORS["text_white"],
            command=self._sync_today,
        )
        self.btn_sync.pack(fill="x", padx=20, pady=(0, 8))

        # 分隔线
        divider2 = ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["divider"])
        divider2.pack(fill="x", padx=24, pady=16)

        # 选股策略区域
        strategy_label = ctk.CTkLabel(
            sidebar, text="选股策略",
            font=ctk.CTkFont(size=11, weight="bold", family=FONT_UI),
            text_color=COLORS["text_faint"],
        )
        strategy_label.pack(anchor="w", padx=24, pady=(0, 12))

        # 策略选择
        self.strategy_var = ctk.StringVar(value=list(self.strategies.keys())[0])
        self.strategy_menu = ctk.CTkOptionMenu(
            sidebar, variable=self.strategy_var,
            values=list(self.strategies.keys()),
            height=38, font=ctk.CTkFont(size=13, family=FONT_UI),
            fg_color=COLORS["bg"],
            button_color=COLORS["bg"],
            button_hover_color=COLORS["border"],
            dropdown_fg_color=COLORS["card"],
            dropdown_hover_color=COLORS["bg_3"],
            dropdown_text_color=COLORS["text"],
            text_color=COLORS["text"],
            corner_radius=9,
        )
        self.strategy_menu.pack(fill="x", padx=20, pady=(0, 12))

        # 运行策略按钮 — 赤陶橙主按钮
        self.btn_run = ctk.CTkButton(
            sidebar, text="运行策略", height=42,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(size=14, weight="bold", family=FONT_UI),
            text_color=COLORS["text_white"],
            corner_radius=10,
            command=self._run_strategy,
        )
        self.btn_run.pack(fill="x", padx=20, pady=(0, 8))

        # 刷新行情按钮 — 通过腾讯财经 API 实时更新股票池价格
        self.btn_refresh = self._create_archive_button(
            sidebar, text="刷新行情(腾讯)",
            fg_color=COLORS["accent_soft"],
            hover_color=COLORS["accent"],
            text_color=COLORS["accent"],
            hover_text_color=COLORS["text_white"],
            command=self._refresh_quotes,
        )
        self.btn_refresh.pack(fill="x", padx=20, pady=(0, 8))

        # 导出按钮
        self.btn_export = ctk.CTkButton(
            sidebar, text="导出CSV", height=38,
            fg_color=COLORS["green"], hover_color=COLORS["green_hover"],
            font=ctk.CTkFont(size=13, family=FONT_UI),
            text_color=COLORS["text_white"],
            corner_radius=10,
            command=self._export_csv,
        )
        self.btn_export.pack(fill="x", padx=20, pady=(0, 16))

        # 侧边栏底部 — 进度和状态
        bottom_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom_frame.pack(side="bottom", fill="x", padx=24, pady=(0, 20))

        # 进度条
        self.progress_bar = ctk.CTkProgressBar(
            bottom_frame, height=3, corner_radius=2,
            fg_color=COLORS["border"],
            progress_color=COLORS["accent"],
            border_width=0,
        )
        self.progress_bar.pack(fill="x", pady=(0, 12))
        self.progress_bar.set(0)

        # 状态标签
        self.status_label = ctk.CTkLabel(
            bottom_frame, text="就绪",
            font=ctk.CTkFont(size=12, family=FONT_UI),
            text_color=COLORS["text_dim"],
            wraplength=210,
        )
        self.status_label.pack(anchor="w")

        # ── 主内容区 ──
        main_container = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        main_container.grid(row=0, column=1, sticky="nsew", padx=(0, 0), pady=0)
        main_container.grid_columnconfigure(0, weight=1)
        main_container.grid_rowconfigure(1, weight=1)
        
        # 顶部标题栏
        title_bar = ctk.CTkFrame(main_container, fg_color=COLORS["bg"], height=60)
        title_bar.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 0))
        title_bar.grid_propagate(False)
        title_bar.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(
            title_bar, text="选股结果",
            font=ctk.CTkFont(size=24, weight="bold", family=FONT_SERIF),
            text_color=COLORS["text"],
        ).place(rely=0.5, anchor="w")

        # 内容卡片区域
        content_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        content_frame.grid(row=1, column=0, sticky="nsew", padx=24, pady=(16, 24))
        content_frame.grid_columnconfigure(0, weight=3)
        content_frame.grid_columnconfigure(1, weight=2)
        content_frame.grid_rowconfigure(0, weight=1)

        # 左侧表格卡片
        table_card = ctk.CTkFrame(
            content_frame, fg_color=COLORS["card"],
            corner_radius=12, border_width=1,
            border_color=COLORS["border"],
        )
        table_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._build_table(table_card)

        # 右侧图表卡片
        chart_card = ctk.CTkFrame(
            content_frame, fg_color=COLORS["card"],
            corner_radius=12, border_width=1,
            border_color=COLORS["border"],
        )
        chart_card.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        self._build_chart_area(chart_card)

    def _create_archive_button(self, parent, text, fg_color, hover_color, text_color, hover_text_color, command):
        """创建Archive风格按钮"""
        btn = ctk.CTkButton(
            parent, text=text, height=38,
            fg_color=fg_color, hover_color=hover_color,
            font=ctk.CTkFont(size=13, weight="bold", family=FONT_UI),
            text_color=text_color,
            corner_radius=10,
            border_width=0,
            command=command,
        )
        btn.bind("<Enter>", lambda e: btn.configure(text_color=hover_text_color))
        btn.bind("<Leave>", lambda e: btn.configure(text_color=text_color))
        return btn

    def _build_table(self, parent):
        cols = ("code", "close", "pct", "turnover", "signal")
        headers = {"code": "代码", "close": "收盘价", "pct": "涨跌幅%", "turnover": "成交额(万)", "signal": "信号"}
        widths = {"code": 100, "close": 100, "pct": 90, "turnover": 120, "signal": 110}

        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16, pady=16)

        # 表头 — Archive风格
        header_frame = ctk.CTkFrame(
            container, fg_color=COLORS["header_bg"],
            corner_radius=8, height=40,
            border_width=1, border_color=COLORS["border"],
        )
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        for i, c in enumerate(cols):
            w = widths[c]
            lbl = ctk.CTkLabel(
                header_frame, text=headers[c],
                font=ctk.CTkFont(size=12, weight="bold", family=FONT_UI),
                text_color=COLORS["text_faint"],
                width=w,
            )
            lbl.pack(side="left", padx=4)

        # 滚动区域
        self.table_scroll = ctk.CTkScrollableFrame(
            container, fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.table_scroll.pack(fill="both", expand=True, pady=(6, 0))
        self.table_rows: list[ctk.CTkFrame] = []

    def _build_chart_area(self, parent):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16, pady=16)
        self.chart_frame = container

        # 空状态提示
        self.chart_placeholder = ctk.CTkFrame(
            container, fg_color=COLORS["bg_3"],
            corner_radius=12, width=200, height=160,
        )
        self.chart_placeholder.pack(expand=True)
        self.chart_placeholder.pack_propagate(False)
        
        ctk.CTkLabel(
            self.chart_placeholder, text="📊",
            font=ctk.CTkFont(size=36),
            text_color=COLORS["text_faint"],
        ).pack(pady=(30, 8))
        
        ctk.CTkLabel(
            self.chart_placeholder, text="点击左侧表格",
            font=ctk.CTkFont(size=14, weight="bold", family=FONT_UI),
            text_color=COLORS["text_dim"],
        ).pack()
        
        ctk.CTkLabel(
            self.chart_placeholder, text="查看K线图",
            font=ctk.CTkFont(size=12, family=FONT_UI),
            text_color=COLORS["text_faint"],
        ).pack()

    # ── 操作 ──
    def _set_status(self, msg):
        self.after(0, lambda: self.status_label.configure(text=msg))

    def _populate_table(self, symbols, strategy_name):
        for row in self.table_rows:
            row.destroy()
        self.table_rows.clear()

        cols = ("code", "close", "pct", "turnover", "signal")
        widths = {"code": 100, "close": 100, "pct": 90, "turnover": 120, "signal": 110}

        for idx, code in enumerate(symbols):
            try:
                df = self.engine.get_ohlcv(code)
                if df.empty:
                    continue
                last = df.iloc[-1]
                prev_close = df.iloc[-2]["close"] if len(df) > 1 else last["close"]
                pct = (last["close"] - prev_close) / prev_close * 100 if prev_close else 0
                turnover_w = last["turnover"] / 10000

                bg = COLORS["row_even"] if idx % 2 == 0 else COLORS["row_odd"]
                row_frame = ctk.CTkFrame(
                    self.table_scroll, fg_color=bg,
                    corner_radius=6, height=40,
                    border_width=0,
                )
                row_frame.pack(fill="x", pady=(0, 2))
                row_frame.pack_propagate(False)
                
                # 悬停效果
                row_frame.bind("<Enter>", lambda e, f=row_frame: f.configure(fg_color=COLORS["row_hover"]))
                row_frame.bind("<Leave>", lambda e, f=row_frame, b=bg: f.configure(fg_color=b))

                values = {
                    "code": code,
                    "close": f"{last['close']:.2f}",
                    "pct": f"{pct:+.2f}%",
                    "turnover": f"{turnover_w:,.0f}",
                    "signal": strategy_name,
                }

                for c in cols:
                    w = widths[c]
                    if c == "pct":
                        if pct > 0:
                            color = COLORS["green"]
                        elif pct < 0:
                            color = COLORS["red"]
                        else:
                            color = COLORS["text_dim"]
                    else:
                        color = COLORS["text"]
                    
                    lbl = ctk.CTkLabel(
                        row_frame, text=values[c],
                        font=ctk.CTkFont(size=12, family=FONT_UI),
                        text_color=color,
                        width=w,
                    )
                    lbl.pack(side="left", padx=4)

                row_frame.bind("<Button-1>", lambda e, code=code: self._draw_kline(str(code)))
                for child in row_frame.winfo_children():
                    child.bind("<Button-1>", lambda e, code=code: self._draw_kline(str(code)))
                self.table_rows.append(row_frame)
            except Exception:
                continue

    def _draw_kline(self, code):
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        except ImportError:
            return

        df = self.engine.get_ohlcv(code)
        if df.empty or len(df) < 5:
            return

        df = df.tail(60).copy()
        df["date"] = pd.to_datetime(df["date"])
        df["idx"] = range(len(df))

        for w in self.chart_frame.winfo_children():
            w.destroy()

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(5.5, 5.5),
            gridspec_kw={"height_ratios": [3, 1]}, dpi=100,
        )
        
        # Archive风格图表
        fig.patch.set_facecolor(COLORS["chart_bg"])
        for ax in (ax1, ax2):
            ax.set_facecolor(COLORS["chart_bg"])
            ax.tick_params(colors=COLORS["text_dim"], labelsize=8)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_color(COLORS["border"])
            ax.spines["bottom"].set_color(COLORS["border"])
            ax.grid(True, alpha=0.3, color=COLORS["chart_grid"], linestyle="-", linewidth=0.5)

        # K线
        for _, row in df.iterrows():
            color = COLORS["kline_up"] if row["close"] >= row["open"] else COLORS["kline_down"]
            ax1.plot([row["idx"], row["idx"]], [row["low"], row["high"]], color=color, linewidth=1.0)
            ax1.plot([row["idx"], row["idx"]], [row["open"], row["close"]], color=color, linewidth=3.0, solid_capstyle="round")

        # MA5 / MA20
        df["ma5"] = df["close"].rolling(5).mean()
        df["ma20"] = df["close"].rolling(20).mean()
        ax1.plot(df["idx"], df["ma5"], color=COLORS["ma5"], linewidth=1.2, alpha=0.9, label="MA5")
        ax1.plot(df["idx"], df["ma20"], color=COLORS["ma20"], linewidth=1.2, alpha=0.9, label="MA20")
        ax1.legend(fontsize=8, loc="upper left", facecolor=COLORS["chart_bg"], edgecolor=COLORS["border"], labelcolor=COLORS["text"])

        ax1.set_title(f"{code}  K线图", color=COLORS["text"], fontsize=13, pad=10, fontweight="bold")
        ax1.set_ylabel("价格", color=COLORS["text_dim"], fontsize=9)

        # 成交量
        vol_colors = [COLORS["kline_up"] if row["close"] >= row["open"] else COLORS["kline_down"] for _, row in df.iterrows()]
        ax2.bar(df["idx"], df["volume"], color=vol_colors, alpha=0.6, width=0.6, edgecolor="none")
        ax2.set_ylabel("成交量", color=COLORS["text_dim"], fontsize=9)

        tick_idx = df["idx"].iloc[::10].tolist()
        tick_label = [df["date"].iloc[i].strftime("%m-%d") for i in tick_idx]
        ax2.set_xticks(tick_idx)
        ax2.set_xticklabels(tick_label, color=COLORS["text_dim"], fontsize=8, rotation=30)
        ax1.set_xticks([])

        plt.tight_layout(pad=1.5)
        canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        plt.close(fig)

    # ── 业务逻辑 ──
    def _backfill(self):
        self.btn_backfill.configure(state="disabled")
        self.progress_bar.set(0)

        def task():
            self._set_status("回填历史数据中...")
            try:
                symbols = self.engine.get_all_symbols()
                total = len(symbols)

                def _on_progress(current: int, t: int):
                    pct = current / t if t else 0
                    self.after(0, lambda p=pct: self.progress_bar.set(p))
                    self.after(0, lambda c=current, tt=t: self._set_status(
                        f"回填中... {c}/{tt} ({c/tt*100:.0f}%)" if tt else "回填中..."
                    ))

                self.engine.backfill(symbols, progress_callback=_on_progress)
                self.after(0, lambda: self.progress_bar.set(1.0))
                self.after(0, lambda: self._set_status("回填完成"))
                self.after(0, lambda: self._show_toast("历史数据回填完成", "success"))
            except Exception as e:
                self.after(0, lambda: self._set_status(f"回填失败: {e}"))
                self.after(0, lambda: self._show_toast(f"回填失败: {e}", "error"))
            finally:
                self.after(0, lambda: self.btn_backfill.configure(state="normal"))

        threading.Thread(target=task, daemon=True).start()

    def _sync_today(self):
        self.btn_sync.configure(state="disabled")

        def task():
            self._set_status("同步最新数据...")
            try:
                count = self.engine.sync_today_bulk()
                self.after(0, lambda: self._set_status(f"同步完成，更新 {count} 条"))
                self.after(0, lambda: self._show_toast(f"同步完成，更新 {count} 条", "success"))
            except Exception as e:
                self.after(0, lambda: self._set_status(f"同步失败: {e}"))
                self.after(0, lambda: self._show_toast(f"同步失败: {e}", "error"))
            finally:
                self.after(0, lambda: self.btn_sync.configure(state="normal"))

        threading.Thread(target=task, daemon=True).start()

    def _run_strategy(self):
        name = self.strategy_var.get()
        cls = self.strategies[name]
        self.btn_run.configure(state="disabled")

        def task():
            self._set_status(f"执行策略: {name}...")
            try:
                strategy = cls(engine=self.engine, settings=self.settings)
                result = strategy.run()
                self.results = result
                self._last_strategy_name = name
                self.after(0, lambda: self._populate_table(result, name))
                self.after(0, lambda: self._set_status(f"{name} 完成，选出 {len(result)} 只"))
                self.after(0, lambda: self._show_toast(f"{name} 选出 {len(result)} 只股票", "success"))
            except Exception as e:
                self.after(0, lambda: self._set_status(f"策略执行失败: {e}"))
                self.after(0, lambda: self._show_toast(f"策略失败: {e}", "error"))
            finally:
                self.after(0, lambda: self.btn_run.configure(state="normal"))

        threading.Thread(target=task, daemon=True).start()

    def _refresh_quotes(self):
        """通过腾讯财经 API 实时刷新股票池中所有股票的当前价/涨跌幅（单线程批量拉取）。"""
        if not self.results:
            self._show_toast("没有股票可刷新，请先运行策略", "error")
            return

        self.btn_refresh.configure(state="disabled")

        def task():
            self._set_status("正在从腾讯财经刷新行情...")
            try:
                quotes = self.engine.fetch_realtime_quotes(list(self.results))
                strategy_name = getattr(self, "_last_strategy_name", "—")
                self.after(0, lambda: self._populate_table_from_quotes(
                    self.results, quotes, strategy_name,
                ))
                self.after(0, lambda: self._set_status(
                    f"行情刷新完成，更新 {len(quotes)} 只"))
                self.after(0, lambda: self._show_toast(
                    f"已刷新 {len(quotes)} 只股票实时行情", "success"))
            except Exception as e:
                self.after(0, lambda: self._set_status(f"行情刷新失败: {e}"))
                self.after(0, lambda: self._show_toast(f"行情刷新失败: {e}", "error"))
            finally:
                self.after(0, lambda: self.btn_refresh.configure(state="normal"))

        threading.Thread(target=task, daemon=True).start()

    def _populate_table_from_quotes(self, symbols, quotes, strategy_name):
        """用腾讯实时行情重新渲染表格（结构与 _populate_table 一致）。"""
        for row in self.table_rows:
            row.destroy()
        self.table_rows.clear()

        cols = ("code", "close", "pct", "turnover", "signal")
        widths = {"code": 100, "close": 100, "pct": 90, "turnover": 120, "signal": 110}

        for idx, code in enumerate(symbols):
            q = quotes.get(code)
            if not q:
                continue
            close = q["close"]
            pct = q["pct"]
            turnover_w = q["turnover"] / 10000  # 腾讯成交额存的是元，转回万元

            bg = COLORS["row_even"] if idx % 2 == 0 else COLORS["row_odd"]
            row_frame = ctk.CTkFrame(
                self.table_scroll, fg_color=bg,
                corner_radius=6, height=40,
                border_width=0,
            )
            row_frame.pack(fill="x", pady=(0, 2))
            row_frame.pack_propagate(False)

            row_frame.bind("<Enter>", lambda e, f=row_frame: f.configure(fg_color=COLORS["row_hover"]))
            row_frame.bind("<Leave>", lambda e, f=row_frame, b=bg: f.configure(fg_color=b))

            values = {
                "code": code,
                "close": f"{close:.2f}",
                "pct": f"{pct:+.2f}%",
                "turnover": f"{turnover_w:,.0f}",
                "signal": strategy_name,
            }

            for c in cols:
                w = widths[c]
                if c == "pct":
                    if pct > 0:
                        color = COLORS["green"]
                    elif pct < 0:
                        color = COLORS["red"]
                    else:
                        color = COLORS["text_dim"]
                else:
                    color = COLORS["text"]

                lbl = ctk.CTkLabel(
                    row_frame, text=values[c],
                    font=ctk.CTkFont(size=12, family=FONT_UI),
                    text_color=color,
                    width=w,
                )
                lbl.pack(side="left", padx=4)

            row_frame.bind("<Button-1>", lambda e, code=code: self._draw_kline(str(code)))
            for child in row_frame.winfo_children():
                child.bind("<Button-1>", lambda e, code=code: self._draw_kline(str(code)))
            self.table_rows.append(row_frame)

    def _export_csv(self):
        if not self.results:
            self._show_toast("没有数据可导出", "error")
            return

        import csv
        from datetime import datetime
        from tkinter import filedialog

        strategy_name = self.strategy_var.get()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"{strategy_name}_{timestamp}.csv"

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_filename,
        )

        if not file_path:
            return

        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["代码", "收盘价", "涨跌幅%", "成交额(万)", "信号"])

                for code in self.results:
                    try:
                        df = self.engine.get_ohlcv(code)
                        if df.empty:
                            continue
                        last = df.iloc[-1]
                        prev_close = df.iloc[-2]["close"] if len(df) > 1 else last["close"]
                        pct = (last["close"] - prev_close) / prev_close * 100 if prev_close else 0
                        turnover_w = last["turnover"] / 10000
                        writer.writerow([
                            code,
                            f"{last['close']:.2f}",
                            f"{pct:+.2f}",
                            f"{turnover_w:,.0f}",
                            strategy_name,
                        ])
                    except Exception:
                        continue

            self._show_toast(f"已导出 {len(self.results)} 条数据到 {file_path}", "success")
        except Exception as e:
            self._show_toast(f"导出失败: {e}", "error")

    def _show_toast(self, msg: str, kind: str = "info"):
        """Archive风格通知提示"""
        toast = ctk.CTkToplevel(self)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        
        if kind == "success":
            color = COLORS["green"]
            bg_color = COLORS["green_light"]
        elif kind == "error":
            color = COLORS["red"]
            bg_color = COLORS["red_light"]
        else:
            color = COLORS["accent"]
            bg_color = COLORS["accent_soft"]
        
        toast.configure(fg_color=bg_color)

        content_frame = ctk.CTkFrame(toast, fg_color="transparent")
        content_frame.pack(padx=20, pady=14)
        
        icon = "✓" if kind == "success" else ("✕" if kind == "error" else "ℹ")
        ctk.CTkLabel(
            content_frame, text=icon,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=color,
        ).pack(side="left", padx=(0, 10))
        
        ctk.CTkLabel(
            content_frame, text=msg,
            font=ctk.CTkFont(size=13, family=FONT_UI),
            text_color=COLORS["text"],
        ).pack(side="left")

        toast_frame = ctk.CTkFrame(
            toast, fg_color="transparent",
            corner_radius=12, border_width=1,
            border_color=color,
        )
        toast_frame.place(relwidth=1, relheight=1)

        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - toast.winfo_reqwidth()) // 2
        y = self.winfo_y() + 60
        toast.geometry(f"+{x}+{y}")

        toast.after(2800, toast.destroy)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = StockApp()
    app.mainloop()
