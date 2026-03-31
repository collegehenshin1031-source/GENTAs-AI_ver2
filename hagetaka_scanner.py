"""
ハゲタカスコープ - 全銘柄スキャン＆検知エンジン v2
高速化 + 二段階スコアリング（ゲート→スコア）
"""

from __future__ import annotations
import time
import random
from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import streamlit as st


class SignalLevel(Enum):
    """シグナルレベル"""
    LOCKON = "🔴 ロックオン"      # 最高レベル - 即通知
    HIGH = "🟠 高警戒"            # 要注目
    MEDIUM = "🟡 監視中"          # 継続監視
    LOW = "🟢 平常"               # 特に異常なし


class ScanMode(Enum):
    """スキャンモード"""
    QUICK = "quick"           # クイックスキャン（出来高上位）
    PRIME = "prime"           # プライム市場
    STANDARD = "standard"     # スタンダード市場
    GROWTH = "growth"         # グロース市場
    ALL = "all"               # 全銘柄
    CUSTOM = "custom"         # カスタム入力


@dataclass
class ScanOption:
    """スキャンオプション"""
    mode: ScanMode
    label: str
    description: str
    estimated_count: int
    estimated_time: str
    warning: Optional[str] = None


# スキャンオプション定義
SCAN_OPTIONS = {
    ScanMode.QUICK: ScanOption(
        mode=ScanMode.QUICK,
        label="⚡ クイックスキャン（推奨）",
        description="主要銘柄100社を高速スキャン",
        estimated_count=100,
        estimated_time="約1〜2分",
        warning=None
    ),
    ScanMode.PRIME: ScanOption(
        mode=ScanMode.PRIME,
        label="🏢 プライム市場",
        description="東証プライム上場銘柄",
        estimated_count=1800,
        estimated_time="約10〜15分",
        warning=None
    ),
    ScanMode.STANDARD: ScanOption(
        mode=ScanMode.STANDARD,
        label="🏬 スタンダード市場",
        description="東証スタンダード上場銘柄",
        estimated_count=1400,
        estimated_time="約8〜12分",
        warning=None
    ),
    ScanMode.GROWTH: ScanOption(
        mode=ScanMode.GROWTH,
        label="🌱 グロース市場",
        description="東証グロース上場銘柄",
        estimated_count=500,
        estimated_time="約3〜5分",
        warning=None
    ),
    ScanMode.ALL: ScanOption(
        mode=ScanMode.ALL,
        label="🌐 全銘柄スキャン",
        description="日本株全銘柄（約4,000社）",
        estimated_count=4000,
        estimated_time="約20〜30分",
        warning=None
    ),
    ScanMode.CUSTOM: ScanOption(
        mode=ScanMode.CUSTOM,
        label="✏️ 銘柄コードを直接入力",
        description="スキャンしたい銘柄を指定",
        estimated_count=0,
        estimated_time="入力数による",
        warning=None
    ),
}


# ==========================================
# ゲート条件（入口フィルター）
# ==========================================
GATE_CONDITIONS = {
    "min_trading_value": 1e8,     # 売買代金20日平均: 1億以上（緩和）
    "min_volume_ratio": 1.0,      # 出来高倍率: 1.0倍以上（実質なし）
    "min_price": 100,             # 株価: 100円以上（緩和）
}

# ロックオン設定
LOCKON_SETTINGS = {
    "min_score": 60,              # ロックオン最低スコア
    "max_lockon_count": 5,        # ロックオン上限数
    "high_alert_score": 45,       # 高警戒スコア
    "medium_score": 30,           # 監視中スコア
}


