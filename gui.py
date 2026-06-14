"""Sequoia-X V2 GUI — customtkinter 现代化界面"""

import multiprocessing
import sys
import threading
from pathlib import Path

import customtkinter as ctk
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "bg": "#0f0f1a",
    "card": "#1a1a2e",
    "card_hover": "#22223a",
    "accent": "#6c5ce7",
    "accent_hover": "#7c6cf7",
    "danger": "#e74c3c",
    "danger_hover": "#c0392b",
    "success": "#2ecc71",
    "text": "#e0e0e0",
    "text_dim": "#888899",
    "border": "#2a2a3e",
    "row_even": "#16162b",
    "row_odd": "#1e1e35",
}


class StockApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Sequoia-X · A股量化选股")
        self.geometry("1200x750")
        self.minsize(900, 600)
        self.configure(fg_color=COLORS["bg"])
        self.results: list[str] = []
        self._init_engine()
        self._build_ui()

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

    # ── UI ──
    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── 侧边栏 ──
        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=COLORS["card"])
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        # Logo
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", padx=20, pady=(24, 4))
        ctk.CTkLabel(
            logo_frame, text="Sequoia-X",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            logo_frame, text="A股量化选股",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_dim"],
        ).pack(anchor="w")

        # 分隔线
        ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=16, pady=16)

        # 数据操作标题
        ctk.CTkLabel(
            sidebar, text="数据操作",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_dim"],
        ).pack(anchor="w", padx=20, pady=(0, 8))

        self.btn_backfill = ctk.CTkButton(
            sidebar, text="回填历史数据", height=38,
            fg_color=COLORS["danger"], hover_color=COLORS["danger_hover"],
            font=ctk.CTkFont(size=13), corner_radius=8,
            command=self._backfill,
        )
        self.btn_backfill.pack(fill="x", padx=16, pady=(0, 6))

        self.btn_sync = ctk.CTkButton(
            sidebar, text="同步最新数据", height=38,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(size=13), corner_radius=8,
            command=self._sync_today,
        )
        self.btn_sync.pack(fill="x", padx=16, pady=(0, 6))

        # 分隔线
        ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=16, pady=10)

        # 策略选择标题
        ctk.CTkLabel(
            sidebar, text="选股策略",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_dim"],
        ).pack(anchor="w", padx=20, pady=(0, 8))

        # 导出按钮
        self.btn_export = ctk.CTkButton(
            sidebar, text="导出CSV", height=38,
            fg_color=COLORS["success"], hover_color="#27ae60",
            font=ctk.CTkFont(size=13), corner_radius=8,
            command=self._export_csv,
        )
        self.btn_export.pack(fill="x", padx=16, pady=(0, 6))

        self.strategy_var = ctk.StringVar(value=list(self.strategies.keys())[0])
        self.strategy_menu = ctk.CTkOptionMenu(
            sidebar, variable=self.strategy_var,
            values=list(self.strategies.keys()),
            height=38, font=ctk.CTkFont(size=13),
            fg_color=COLORS["border"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["card"],
            dropdown_hover_color=COLORS["accent"],
            corner_radius=8,
        )
        self.strategy_menu.pack(fill="x", padx=16, pady=(0, 6))

        self.btn_run = ctk.CTkButton(
            sidebar, text="运行策略", height=38,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(size=13, weight="bold"), corner_radius=8,
            command=self._run_strategy,
        )
        self.btn_run.pack(fill="x", padx=16, pady=(0, 16))

        # 侧边栏底部状态
        self.status_label = ctk.CTkLabel(
            sidebar, text="就绪",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_dim"],
            wraplength=190,
        )
        self.status_label.pack(side="bottom", padx=20, pady=(0, 16), anchor="w")

        # 进度条
        self.progress_bar = ctk.CTkProgressBar(
            sidebar, height=4, corner_radius=2,
            fg_color=COLORS["border"], progress_color=COLORS["accent"],
        )
        self.progress_bar.pack(side="bottom", fill="x", padx=16, pady=(0, 8))
        self.progress_bar.set(0)

        # ── 主内容区 ──
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=(0, 16), pady=16)
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(1, weight=1)

        # 顶部标签
        ctk.CTkLabel(
            main, text="选股结果",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="w", padx=4, pady=(0, 8))

        ctk.CTkLabel(
            main, text="K线图",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text"],
        ).grid(row=0, column=1, sticky="w", padx=4, pady=(0, 8))

        # 左侧表格卡片
        table_card = ctk.CTkFrame(main, fg_color=COLORS["card"], corner_radius=12)
        table_card.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self._build_table(table_card)

        # 右侧图表卡片
        chart_card = ctk.CTkFrame(main, fg_color=COLORS["card"], corner_radius=12)
        chart_card.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        self._build_chart_area(chart_card)

    def _build_table(self, parent):
        cols = ("code", "close", "pct", "turnover", "signal")
        headers = {"code": "代码", "close": "收盘价", "pct": "涨跌幅%", "turnover": "成交额(万)", "signal": "信号"}
        widths = {"code": 90, "close": 90, "pct": 80, "turnover": 110, "signal": 100}

        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=12, pady=12)

        # 表头
        header_frame = ctk.CTkFrame(container, fg_color=COLORS["border"], corner_radius=6, height=36)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        for i, c in enumerate(cols):
            w = widths[c]
            lbl = ctk.CTkLabel(
                header_frame, text=headers[c],
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COLORS["accent"],
                width=w,
            )
            lbl.pack(side="left", padx=2)

        # 滚动区域
        self.table_scroll = ctk.CTkScrollableFrame(
            container, fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.table_scroll.pack(fill="both", expand=True, pady=(4, 0))
        self.table_rows: list[ctk.CTkFrame] = []

    def _build_chart_area(self, parent):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=12, pady=12)
        self.chart_frame = container

        # 空状态提示
        self.chart_placeholder = ctk.CTkLabel(
            container, text="点击左侧表格查看K线图",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_dim"],
        )
        self.chart_placeholder.pack(expand=True)

    # ── 操作 ──
    def _set_status(self, msg):
        self.after(0, lambda: self.status_label.configure(text=msg))

    def _populate_table(self, symbols, strategy_name):
        for row in self.table_rows:
            row.destroy()
        self.table_rows.clear()

        cols = ("code", "close", "pct", "turnover", "signal")
        widths = {"code": 90, "close": 90, "pct": 80, "turnover": 110, "signal": 100}

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
                row_frame = ctk.CTkFrame(self.table_scroll, fg_color=bg, corner_radius=0, height=34)
                row_frame.pack(fill="x", pady=1)
                row_frame.pack_propagate(False)

                values = {
                    "code": code,
                    "close": f"{last['close']:.2f}",
                    "pct": f"{pct:+.2f}",
                    "turnover": f"{turnover_w:,.0f}",
                    "signal": strategy_name,
                }

                for c in cols:
                    w = widths[c]
                    color = COLORS["success"] if c == "pct" and pct > 0 else (COLORS["danger"] if c == "pct" and pct < 0 else COLORS["text"])
                    lbl = ctk.CTkLabel(
                        row_frame, text=values[c],
                        font=ctk.CTkFont(size=12),
                        text_color=color,
                        width=w,
                    )
                    lbl.pack(side="left", padx=2)

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
            2, 1, figsize=(5.5, 5),
            gridspec_kw={"height_ratios": [3, 1]}, dpi=100,
        )
        fig.patch.set_facecolor(COLORS["card"])
        for ax in (ax1, ax2):
            ax.set_facecolor(COLORS["row_even"])
            ax.tick_params(colors=COLORS["text_dim"], labelsize=7)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_color(COLORS["border"])
            ax.spines["bottom"].set_color(COLORS["border"])

        # K线
        for _, row in df.iterrows():
            color = COLORS["success"] if row["close"] >= row["open"] else COLORS["danger"]
            ax1.plot([row["idx"], row["idx"]], [row["low"], row["high"]], color=color, linewidth=0.8)
            ax1.plot([row["idx"], row["idx"]], [row["open"], row["close"]], color=color, linewidth=3.5)

        # MA5 / MA20
        df["ma5"] = df["close"].rolling(5).mean()
        df["ma20"] = df["close"].rolling(20).mean()
        ax1.plot(df["idx"], df["ma5"], color="#f1c40f", linewidth=1, alpha=0.8, label="MA5")
        ax1.plot(df["idx"], df["ma20"], color="#e67e22", linewidth=1, alpha=0.8, label="MA20")
        ax1.legend(fontsize=7, loc="upper left", facecolor=COLORS["row_even"], edgecolor=COLORS["border"], labelcolor=COLORS["text"])

        ax1.set_title(f"{code}  K线图", color=COLORS["accent"], fontsize=11, pad=6)
        ax1.set_ylabel("价格", color=COLORS["text_dim"], fontsize=8)

        # 成交量
        vol_colors = [COLORS["success"] if row["close"] >= row["open"] else COLORS["danger"] for _, row in df.iterrows()]
        ax2.bar(df["idx"], df["volume"], color=vol_colors, alpha=0.7, width=0.7)
        ax2.set_ylabel("成交量", color=COLORS["text_dim"], fontsize=8)

        tick_idx = df["idx"].iloc[::10].tolist()
        tick_label = [df["date"].iloc[i].strftime("%m-%d") for i in tick_idx]
        ax2.set_xticks(tick_idx)
        ax2.set_xticklabels(tick_label, color=COLORS["text_dim"], fontsize=7, rotation=30)
        ax1.set_xticks([])

        plt.tight_layout()
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
                self.after(0, lambda: self._populate_table(result, name))
                self.after(0, lambda: self._set_status(f"{name} 完成，选出 {len(result)} 只"))
                self.after(0, lambda: self._show_toast(f"{name} 选出 {len(result)} 只股票", "success"))
            except Exception as e:
                self.after(0, lambda: self._set_status(f"策略执行失败: {e}"))
                self.after(0, lambda: self._show_toast(f"策略失败: {e}", "error"))
            finally:
                self.after(0, lambda: self.btn_run.configure(state="normal"))

        threading.Thread(target=task, daemon=True).start()

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
        toast = ctk.CTkToplevel(self)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)

        color = COLORS["success"] if kind == "success" else (COLORS["danger"] if kind == "error" else COLORS["accent"])
        toast.configure(fg_color=color)

        ctk.CTkLabel(
            toast, text=msg, font=ctk.CTkFont(size=13),
            text_color="white", padx=20, pady=12,
        ).pack()

        # 居中显示在窗口上方
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - toast.winfo_reqwidth()) // 2
        y = self.winfo_y() + 40
        toast.geometry(f"+{x}+{y}")

        toast.after(2500, toast.destroy)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = StockApp()
    app.mainloop()
