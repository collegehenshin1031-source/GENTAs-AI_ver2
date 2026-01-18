"""
M&A予兆検知エンジン
- ニューススクレイピング
- キーワード検知
- M&Aスコア算出
"""
from __future__ import annotations
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re
import time
import random
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pandas as pd

# ==========================================
# 設定
# ==========================================
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# M&A関連キーワード（重要度順）
MA_KEYWORDS = {
    # 最重要（直接的なM&Aシグナル）
    "critical": [
        "完全子会社化", "TOB", "株式公開買付", "MBO", "株式交換",
        "吸収合併", "経営統合", "買収", "子会社化", "親会社",
        "株式移転", "スクイーズアウト", "少数株主", "上場廃止"
    ],
    # 重要（間接的なシグナル）
    "high": [
        "資本提携", "業務提携", "第三者割当", "大株主", "筆頭株主",
        "株式取得", "持株比率", "支配権", "経営権", "事業譲渡",
        "再編", "リストラ", "構造改革", "内製化", "グループ再編"
    ],
    # 参考（注意すべきシグナル）
    "medium": [
        "シナジー", "相乗効果", "事業統合", "効率化", "コスト削減",
        "収益改善", "黒字化", "増配", "自社株買い", "株主還元",
        "アクティビスト", "物言う株主", "株主提案", "敵対的"
    ]
}

# 除外キーワード（M&A阻害要因）
EXCLUSION_KEYWORDS = [
    "自社株買い発表", "大規模自社株買い", "買収防衛策", "ポイズンピル"
]


class MASignalLevel(Enum):
    """M&Aシグナルレベル"""
    CRITICAL = "🔴 緊急"
    HIGH = "🟠 高"
    MEDIUM = "🟡 中"
    LOW = "🟢 低"
    NONE = "⚪ なし"


@dataclass
class NewsItem:
    """ニュースアイテム"""
    title: str
    url: str
    source: str
    date: Optional[datetime] = None
    snippet: str = ""
    matched_keywords: List[str] = field(default_factory=list)
    signal_level: MASignalLevel = MASignalLevel.NONE


@dataclass
class MAScore:
    """M&A予兆スコア"""
    code: str
    name: str
    total_score: int  # 0-100
    signal_level: MASignalLevel
    news_score: int  # ニュース分析スコア（0-40）
    volume_score: int  # 出来高異常スコア（0-30）
    valuation_score: int  # バリュエーションスコア（0-20）
    technical_score: int  # テクニカルスコア（0-10）
    news_items: List[NewsItem] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    exclusion_flags: List[str] = field(default_factory=list)
    reason_tags: List[str] = field(default_factory=list)


def get_sleep_time() -> float:
    """ランダムなスリープ時間を返す"""
    return random.uniform(1.0, 2.5)


