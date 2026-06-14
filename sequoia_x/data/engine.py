"""数据引擎模块：负责 SQLite 行情数据存储与 baostock 增量同步。"""

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from sequoia_x.core.config import Settings
from sequoia_x.core.logger import get_logger

logger = get_logger(__name__)


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS stock_daily (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol   TEXT    NOT NULL,
    date     TEXT    NOT NULL,
    open     REAL,
    high     REAL,
    low      REAL,
    close    REAL,
    volume   REAL,
    turnover REAL,
    UNIQUE (symbol, date)
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_symbol_date ON stock_daily (symbol, date);
"""


def _bs_fetch_batch(tasks: list, lock: threading.Lock) -> list:
    """多线程 worker：通过锁串行化 baostock 调用，批量拉取数据。"""
    import baostock as bs
    results = []
    for symbol, bs_code, start, end in tasks:
        try:
            with lock:
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,open,high,low,close,volume,amount",
                    start_date=start,
                    end_date=end,
                    frequency="d",
                    adjustflag="3",  # 不复权，真实价格
                )
                if rs.error_code != "0":
                    continue
                while rs.next():
                    results.append([symbol] + rs.get_row_data())
        except Exception:
            continue
    return results


class DataEngine:
    """行情数据引擎，负责 SQLite 存储和 baostock 数据同步。"""

    def __init__(self, settings: Settings) -> None:
        self.db_path: str = settings.db_path
        self.start_date: str = settings.start_date
        self._bs_lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_INDEX_SQL)
            conn.commit()
        logger.info(f"数据库初始化完成：{self.db_path}")

    def _get_last_date(self, symbol: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(date) FROM stock_daily WHERE symbol = ?",
                (symbol,),
            ).fetchone()
        return row[0] if row and row[0] else None

    def get_ohlcv(self, symbol: str) -> pd.DataFrame:
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql(
                "SELECT * FROM stock_daily WHERE symbol = ? ORDER BY date",
                conn,
                params=(symbol,),
            )
        return df

    @staticmethod
    def _to_baostock_code(symbol: str) -> str:
        """将纯数字代码转为 baostock 格式：6/9开头 -> sh，其余 -> sz。"""
        prefix = "sh" if symbol.startswith(("6", "9")) else "sz"
        return f"{prefix}.{symbol}"

    # ── 数据同步 ──

    def sync_today_bulk(self) -> int:
        """多线程并行通过 baostock 拉取增量数据（后复权），写入 SQLite。"""
        from datetime import date, timedelta

        import baostock as bs

        today_str = date.today().strftime("%Y-%m-%d")

        tasks = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT symbol, MAX(date) FROM stock_daily GROUP BY symbol"
            ).fetchall()

        if not rows:
            logger.warning("本地无股票数据，请先执行 --backfill")
            return 0

        for symbol, last_date in rows:
            if last_date and last_date >= today_str:
                continue
            start = today_str
            if last_date:
                start = (date.fromisoformat(last_date) + timedelta(days=1)).strftime("%Y-%m-%d")
            tasks.append((symbol, self._to_baostock_code(symbol), start, today_str))

        if not tasks:
            logger.info("所有股票已是最新，无需更新")
            return 0

        logger.info(f"需要更新 {len(tasks)} 只股票，启动多线程并行拉取...")

        lg = bs.login()
        if lg.error_code != "0":
            logger.error(f"baostock 登录失败: {lg.error_msg}")
            return 0

        try:
            n_workers = min(8, len(tasks))
            chunks = [tasks[i::n_workers] for i in range(n_workers)]

            all_rows = []
            with ThreadPoolExecutor(max_workers=n_workers) as executor:
                futures = [
                    executor.submit(_bs_fetch_batch, chunk, self._bs_lock)
                    for chunk in chunks
                ]
                for future in as_completed(futures):
                    batch = future.result()
                    if batch:
                        all_rows.extend(batch)

            if not all_rows:
                logger.info("无新数据（可能非交易日）")
                return 0

            df = pd.DataFrame(all_rows, columns=["symbol", "date", "open", "high", "low", "close", "volume", "turnover"])
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["close"])
            df = df[df["volume"] > 0]

            count = len(df)
            with sqlite3.connect(self.db_path) as conn:
                for d in df["date"].unique().tolist():
                    conn.execute("DELETE FROM stock_daily WHERE date = ?", (d,))
                df.to_sql("stock_daily", conn, if_exists="append", index=False, method="multi", chunksize=500)
                conn.commit()

            logger.info(f"sync_today_bulk: 写入 {count} 条数据")
            return count
        finally:
            bs.logout()

    def backfill(
        self,
        symbols: list[str],
        progress_callback=None,
    ) -> None:
        """通过 baostock 批量回填历史日 K 线数据（后复权），多线程并行加速。

        Args:
            symbols: 股票代码列表。
            progress_callback: 进度回调，签名为 callback(current: int, total: int)。
        """
        import time
        from datetime import date, timedelta

        import baostock as bs

        today_str = date.today().strftime("%Y-%m-%d")
        max_retries = 3

        def _login():
            with self._bs_lock:
                lg = bs.login()
                if lg.error_code != "0":
                    logger.error(f"baostock 登录失败: {lg.error_msg}")
                    return False
                return True

        if not _login():
            return

        total = len(symbols)
        success = 0
        skipped = 0
        failed = 0

        def _fetch_one(symbol: str) -> tuple:
            """单只股票的 baostock 拉取（在线程中调用，用锁串行化）。"""
            last_date = self._get_last_date(symbol)
            if last_date and last_date >= today_str:
                return ("skip", symbol)

            start = last_date or self.start_date
            if last_date:
                start = (date.fromisoformat(last_date) + timedelta(days=1)).strftime("%Y-%m-%d")

            bs_code = self._to_baostock_code(symbol)

            for attempt in range(max_retries):
                try:
                    with self._bs_lock:
                        rs = bs.query_history_k_data_plus(
                            bs_code,
                            "date,open,high,low,close,volume,amount",
                            start_date=start,
                            end_date=today_str,
                            frequency="d",
                            adjustflag="3",  # 不复权，真实价格
                        )
                        if rs.error_code != "0":
                            raise RuntimeError(rs.error_msg)
                        rows = []
                        while rs.next():
                            rows.append(rs.get_row_data())
                    return ("ok", symbol, rows)
                except Exception as exc:
                    if attempt < max_retries - 1:
                        wait = 2 ** (attempt + 1)
                        logger.warning(f"[{symbol}] 第{attempt + 1}次失败: {exc}，{wait}s 后重试")
                        time.sleep(wait)
                        with self._bs_lock:
                            bs.logout()
                        time.sleep(1)
                        _login()
                    else:
                        logger.warning(f"[{symbol}] {max_retries}次重试均失败，跳过")
            return ("fail", symbol)

        try:
            n_workers = min(8, total)
            completed = 0

            with ThreadPoolExecutor(max_workers=n_workers) as executor:
                futures = {executor.submit(_fetch_one, s): s for s in symbols}
                for future in as_completed(futures):
                    result = future.result()
                    completed += 1

                    if progress_callback:
                        progress_callback(completed, total)

                    if result[0] == "skip":
                        skipped += 1
                        continue
                    elif result[0] == "fail":
                        failed += 1
                        continue

                    _, symbol, rows = result
                    if not rows:
                        skipped += 1
                        continue

                    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])
                    for col in ["open", "high", "low", "close", "volume", "amount"]:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                    df = df.dropna(subset=["close"])
                    df = df[df["volume"] > 0]

                    if df.empty:
                        skipped += 1
                        continue

                    df["symbol"] = symbol
                    df = df.rename(columns={"amount": "turnover"})
                    df = df[["symbol", "date", "open", "high", "low", "close", "volume", "turnover"]]

                    try:
                        with sqlite3.connect(self.db_path) as conn:
                            df.to_sql(
                                "stock_daily", conn, if_exists="append",
                                index=False, method="multi", chunksize=500,
                            )
                    except sqlite3.IntegrityError:
                        pass

                    success += 1

                    if completed % 500 == 0:
                        logger.info(
                            f"已处理 {completed}/{total}，"
                            f"成功 {success} 跳过 {skipped} 失败 {failed}"
                        )

        finally:
            with self._bs_lock:
                bs.logout()

        logger.info(f"回填完成 — 成功: {success} | 跳过: {skipped} | 失败: {failed}")

    # ── 股票列表 ──

    def get_all_symbols(self) -> list[str]:
        """通过 baostock 获取全市场 A 股代码列表。"""
        import baostock as bs

        lg = bs.login()
        if lg.error_code != "0":
            logger.error(f"baostock 登录失败: {lg.error_msg}")
            return []

        try:
            rs = bs.query_stock_basic(code_name="", code="")
            symbols = []
            while rs.next():
                row = rs.get_row_data()
                code = row[0]           # "sh.600000" or "sz.000001"
                status = row[4]         # "1" = 上市
                stock_type = row[5]     # "1" = 股票
                if status == "1" and stock_type == "1":
                    symbols.append(code.split(".")[1])  # 提取纯数字代码
            logger.info(f"获取股票列表完成，共 {len(symbols)} 只")
            return symbols
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return []
        finally:
            bs.logout()

    def get_local_symbols(self) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM stock_daily"
            ).fetchall()
        return [row[0] for row in rows]
