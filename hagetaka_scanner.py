"""
ハゲタカスコープ - 全銘柄スキャン＆検知エンジン
約3,800銘柄から「ハゲタカの足跡」を自動検知する
"""

from __future__ import annotations
import time
import random
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np


class SignalLevel(Enum):
    """シグナルレベル"""
    LOCKON = "🔴 ロックオン"      # 最高レベル - 即通知
    HIGH = "🟠 高警戒"            # 要注目
    MEDIUM = "🟡 監視中"          # 継続監視
    LOW = "🟢 平常"               # 特に異常なし


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
    
    # M&Aスコア（既存機能との連携用）
    ma_score: int = 0
    
    # 検知日時
    detected_at: datetime = field(default_factory=datetime.now)


def get_all_japan_stocks() -> List[str]:
    """
    日本の全上場銘柄コードを取得
    ※実際の運用では外部APIやCSVから取得
    """
    # 東証プライム・スタンダード・グロースの主要銘柄
    # 実運用では全銘柄リストをCSVなどから読み込む
    
    # サンプルとして代表的な銘柄を返す
    # 実際には約3,800銘柄
    sample_codes = [
        # プライム市場（大型）
        "7203", "9984", "6758", "8306", "9432", "6861", "7267", "4502", "6501", "8058",
        "9433", "6902", "7751", "4063", "8316", "6098", "9022", "8411", "4568", "6981",
        # スタンダード・グロース（中小型）
        "3092", "4385", "6095", "7342", "4436", "6532", "3697", "4480", "6560", "7342",
        "2413", "3064", "4307", "6035", "7148", "3688", "4384", "6184", "7071", "9434",
        # その他
        "1332", "1333", "1605", "1721", "1801", "1802", "1803", "1808", "1812", "1820",
        "1878", "1925", "1928", "1963", "2002", "2127", "2175", "2181", "2269", "2282",
        "2501", "2502", "2503", "2531", "2593", "2651", "2670", "2702", "2768", "2801",
        "2802", "2871", "2875", "2897", "2914", "3001", "3038", "3048", "3086", "3088",
        "3099", "3105", "3107", "3116", "3141", "3197", "3231", "3254", "3288", "3289",
        "3349", "3382", "3391", "3405", "3407", "3436", "3543", "3626", "3632", "3635",
    ]
    
    return sample_codes


def get_stock_data(code: str) -> Optional[Dict[str, Any]]:
    """
    銘柄データを取得
    """
    try:
        ticker = yf.Ticker(f"{code}.T")
        
        # 株価履歴（6ヶ月）
        hist = ticker.history(period="6mo")
        if hist.empty:
            return None
        
        # 基本情報
        info = ticker.info
        
        # 最新データ
        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else latest
        
        # 出来高データ
        current_volume = int(latest['Volume'])
        avg_volume_20d = int(hist['Volume'].tail(20).mean()) if len(hist) >= 20 else current_volume
        avg_volume_5d = int(hist['Volume'].tail(5).mean()) if len(hist) >= 5 else current_volume
        
        # 出来高倍率
        volume_ratio = current_volume / avg_volume_20d if avg_volume_20d > 0 else 1.0
        
        # 浮動株回転率（推定）
        shares_outstanding = info.get('sharesOutstanding', 0)
        float_shares = shares_outstanding * 0.3  # 浮動株比率30%と仮定
        turnover_pct = (current_volume / float_shares * 100) if float_shares > 0 else 0
        
        # 5日間の出来高トレンド
        if len(hist) >= 10:
            vol_5d_recent = hist['Volume'].tail(5).mean()
            vol_5d_prev = hist['Volume'].tail(10).head(5).mean()
            volume_trend = vol_5d_recent / vol_5d_prev if vol_5d_prev > 0 else 1.0
        else:
            volume_trend = 1.0
        
        # 価格帯別出来高（板の違和感検知用）
        price_levels = pd.cut(hist['Close'], bins=20)
        volume_by_price = hist.groupby(price_levels, observed=False)['Volume'].sum()
        
        return {
            "code": code,
            "name": info.get('shortName', info.get('longName', code)),
            "price": float(latest['Close']),
            "prev_close": float(prev['Close']),
            "change_pct": ((latest['Close'] - prev['Close']) / prev['Close'] * 100) if prev['Close'] > 0 else 0,
            "volume": current_volume,
            "avg_volume_20d": avg_volume_20d,
            "avg_volume_5d": avg_volume_5d,
            "volume_ratio": volume_ratio,
            "volume_trend": volume_trend,  # 5日間の出来高トレンド
            "turnover_pct": turnover_pct,
            "market_cap": info.get('marketCap', 0),
            "float_shares": float_shares,
            "hist": hist,
            "volume_by_price": volume_by_price,
            "high_52w": info.get('fiftyTwoWeekHigh', 0),
            "low_52w": info.get('fiftyTwoWeekLow', 0),
        }
        
    except Exception as e:
        print(f"Error getting data for {code}: {e}")
        return None