def scrape_yahoo_news(query: str, max_results: int = 10) -> List[NewsItem]:
    """
    Yahoo!ニュースから関連ニュースをスクレイピング
    """
    news_items = []
    
    try:
        # Yahoo!ニュース検索
        search_url = f"https://news.yahoo.co.jp/search?p={requests.utils.quote(query)}&ei=UTF-8"
        
        time.sleep(get_sleep_time())
        response = requests.get(search_url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            return news_items
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ニュース記事を抽出
        articles = soup.select('div.newsFeed_item, article.newsFeed_item, div[class*="NewsItem"]')
        
        if not articles:
            # 別のセレクタを試す
            articles = soup.select('a[href*="/articles/"]')
        
        for article in articles[:max_results]:
            try:
                # タイトル取得
                title_elem = article.select_one('h2, h3, span[class*="title"], div[class*="title"]')
                if not title_elem:
                    title_elem = article
                title = title_elem.get_text(strip=True)
                
                if not title or len(title) < 5:
                    continue
                
                # URL取得
                link = article.select_one('a[href*="/articles/"]')
                if link:
                    url = link.get('href', '')
                    if not url.startswith('http'):
                        url = f"https://news.yahoo.co.jp{url}"
                else:
                    url = ""
                
                # キーワードマッチング
                matched = []
                signal = MASignalLevel.NONE
                
                for kw in MA_KEYWORDS["critical"]:
                    if kw in title:
                        matched.append(kw)
                        signal = MASignalLevel.CRITICAL
                
                if signal == MASignalLevel.NONE:
                    for kw in MA_KEYWORDS["high"]:
                        if kw in title:
                            matched.append(kw)
                            signal = MASignalLevel.HIGH
                
                if signal == MASignalLevel.NONE:
                    for kw in MA_KEYWORDS["medium"]:
                        if kw in title:
                            matched.append(kw)
                            signal = MASignalLevel.MEDIUM
                
                news_items.append(NewsItem(
                    title=title,
                    url=url,
                    source="Yahoo!ニュース",
                    matched_keywords=matched,
                    signal_level=signal
                ))
                
            except Exception:
                continue
                
    except Exception as e:
        print(f"News scraping error: {e}")
    
    return news_items


def scrape_google_news(query: str, max_results: int = 5) -> List[NewsItem]:
    """
    Google News（日本語）から関連ニュースを取得
    ※レート制限に注意
    """
    news_items = []
    
    try:
        search_url = f"https://news.google.com/search?q={requests.utils.quote(query)}&hl=ja&gl=JP&ceid=JP:ja"
        
        time.sleep(get_sleep_time())
        response = requests.get(search_url, headers=HEADERS, timeout=10)
        
        if response.status_code != 200:
            return news_items
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Google Newsの記事を抽出
        articles = soup.select('article')
        
        for article in articles[:max_results]:
            try:
                title_elem = article.select_one('h3, h4, a[href*="./articles/"]')
                if not title_elem:
                    continue
                    
                title = title_elem.get_text(strip=True)
                if not title or len(title) < 5:
                    continue
                
                # キーワードマッチング
                matched = []
                signal = MASignalLevel.NONE
                
                for kw in MA_KEYWORDS["critical"]:
                    if kw in title:
                        matched.append(kw)
                        signal = MASignalLevel.CRITICAL
                
                if signal == MASignalLevel.NONE:
                    for kw in MA_KEYWORDS["high"]:
                        if kw in title:
                            matched.append(kw)
                            signal = MASignalLevel.HIGH
                
                news_items.append(NewsItem(
                    title=title,
                    url="",
                    source="Google News",
                    matched_keywords=matched,
                    signal_level=signal
                ))
                
            except Exception:
                continue
                
    except Exception:
        pass
    
    return news_items


def analyze_news_for_ma(company_name: str, code: str) -> Tuple[int, List[NewsItem], List[str]]:
    """
    企業のニュースを分析してM&Aスコアを算出
    
    Returns:
        (score, news_items, matched_keywords)
    """
    all_news = []
    all_keywords = set()
    
    # 検索クエリを複数パターンで実行
    queries = [
        f"{company_name} M&A",
        f"{company_name} TOB",
        f"{company_name} 完全子会社化",
        f"{code} 株式",
    ]
    
    for query in queries:
        news = scrape_yahoo_news(query, max_results=5)
        for item in news:
            # 重複チェック
            if not any(n.title == item.title for n in all_news):
                all_news.append(item)
                all_keywords.update(item.matched_keywords)
    
    # スコア算出（最大40点）
    score = 0
    
    # クリティカルキーワードがあれば大幅加点
    critical_count = sum(1 for n in all_news if n.signal_level == MASignalLevel.CRITICAL)
    high_count = sum(1 for n in all_news if n.signal_level == MASignalLevel.HIGH)
    medium_count = sum(1 for n in all_news if n.signal_level == MASignalLevel.MEDIUM)
    
    score += min(25, critical_count * 10)  # 最大25点
    score += min(10, high_count * 3)  # 最大10点
    score += min(5, medium_count * 1)  # 最大5点
    
    return min(40, score), all_news, list(all_keywords)


def calculate_volume_score(
    volume_ratio: Optional[float],
    turnover_pct: Optional[float],
    turnover_5d_pct: Optional[float]
) -> int:
    """
    出来高関連スコアを算出（最大30点）
    """
    score = 0
    
    # 出来高倍率（対20日平均）
    if volume_ratio:
        if volume_ratio >= 5.0:
            score += 15  # 異常な急増
        elif volume_ratio >= 3.0:
            score += 10
        elif volume_ratio >= 2.0:
            score += 5
    
    # 当日回転率
    if turnover_pct:
        if turnover_pct >= 10.0:
            score += 10  # 浮動株の10%以上が回転
        elif turnover_pct >= 5.0:
            score += 7
        elif turnover_pct >= 3.0:
            score += 3
    
    # 5日累積回転率
    if turnover_5d_pct:
        if turnover_5d_pct >= 30.0:
            score += 5  # 1週間で浮動株の3割入替
        elif turnover_5d_pct >= 15.0:
            score += 3
    
    return min(30, score)


def calculate_valuation_score(
    pbr: Optional[float],
    upside_pct: Optional[float],
    market_cap: Optional[float]
) -> int:
    """
    バリュエーションスコアを算出（最大20点）
    M&Aターゲットになりやすい条件を評価
    """
    score = 0
    
    # PBR（低いほど買収メリット大）
    if pbr is not None:
        if pbr < 0.5:
            score += 8  # 超割安
        elif pbr < 0.8:
            score += 6
        elif pbr < 1.0:
            score += 4
    
    # 時価総額（中小型が狙われやすい）
    if market_cap:
        mc_oku = market_cap / 100000000  # 億円換算
        if 300 <= mc_oku <= 2000:
            score += 6  # TOBしやすいサイズ
        elif 2000 < mc_oku <= 5000:
            score += 3
    
    # 理論株価との乖離（割安度）
    if upside_pct:
        if upside_pct >= 50:
            score += 6  # 大幅割安
        elif upside_pct >= 30:
            score += 4
        elif upside_pct >= 15:
            score += 2
    
    return min(20, score)


def calculate_technical_score(signal_icon: str) -> int:
    """
    テクニカルスコアを算出（最大10点）
    """
    score_map = {
        "↑◎": 10,  # 激熱
        "↗〇": 7,   # 買い
        "→△": 3,   # 様子見
        "↘▲": 1,   # 売り
        "↓✖": 0,   # 危険
    }
    return score_map.get(signal_icon, 0)


def check_exclusion_factors(news_items: List[NewsItem]) -> Tuple[int, List[str]]:
    """
    M&A阻害要因をチェック
    Returns:
        (減点スコア, 検出されたフラグ)
    """
    penalty = 0
    flags = []
    
    for news in news_items:
        for kw in EXCLUSION_KEYWORDS:
            if kw in news.title:
                flags.append(kw)
                penalty += 15  # 大幅減点
    
    return penalty, list(set(flags))


def generate_reason_tags(
    news_score: int,
    volume_score: int,
    valuation_score: int,
    matched_keywords: List[str]
) -> List[str]:
    """
    スコアの理由タグを生成
    """
    tags = []
    
    if news_score >= 20:
        tags.append("📰 M&Aニュース検知")
    if volume_score >= 15:
        tags.append("📈 出来高急増")
    if valuation_score >= 12:
        tags.append("💰 割安×買収適正サイズ")
    
    # キーワードベースのタグ
    if any(kw in matched_keywords for kw in ["完全子会社化", "TOB", "株式公開買付"]):
        tags.append("🎯 直接シグナル")
    if any(kw in matched_keywords for kw in ["親会社", "グループ再編", "内製化"]):
        tags.append("🏢 親子関係")
    if any(kw in matched_keywords for kw in ["アクティビスト", "物言う株主"]):
        tags.append("🦅 アクティビスト")
    
    return tags


def get_signal_level(total_score: int) -> MASignalLevel:
    """
    総合スコアからシグナルレベルを判定
    """
    if total_score >= 70:
        return MASignalLevel.CRITICAL
    elif total_score >= 50:
        return MASignalLevel.HIGH
    elif total_score >= 30:
        return MASignalLevel.MEDIUM
    elif total_score >= 15:
        return MASignalLevel.LOW
    else:
        return MASignalLevel.NONE


def analyze_ma_potential(
    code: str,
    name: str,
    price: Optional[float],
    pbr: Optional[float],
    upside_pct: Optional[float],
    market_cap: Optional[float],
    volume_ratio: Optional[float],
    turnover_pct: Optional[float],
    turnover_5d_pct: Optional[float],
    signal_icon: str,
    skip_news: bool = False
) -> MAScore:
    """
    M&A予兆を総合分析
    
    Args:
        skip_news: ニューススクレイピングをスキップするか（高速化用）
    """
    # 1. ニュース分析（最大40点）
    if skip_news:
        news_score = 0
        news_items = []
        matched_keywords = []
    else:
        news_score, news_items, matched_keywords = analyze_news_for_ma(name, code)
    
    # 2. 出来高スコア（最大30点）
    volume_score = calculate_volume_score(volume_ratio, turnover_pct, turnover_5d_pct)
    
    # 3. バリュエーションスコア（最大20点）
    valuation_score = calculate_valuation_score(pbr, upside_pct, market_cap)
    
    # 4. テクニカルスコア（最大10点）
    technical_score = calculate_technical_score(signal_icon)
    
    # 5. 除外要因チェック
    penalty, exclusion_flags = check_exclusion_factors(news_items)
    
    # 総合スコア計算
    raw_score = news_score + volume_score + valuation_score + technical_score
    total_score = max(0, raw_score - penalty)
    
    # シグナルレベル判定
    signal_level = get_signal_level(total_score)
    
    # 理由タグ生成
    reason_tags = generate_reason_tags(news_score, volume_score, valuation_score, matched_keywords)
    
    return MAScore(
        code=code,
        name=name,
        total_score=total_score,
        signal_level=signal_level,
        news_score=news_score,
        volume_score=volume_score,
        valuation_score=valuation_score,
        technical_score=technical_score,
        news_items=news_items,
        matched_keywords=matched_keywords,
        exclusion_flags=exclusion_flags,
        reason_tags=reason_tags
    )


def batch_analyze_ma(
    stock_data_list: List[Dict[str, Any]],
    with_news: bool = True
) -> List[MAScore]:
    """
    複数銘柄を一括でM&A分析
    """
    results = []
    
    for data in stock_data_list:
        if data.get("name") == "存在しない銘柄":
            continue
        
        # PBR計算
        price = data.get("price")
        bps = None  # yfinanceから直接取得できないため、別途計算が必要
        
        # fair_value_calc_y4から取得したデータを使用
        pbr = None
        if price and data.get("fair_value"):
            # 簡易的にPBR推定（理論株価から逆算）
            # Graham数: √(22.5 × EPS × BPS) = fair_value
            # この情報だけではPBRは算出できないが、市場データがあれば使用
            pass
        
        score = analyze_ma_potential(
            code=data.get("code", ""),
            name=data.get("name", ""),
            price=price,
            pbr=pbr,
            upside_pct=data.get("upside_pct"),
            market_cap=data.get("market_cap"),
            volume_ratio=data.get("volume_ratio"),
            turnover_pct=data.get("turnover_pct"),
            turnover_5d_pct=data.get("turnover_5d_pct") if "turnover_5d_pct" in data else None,
            signal_icon=data.get("signal_icon", "—"),
            skip_news=not with_news
        )
        
        results.append(score)
    
    # スコア順でソート
    results.sort(key=lambda x: x.total_score, reverse=True)
    
    return results
