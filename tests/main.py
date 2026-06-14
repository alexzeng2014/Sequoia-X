# -*- coding: utf-8 -*-
"""
A股短线推荐助手 (A-Share Short-Term Stock Recommender)
================================================================================
依赖库安装方式:
    pip install baostock pandas PyQt5 requests

使用说明:
    1. 确保已安装上述依赖库
    2. 直接运行: python main.py
    3. 设置参数后点击"一键推荐"按钮
    4. 可选填入DeepSeek API Key启用AI推荐理由

技术架构:
    - GUI: PyQt5 (主线程)
    - 数据获取: baostock (独立线程)
    - 量化计算: pandas
    - AI增强: DeepSeek API (可选)

作者: A-Share Quant Assistant
版本: 1.0.0
"""

import sys
import time
import json
import os
import traceback
from datetime import datetime, timedelta
from threading import Thread, Lock
from pathlib import Path

import requests
import baostock as bs
import pandas as pd
import numpy as np

# PyQt5 相关导入
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QCheckBox, QLineEdit, QTableWidget,
    QTableWidgetItem, QTextEdit, QStatusBar, QGroupBox, QMessageBox,
    QFileDialog, QHeaderView, QAbstractItemView, QSplitter, QFrame,
    QProgressBar, QSpinBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QMutex, QTimer
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon

# =============================================================================
# 全局常量配置
# =============================================================================

# DeepSeek API配置
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_TIMEOUT = 5  # 秒

# 量化策略配置
DEFAULT_TRADING_DAYS = 10       # 获取数据天数
MIN_AVG_AMOUNT = 5000           # 5日均成交额最低门槛(万元)
MIN_LISTING_DAYS = 60            # 上市最少天数
MIN_SCORE_THRESHOLD = 35         # 最低推荐分数阈值

# K线质量过滤阈值
KLINE_UPPER_SHADOW_MAX = 0.50    # 上影线最大比例(50%)
KLINE_BODY_RATIO_MIN = 0.30      # 实体最小比例(30%)
KLINE_NEW_HIGH_TOLERANCE = 0.005  # 收盘价新高容忍度(0.5%)

# 评分规则权重（融合版 v5：技术40+基本15+情绪35-风险20，注入v4精华）
SCORE_RULES = {
    # ── 技术面 40分 ──
    'tech': {
        'price_trend': {        # 10分 - 基于 change_pct
            (5.0, float('inf')): 10,
            (2.0, 5.0): 8,
            (0.0, 2.0): 5,
            (-2.0, 0.0): 2,
            (float('-inf'), -2.0): 0,
        },
        'price_position': {     # 5分 - 基于 (close-low)/(high-low)
            (0.70, float('inf')): 5,
            (0.50, 0.70): 4,
            (0.30, 0.50): 2,
            (0.00, 0.30): 1,
        },
        'turnover': {          # 10分 - 基于换手率
            (10.0, float('inf')): 10,
            (5.0, 10.0): 8,
            (2.0, 5.0): 6,
            (1.0, 2.0): 3,
            (float('-inf'), 1.0): 0,
        },
        'open_gap': {          # 5分 - 基于 (open-preclose)/preclose
            (2.0, float('inf')): 5,
            (0.0, 2.0): 3,
            (-2.0, 0.0): 1,
            (float('-inf'), -2.0): 0,
        },
        'ma_bull': {           # 5分 - 多头排列 MA5>MA10>MA20
            'enabled': True,
            'score': 5,
        },
        'breakthrough': {      # 5分 - 10日新高
            'enabled': True,
            'score': 5,
        },
    },
    # ── 基本面 15分 ──
    'fund': {
        'amount': {            # 10分 - 基于成交额
            (1_000_000_000, float('inf')): 10,
            (500_000_000, 1_000_000_000): 8,
            (100_000_000, 500_000_000): 6,
            (50_000_000, 100_000_000): 4,
            (float('-inf'), 50_000_000): 2,
        },
        'pe_check': {          # 5分 - PE极端修正（异常扣分，优秀加分）
            'good': (0, 30),       # 0-30 PE → +5
            'bad': (200, float('inf')),  # >200 或 <0 → -5
            'score': 5,
        },
    },
    # ── 情绪面 35分 ──
    'sentiment': {
        'momentum': {          # 10分 - 基于 change_pct
            (7.0, float('inf')): 10,
            (4.0, 7.0): 8,
            (1.0, 4.0): 5,
            (-1.0, 1.0): 3,
            (-3.0, -1.0): 1,
            (float('-inf'), -3.0): 0,
        },
        'capital_activity': {  # 10分 - 基于 turnover + amount
            (15.0, 500_000_000): 10,
            (8.0, 300_000_000): 8,
            (3.0, 100_000_000): 5,
            (1.0, float('-inf')): 2,
            (float('-inf'), float('-inf')): 0,
        },
        'volume_ratio': {      # 10分 - 量比异动（v4精华）
            'high_clean': 10,    # ≥2.0 且 上影≤25%
            'high_punish': 2,    # ≥2.0 但 上影>25%
            'mid': 6,            # 1.5-2.0
            'low': 3,            # 1.2-1.5
            'upper_shadow_threshold': 0.25,
        },
        'consecutive_up': {    # 5分 - 连续3日上涨
            'days': 3,
            'score': 5,
        },
    },
    # ── 风险扣分 封顶20分 ──
    'risk': {
        'drop': {              # 大跌
            (float('-inf'), -5.0): 8,
            (-5.0, -3.0): 4,
        },
        'liquidity': {         # 流动性枯竭
            (float('-inf'), 0.5): 5,
        },
        'upper_shadow': {      # 长上影线
            (5.0, float('inf')): 5,
            (3.0, 5.0): 3,
        },
        'shrink_volume': {     # 缩量上涨预警（v4精华）
            'pct_threshold': 2.0,
            'vr_threshold': 0.8,
            'score': 5,
        },
    },
}

# 板块代码前缀
MARKET_GROUPS = {
    '上海主板': ['sh.600', 'sh.601', 'sh.603', 'sh.605'],
    '深圳主板': ['sz.000', 'sz.001', 'sz.002', 'sz.003'],
    '创业板':   ['sz.300', 'sz.301'],
    '科创板':   ['sh.688'],
    'ETF基金':  ['sh.51', 'sz.159', 'sh.56'],
    '北交所':   ['bj.'],
}
ALL_MARKET_NAMES = list(MARKET_GROUPS.keys())


def get_market_group(code: str) -> str:
    for group, prefixes in MARKET_GROUPS.items():
        for prefix in prefixes:
            if code.startswith(prefix):
                return group
    return '其他'


# =============================================================================
# 工具函数
# =============================================================================

CHECKPOINT_VERSION = 3
CACHE_VERSION = 3

KLINE_CACHE_MAX_ITEMS = 12000
DEFAULT_WORKERS = 4


def get_app_data_dir() -> Path:
    app_data = os.getenv("LOCALAPPDATA")
    if app_data:
        data_dir = Path(app_data) / "AStockRecommender"
    else:
        data_dir = Path.home() / ".astock_recommender"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_checkpoint_file() -> Path:
    """Return a writable checkpoint path shared by source and packaged runs."""
    return get_app_data_dir() / "recommend_checkpoint.json"


def get_cache_file() -> Path:
    return get_app_data_dir() / "data_cache.json"


def read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_json_atomic(path: Path, data: dict):
    tmp_file = path.with_suffix(".tmp")
    with tmp_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_file.replace(path)


def read_checkpoint() -> dict:
    data = read_json_file(get_checkpoint_file())
    if data.get("version") == CHECKPOINT_VERSION:
        return data
    return {}


def clear_checkpoint():
    try:
        get_checkpoint_file().unlink(missing_ok=True)
    except Exception:
        pass