def calculate_stealth_score(data: Dict[str, Any]) -> tuple[int, List[str]]:
    """
    ステルス集積スコアを計算（最大35点）
    - 出来高が徐々に増加している
    - 大きな値動きなく株が集められている
    """
    score = 0
    signals = []
    
    # 1. 出来高トレンド（最大15点）
    volume_trend = data.get("volume_trend", 1.0)
    if volume_trend >= 2.0:
        score += 15
        signals.append("📈 出来高が5日前比2倍以上に増加")
    elif volume_trend >= 1.5:
        score += 10
        signals.append("📈 出来高が5日前比1.5倍に増加")
    elif volume_trend >= 1.2:
        score += 5
        signals.append("📈 出来高が緩やかに増加傾向")
    
    # 2. 価格変動が小さいのに出来高増加（最大10点）
    change_pct = abs(data.get("change_pct", 0))
    volume_ratio = data.get("volume_ratio", 1.0)
    
    if change_pct < 2.0 and volume_ratio >= 2.0:
        score += 10
        signals.append("🥷 値動き小×出来高増＝ステルス集積の可能性")
    elif change_pct < 3.0 and volume_ratio >= 1.5:
        score += 5
        signals.append("🥷 目立たない買い集めの兆候")
    
    # 3. 時価総額が買収適正サイズ（最大10点）
    market_cap = data.get("market_cap", 0)
    if market_cap > 0:
        market_cap_oku = market_cap / 1e8  # 億円換算
        if 300 <= market_cap_oku <= 3000:
            score += 10
            signals.append("🎯 時価総額がハゲタカ好適サイズ")
        elif 100 <= market_cap_oku < 300 or 3000 < market_cap_oku <= 5000:
            score += 5
            signals.append("🎯 時価総額が買収対象圏内")
    
    return min(score, 35), signals


def calculate_board_score(data: Dict[str, Any]) -> tuple[int, List[str]]:
    """
    板の違和感スコアを計算（最大35点）
    - 価格帯別出来高の偏り
    - 需給の壁の存在
    """
    score = 0
    signals = []
    
    hist = data.get("hist")
    if hist is None or hist.empty:
        return 0, []
    
    price = data.get("price", 0)
    if price <= 0:
        return 0, []
    
    # 1. 現在値付近に出来高の壁があるか（最大15点）
    volume_by_price = data.get("volume_by_price")
    if volume_by_price is not None and not volume_by_price.empty:
        # 最大出来高の価格帯を特定
        max_vol_idx = volume_by_price.idxmax()
        if max_vol_idx is not None:
            try:
                wall_price = max_vol_idx.mid
                price_diff_pct = abs(price - wall_price) / price * 100
                
                if price_diff_pct < 5:
                    score += 15
                    signals.append("🧱 需給の壁で激戦中（ブレイク間近）")
                elif price_diff_pct < 10:
                    score += 10
                    signals.append("🧱 需給の壁が近い（要注目）")
            except:
                pass
    
    # 2. 52週高値・安値との位置関係（最大10点）
    high_52w = data.get("high_52w", 0)
    low_52w = data.get("low_52w", 0)
    
    if high_52w > 0 and low_52w > 0:
        range_52w = high_52w - low_52w
        if range_52w > 0:
            position = (price - low_52w) / range_52w
            
            if position <= 0.3:
                score += 10
                signals.append("📉 52週安値圏（底値買い狙い）")
            elif position >= 0.9:
                score += 5
                signals.append("📈 52週高値圏（ブレイク狙い）")
    
    # 3. ボリンジャーバンドの位置（最大10点）
    if len(hist) >= 20:
        close = hist['Close']
        sma20 = close.rolling(20).mean().iloc[-1]
        std20 = close.rolling(20).std().iloc[-1]
        
        upper_band = sma20 + 2 * std20
        lower_band = sma20 - 2 * std20
        
        if price <= lower_band:
            score += 10
            signals.append("📊 ボリンジャー下限（売られすぎ）")
        elif price >= upper_band:
            score += 5
            signals.append("📊 ボリンジャー上限（勢いあり）")
    
    return min(score, 35), signals


