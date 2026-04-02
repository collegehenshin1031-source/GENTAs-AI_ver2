"""
Yahoo Finance への依存を減らす市場データ取得。
東証（.T）は Stooq の日足を優先し、英字銘柄（151A 等）でも取得しやすい順序にする。
ファンダ系（時価総額・配当）は yfinance の info を別途・短回数で取得。
"""

from __future__ import annotations

import io
import random
import time
from typing import Any

import pandas as pd
import requests
import yfinance as yf
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]


def get_yf_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update(
        {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return session


def normalize_tokyo_ticker(ticker: str) -> str:
    s = str(ticker or "").strip().upper()
    if not s:
        return ""
    return s if s.endswith(".T") else f"{s.replace('.T', '')}.T"


def fetch_stooq_hist_jp(ticker: str) -> pd.DataFrame | None:
    """Stooq 日足（例: 151a.jp）。東証の英字コード対応。"""
    code = str(ticker or "").replace(".T", "").strip()
    if not code:
        return None
    sym = f"{code.lower()}.jp"
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    try:
        r = requests.get(url, timeout=25)
        r.raise_for_status()
        raw = r.text.strip()
        if not raw or raw.lower().startswith("no data"):
            return None
        df = pd.read_csv(io.StringIO(raw))
    except Exception:
        return None
    if df is None or df.empty:
        return None
    colmap = {str(c).strip(): str(c).strip() for c in df.columns}
    df = df.rename(columns=colmap)
    lower = {c.lower(): c for c in df.columns}

    def col(name: str) -> str | None:
        return lower.get(name.lower())

    dcol, ocol, hcol, lcol, ccol, vcol = (
        col("date"),
        col("open"),
        col("high"),
        col("low"),
        col("close"),
        col("volume"),
    )
    if not all([dcol, ocol, hcol, lcol, ccol]):
        return None
    vol_series = (
        pd.to_numeric(df[vcol], errors="coerce").fillna(0) if vcol else pd.Series(0.0, index=df.index)
    )
    out = pd.DataFrame(
        {
            "Open": pd.to_numeric(df[ocol], errors="coerce"),
            "High": pd.to_numeric(df[hcol], errors="coerce"),
            "Low": pd.to_numeric(df[lcol], errors="coerce"),
            "Close": pd.to_numeric(df[ccol], errors="coerce"),
            "Volume": vol_series,
        }
    )
    out.index = pd.to_datetime(df[dcol], errors="coerce")
    out = out[~out.index.isna()].dropna(subset=["Close"], how="any").sort_index()
    out = out.tail(520)
    if len(out) < 5:
        return None
    out["Volume"] = out["Volume"].fillna(0)
    return out


def try_yfinance_info_only(ticker: str, attempts: int = 3) -> dict[str, Any]:
    """チャート用OHLCVは別取得済みのとき、info だけ短回数で試す。"""
    t = normalize_tokyo_ticker(ticker)
    if not t.endswith(".T"):
        t = ticker
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            session = get_yf_session()
            stock = yf.Ticker(t, session=session)
            info = stock.info or {}
            if isinstance(info, dict) and info:
                return info
        except Exception as e:
            last_err = e
        time.sleep(1.2 * (i + 1))
    return {}


def fetch_yfinance_hist_and_info(ticker: str, period: str = "2y") -> tuple[pd.DataFrame | None, dict[str, Any]]:
    session = get_yf_session()
    stock = yf.Ticker(ticker, session=session)
    hist = stock.history(period=period)
    info: dict[str, Any] = {}
    try:
        info = stock.info or {}
    except Exception:
        info = {}
    return hist, info if isinstance(info, dict) else {}


def fetch_ohlcv_and_info_robust(
    ticker: str,
    *,
    max_yf_retries: int = 3,
    base_delay: float = 4.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    東証: Stooq 優先 → 失敗時 yfinance。
    取得後、Stooq 経路なら info は別途 yfinance のみ（チャートAPI負荷を分散）。
    """
    t_tokyo = normalize_tokyo_ticker(ticker)
    if not t_tokyo:
        raise ValueError("無効なティッカーです")
    last_error: Exception | None = None

    if t_tokyo.endswith(".T"):
        hist_sq = fetch_stooq_hist_jp(t_tokyo)
        if hist_sq is not None and len(hist_sq) >= 5:
            info = try_yfinance_info_only(t_tokyo)
            return hist_sq, info

    for attempt in range(max_yf_retries):
        try:
            hist, info = fetch_yfinance_hist_and_info(t_tokyo, period="2y")
            if hist is not None and not hist.empty and len(hist) >= 5:
                return hist, info
            raise ValueError("データが空または不十分です")
        except Exception as e:
            last_error = e
            if attempt < max_yf_retries - 1:
                time.sleep(base_delay * (2**attempt))

    if t_tokyo.endswith(".T"):
        hist_sq = fetch_stooq_hist_jp(t_tokyo)
        if hist_sq is not None and len(hist_sq) >= 5:
            info = try_yfinance_info_only(t_tokyo)
            return hist_sq, info

    raise last_error if last_error else ValueError("データ取得に失敗しました")