def get_trading_dates(start_date: str, end_date: str) -> list:
    """获取指定日期范围内的交易日列表"""
    bs.login()
    rs = bs.query_trade_dates(start_date=start_date, end_date=end_date)
    dates = []
    while rs.next():
        row = rs.get_row_data()
        if row[1] == '1':  # is_trading_day
            dates.append(row[0])
    return dates


def is_st_stock(stock_name: str) -> bool:
    """判断是否为ST股票"""
    return 'ST' in stock_name or '*ST' in stock_name or 'S*ST' in stock_name


def format_pct(value: float) -> str:
    """格式化百分比显示"""
    return f"{value:+.2f}%"


def format_number(value: float, decimals: int = 2) -> str:
    """格式化数字显示"""
    return f"{value:.{decimals}f}"


def calculate_upper_shadow_ratio(row) -> float:
    """计算上影线比例: (high - max(open, close)) / (high - low)"""
    high, low = float(row['high']), float(row['low'])
    if high <= low:
        return 0.0
    body_top = max(float(row['open']), float(row['close']))
    return (high - body_top) / (high - low)


def calculate_body_ratio(row) -> float:
    """计算实体比例: |close - open| / (high - low)"""
    high, low = float(row['high']), float(row['low'])
    if high <= low:
        return 0.0
    return abs(float(row['close']) - float(row['open'])) / (high - low)


def check_kline_quality(df) -> bool:
    """检查最新K线质量: 上影线不能太长、实体不能太小、不能收阴线"""
    if df is None or len(df) < 1:
        return False
    latest = df.iloc[-1]

    high, low = float(latest['high']), float(latest['low'])
    if high <= low:
        return False  # 十字星/无波动

    upper_shadow = calculate_upper_shadow_ratio(latest)
    if upper_shadow > KLINE_UPPER_SHADOW_MAX:
        return False  # 上影线过长，冲高回落嫌疑

    body = calculate_body_ratio(latest)
    if body < KLINE_BODY_RATIO_MIN:
        return False  # 实体过小，方向不明确

    if float(latest['close']) < float(latest['open']):
        return False  # 收阴线

    return True


# =============================================================================
# 数据获取服务 (在独立线程中运行)
# =============================================================================