@dataclass
class HagetakaSignal:
    """ハゲタカ検知シグナル"""
    code: str
    name: str
    signal_level: SignalLevel
    total_score: int  # 0-100
    
    # 3つの兆候スコア
    stealth_score: int = 0      # ステルス集積スコア (0-35)
    board_score: int = 0        # 板の違和感スコア (0-35)
    volume_score: int = 0       # 出来高臨界点スコア (0-30)
    
    # ボーナススコア
    bonus_score: int = 0
    
    # 検知理由
    signals: List[str] = field(default_factory=list)
    
    # 株価データ
    price: float = 0
    change_pct: float = 0       # 前日比
    volume: int = 0
    avg_volume: int = 0
    volume_ratio: float = 0     # 出来高倍率
    turnover_pct: float = 0     # 浮動株回転率
    market_cap: float = 0       # 時価総額
    trading_value: float = 0    # 売買代金
    
    # M&Aスコア（既存機能との連携用）
    ma_score: int = 0
    
    # 検知日時
    detected_at: datetime = field(default_factory=datetime.now)


# ==========================================
# キャッシュ付きデータ取得
# ==========================================
@st.cache_data(ttl=300, show_spinner=False)  # 5分キャッシュ
def get_stock_data_cached(code: str) -> Optional[Dict[str, Any]]:
    """
    銘柄データを取得（キャッシュ付き）
    """
    return _fetch_stock_data(code)


def _fetch_stock_data(code: str) -> Optional[Dict[str, Any]]:
    """
    銘柄データを取得（内部実装）
    """
    try:
        ticker = yf.Ticker(f"{code}.T")
        
        # 株価履歴（1ヶ月で十分 - 高速化）
        hist = ticker.history(period="1mo")
        if hist.empty or len(hist) < 5:
            return None
        
        # 基本情報
        info = ticker.info
        
        # 最新データ
        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else latest
        
        # 出来高データ
        current_volume = int(latest['Volume'])
        avg_volume_20d = int(hist['Volume'].mean()) if len(hist) >= 5 else current_volume
        
        # 出来高倍率
        volume_ratio = current_volume / avg_volume_20d if avg_volume_20d > 0 else 1.0
        
        # 売買代金
        trading_value = float(latest['Close']) * current_volume
        avg_trading_value = float(hist['Close'] * hist['Volume']).mean()
        
        # 浮動株回転率（推定）
        shares_outstanding = info.get('sharesOutstanding', 0)
        float_shares = shares_outstanding * 0.3 if shares_outstanding else current_volume * 10
        turnover_pct = (current_volume / float_shares * 100) if float_shares > 0 else 0
        
        # 5日間の出来高トレンド
        if len(hist) >= 10:
            vol_5d_recent = hist['Volume'].tail(5).mean()
            vol_5d_prev = hist['Volume'].iloc[-10:-5].mean() if len(hist) >= 10 else vol_5d_recent
            volume_trend = vol_5d_recent / vol_5d_prev if vol_5d_prev > 0 else 1.0
        else:
            volume_trend = 1.0
        
        # 市場時価総額
        market_cap = info.get('marketCap', 0)
        
        return {
            "code": code,
            "name": info.get('shortName', info.get('longName', code)),
            "price": float(latest['Close']),
            "prev_close": float(prev['Close']),
            "change_pct": ((latest['Close'] - prev['Close']) / prev['Close'] * 100) if prev['Close'] > 0 else 0,
            "volume": current_volume,
            "avg_volume_20d": avg_volume_20d,
            "volume_ratio": volume_ratio,
            "volume_trend": volume_trend,
            "turnover_pct": turnover_pct,
            "market_cap": market_cap,
            "trading_value": trading_value,
            "avg_trading_value": avg_trading_value,
            "float_shares": float_shares,
            "hist": hist,
            "high_20d": hist['High'].max(),
            "low_20d": hist['Low'].min(),
        }
        
    except Exception as e:
        return None


# ==========================================
# ゲート判定（高速フィルタリング）
# ==========================================
def pass_gate(data: Dict[str, Any]) -> bool:
    """
    ゲート条件をパスするかチェック（両方満たす）
    """
    if data is None:
        return False
    
    # 売買代金チェック
    avg_trading_value = data.get("avg_trading_value", 0)
    if avg_trading_value < GATE_CONDITIONS["min_trading_value"]:
        return False
    
    # 出来高倍率チェック
    volume_ratio = data.get("volume_ratio", 0)
    if volume_ratio < GATE_CONDITIONS["min_volume_ratio"]:
        return False
    
    # 株価チェック
    price = data.get("price", 0)
    if price < GATE_CONDITIONS["min_price"]:
        return False
    
    return True


