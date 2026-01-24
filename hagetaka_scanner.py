"""
ハゲタカスコープ - 全銘柄スキャン＆検知エンジン
約3,800銘柄から「ハゲタカの足跡」を自動検知する
"""

from __future__ import annotations
import time
import random
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np
import requests


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
        description="出来高急増銘柄を優先スキャン",
        estimated_count=300,
        estimated_time="約3〜5分",
        warning=None
    ),
    ScanMode.PRIME: ScanOption(
        mode=ScanMode.PRIME,
        label="🏢 プライム市場",
        description="東証プライム上場銘柄",
        estimated_count=1800,
        estimated_time="約15〜20分",
        warning="時間がかかります"
    ),
    ScanMode.STANDARD: ScanOption(
        mode=ScanMode.STANDARD,
        label="🏬 スタンダード市場",
        description="東証スタンダード上場銘柄",
        estimated_count=1400,
        estimated_time="約12〜15分",
        warning="時間がかかります"
    ),
    ScanMode.GROWTH: ScanOption(
        mode=ScanMode.GROWTH,
        label="🌱 グロース市場",
        description="東証グロース上場銘柄",
        estimated_count=500,
        estimated_time="約5〜8分",
        warning=None
    ),
    ScanMode.ALL: ScanOption(
        mode=ScanMode.ALL,
        label="🌐 全銘柄スキャン",
        description="日本株全銘柄（約3,800社）",
        estimated_count=3800,
        estimated_time="約45分〜1時間",
        warning="⚠️ 非常に時間がかかります。自動監視（GitHub Actions）での実行を推奨します。"
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


def fetch_jpx_stock_list() -> pd.DataFrame:
    """
    JPX（日本取引所）から全銘柄リストを取得
    """
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    
    try:
        df = pd.read_excel(url, dtype={'コード': str})
        # 必要なカラムのみ抽出
        df = df[['コード', '銘柄名', '市場・商品区分']].copy()
        df.columns = ['code', 'name', 'market']
        df['code'] = df['code'].astype(str).str.strip()
        return df
    except Exception as e:
        print(f"JPX銘柄リスト取得エラー: {e}")
        return pd.DataFrame()


def get_stocks_by_market(market: str) -> List[str]:
    """
    市場別に銘柄コードを取得
    """
    df = fetch_jpx_stock_list()
    if df.empty:
        return get_fallback_stocks(market)
    
    if market == "prime":
        filtered = df[df['market'].str.contains('プライム', na=False)]
    elif market == "standard":
        filtered = df[df['market'].str.contains('スタンダード', na=False)]
    elif market == "growth":
        filtered = df[df['market'].str.contains('グロース', na=False)]
    else:
        filtered = df
    
    return filtered['code'].tolist()


def get_fallback_stocks(market: str = "all") -> List[str]:
    """
    JPX取得失敗時のフォールバック銘柄リスト
    """
    # 主要銘柄のハードコードリスト（フォールバック用）
    prime_stocks = [
        "7203", "9984", "6758", "8306", "9432", "6861", "7267", "4502", "6501", "8058",
        "9433", "6902", "7751", "4063", "8316", "6098", "9022", "8411", "4568", "6981",
        "7974", "6367", "6594", "8035", "4519", "6273", "9983", "8031", "6954", "7741",
        "4661", "6503", "8766", "9020", "6702", "8801", "4503", "6971", "7269", "8802",
        "3382", "8267", "9101", "4452", "6301", "7733", "4901", "8591", "6326", "5401",
    ]
    
    growth_stocks = [
        "4385", "4436", "6095", "7342", "4480", "6560", "3697", "4478", "4449", "7342",
        "4477", "4071", "4485", "7095", "4053", "4168", "4054", "4484", "4491", "4446",
    ]
    
    standard_stocks = [
        "3092", "6532", "2413", "3064", "4307", "6035", "7148", "3688", "4384", "6184",
        "7071", "9434", "1332", "1333", "1605", "1721", "1801", "1802", "1803", "1808",
    ]
    
    if market == "prime":
        return prime_stocks
    elif market == "growth":
        return growth_stocks
    elif market == "standard":
        return standard_stocks
    else:
        return prime_stocks + growth_stocks + standard_stocks


def get_volume_ranking_stocks(top_n: int = 300) -> List[str]:
    """
    出来高ランキング上位銘柄を取得（クイックスキャン用）
    Yahoo Finance Japanから取得を試み、失敗時はフォールバック
    """
    try:
        # 複数のソースから出来高上位銘柄を取得
        # 方法1: 主要指数構成銘柄 + 最近の出来高上位
        
        # 日経225構成銘柄（出来高が多い傾向）
        nikkei225 = [
            "1332", "1333", "1605", "1721", "1801", "1802", "1803", "1808", "1812", "1925",
            "1928", "1963", "2002", "2269", "2282", "2413", "2432", "2501", "2502", "2503",
            "2531", "2768", "2801", "2802", "2871", "2914", "3086", "3099", "3101", "3103",
            "3105", "3107", "3289", "3382", "3401", "3402", "3405", "3407", "3436", "3861",
            "3863", "4004", "4005", "4021", "4042", "4043", "4061", "4063", "4151", "4183",
            "4188", "4208", "4272", "4324", "4452", "4502", "4503", "4506", "4507", "4519",
            "4523", "4543", "4568", "4578", "4661", "4689", "4704", "4751", "4755", "4901",
            "4902", "4911", "5019", "5020", "5101", "5108", "5201", "5202", "5214", "5232",
            "5233", "5301", "5332", "5333", "5401", "5406", "5411", "5413", "5541", "5631",
            "5703", "5706", "5707", "5711", "5713", "5714", "5801", "5802", "5803", "5901",
            "6098", "6103", "6113", "6141", "6178", "6273", "6301", "6302", "6305", "6326",
            "6361", "6367", "6471", "6472", "6473", "6479", "6501", "6503", "6504", "6506",
            "6645", "6674", "6701", "6702", "6703", "6724", "6752", "6753", "6758", "6762",
            "6770", "6841", "6857", "6861", "6902", "6952", "6954", "6971", "6976", "6981",
            "7003", "7004", "7011", "7012", "7013", "7186", "7201", "7202", "7203", "7205",
            "7211", "7261", "7267", "7269", "7270", "7272", "7731", "7733", "7741", "7751",
            "7752", "7762", "7832", "7911", "7912", "7951", "7974", "8001", "8002", "8015",
            "8028", "8031", "8035", "8053", "8058", "8233", "8252", "8253", "8267", "8303",
            "8304", "8306", "8308", "8309", "8316", "8331", "8354", "8355", "8411", "8601",
            "8604", "8628", "8630", "8697", "8725", "8750", "8766", "8795", "8801", "8802",
            "8804", "8830", "9001", "9005", "9007", "9008", "9009", "9020", "9021", "9022",
            "9062", "9064", "9101", "9104", "9107", "9201", "9202", "9301", "9412", "9432",
            "9433", "9434", "9501", "9502", "9503", "9531", "9532", "9602", "9613", "9735",
            "9766", "9983", "9984",
        ]
        
        # TOPIX Core30 + 出来高が多い人気銘柄を追加
        popular_stocks = [
            "6758", "7203", "9984", "8306", "9432", "6861", "7267", "4502", "8058", "9433",
            "6501", "7751", "4063", "8316", "7974", "6367", "8035", "9983", "6902", "4519",
            "6954", "7741", "6273", "8031", "4661", "6503", "8766", "9020", "6702", "8801",
            "3382", "8267", "9101", "4452", "6301", "7733", "4901", "8591", "5401", "6326",
        ]
        
        # グロース市場の人気銘柄（ボラティリティが高い）
        growth_popular = [
            "4385", "4436", "4478", "4477", "4071", "4485", "7095", "4168", "4054", "4484",
            "4491", "4446", "4053", "4449", "6095", "7342", "4480", "6560", "3697", "4481",
        ]
        
        # 統合して重複除去
        all_candidates = list(dict.fromkeys(nikkei225 + popular_stocks + growth_popular))
        
        return all_candidates[:top_n]
        
    except Exception as e:
        print(f"出来高ランキング取得エラー: {e}")
        return get_fallback_stocks("all")[:top_n]


def get_all_japan_stocks() -> List[str]:
    """
    日本の全上場銘柄コードを取得
    """
    df = fetch_jpx_stock_list()
    if df.empty:
        return get_fallback_stocks("all")
    return df['code'].tolist()


def get_scan_targets(mode: ScanMode, custom_codes: List[str] = None) -> List[str]:
    """
    スキャンモードに応じた銘柄リストを取得
    """
    if mode == ScanMode.QUICK:
        return get_volume_ranking_stocks(300)
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
    else:
        return get_volume_ranking_stocks(300)


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