class DataService:
    """BaoStock数据服务"""

    def __init__(self):
        self.log_callback = None
        self.progress_callback = None
        self._mutex = QMutex()
        self._bs_lock = Lock()
        cache = read_json_file(get_cache_file())
        if cache.get("version") != CACHE_VERSION:
            cache = {}
        self.listing_date_cache = cache.get("listing_dates", {})
        self.kline_cache = cache.get("kline_data", {})
        self._cache_dirty_count = 0

    def set_callbacks(self, log_cb=None, progress_cb=None):
        self.log_callback = log_cb
        self.progress_callback = progress_cb

    def log(self, message: str):
        if self.log_callback:
            self.log_callback(message)

    def update_progress(self, current: int, total: int, stock_code: str = ""):
        if self.progress_callback:
            self.progress_callback(current, total, stock_code)

    def login(self):
        """登录BaoStock"""
        try:
            bs.login()
            self.log("BaoStock登录成功")
            return True
        except Exception as e:
            self.log(f"BaoStock登录失败: {e}")
            return False

    def logout(self):
        """登出BaoStock"""
        try:
            self.save_cache()
            bs.logout()
            self.log("BaoStock已登出")
        except:
            pass

    def save_cache(self):
        if self._cache_dirty_count <= 0:
            return
        data = {
            "version": CACHE_VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "listing_dates": self.listing_date_cache,
            "kline_data": self._trim_kline_cache(),
        }
        try:
            write_json_atomic(get_cache_file(), data)
            self._cache_dirty_count = 0
        except Exception as e:
            self.log(f"缓存保存失败: {e}")

    def _mark_cache_dirty(self):
        self._cache_dirty_count += 1
        if self._cache_dirty_count >= 100:
            self.save_cache()

    def _trim_kline_cache(self) -> dict:
        if len(self.kline_cache) > KLINE_CACHE_MAX_ITEMS:
            items = sorted(
                self.kline_cache.items(),
                key=lambda item: item[1].get("cached_at", "")
            )
            self.kline_cache = dict(items[-KLINE_CACHE_MAX_ITEMS:])
        return self.kline_cache

    def _kline_cache_key(self, code: str, days: int, end_date: str) -> str:
        return f"{end_date}|{days}|{code}"

    def get_previous_trading_date(self) -> str:
        """获取最近一个可用的交易日（非交易日或收盘前自动回退到上一交易日）"""
        today = datetime.now()
        today_str = today.strftime('%Y-%m-%d')

        start = (today - timedelta(days=10)).strftime('%Y-%m-%d')
        rs = bs.query_trade_dates(start_date=start, end_date=today_str)
        dates = []
        while rs.next():
            row = rs.get_row_data()
            if row[1] == '1':
                dates.append(row[0])

        if not dates:
            self.log(f"未找到交易日记录，使用 {today_str}")
            return today_str

        # 如果今天是交易日且已收盘（15:30之后），使用今天
        if today_str == dates[-1]:
            if today.hour > 15 or (today.hour == 15 and today.minute >= 30):
                self.log(f"今日 {today_str} 已收盘，使用当日数据")
                return today_str
            # 没到收盘时间，用上一个交易日
            if len(dates) > 1:
                self.log(f"今日 {today_str} 尚未收盘，使用上一交易日 {dates[-2]}")
                return dates[-2]
            return today_str

        # 今天不是交易日，用最后一个交易日
        self.log(f"今日 {today_str} 非交易日，使用最近交易日 {dates[-1]}")
        return dates[-1]

    def get_trade_status(self, code: str, date: str) -> bool:
        """查询股票在指定日期是否正常交易"""
        try:
            rs = bs.query_history_k_data_plus(
                code,
                "date,code,turn",
                start_date=date,
                end_date=date,
                frequency='d',
                adjustflag='2'
            )
            while rs.next():
                row = rs.get_row_data()
                if row and len(row) > 2 and row[2]:
                    return float(row[2]) > 0  # 有换手率说明在交易
            return False
        except:
            return False

    def get_stock_list(self, date: str, selected_markets: list = None) -> list:
        """获取股票列表，按板块过滤

        query_all_stock返回字段: code, tradeStatus, code_name (共3个字段)
        """
        if selected_markets is None:
            selected_markets = ALL_MARKET_NAMES
        self.log(f"正在获取股票列表，板块: {', '.join(selected_markets)}...")

        try:
            rs = bs.query_all_stock(day=date)
            if rs.error_code != '0':
                self.log(f"query_all_stock错误({date}): {rs.error_msg}")
                fallback_date = self.get_previous_trading_date()
                self.log(f"尝试使用最近交易日: {fallback_date}")
                rs = bs.query_all_stock(day=fallback_date)
                if rs.error_code != '0':
                    self.log(f"最近交易日也失败: {rs.error_msg}")
                    return []

            stocks = []
            if rs.data:
                for row in rs.data:
                    if len(row) < 3:
                        continue
                    code, trade_status, name = row[0], row[1], row[2]
                    if trade_status != '1':
                        continue
                    # 过滤掉指数
                    if code.startswith('sh.000') or code.startswith('sh.001') or \
                       code.startswith('sh.002') or code.startswith('sh.003'):
                        continue
                    # 按板块过滤
                    mg = get_market_group(code)
                    if mg not in selected_markets:
                        continue
                    stocks.append({'code': code, 'name': name})

            self.log(f"获取到 {len(stocks)} 只正常交易股票")
            return stocks
        except Exception as e:
            self.log(f"获取股票列表失败: {e}")
            traceback.print_exc()
            return []

    def preload_listing_dates(self, codes: list):
        missing_codes = {code for code in codes if code not in self.listing_date_cache}
        if not missing_codes:
            self.log(f"上市日期缓存命中: {len(codes)} 只")
            return

        try:
            rs = bs.query_stock_basic()
            loaded = 0
            while rs.next():
                row = rs.get_row_data()
                if row and len(row) > 2 and row[0] in missing_codes:
                    self.listing_date_cache[row[0]] = row[2]
                    loaded += 1
            if loaded:
                self._mark_cache_dirty()
                self.save_cache()
            self.log(f"上市日期预加载完成: 新增 {loaded} 只，缓存 {len(self.listing_date_cache)} 只")
        except Exception as e:
            self.log(f"上市日期预加载失败，将按需查询: {e}")

    def get_listing_date(self, code: str) -> str:
        """获取股票上市日期（优先查缓存，失败回退 baostock 单只查询）"""
        if code in self.listing_date_cache:
            return self.listing_date_cache[code]
        try:
            with self._bs_lock:
                rs = bs.query_stock_basic(code=code)
            while rs.next():
                row = rs.get_row_data()
                if row and len(row) > 2:
                    date = row[2]
                    self.listing_date_cache[code] = date
                    self._mark_cache_dirty()
                    return date
            return ""
        except:
            return ""

    def get_market_index_pct(self) -> float:
        """获取科创50指数当日涨跌幅（用于市场环境修正）"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            rs = bs.query_history_k_data_plus(
                "sh.000688",
                "date,pctChg",
                start_date=today,
                end_date=today,
                frequency='d',
                adjustflag='2'
            )
            while rs.next():
                row = rs.get_row_data()
                if row and len(row) > 1 and row[1]:
                    return float(row[1])
            return 0.0
        except:
            return 0.0

    def get_kline_data(self, code: str, days: int = DEFAULT_TRADING_DAYS, end_date: str = None) -> pd.DataFrame:
        """获取股票K线数据（前复权）"""
        try:
            if end_date is None:
                end_date = datetime.now().strftime('%Y-%m-%d')
            cache_key = self._kline_cache_key(code, days, end_date)
            cached = self.kline_cache.get(cache_key)
            if cached and cached.get("rows"):
                df = pd.DataFrame(cached["rows"])
                if len(df) > 0:
                    df['date'] = pd.to_datetime(df['date'])
                    expected_cols = ['open', 'high', 'low', 'close', 'preclose', 'volume', 'amount', 'turn', 'pctChg', 'peTTM']
                    for col in expected_cols:
                        if col not in df.columns:
                            df[col] = np.nan
                        else:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                    df = df.sort_values('date').reset_index(drop=True)
                return df

            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            start_date = (end_dt - timedelta(days=days * 2)).strftime('%Y-%m-%d')

            with self._bs_lock:
                rs = bs.query_history_k_data_plus(
                    code,
                    "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg,peTTM",
                    start_date=start_date,
                    end_date=end_date,
                    frequency='d',
                    adjustflag='2'  # 前复权
                )

                data_list = []
                while rs.next():
                    row = rs.get_row_data()
                    data_list.append({
                        'date': row[0],
                        'code': row[1],
                        'open': float(row[2]) if row[2] else np.nan,
                        'high': float(row[3]) if row[3] else np.nan,
                        'low': float(row[4]) if row[4] else np.nan,
                        'close': float(row[5]) if row[5] else np.nan,
                        'preclose': float(row[6]) if row[6] else np.nan,
                        'volume': float(row[7]) if row[7] else np.nan,
                        'amount': float(row[8]) if row[8] else np.nan,
                        'turn': float(row[9]) if row[9] else np.nan,
                        'pctChg': float(row[10]) if row[10] else np.nan,
                        'peTTM': float(row[11]) if row[11] else np.nan,
                    })

            df = pd.DataFrame(data_list)
            if len(df) > 0:
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date').reset_index(drop=True)
                self.kline_cache[cache_key] = {
                    "cached_at": datetime.now().isoformat(timespec="seconds"),
                    "rows": df.assign(date=df['date'].dt.strftime('%Y-%m-%d')).to_dict('records'),
                }
                self._mark_cache_dirty()
            return df
        except Exception as e:
            return pd.DataFrame()


# =============================================================================
# 量化分析引擎
# =============================================================================

class QuantEngine:
    """量化分析引擎"""

    def __init__(self, data_service: DataService):
        self.ds = data_service

    def calculate_indicators(self, df: pd.DataFrame, stock_name: str = "",
                              market_index_pct: float = 0.0) -> dict:
        """计算技术指标（v4版：纯BaoStock，新增多头排列/乖离率/跳空/缩量预警/量比持续）"""
        if df is None or len(df) < 5:
            return None

        try:
            # 最新交易日数据
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else latest

            # 计算均线
            if len(df) >= 5:
                ma5 = df['close'].rolling(window=5).mean().iloc[-1]
            else:
                ma5 = df['close'].mean()

            if len(df) >= 10:
                ma10 = df['close'].rolling(window=10).mean().iloc[-1]
            else:
                ma10 = df['close'].mean()

            if len(df) >= 20:
                ma20 = df['close'].rolling(window=20).mean().iloc[-1]
            else:
                ma20 = df['close'].mean()

            # 5日平均成交量
            avg_volume_5d = df['volume'].rolling(window=5).mean().iloc[-1]

            # 5日平均换手率
            avg_turn_5d = df['turn'].rolling(window=5).mean().iloc[-1]

            # 今日成交量 / 5日均量
            if avg_volume_5d > 0:
                volume_ratio = latest['volume'] / avg_volume_5d
            else:
                volume_ratio = 0

            # 收盘价创10日新高
            close_high_10d = df['close'].tail(10).max() if len(df) >= 10 else df['close'].max()
            is_new_high_10d = latest['close'] >= close_high_10d * (1 - KLINE_NEW_HIGH_TOLERANCE)

            # K线质量指标
            upper_shadow_ratio = calculate_upper_shadow_ratio(latest)
            body_ratio = calculate_body_ratio(latest)
            kline_quality_ok = check_kline_quality(df)

            # 判断是否站上均线
            close_above_ma5 = latest['close'] > ma5
            close_above_ma10 = latest['close'] > ma10
            open_below_ma5 = latest['open'] < ma5

            # 多头排列 MA5 > MA10 > MA20
            bull_arrangement = (ma5 > ma10) and (ma10 > ma20)

            # 乖离率（偏离MA5的幅度）
            bias_ma5 = abs(latest['close'] - ma5) / ma5 if ma5 > 0 else 0

            # 向上跳空缺口（今日开盘 > 昨日最高）
            gap_up = latest['open'] > prev['high'] if len(df) >= 2 else False

            # 3日振幅控制
            recent_3 = df.tail(3)
            amplitude_3d = ((recent_3['high'] - recent_3['low']) / recent_3['close']).mean() if len(recent_3) >= 3 else 0

            # 连续上涨天数
            consecutive_up_days = 0
            for i in range(1, len(df) + 1):
                if float(df.iloc[-i]['pctChg']) > 0:
                    consecutive_up_days += 1
                else:
                    break

            # 连续3日量比 > 1.0
            vr_sustained = False
            if len(df) >= 3:
                vr_sustained = all(
                    (df.iloc[-i]['volume'] / df['volume'].rolling(window=5).mean().iloc[-i]) > 1.0
                    for i in range(1, 4)
                )

            # 计算评分
            score = self.calculate_score(
                pctChg=latest['pctChg'],
                turnover=latest['turn'],
                amount=latest['amount'],
                peTTM=latest.get('peTTM', np.nan),
                close=latest['close'],
                high=latest['high'],
                low=latest['low'],
                open_price=latest['open'],
                preclose=latest.get('preclose', np.nan),
                upper_shadow_ratio=upper_shadow_ratio,
                volume_ratio=volume_ratio,
                bull_arrangement=bull_arrangement,
                is_new_high_10d=is_new_high_10d,
                consecutive_up_days=consecutive_up_days,
            )

            return {
                'pctChg': latest['pctChg'],
                'volume_ratio': volume_ratio,
                'turnover': latest['turn'],
                'amount': latest['amount'],
                'peTTM': latest.get('peTTM', np.nan),
                'close': latest['close'],
                'high': latest['high'],
                'low': latest['low'],
                'open': latest['open'],
                'preclose': latest.get('preclose', np.nan),
                'ma5': ma5,
                'ma10': ma10,
                'ma20': ma20,
                'avg_volume_5d': avg_volume_5d,
                'avg_turn_5d': avg_turn_5d,
                'is_new_high_10d': is_new_high_10d,
                'close_above_ma5': close_above_ma5,
                'close_above_ma10': close_above_ma10,
                'open_below_ma5': open_below_ma5,
                'bull_arrangement': bull_arrangement,
                'bias_ma5': bias_ma5,
                'gap_up': gap_up,
                'upper_shadow_ratio': upper_shadow_ratio,
                'body_ratio': body_ratio,
                'kline_quality_ok': kline_quality_ok,
                'amplitude_3d': amplitude_3d,
                'consecutive_up_days': consecutive_up_days,
                'vr_sustained': vr_sustained,
                'market_index_pct': market_index_pct,
                'score': score['total'],
                'tech_score': score['tech'],
                'fund_score': score['fund'],
                'sentiment_score': score['sentiment'],
                'risk_score': score['risk'],
                'confidence': score['confidence'],
                'signal': score['signal'],
            }
        except Exception as e:
            return None

    def _score_range_lookup(self, value: float, ranges: dict) -> int:
        """根据区间查找对应分值"""
        for (low, high), score in ranges.items():
            if low <= value < high:
                return score
        return 0

    def calculate_score(self, pctChg: float, turnover: float, amount: float,
                        peTTM: float, close: float, high: float, low: float,
                        open_price: float, preclose: float,
                        upper_shadow_ratio: float = 0.0,
                        volume_ratio: float = 0.0,
                        bull_arrangement: bool = False,
                        is_new_high_10d: bool = False,
                        consecutive_up_days: int = 0) -> dict:
        """计算推荐评分（融合版 v5：技术40+基本15+情绪35-风险20）"""
        tech = 0
        fund = 0
        sentiment = 0
        risk = 0

        # ── 技术面 40分 ──
        tech_rules = SCORE_RULES['tech']

        # 1. 价格趋势 (10分)
        tech += self._score_range_lookup(pctChg, tech_rules['price_trend'])

        # 2. 价格位置 (5分)
        if high > low:
            pos = (close - low) / (high - low)
            tech += self._score_range_lookup(pos, tech_rules['price_position'])
        else:
            tech += 3

        # 3. 换手率 (10分)
        tech += self._score_range_lookup(turnover, tech_rules['turnover'])

        # 4. 开盘强度 (5分)
        if preclose > 0:
            gap = (open_price - preclose) / preclose * 100
            tech += self._score_range_lookup(gap, tech_rules['open_gap'])
        else:
            tech += 3

        # 5. 多头排列 (5分) - v4精华
        if bull_arrangement:
            tech += tech_rules['ma_bull']['score']

        # 6. 10日新高 (5分) - v4精华
        if is_new_high_10d:
            tech += tech_rules['breakthrough']['score']

        tech = min(40, tech)

        # ── 基本面 15分 ──
        fund_rules = SCORE_RULES['fund']

        # 1. 成交额 (10分)
        fund += self._score_range_lookup(amount, fund_rules['amount'])

        # 2. PE修正 (5分) - 短线只看极端
        pe_low, pe_high = fund_rules['pe_check']['good']
        pe_bad_low, pe_bad_high = fund_rules['pe_check']['bad']
        if pe_low <= peTTM <= pe_high:
            fund += fund_rules['pe_check']['score']
        elif peTTM < 0 or peTTM >= pe_bad_low:
            fund -= fund_rules['pe_check']['score']

        fund = min(15, fund)
        if fund < 0:
            fund = 0

        # ── 情绪面 35分 ──
        senti_rules = SCORE_RULES['sentiment']

        # 1. 涨跌动能 (10分)
        sentiment += self._score_range_lookup(pctChg, senti_rules['momentum'])

        # 2. 资金活跃度 (10分)
        if turnover >= 15 and amount >= 500_000_000:
            sentiment += 10
        elif turnover >= 8 or amount >= 300_000_000:
            sentiment += 8
        elif turnover >= 3 or amount >= 100_000_000:
            sentiment += 5
        elif turnover >= 1:
            sentiment += 2
        else:
            sentiment += 0

        # 3. 量比异动 (10分) - v4精华
        vr_rules = senti_rules['volume_ratio']
        if volume_ratio >= 2.0:
            if upper_shadow_ratio > vr_rules['upper_shadow_threshold']:
                sentiment += vr_rules['high_punish']
            else:
                sentiment += vr_rules['high_clean']
        elif volume_ratio >= 1.5:
            sentiment += vr_rules['mid']
        elif volume_ratio >= 1.2:
            sentiment += vr_rules['low']

        # 4. 连续上涨 (5分) - v4精华
        if consecutive_up_days >= senti_rules['consecutive_up']['days']:
            sentiment += senti_rules['consecutive_up']['score']

        sentiment = min(35, sentiment)

        # ── 风险扣分 封顶20分 ──
        risk_rules = SCORE_RULES['risk']

        # 1. 大跌
        if pctChg <= -5.0:
            risk += 8
        elif pctChg <= -3.0:
            risk += 4

        # 2. 流动性枯竭
        if turnover < 0.5 and amount < 10_000_000:
            risk += 5

        # 3. 长上影线
        if high > 0 and preclose > 0:
            upper = (high - max(close, open_price)) / preclose * 100
            if upper >= 5.0:
                risk += 5
            elif upper >= 3.0:
                risk += 3

        # 4. 缩量上涨预警 (v4精华)
        shrink = risk_rules['shrink_volume']
        if pctChg > shrink['pct_threshold'] and volume_ratio < shrink['vr_threshold']:
            risk += shrink['score']

        risk = min(20, risk)

        # ── 总分 ──
        total = tech + fund + sentiment - risk
        total = max(0, min(100, round(total)))

        # ── 置信度 ──
        if turnover >= 5.0 and amount >= 100_000_000:
            confidence = "高"
        elif turnover >= 1.0:
            confidence = "中"
        else:
            confidence = "低"

        # ── 信号 ──
        if total >= 80:
            signal = "🟢买入"
        elif total >= 60:
            signal = "🟡观望偏多"
        elif total >= 40:
            signal = "🟡观望"
        elif total >= 20:
            signal = "🟡观望偏空"
        else:
            signal = "🔴卖出"

        return {
            "total": total,
            "tech": tech,
            "fund": fund,
            "sentiment": sentiment,
            "risk": risk,
            "confidence": confidence,
            "signal": signal,
        }

    def get_score_label(self, score: int) -> str:
        """直接返回分数"""
        return str(score)


# =============================================================================
# 推荐理由生成器
# =============================================================================

class ReasonGenerator:
    """推荐理由生成器"""

    def __init__(self):
        self.use_ai = False
        self.api_key = ""
        self.session = requests.Session()

    def set_api_key(self, api_key: str):
        self.api_key = api_key
        self.use_ai = bool(api_key and api_key.strip())

    def generate_template_reason(self, indicators: dict, stock_name: str) -> str:
        """生成模板推荐理由（v4版：纯BaoStock，多头排列/乖离率/跳空/缩量预警/量比持续）"""
        parts = []

        pct = indicators['pctChg']
        vr = indicators['volume_ratio']
        turn = indicators['turnover']
        is_new_high = indicators['is_new_high_10d']
        above_ma5 = indicators['close_above_ma5']
        above_ma10 = indicators['close_above_ma10']
        pullback = indicators['open_below_ma5'] and above_ma5
        upper_shadow = indicators.get('upper_shadow_ratio', 0)
        bull_arr = indicators.get('bull_arrangement', False)
        bias = indicators.get('bias_ma5', 0)
        gap = indicators.get('gap_up', False)
        amplitude_3d = indicators.get('amplitude_3d', 0)
        consecutive_up = indicators.get('consecutive_up_days', 0)
        vr_sust = indicators.get('vr_sustained', False)

        # 涨幅描述（3档精细化）
        if 2 <= pct < 5:
            parts.append(f"主升浪区间涨幅{pct:.2f}%")
        elif 5 <= pct < 9:
            parts.append(f"强势上涨{pct:.2f}%")
        elif 1 <= pct < 2:
            parts.append(f"温和上涨{pct:.2f}%")
        elif pct >= 9:
            parts.append(f"强势涨停({pct:.2f}%)")

        # 成交量描述（联动上影线）
        if vr >= 2.0 and upper_shadow > 0.25:
            parts.append(f"放量{vr:.1f}倍但上影线过长，需警惕")
        elif vr >= 2.0:
            parts.append(f"成交量较5日均量放大{vr:.1f}倍，资金明显介入")
        elif vr >= 1.5:
            parts.append(f"成交量较5日均量放大{vr:.1f}倍")
        elif vr >= 1.2:
            parts.append(f"成交量较5日均量有所放大({vr:.1f}倍)")

        # 换手率描述（双向）
        if 3 <= turn <= 15:
            parts.append(f"换手率{turn:.1f}%(最佳区间)")
        elif 1 <= turn < 3:
            parts.append(f"换手率{turn:.1f}%(略偏冷)")
        elif 15 < turn <= 20:
            parts.append(f"换手率{turn:.1f}%(略偏热)")
        elif turn > 20:
            parts.append(f"换手率{turn:.1f}%(过热)")

        # 均线描述（合并）
        if above_ma5 and above_ma10:
            parts.append("股价站上5日和10日均线")
        elif above_ma5:
            parts.append("股价站稳5日均线")

        # 多头排列
        if bull_arr:
            parts.append("均线多头排列（MA5>MA10>MA20）")

        # 乖离率
        if bias < 0.03:
            parts.append("乖离率极小，未过热")
        elif bias > 0.08:
            parts.append(f"乖离率{bias*100:.1f}%，偏离均线过远")

        # 向上跳空
        if gap:
            parts.append("向上跳空高开，强势突破")

        # 新高描述（收盘价）
        if is_new_high:
            parts.append("收盘创10日新高")

        # 3日振幅（稳定性）
        if amplitude_3d < 0.05:
            parts.append("近3日振幅极小，走势稳定")
        elif amplitude_3d > 0.15:
            parts.append(f"近3日振幅{amplitude_3d*100:.1f}%，波动剧烈")

        # 连续上涨
        if consecutive_up >= 3:
            parts.append(f"连续{consecutive_up}日上涨， momentum 强劲")

        # 量比持续放大
        if vr_sust:
            parts.append("量比持续放大，资金持续流入")

        # 回踩描述
        if pullback:
            parts.append("回踩均线后起涨")

        return "；".join(parts) + "。"

    def generate_ai_reason(self, indicators: dict, stock_name: str) -> str:
        """使用DeepSeek API生成推荐理由"""
        if not self.use_ai or not self.api_key:
            return self.generate_template_reason(indicators, stock_name)

        # 构建指标摘要（v4版）
        upper_shadow = indicators.get('upper_shadow_ratio', 0)
        amplitude = indicators.get('amplitude_3d', 0)
        consecutive_up = indicators.get('consecutive_up_days', 0)
        market_idx = indicators.get('market_index_pct', 0)
        bull_arr = indicators.get('bull_arrangement', False)
        bias = indicators.get('bias_ma5', 0)
        gap = indicators.get('gap_up', False)
        vr_sust = indicators.get('vr_sustained', False)
        indicators_text = (
            f"股票名称：{stock_name}；"
            f"涨跌幅：{indicators['pctChg']:.2f}%；"
            f"成交量比：{indicators['volume_ratio']:.2f}倍；"
            f"换手率：{indicators['turnover']:.2f}%；"
            f"收盘价：{indicators['close']:.2f}元；"
            f"5日均线：{indicators['ma5']:.2f}元；"
            f"10日均线：{indicators['ma10']:.2f}元；"
            f"20日均线：{indicators['ma20']:.2f}元；"
            f"上影线比例：{upper_shadow:.2f}；"
            f"近3日振幅：{amplitude*100:.1f}%；"
            f"连续上涨：{consecutive_up}天；"
            f"乖离率：{bias*100:.1f}%；"
            f"科创50涨跌幅：{market_idx:.2f}%；"
            f"{'收盘创10日新高；' if indicators['is_new_high_10d'] else ''}"
            f"{'站上5日均线；' if indicators['close_above_ma5'] else ''}"
            f"{'站上10日均线；' if indicators['close_above_ma10'] else ''}"
            f"{'多头排列；' if bull_arr else ''}"
            f"{'向上跳空；' if gap else ''}"
            f"{'量比持续放大；' if vr_sust else ''}"
            f"{'回踩均线起涨；' if (indicators['open_below_ma5'] and indicators['close_above_ma5']) else ''}"
        )

        prompt = f"""你是一个A股短线分析助手，请根据以下技术指标，用一段话（不超过80字）解释该股票短线强势的逻辑，语气专业。