# ==========================================
# 新スコアリング（Best 2 of 3方式）
# ==========================================
def calculate_stealth_score_v2(data: Dict[str, Any]) -> Tuple[int, List[str], List[int]]:
    """
    ステルス集積スコア v2（Best 2 of 3）
    最大35点
    """
    scores = []
    signals = []
    
    # 条件1: 出来高トレンド（最大15点）
    volume_trend = data.get("volume_trend", 1.0)
    if volume_trend >= 1.8:
        scores.append(15)
        signals.append("📈 出来高が5日前比1.8倍以上に増加")
    elif volume_trend >= 1.4:
        scores.append(10)
        signals.append("📈 出来高が5日前比1.4倍に増加")
    elif volume_trend >= 1.2:
        scores.append(5)
        signals.append("📈 出来高が緩やかに増加傾向")
    else:
        scores.append(0)
    
    # 条件2: 値動き小×出来高増（最大12点）
    change_pct = abs(data.get("change_pct", 0))
    volume_ratio = data.get("volume_ratio", 1.0)
    
    if change_pct < 2.0 and volume_ratio >= 1.8:
        scores.append(12)
        signals.append("🥷 値動き小×出来高増＝ステルス集積の可能性")
    elif change_pct < 3.0 and volume_ratio >= 1.5:
        scores.append(8)
        signals.append("🥷 目立たない買い集めの兆候")
    elif volume_ratio >= 1.3:
        scores.append(4)
        signals.append("🥷 出来高やや増加")
    else:
        scores.append(0)
    
    # 条件3: 時価総額が買収適正サイズ（最大10点）
    market_cap = data.get("market_cap", 0)
    if market_cap > 0:
        market_cap_oku = market_cap / 1e8
        if 300 <= market_cap_oku <= 3000:
            scores.append(10)
            signals.append("🎯 時価総額がハゲタカ好適サイズ")
        elif 100 <= market_cap_oku < 300 or 3000 < market_cap_oku <= 5000:
            scores.append(6)
            signals.append("🎯 時価総額が買収対象圏内")
        else:
            scores.append(0)
    else:
        scores.append(0)
    
    # Best 2 of 3
    sorted_scores = sorted(scores, reverse=True)
    total = sum(sorted_scores[:2])
    active_signals = [s for s, sc in zip(signals, scores) if sc > 0]
    
    return min(total, 35), active_signals, scores