def calculate_volume_critical_score(data: Dict[str, Any]) -> tuple[int, List[str]]:
    """
    出来高臨界点スコアを計算（最大30点）
    - 出来高の急増
    - 浮動株回転率の異常
    """
    score = 0
    signals = []
    
    # 1. 出来高倍率（最大15点）
    volume_ratio = data.get("volume_ratio", 1.0)
    
    if volume_ratio >= 5.0:
        score += 15
        signals.append("🔥 出来高5倍超（緊急事態）")
    elif volume_ratio >= 3.0:
        score += 12
        signals.append("🚀 出来高3倍超（着火）")
    elif volume_ratio >= 2.0:
        score += 8
        signals.append("⚡ 出来高2倍超（予兆）")
    elif volume_ratio >= 1.5:
        score += 4
        signals.append("⚡ 出来高1.5倍超")
    
    # 2. 浮動株回転率（最大15点）
    turnover_pct = data.get("turnover_pct", 0)
    
    if turnover_pct >= 10.0:
        score += 15
        signals.append("🌪️ 浮動株激動（10%超回転）")
    elif turnover_pct >= 5.0:
        score += 10
        signals.append("🌪️ 浮動株活況（5%超回転）")
    elif turnover_pct >= 2.0:
        score += 5
        signals.append("🌪️ 浮動株回転率上昇")
    
    return min(score, 30), signals


def analyze_hagetaka_signal(data: Dict[str, Any]) -> HagetakaSignal:
    """
    ハゲタカシグナルを総合分析
    """
    code = data.get("code", "")
    name = data.get("name", "")
    
    # 3つの兆候を計算
    stealth_score, stealth_signals = calculate_stealth_score(data)
    board_score, board_signals = calculate_board_score(data)
    volume_score, volume_signals = calculate_volume_critical_score(data)
    
    # 総合スコア
    total_score = stealth_score + board_score + volume_score
    
    # シグナルレベル判定
    if total_score >= 70:
        signal_level = SignalLevel.LOCKON
    elif total_score >= 50:
        signal_level = SignalLevel.HIGH
    elif total_score >= 30:
        signal_level = SignalLevel.MEDIUM
    else:
        signal_level = SignalLevel.LOW
    
    # 全シグナルを統合
    all_signals = stealth_signals + board_signals + volume_signals
    
    return HagetakaSignal(
        code=code,
        name=name,
        signal_level=signal_level,
        total_score=total_score,
        stealth_score=stealth_score,
        board_score=board_score,
        volume_score=volume_score,
        signals=all_signals,
        price=data.get("price", 0),
        change_pct=data.get("change_pct", 0),
        volume=data.get("volume", 0),
        avg_volume=data.get("avg_volume_20d", 0),
        volume_ratio=data.get("volume_ratio", 0),
        turnover_pct=data.get("turnover_pct", 0),
        market_cap=data.get("market_cap", 0),
    )


def scan_all_stocks(codes: List[str] = None, progress_callback=None) -> List[HagetakaSignal]:
    """
    全銘柄をスキャンしてハゲタカシグナルを検知
    
    Args:
        codes: スキャン対象の銘柄コードリスト（Noneの場合は全銘柄）
        progress_callback: 進捗コールバック関数
    
    Returns:
        検知されたシグナルのリスト（スコア順）
    """
    if codes is None:
        codes = get_all_japan_stocks()
    
    signals = []
    total = len(codes)
    
    for i, code in enumerate(codes):
        if progress_callback:
            progress_callback(i + 1, total, code)
        
        # データ取得
        data = get_stock_data(code)
        if data is None:
            continue
        
        # シグナル分析
        signal = analyze_hagetaka_signal(data)
        signals.append(signal)
        
        # API制限対策
        time.sleep(random.uniform(0.3, 0.8))
    
    # スコア順にソート
    signals.sort(key=lambda x: x.total_score, reverse=True)
    
    return signals


def get_lockons(signals: List[HagetakaSignal], min_score: int = 50) -> List[HagetakaSignal]:
    """
    ロックオン銘柄（高スコア銘柄）を抽出
    """
    return [s for s in signals if s.total_score >= min_score]


def get_watchlist_signals(signals: List[HagetakaSignal], min_score: int = 30) -> List[HagetakaSignal]:
    """
    監視リスト銘柄（中スコア以上）を抽出
    """
    return [s for s in signals if s.total_score >= min_score]