指标：{indicators_text}

请直接输出推荐理由，不要添加额外说明。"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 150,
            "temperature": 0.7
        }

        try:
            response = self.session.post(
                DEEPSEEK_API_URL,
                headers=headers,
                json=payload,
                timeout=DEEPSEEK_TIMEOUT
            )

            if response.status_code == 200:
                result = response.json()
                reason = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                if reason:
                    return reason.strip()
        except requests.exceptions.Timeout:
            raise Exception("DeepSeek API调用超时")
        except Exception as e:
            raise Exception(f"DeepSeek API调用失败: {str(e)}")

        # 失败时使用模板
        return self.generate_template_reason(indicators, stock_name)

    def generate_reason(self, indicators: dict, stock_name: str) -> str:
        """生成推荐理由（优先AI，失败后降级）"""
        if self.use_ai:
            try:
                return self.generate_ai_reason(indicators, stock_name)
            except Exception as e:
                raise e  # 让调用者处理降级
        return self.generate_template_reason(indicators, stock_name)


# =============================================================================
# 工作线程
# =============================================================================

class WorkerThread(QThread):
    """工作线程，用于执行耗时的选股操作"""

    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int, str)
    result_signal = pyqtSignal(list)
    finished_signal = pyqtSignal()

    def __init__(self, selected_markets: list, trading_days: int, use_ai: bool,
                 ai_api_key: str, resume_trade_date: str = "", workers: int = DEFAULT_WORKERS):
        super().__init__()
        self.selected_markets = selected_markets
        self.trading_days = trading_days
        self.use_ai = use_ai
        self.ai_api_key = ai_api_key
        self.resume_trade_date = resume_trade_date
        self.workers = workers
        self.ds = DataService()
        self.engine = QuantEngine(self.ds)
        self.reason_gen = ReasonGenerator()
        self.reason_gen.set_api_key(ai_api_key)
        self._is_running = True

    def _process_stock(self, stock: dict, trade_date: str, cutoff_date: str,
                        market_index_pct: float) -> dict:
        """处理单只股票"""
        code = stock['code']
        name = stock['name']

        try:
            if is_st_stock(name):
                return {'filter': 'st', 'code': code}

            listing_date = self.ds.get_listing_date(code)
            if listing_date and listing_date > cutoff_date:
                return {'filter': 'listing', 'code': code}

            df = self.ds.get_kline_data(code, days=DEFAULT_TRADING_DAYS + 5, end_date=trade_date)
            if df is None or len(df) < 5:
                return {'filter': 'kline_failed', 'code': code}

            latest_pct = float(df.iloc[-1]['pctChg']) if not pd.isna(df.iloc[-1]['pctChg']) else 0
            if latest_pct <= 0:
                return {'filter': 'pct', 'code': code}

            if not check_kline_quality(df):
                return {'filter': 'kline_quality', 'code': code}

            avg_amount_5d = df['amount'].tail(5).mean() / 10000
            if avg_amount_5d < MIN_AVG_AMOUNT:
                return {'filter': 'liquidity', 'code': code}

            avg_vol_5d = df['volume'].tail(5).mean()
            latest_vol = df.iloc[-1]['volume']
            volume_ratio = latest_vol / avg_vol_5d if avg_vol_5d > 0 else 0
            if volume_ratio < 0.5 and latest_pct > 0:
                return {'filter': 'volume_shrink', 'code': code}

            indicators = self.engine.calculate_indicators(df, stock_name=name, market_index_pct=market_index_pct)
            if not indicators:
                return {'filter': 'indicator_failed', 'code': code}

            score = indicators['score']
            if score < MIN_SCORE_THRESHOLD:
                return {'filter': 'score', 'code': code}

            reason = self.reason_gen.generate_template_reason(indicators, name)

            return {
                'result': {
                    'code': code, 'name': name,
                    'close': indicators['close'], 'pctChg': indicators['pctChg'],
                    'turnover': indicators['turnover'], 'amount': indicators['amount'],
                    'volume_ratio': indicators['volume_ratio'],
                    'peTTM': indicators['peTTM'],
                    'score': score,
                    'tech_score': indicators['tech_score'],
                    'fund_score': indicators['fund_score'],
                    'sentiment_score': indicators['sentiment_score'],
                    'risk_score': indicators['risk_score'],
                    'confidence': indicators['confidence'],
                    'signal': indicators['signal'],
                    'stars': score,
                    'reason': reason,
                },
                'code': code, 'name': name, 'indicators': indicators,
            }
        except Exception:
            return {'filter': 'error', 'code': code}

    def run(self):
        try:
            if not self.ds.login():
                self.log_signal.emit("错误: BaoStock登录失败")
                self.finished_signal.emit()
                return

            trade_date = self.resume_trade_date or self.ds.get_previous_trading_date()
            self.log_signal.emit(f"使用交易日: {trade_date}")

            market_index_pct = self.ds.get_market_index_pct()
            self.log_signal.emit(f"科创50涨跌幅: {market_index_pct:.2f}%")

            stocks = self.ds.get_stock_list(trade_date, self.selected_markets)
            if not stocks:
                self.log_signal.emit("错误: 未获取到任何股票")
                self.finished_signal.emit()
                return

            codes = [s['code'] for s in stocks]
            self.ds.preload_listing_dates(codes)

            total = len(stocks)
            cutoff_date = (datetime.strptime(trade_date, '%Y-%m-%d') - timedelta(days=MIN_LISTING_DAYS)).strftime('%Y-%m-%d')
            self.log_signal.emit(f"开始分析 {total} 只股票...")

            stats = {'total': total, 'st_filtered': 0, 'listing_filtered': 0,
                     'kline_failed': 0, 'indicator_failed': 0, 'liquidity_filtered': 0,
                     'pct_filtered': 0, 'kline_quality_filtered': 0,
                     'volume_shrink_filtered': 0, 'score_filtered': 0}

            results = []
            ai_pending = [] if self.use_ai else None

            for idx, stock in enumerate(stocks):
                if not self._is_running:
                    break

                code = stock['code']
                name = stock['name']
                completed = idx + 1

                self.progress_signal.emit(completed, total, f"{code} {name}")

                now = time.time()
                if completed == 1 or completed % 50 == 0:
                    self.log_signal.emit(f"[进度 {completed}/{total}] {code} {name}...")

                out = self._process_stock(stock, trade_date, cutoff_date, market_index_pct)

                if 'result' in out:
                    results.append(out['result'])
                    if ai_pending is not None:
                        ai_pending.append(out)
                    self.log_signal.emit(
                        f"  ✓ 找到候选: {code} {name} (评分:{out['result']['score']}, 涨幅:{out['result']['pctChg']:.2f}%)")
                else:
                    ft = out.get('filter', '')
                    if ft == 'error':
                        pass
                    elif ft in stats:
                        stats[ft] += 1
                    elif ft + '_filtered' in stats:
                        stats[ft + '_filtered'] += 1

            if ai_pending:
                self.log_signal.emit("正在批量生成 AI 推荐理由...")
                for item in ai_pending[:20]:
                    try:
                        reason = self.reason_gen.generate_reason(item['indicators'], item['name'])
                        for r in results:
                            if r['code'] == item['code']:
                                r['reason'] = reason
                                break
                    except:
                        pass

            self.log_signal.emit("=" * 50)
            self.log_signal.emit("过滤统计:")
            self.log_signal.emit(f"  总股票数: {stats['total']}")
            self.log_signal.emit(f"  ST股票过滤: {stats['st_filtered']}")
            self.log_signal.emit(f"  上市不足60日过滤: {stats['listing_filtered']}")
            self.log_signal.emit(f"  K线数据获取失败: {stats['kline_failed']}")
            self.log_signal.emit(f"  指标计算失败: {stats['indicator_failed']}")
            self.log_signal.emit(f"  流动性不足过滤: {stats['liquidity_filtered']}")
            self.log_signal.emit(f"  涨跌幅≤0过滤: {stats['pct_filtered']}")
            self.log_signal.emit(f"  K线质量不过关: {stats['kline_quality_filtered']}")
            self.log_signal.emit(f"  评分低于阈值过滤: {stats['score_filtered']}")
            self.log_signal.emit(f"  符合条件: {len(results)} 只")
            self.log_signal.emit("=" * 50)

            results.sort(key=lambda x: x['score'], reverse=True)
            self.log_signal.emit(f"分析完成，共筛选出 {len(results)} 只符合条件的股票")

            self.result_signal.emit(results)
            clear_checkpoint()

        except Exception as e:
            self.log_signal.emit(f"错误: {str(e)}")
            traceback.print_exc()
        finally:
            self.ds.logout()
            self.finished_signal.emit()

    def stop(self):
        self._is_running = False