def calculate_board_score_v2(data: Dict[str, Any]) -> Tuple[int, List[str], List[int]]:
    """
    板の違和感スコア v2（Best 2 of 3）
    最大35点
    """
    scores = []
    signals = []
    
    hist = data.get("hist")
    price = data.get("price", 0)
    
    if hist is None or hist.empty or price <= 0:
        return 0, [], [0, 0, 0]
    
    # 条件1: 20日高値/安値との位置関係（最大15点）
    high_20d = data.get("high_20d", price)
    low_20d = data.get("low_20d", price)
    
    if high_20d > low_20d:
        position = (price - low_20d) / (high_20d - low_20d)
        
        if position <= 0.2:
            scores.append(15)
            signals.append("📉 20日安値圏（底値買い狙い）")
        elif position >= 0.9:
            scores.append(12)
            signals.append("📈 20日高値ブレイク狙い")
        elif position <= 0.4:
            scores.append(8)
            signals.append("📉 安値圏で推移")
        else:
            scores.append(0)
    else:
        scores.append(0)
    
    # 条件2: ボリンジャーバンドの位置（最大12点）
    if len(hist) >= 20:
        close = hist['Close']
        sma20 = close.rolling(20).mean().iloc[-1]
        std20 = close.rolling(20).std().iloc[-1]
        
        if pd.notna(sma20) and pd.notna(std20) and std20 > 0:
            upper_band = sma20 + 2 * std20
            lower_band = sma20 - 2 * std20
            
            if price <= lower_band:
                scores.append(12)
                signals.append("📊 ボリンジャー下限（売られすぎ）")
            elif price >= upper_band:
                scores.append(10)
                signals.append("📊 ボリンジャー上限（勢いあり）")
            elif price <= sma20 - std20:
                scores.append(6)
                signals.append("📊 -1σ圏内")
            else:
                scores.append(0)
        else:
            scores.append(0)
    else:
        scores.append(0)
    
    # 条件3: 移動平均との乖離（最大10点）
    if len(hist) >= 5:
        sma5 = hist['Close'].rolling(5).mean().iloc[-1]
        if pd.notna(sma5) and sma5 > 0:
            deviation = (price - sma5) / sma5 * 100
            
            if deviation >= 5:
                scores.append(10)
                signals.append("📈 5日線を大きく上回る")
            elif deviation <= -5:
                scores.append(10)
                signals.append("📉 5日線を大きく下回る（反発狙い）")
            elif abs(deviation) >= 2:
                scores.append(5)
                signals.append("📊 5日線から乖離")
            else:
                scores.append(0)
        else:
            scores.append(0)
    else:
        scores.append(0)
    
    # Best 2 of 3
    sorted_scores = sorted(scores, reverse=True)
    total = sum(sorted_scores[:2])
    active_signals = [s for s, sc in zip(signals, scores) if sc > 0]
    
    return min(total, 35), active_signals, scores


def calculate_volume_critical_score_v2(data: Dict[str, Any]) -> Tuple[int, List[str], List[int]]:
    """
    出来高臨界点スコア v2（Best 2 of 3）
    最大30点
    """
    scores = []
    signals = []
    
    # 条件1: 出来高倍率（最大15点）- 条件緩和
    volume_ratio = data.get("volume_ratio", 1.0)
    
    if volume_ratio >= 3.0:
        scores.append(15)
        signals.append("🔥 出来高3倍超（着火）")
    elif volume_ratio >= 2.0:
        scores.append(12)
        signals.append("🚀 出来高2倍超（予兆）")
    elif volume_ratio >= 1.5:
        scores.append(8)
        signals.append("⚡ 出来高1.5倍超")
    elif volume_ratio >= 1.3:
        scores.append(4)
        signals.append("⚡ 出来高1.3倍超")
    else:
        scores.append(0)
    
    # 条件2: 浮動株回転率（最大12点）- 条件緩和
    turnover_pct = data.get("turnover_pct", 0)
    
    if turnover_pct >= 6.0:
        scores.append(12)
        signals.append("🌪️ 浮動株激動（6%超回転）")
    elif turnover_pct >= 3.0:
        scores.append(9)
        signals.append("🌪️ 浮動株活況（3%超回転）")
    elif turnover_pct >= 1.5:
        scores.append(5)
        signals.append("🌪️ 浮動株回転率上昇")
    else:
        scores.append(0)
    
    # 条件3: 売買代金の増加（最大10点）
    trading_value = data.get("trading_value", 0)
    avg_trading_value = data.get("avg_trading_value", 0)
    
    if avg_trading_value > 0:
        tv_ratio = trading_value / avg_trading_value
        if tv_ratio >= 2.5:
            scores.append(10)
            signals.append("💰 売買代金が平均の2.5倍超")
        elif tv_ratio >= 1.8:
            scores.append(7)
            signals.append("💰 売買代金が平均の1.8倍超")
        elif tv_ratio >= 1.3:
            scores.append(4)
            signals.append("💰 売買代金増加")
        else:
            scores.append(0)
    else:
        scores.append(0)
    
    # Best 2 of 3
    sorted_scores = sorted(scores, reverse=True)
    total = sum(sorted_scores[:2])
    active_signals = [s for s, sc in zip(signals, scores) if sc > 0]
    
    return min(total, 30), active_signals, scores


def calculate_bonus_score(data: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    ボーナススコア（レア条件）
    最大+15点
    """
    bonus = 0
    signals = []
    
    # ボーナス1: 出来高2.5倍以上
    volume_ratio = data.get("volume_ratio", 1.0)
    if volume_ratio >= 2.5:
        bonus += 5
        signals.append("🌟 出来高急増ボーナス")
    
    # ボーナス2: 回転率6%以上
    turnover_pct = data.get("turnover_pct", 0)
    if turnover_pct >= 6.0:
        bonus += 5
        signals.append("🌟 高回転率ボーナス")
    
    # ボーナス3: 時価総額500億以下の小型株
    market_cap = data.get("market_cap", 0)
    if market_cap > 0 and market_cap <= 5e10:
        market_cap_oku = market_cap / 1e8
        if volume_ratio >= 1.5:
            bonus += 5
            signals.append(f"🌟 小型株急動意ボーナス（{market_cap_oku:.0f}億円）")
    
    return min(bonus, 15), signals


def analyze_hagetaka_signal_v2(data: Dict[str, Any]) -> HagetakaSignal:
    """
    ハゲタカシグナルを総合分析 v2
    """
    code = data.get("code", "")
    name = data.get("name", "")
    
    # 3つの兆候を計算（Best 2 of 3）
    stealth_score, stealth_signals, _ = calculate_stealth_score_v2(data)
    board_score, board_signals, _ = calculate_board_score_v2(data)
    volume_score, volume_signals, _ = calculate_volume_critical_score_v2(data)
    
    # ボーナススコア
    bonus_score, bonus_signals = calculate_bonus_score(data)
    
    # 総合スコア
    base_score = stealth_score + board_score + volume_score
    total_score = min(base_score + bonus_score, 100)
    
    # 全シグナルを統合
    all_signals = stealth_signals + board_signals + volume_signals + bonus_signals
    
    # シグナルレベルは後で決定（上位N件制限のため）
    signal_level = SignalLevel.LOW
    if total_score >= LOCKON_SETTINGS["min_score"]:
        signal_level = SignalLevel.HIGH  # 暫定
    elif total_score >= LOCKON_SETTINGS["high_alert_score"]:
        signal_level = SignalLevel.HIGH
    elif total_score >= LOCKON_SETTINGS["medium_score"]:
        signal_level = SignalLevel.MEDIUM
    
    return HagetakaSignal(
        code=code,
        name=name,
        signal_level=signal_level,
        total_score=total_score,
        stealth_score=stealth_score,
        board_score=board_score,
        volume_score=volume_score,
        bonus_score=bonus_score,
        signals=all_signals,
        price=data.get("price", 0),
        change_pct=data.get("change_pct", 0),
        volume=data.get("volume", 0),
        avg_volume=data.get("avg_volume_20d", 0),
        volume_ratio=data.get("volume_ratio", 0),
        turnover_pct=data.get("turnover_pct", 0),
        market_cap=data.get("market_cap", 0),
        trading_value=data.get("trading_value", 0),
    )


# ==========================================
# 並列データ取得
# ==========================================
def fetch_stocks_parallel(codes: List[str], max_workers: int = 3) -> Dict[str, Dict]:
    """
    並列でデータ取得（API制限対策で並列数を抑制）
    """
    results = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {
            executor.submit(get_stock_data_cached, code): code 
            for code in codes
        }
        
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            try:
                data = future.result()
                if data:
                    results[code] = data
            except Exception:
                pass
    
    # API制限対策: バッチ間で少し待つ
    time.sleep(0.5)
    
    return results


# ==========================================
# メインスキャン関数
# ==========================================
def scan_all_stocks(
    codes: List[str], 
    progress_callback: Callable[[int, int, str], None] = None,
    use_gate: bool = True
) -> List[HagetakaSignal]:
    """
    全銘柄をスキャンしてハゲタカシグナルを検知
    
    Args:
        codes: スキャン対象の銘柄コードリスト
        progress_callback: 進捗コールバック関数
        use_gate: ゲート条件を使用するか
    
    Returns:
        検知されたシグナルのリスト（スコア順）
    """
    signals = []
    total = len(codes)
    
    # Phase 1: 並列でデータ取得（バッチサイズを小さく）
    if progress_callback:
        progress_callback(0, total, "データ取得中...")
    
    batch_size = 20  # 50→20に縮小
    all_data = {}
    failed_count = 0
    
    for i in range(0, total, batch_size):
        batch_codes = codes[i:i+batch_size]
        batch_data = fetch_stocks_parallel(batch_codes, max_workers=3)  # 10→3に縮小
        
        failed_count += len(batch_codes) - len(batch_data)
        all_data.update(batch_data)
        
        if progress_callback:
            progress_callback(
                min(i + batch_size, total), 
                total, 
                f"取得成功: {len(all_data)}件 / 失敗: {failed_count}件"
            )
        
        # API制限対策: バッチ間で待機
        time.sleep(0.3)
    
    # Phase 2: ゲート判定（高速フィルタリング）
    if use_gate:
        filtered_data = {code: data for code, data in all_data.items() if pass_gate(data)}
    else:
        filtered_data = all_data
    
    if progress_callback:
        progress_callback(total, total, f"ゲート通過: {len(filtered_data)}件 / 取得成功: {len(all_data)}件")
    
    # Phase 3: スコアリング
    for code, data in filtered_data.items():
        signal = analyze_hagetaka_signal_v2(data)
        signals.append(signal)
    
    # スコア順にソート
    signals.sort(key=lambda x: x.total_score, reverse=True)
    
    # Phase 4: ロックオン判定（上位N件制限）
    lockon_count = 0
    for signal in signals:
        if signal.total_score >= LOCKON_SETTINGS["min_score"] and lockon_count < LOCKON_SETTINGS["max_lockon_count"]:
            signal.signal_level = SignalLevel.LOCKON
            lockon_count += 1
        elif signal.total_score >= LOCKON_SETTINGS["high_alert_score"]:
            signal.signal_level = SignalLevel.HIGH
        elif signal.total_score >= LOCKON_SETTINGS["medium_score"]:
            signal.signal_level = SignalLevel.MEDIUM
        else:
            signal.signal_level = SignalLevel.LOW
    
    return signals


# ==========================================
# 銘柄リスト取得関数
# ==========================================
@st.cache_data(ttl=86400, show_spinner=False)  # 24時間キャッシュ
def fetch_jpx_stock_list() -> pd.DataFrame:
    """
    JPX（日本取引所）から全銘柄リストを取得
    """
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    
    try:
        df = pd.read_excel(url, dtype={'コード': str})
        df = df[['コード', '銘柄名', '市場・商品区分']].copy()
        df.columns = ['code', 'name', 'market']
        df['code'] = df['code'].astype(str).str.strip()
        return df
    except Exception as e:
        print(f"JPX銘柄リスト取得エラー: {e}")
        return pd.DataFrame()


def get_stocks_by_market(market: str) -> List[str]:
    """市場別に銘柄コードを取得"""
    df = fetch_jpx_stock_list()
    if df.empty:
        return get_fallback_stocks(market)
    
    market_map = {
        "prime": "プライム",
        "standard": "スタンダード",
        "growth": "グロース",
    }
    
    if market in market_map:
        filtered = df[df['market'].str.contains(market_map[market], na=False)]
        return filtered['code'].tolist()
    
    return df['code'].tolist()


def get_fallback_stocks(market: str = "all") -> List[str]:
    """フォールバック銘柄リスト"""
    prime = [
        "7203", "9984", "6758", "8306", "9432", "6861", "7267", "4502", "6501", "8058",
        "9433", "6902", "7751", "4063", "8316", "6098", "9022", "8411", "4568", "6981",
        "7974", "6367", "6594", "8035", "4519", "6273", "9983", "8031", "6954", "7741",
    ]
    growth = [
        "4385", "4436", "4478", "4477", "4071", "4485", "7095", "4168", "4054", "4484",
    ]
    standard = [
        "3092", "6532", "2413", "3064", "4307", "6035", "7148", "3688", "4384", "6184",
    ]
    
    if market == "prime":
        return prime
    elif market == "growth":
        return growth
    elif market == "standard":
        return standard
    return prime + growth + standard


def get_volume_ranking_stocks(top_n: int = 100) -> List[str]:
    """
    クイックスキャン用銘柄リスト（出来高上位を想定）
    """
    # 日経225 + 人気銘柄
    stocks = [
        "7203", "9984", "6758", "8306", "9432", "6861", "7267", "4502", "6501", "8058",
        "9433", "6902", "7751", "4063", "8316", "6098", "9022", "8411", "4568", "6981",
        "7974", "6367", "6594", "8035", "4519", "6273", "9983", "8031", "6954", "7741",
        "4661", "6503", "8766", "9020", "6702", "8801", "4503", "6971", "7269", "8802",
        "3382", "8267", "9101", "4452", "6301", "7733", "4901", "8591", "6326", "5401",
        "4385", "4436", "4478", "4477", "4071", "4485", "7095", "4168", "4054", "4484",
        "2914", "4911", "7011", "5713", "6753", "4543", "6762", "3407", "6479", "7832",
        "6506", "7731", "9613", "4704", "6723", "8604", "2801", "6857", "9735", "4901",
        "6988", "4523", "6770", "9107", "6645", "7272", "4578", "6471", "4689", "7012",
        "2502", "8053", "6841", "5802", "4507", "6952", "7261", "1925", "5020", "6504",
    ]
    return stocks[:top_n]


def get_all_japan_stocks() -> List[str]:
    """全銘柄コードを取得"""
    df = fetch_jpx_stock_list()
    if df.empty:
        return get_fallback_stocks("all")
    return df['code'].tolist()


def get_scan_targets(mode: ScanMode, custom_codes: List[str] = None) -> List[str]:
    """スキャンモードに応じた銘柄リストを取得"""
    if mode == ScanMode.QUICK:
        return get_volume_ranking_stocks(100)
    elif mode == ScanMode.PRIME:
        return get_stocks_by_market("prime")
    elif mode == ScanMode.STANDARD:
        return get_stocks_by_market("standard")
    elif mode == ScanMode.GROWTH:
        return get_stocks_by_market("growth")
    elif mode == ScanMode.ALL:
        return get_all_japan_stocks()
    elif mode == ScanMode.CUSTOM:
        return custom_codes or []
    return get_volume_ranking_stocks(100)


def get_lockons(signals: List[HagetakaSignal]) -> List[HagetakaSignal]:
    """ロックオン銘柄を抽出"""
    return [s for s in signals if s.signal_level == SignalLevel.LOCKON]


def get_watchlist_signals(signals: List[HagetakaSignal], min_score: int = 30) -> List[HagetakaSignal]:
    """監視リスト銘柄を抽出"""
    return [s for s in signals if s.total_score >= min_score]

# ==========================================
# 夜間バッチ連携（アプローチA）用 キャッシュ読み込み機能
# ==========================================
import json
import os

def load_daily_cache() -> Dict[str, Any]:
    """夜間バッチで作成された全銘柄データを読み込む（負荷ゼロ処理）"""
    cache_path = "data/daily_ma_cache.json"
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                return cache.get("data", {})
        except Exception as e:
            print(f"キャッシュ読み込みエラー: {e}")
    return {}

def get_cached_or_fetch(codes: List[str]) -> Dict[str, Any]:
    """
    全銘柄スキャン時はキャッシュを返し、個別検索時はリアルタイム取得するハイブリッド関数。
    """
    # 銘柄数が1000以上の場合は全銘柄スキャンと判定し、夜間キャッシュを返す
    if len(codes) > 1000:
        cached_data = load_daily_cache()
        if cached_data:
            # 要求されたコードのデータのみを抽出して返す
            return {code: cached_data[code] for code in codes if code in cached_data}
            
    # 個別検索やクイックスキャン（少数）の場合は、これまで通りリアルタイム取得
    import fair_value_calc_y4 as fv
    return fv.calc_genta_bundle(codes)