# =============================================================================
# 主窗口
# =============================================================================

class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.results = []
        self.worker = None
        self.pending_resume_trade_date = ""
        self.init_ui()
        QTimer.singleShot(0, self.auto_resume_if_needed)

    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("A股短线推荐助手 v1.0")
        self.setGeometry(100, 100, 1200, 800)

        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # ========== 顶部标题 ==========
        title_label = QLabel("A股短线推荐助手")
        title_font = QFont("微软雅黑", 18, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # ========== 参数设置区域 ==========
        settings_group = QGroupBox("参数设置")
        settings_layout = QVBoxLayout()

        # 第一行设置
        row1_layout = QHBoxLayout()

        # 日期范围
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("日期范围:"))
        self.date_range_combo = QComboBox()
        self.date_range_combo.addItems(["最近3个交易日", "最近5个交易日", "最近10个交易日", "最近20个交易日"])
        self.date_range_combo.setCurrentIndex(0)
        date_layout.addWidget(self.date_range_combo)
        row1_layout.addLayout(date_layout)

        # 板块选择（多选）
        market_layout = QHBoxLayout()
        market_layout.addWidget(QLabel("板块:"))
        self.market_checkboxes = {}
        for name in ALL_MARKET_NAMES:
            cb = QCheckBox(name)
            cb.setChecked(True)
            self.market_checkboxes[name] = cb
            market_layout.addWidget(cb)
        market_layout.addStretch()
        row1_layout.addLayout(market_layout)

        row1_layout.addStretch()
        settings_layout.addLayout(row1_layout)

        # 第二行设置
        row2_layout = QHBoxLayout()

        # AI推荐理由
        self.ai_checkbox = QCheckBox("启用AI推荐理由")
        self.ai_checkbox.stateChanged.connect(self.on_ai_checkbox_changed)
        row2_layout.addWidget(self.ai_checkbox)

        # API Key输入
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("输入DeepSeek API Key (可选)")
        self.api_key_edit.setMaximumWidth(300)
        self.api_key_edit.setEnabled(False)
        row2_layout.addWidget(self.api_key_edit)

        row2_layout.addStretch()

        # 线程数
        thread_layout = QHBoxLayout()
        thread_layout.addWidget(QLabel("线程数:"))
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 16)
        self.workers_spin.setValue(DEFAULT_WORKERS)
        self.workers_spin.setFixedWidth(50)
        thread_layout.addWidget(self.workers_spin)
        row2_layout.addLayout(thread_layout)

        # 最低评分
        star_layout = QHBoxLayout()
        star_layout.addWidget(QLabel("最低评分:"))
        self.min_star_combo = QComboBox()
        self.min_star_combo.addItems(["35分以上", "50分以上", "65分以上", "80分以上"])
        self.min_star_combo.setCurrentIndex(0)
        star_layout.addWidget(self.min_star_combo)
        row2_layout.addLayout(star_layout)

        settings_layout.addLayout(row2_layout)
        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)

        # ========== 操作按钮区域 ==========
        button_layout = QHBoxLayout()

        self.start_button = QPushButton("一键推荐")
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 12px 30px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.start_button.clicked.connect(self.on_start_clicked)
        button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 12px 30px;
                font-size: 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.stop_button.clicked.connect(self.on_stop_clicked)
        button_layout.addWidget(self.stop_button)

        self.export_button = QPushButton("导出CSV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.on_export_clicked)
        button_layout.addWidget(self.export_button)

        button_layout.addStretch()

        main_layout.addLayout(button_layout)

        # ========== 进度显示区域 ==========
        progress_layout = QVBoxLayout()

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumHeight(25)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #aaa;
                border-radius: 3px;
                text-align: center;
                background-color: #f0f0f0;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
            }
        """)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m (%p%)")
        progress_layout.addWidget(self.progress_bar)

        # 当前处理股票标签
        self.current_stock_label = QLabel("就绪")
        self.current_stock_label.setStyleSheet("color: #666; font-size: 12px;")
        self.current_stock_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.current_stock_label)

        main_layout.addLayout(progress_layout)

        # ========== 结果表格 ==========
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(12)
        self.result_table.setHorizontalHeaderLabels([
            "股票代码", "股票名称", "现价(元)", "涨跌幅(%)",
            "换手率(%)", "PE(TTM)", "技术(40)", "基本(15)",
            "情绪(35)", "风险(-)", "总分", "信号"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setSortingEnabled(True)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        main_layout.addWidget(self.result_table)

        # ========== 日志区域 ==========
        log_group = QGroupBox("执行日志")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #00ff00;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
            }
        """)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        # ========== 状态栏 ==========
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def on_ai_checkbox_changed(self, state):
        """AI复选框状态改变"""
        self.api_key_edit.setEnabled(state == Qt.Checked)

    def auto_resume_if_needed(self):
        checkpoint = read_checkpoint()
        if not checkpoint or checkpoint.get("status") == "completed":
            return
        if self.worker and self.worker.isRunning():
            return

        params = checkpoint.get("params", {})
        markets = params.get("selected_markets", [])
        trading_days = params.get("trading_days")
        use_ai = bool(params.get("use_ai", False))

        if markets:
            for name, cb in self.market_checkboxes.items():
                cb.setChecked(name in markets)

        trading_days_map = [3, 5, 10, 20]
        if trading_days in trading_days_map:
            self.date_range_combo.setCurrentIndex(trading_days_map.index(trading_days))

        self.ai_checkbox.setChecked(use_ai)
        self.pending_resume_trade_date = checkpoint.get("trade_date", "")
        completed = len(checkpoint.get("completed_codes", []))
        total = checkpoint.get("total", 0)
        trade_date = checkpoint.get("trade_date", "未知")

        message_box = QMessageBox(self)
        message_box.setWindowTitle("发现未完成任务")
        message_box.setIcon(QMessageBox.Question)
        message_box.setText("发现上次未完成的一键推荐任务。")
        message_box.setInformativeText(
            f"交易日: {trade_date}\n"
            f"进度: {completed}/{total}\n\n"
            "请选择要怎么处理。"
        )
        continue_button = message_box.addButton("继续上次任务", QMessageBox.AcceptRole)
        discard_button = message_box.addButton("放弃本次任务", QMessageBox.DestructiveRole)
        later_button = message_box.addButton("暂不处理", QMessageBox.RejectRole)
        message_box.setDefaultButton(later_button)
        message_box.exec_()

        clicked_button = message_box.clickedButton()
        if clicked_button == continue_button:
            self.log(f"继续上次未完成任务: {completed}/{total}")
            self.on_start_clicked()
        elif clicked_button == discard_button:
            clear_checkpoint()
            self.pending_resume_trade_date = ""
            self.log("已放弃上次未完成任务")
            self.status_bar.showMessage("已放弃上次未完成任务")
        else:
            self.pending_resume_trade_date = ""
            self.log(f"发现未完成任务，已暂不处理: {completed}/{total}")
            self.status_bar.showMessage(f"未完成任务已保留: {completed}/{total}")

    def on_start_clicked(self):
        """开始选股"""
        if self.worker and self.worker.isRunning():
            return

        # 获取参数
        selected_markets = [name for name, cb in self.market_checkboxes.items() if cb.isChecked()]
        if not selected_markets:
            QMessageBox.warning(self, "提示", "请至少选择一个板块！")
            return
        date_range = self.date_range_combo.currentIndex()
        use_ai = self.ai_checkbox.isChecked()
        api_key = self.api_key_edit.text().strip() if use_ai else ""

        # 根据日期范围获取交易日天数
        trading_days_map = [3, 5, 10, 20]
        trading_days = trading_days_map[date_range]
        resume_trade_date = self.pending_resume_trade_date
        self.pending_resume_trade_date = ""

        # 清空结果
        self.results = []
        self.result_table.setRowCount(0)
        self.log_text.clear()
        self.export_button.setEnabled(False)

        # 重置进度条
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)
        self.current_stock_label.setText("正在获取股票列表...")

        # 更新按钮状态
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_bar.showMessage("选股中...")

        self.log(f"[{datetime.now().strftime('%H:%M:%S')}] 开始选股...")
        self.log(f"板块: {', '.join(selected_markets)}")
        self.log(f"启用AI理由: {'是' if use_ai else '否'}")
        if resume_trade_date:
            self.log(f"继续上次未完成任务，交易日: {resume_trade_date}")

        # 创建并启动工作线程
        self.worker = WorkerThread(selected_markets, trading_days, use_ai, api_key, resume_trade_date,
                                    workers=self.workers_spin.value())
        self.worker.log_signal.connect(self.on_log_message)
        self.worker.progress_signal.connect(self.on_progress_update)
        self.worker.result_signal.connect(self.on_result_ready)
        self.worker.finished_signal.connect(self.on_worker_finished)
        self.worker.start()

    def on_stop_clicked(self):
        """停止选股"""
        if self.worker:
            self.worker.stop()
            self.log("正在停止...")

    def on_export_clicked(self):
        """导出CSV"""
        if not self.results:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出CSV文件",
            f"短线推荐_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )

        if file_path:
            try:
                df = pd.DataFrame(self.results)
                df = df[['code', 'name', 'close', 'pctChg', 'turnover', 'peTTM', 'tech_score', 'fund_score', 'sentiment_score', 'risk_score', 'score', 'confidence', 'signal', 'reason']]
                df.columns = ['股票代码', '股票名称', '现价(元)', '涨跌幅(%)', '换手率(%)', 'PE(TTM)', '技术面(40)', '基本面(15)', '情绪面(35)', '风险扣分', '总分', '置信度', '信号', '推荐理由']
                df.to_csv(file_path, index=False, encoding='utf-8-sig')
                self.log(f"导出成功: {file_path}")
                QMessageBox.information(self, "导出成功", f"文件已保存至:\n{file_path}")
            except Exception as e:
                self.log(f"导出失败: {str(e)}")
                QMessageBox.warning(self, "导出失败", str(e))

    @pyqtSlot(str)
    def on_log_message(self, message: str):
        """接收日志消息"""
        self.log(message)

    @pyqtSlot(int, int, str)
    def on_progress_update(self, current: int, total: int, stock_info: str):
        """接收进度更新"""
        # 更新进度条
        if total > 0:
            percent = int(current * 100 / total)
            self.progress_bar.setValue(percent)
        self.status_bar.showMessage(f"分析进度: {current}/{total}")

        # 更新当前处理的股票标签
        self.current_stock_label.setText(f"正在分析: {stock_info}")

    @pyqtSlot(list)
    def on_result_ready(self, results: list):
        """接收结果"""
        self.results = results
        self.display_results(results)
        self.export_button.setEnabled(len(results) > 0)

    @pyqtSlot()
    def on_worker_finished(self):
        """工作线程完成"""
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        checkpoint = read_checkpoint()
        if checkpoint and checkpoint.get("status") != "completed":
            total = checkpoint.get("total", 0)
            completed = len(checkpoint.get("completed_codes", []))
            percent = int(completed * 100 / total) if total else self.progress_bar.value()
            self.progress_bar.setValue(percent)
            self.status_bar.showMessage(f"已暂停，下次打开可选择继续: {completed}/{total}")
            self.current_stock_label.setText("已暂停，下次打开可选择继续")
        else:
            self.status_bar.showMessage("选股完成")
            self.progress_bar.setValue(100)
            self.current_stock_label.setText("分析完成")

    def log(self, message: str):
        """添加日志"""
        self.log_text.append(message)
        # 滚动到底部
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def display_results(self, results: list):
        """显示结果"""
        self.result_table.setRowCount(len(results))

        for i, row in enumerate(results):
            # 0: 股票代码
            code_item = QTableWidgetItem(row['code'])
            code_item.setTextAlignment(Qt.AlignCenter)
            self.result_table.setItem(i, 0, code_item)

            # 1: 股票名称
            name_item = QTableWidgetItem(row['name'])
            name_item.setTextAlignment(Qt.AlignCenter)
            self.result_table.setItem(i, 1, name_item)

            # 2: 现价(元)
            close_item = QTableWidgetItem(f"{row['close']:.2f}")
            close_item.setTextAlignment(Qt.AlignCenter)
            self.result_table.setItem(i, 2, close_item)

            # 3: 涨跌幅(%)
            pct_item = QTableWidgetItem(f"{row['pctChg']:+.2f}")
            pct_item.setTextAlignment(Qt.AlignCenter)
            if row['pctChg'] > 0:
                pct_item.setForeground(QColor(255, 0, 0))
            elif row['pctChg'] < 0:
                pct_item.setForeground(QColor(0, 128, 0))
            self.result_table.setItem(i, 3, pct_item)

            # 4: 换手率(%)
            turn_item = QTableWidgetItem(f"{row['turnover']:.2f}")
            turn_item.setTextAlignment(Qt.AlignCenter)
            self.result_table.setItem(i, 4, turn_item)

            # 5: PE(TTM)
            pe_val = row.get('peTTM', np.nan)
            pe_str = f"{pe_val:.2f}" if not pd.isna(pe_val) else "-"
            pe_item = QTableWidgetItem(pe_str)
            pe_item.setTextAlignment(Qt.AlignCenter)
            self.result_table.setItem(i, 5, pe_item)

            # 6: 技术(40)
            tech_val = row.get('tech_score', 0)
            tech_item = QTableWidgetItem(str(tech_val))
            tech_item.setTextAlignment(Qt.AlignCenter)
            self.result_table.setItem(i, 6, tech_item)

            # 7: 基本(15)
            fund_val = row.get('fund_score', 0)
            fund_item = QTableWidgetItem(str(fund_val))
            fund_item.setTextAlignment(Qt.AlignCenter)
            self.result_table.setItem(i, 7, fund_item)

            # 8: 情绪(35)
            senti_val = row.get('sentiment_score', 0)
            senti_item = QTableWidgetItem(str(senti_val))
            senti_item.setTextAlignment(Qt.AlignCenter)
            self.result_table.setItem(i, 8, senti_item)

            # 9: 风险(-)
            risk_val = row.get('risk_score', 0)
            risk_item = QTableWidgetItem(str(risk_val))
            risk_item.setTextAlignment(Qt.AlignCenter)
            if risk_val > 0:
                risk_item.setForeground(QColor(255, 0, 0))
            self.result_table.setItem(i, 9, risk_item)

            # 10: 总分
            score_val = int(row.get('stars', 0))
            score_item = QTableWidgetItem(str(score_val))
            score_item.setTextAlignment(Qt.AlignCenter)
            if score_val >= 80:
                score_item.setForeground(QColor(255, 165, 0))
            elif score_val >= 65:
                score_item.setForeground(QColor(160, 32, 240))
            elif score_val >= 50:
                score_item.setForeground(QColor(0, 128, 0))
            self.result_table.setItem(i, 10, score_item)

            # 11: 信号
            signal = row.get('signal', '')
            signal_item = QTableWidgetItem(signal)
            signal_item.setTextAlignment(Qt.AlignCenter)
            self.result_table.setItem(i, 11, signal_item)

        # 调整列宽
        self.result_table.resizeColumnsToContents()
        self.result_table.setColumnWidth(0, 90)
        self.result_table.setColumnWidth(1, 80)
        self.result_table.setColumnWidth(3, 90)    # 涨跌幅
        self.result_table.setColumnWidth(4, 80)    # 换手率
        self.result_table.setColumnWidth(5, 80)    # PE
        self.result_table.setColumnWidth(6, 60)    # 技术
        self.result_table.setColumnWidth(7, 60)    # 基本
        self.result_table.setColumnWidth(8, 60)    # 情绪
        self.result_table.setColumnWidth(9, 60)    # 风险
        self.result_table.setColumnWidth(10, 60)   # 总分
        self.result_table.setColumnWidth(11, 100)  # 信号


# =============================================================================
# 程序入口
# =============================================================================

def main():
    """程序入口"""
    app = QApplication(sys.argv)

    # 设置样式
    app.setStyle('Fusion')

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
