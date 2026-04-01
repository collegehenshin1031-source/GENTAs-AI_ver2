"""
源太AI🤖ハゲタカSCOPE
- 全銘柄24時間監視
- ハゲタカ（機関投資家）の足跡を自動検知
- ロックオン通知システム
"""

import re
import unicodedata
import time
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

import hagetaka_scanner as scanner
import ma_detector as ma
import notifier

# ==========================================
# 🔑 パスワード設定
# ==========================================
LOGIN_PASSWORD = "88888"
ADMIN_CODE = "888888"

# ==========================================
# UI設定
# ==========================================
st.set_page_config(
    page_title="源太AI🤖ハゲタカSCOPE", 
    page_icon="🦅", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==========================================
# 🎨 先乗り株カレッジ ブランドCSS
# ==========================================
st.markdown("""
<style>
/* 基本設定・Streamlit要素非表示 */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
.stDeployButton {display:none;}

/* 全体背景 */
div[data-testid="stAppViewContainer"] {
    background: linear-gradient(180deg, #FAFAFA 0%, #FFF5F5 100%) !important;
}

/* メインコンテナ */
.main .block-container {
    max-width: 1200px !important;
    padding: 1rem 2rem 3rem 2rem !important;
    margin: 0 auto !important;
}

/* ヘッダー */
h1 {
    text-align: center !important;
    font-size: 2rem !important;
    font-weight: 800 !important;
    background: linear-gradient(135deg, #C41E3A 0%, #E85A71 100%) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
    margin-bottom: 0.5rem !important;
}

/* サブタイトル */
.subtitle {
    text-align: center;
    color: #666;
    font-size: 0.95rem;
    margin-bottom: 1.5rem;
}

/* タブスタイル */
.stTabs [data-baseweb="tab-list"] {
    justify-content: center !important;
    gap: 0 !important;
    background-color: #FFF !important;
    padding: 0.4rem !important;
    border-radius: 16px !important;
    box-shadow: 0 2px 12px rgba(196, 30, 58, 0.1) !important;
    margin-bottom: 1.5rem !important;
}

.stTabs [data-baseweb="tab"] {
    padding: 0.75rem 2rem !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    color: #666 !important;
    transition: all 0.3s ease !important;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #C41E3A 0%, #E85A71 100%) !important;
    color: white !important;
    box-shadow: 0 4px 12px rgba(196, 30, 58, 0.3) !important;
}

.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {
    display: none !important;
}

/* ボタン */
div.stButton {
    text-align: center !important;
}

div.stButton > button:first-child {
    background: linear-gradient(135deg, #C41E3A 0%, #E85A71 100%) !important;
    color: white !important;
    font-weight: 700 !important;
    border-radius: 12px !important;
    border: none !important;
    padding: 0.85rem 2.5rem !important;
    box-shadow: 0 4px 15px rgba(196, 30, 58, 0.25) !important;
    transition: all 0.3s ease !important;
    font-size: 1.05rem !important;
}

div.stButton > button:hover {
    transform: translateY(-3px) !important;
    box-shadow: 0 8px 25px rgba(196, 30, 58, 0.35) !important;
}

/* カード */
.stock-card {
    background: white;
    border-radius: 16px;
    padding: 1.25rem;
    margin: 0.75rem 0;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    border-left: 5px solid #C41E3A;
    transition: all 0.2s ease;
}

.stock-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 20px rgba(196, 30, 58, 0.15);
}

.stock-card.lockon {
    border-left-color: #C41E3A;
    background: linear-gradient(135deg, #FFF 0%, #FFF5F5 100%);
}

.stock-card.high {
    border-left-color: #F97316;
    background: linear-gradient(135deg, #FFF 0%, #FFF7ED 100%);
}

.stock-card.medium {
    border-left-color: #EAB308;
    background: linear-gradient(135deg, #FFF 0%, #FEFCE8 100%);
}

/* スコアバッジ */
.score-badge {
    display: inline-block;
    padding: 0.35rem 0.85rem;
    border-radius: 20px;
    font-weight: 700;
    font-size: 0.9rem;
}

.score-badge.lockon {
    background: linear-gradient(135deg, #C41E3A 0%, #E85A71 100%);
    color: white;
}

.score-badge.high {
    background: linear-gradient(135deg, #F97316 0%, #FB923C 100%);
    color: white;
}

.score-badge.medium {
    background: linear-gradient(135deg, #EAB308 0%, #FACC15 100%);
    color: #1a1a1a;
}

/* シグナルタグ */
.signal-tag {
    display: inline-block;
    background: #F3F4F6;
    padding: 0.25rem 0.6rem;
    border-radius: 6px;
    font-size: 0.8rem;
    margin: 0.15rem;
    color: #374151;
}

/* メトリクス */
[data-testid="stMetric"] {
    background: white !important;
    padding: 1rem !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04) !important;
}

[data-testid="stMetricValue"] {
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: #C41E3A !important;
}

/* Expander */
.stExpander {
    background-color: #FFFFFF !important;
    border: none !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04) !important;
}

/* 入力フォーム */
.stTextArea textarea, .stTextInput input {
    border-radius: 10px !important;
    border: 2px solid #E8E8E8 !important;
    font-size: 16px !important;
}

.stTextArea textarea:focus, .stTextInput input:focus {
    border-color: #C41E3A !important;
}

/* ヒーローセクション */
.hero-section {
    text-align: center;
    padding: 2rem 1rem;
    background: linear-gradient(135deg, #C41E3A 0%, #E85A71 100%);
    border-radius: 20px;
    color: white;
    margin-bottom: 1.5rem;
}

.hero-section h2 {
    color: white !important;
    font-size: 1.3rem;
    margin-bottom: 0.5rem;
}

.hero-section p {
    opacity: 0.9;
    font-size: 0.95rem;
}

/* ステータスインジケーター */
.status-indicator {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: white;
    border-radius: 20px;
    font-size: 0.85rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    animation: pulse 2s infinite;
}

.status-dot.active {
    background: #22C55E;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* レスポンシブ */
@media (max-width: 768px) {
    .main .block-container {
        padding: 0.75rem 1rem 2rem 1rem !important;
    }
    
    h1 {
        font-size: 1.5rem !important;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
    }
    
    .stTabs [data-baseweb="tab"] {
        padding: 0.6rem 1rem !important;
        font-size: 0.9rem !important;
        white-space: nowrap !important;
    }
    
    div.stButton > button:first-child {
        width: 100% !important;
    }
    
    .hero-section {
        padding: 1.5rem 1rem;
    }
}
</style>
""", unsafe_allow_html=True)


# ==========================================
# 認証
# ==========================================
def check_password():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if not st.session_state["logged_in"]:
        st.markdown("## 🔒 ACCESS RESTRICTED")
        password_input = st.text_input("パスワードを入力してください", type="password")
        if st.button("ログイン"):
            input_norm = unicodedata.normalize('NFKC', password_input).upper().strip()
            secret_norm = unicodedata.normalize('NFKC', LOGIN_PASSWORD).upper().strip()
            if input_norm == secret_norm:
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("パスワードが違います 🙅")
        st.stop()

check_password()


# ==========================================
# ヘルパー関数
# ==========================================
def fmt_price(x):
    if x is None or pd.isna(x): return "—"
    try: return f"¥{float(x):,.0f}"
    except: return "—"

def fmt_pct(x):
    if x is None or pd.isna(x): return "—"
    try:
        v = float(x)
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.2f}%"
    except: return "—"

def fmt_volume(x):
    if x is None or pd.isna(x): return "—"
    try:
        v = int(x)
        if v >= 1e6: return f"{v/1e6:.1f}M"
        if v >= 1e3: return f"{v/1e3:.0f}K"
        return str(v)
    except: return "—"

def fmt_market_cap(x):
    if x is None or pd.isna(x) or x == 0: return "—"
    try:
        v = float(x) / 1e8  # 億円換算
        if v >= 10000: return f"{v/10000:.1f}兆円"
        return f"{v:.0f}億円"
    except: return "—"

def get_signal_class(signal_level):
    if signal_level == scanner.SignalLevel.LOCKON:
        return "lockon"
    elif signal_level == scanner.SignalLevel.HIGH:
        return "high"
    else:
        return "medium"


def render_stock_card(signal: scanner.HagetakaSignal):
    """銘柄カードをレンダリング"""
    card_class = get_signal_class(signal.signal_level)
    badge_class = card_class
    
    st.markdown(f"""
    <div class="stock-card {card_class}">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.5rem;">
            <div>
                <span class="score-badge {badge_class}">{signal.signal_level.value}</span>
                <span style="font-size: 1.3rem; font-weight: 700; margin-left: 0.5rem;">{signal.name}</span>
                <span style="color: #666; margin-left: 0.5rem;">({signal.code})</span>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 1.4rem; font-weight: 700;">{fmt_price(signal.price)}</div>
                <div style="color: {'#22C55E' if signal.change_pct >= 0 else '#EF4444'}; font-weight: 600;">
                    {fmt_pct(signal.change_pct)}
                </div>
            </div>
        </div>
        <div style="margin-top: 0.75rem; display: flex; gap: 1.5rem; flex-wrap: wrap; font-size: 0.9rem; color: #666;">
            <span>📊 スコア: <strong style="color: #C41E3A;">{signal.total_score}点</strong></span>
            <span>📈 出来高倍率: <strong>{signal.volume_ratio:.1f}倍</strong></span>
            <span>🌪️ 回転率: <strong>{signal.turnover_pct:.1f}%</strong></span>
            <span>💰 時価総額: <strong>{fmt_market_cap(signal.market_cap)}</strong></span>
        </div>
        <div style="margin-top: 0.75rem;">
            {''.join([f'<span class="signal-tag">{s}</span>' for s in signal.signals[:5]])}
        </div>
    </div>
    """, unsafe_allow_html=True)


# ==========================================
# 通知設定初期化
# ==========================================
def init_session_state():
    if "notification_config" not in st.session_state:
        st.session_state["notification_config"] = notifier.load_notification_config()
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = notifier.load_watchlist()
    if "scan_results" not in st.session_state:
        st.session_state["scan_results"] = []
    if "last_scan_time" not in st.session_state:
        st.session_state["last_scan_time"] = None

init_session_state()


# ==========================================
# メイン画面
# ==========================================
st.title("🦅 源太AI ハゲタカSCOPE")
st.markdown('<p class="subtitle">プロの投資戦略をのぞき見る「カンニング級の裏・攻略本」</p>', unsafe_allow_html=True)

# タブ
tab1, tab2, tab3 = st.tabs(["🎯 ロックオン銘柄", "📊 ハゲタカ監視", "🔔 通知設定"])


# ==========================================
# タブ1: ロックオン銘柄
# ==========================================
with tab1:
    # ヒーローセクション
    st.markdown("""
    <div class="hero-section">
        <h2>🎯 AIが検知した「今日の標的」</h2>
        <p>全3,800銘柄をスキャンし、ハゲタカの足跡が見つかった銘柄を厳選表示</p>
    </div>
    """, unsafe_allow_html=True)
    
    # ステータス表示
    col1, col2, col3 = st.columns(3)
    with col1:
        last_scan = st.session_state.get("last_scan_time")
        if last_scan:
            st.markdown(f"""
            <div class="status-indicator">
                <span class="status-dot active"></span>
                最終スキャン: {last_scan.strftime('%H:%M')}
            </div>
            """, unsafe_allow_html=True)
    
    with col3:
        lockons = [s for s in st.session_state.get("scan_results", []) if s.total_score >= 50]
        st.metric("ロックオン銘柄", f"{len(lockons)}件")
    
    st.divider()
    
    # スキャン設定セクション
    st.markdown("### 🔍 スキャン設定")
    
    # スキャンモード選択（プルダウン）
    scan_mode_options = {
        "⚡ クイックスキャン（推奨）": scanner.ScanMode.QUICK,
        "🌱 グロース市場（約500銘柄）": scanner.ScanMode.GROWTH,
        "🏬 スタンダード市場（約1,400銘柄）": scanner.ScanMode.STANDARD,
        "🏢 プライム市場（約1,800銘柄）": scanner.ScanMode.PRIME,
        "🌐 全銘柄スキャン（約3,800銘柄）": scanner.ScanMode.ALL,
        "✏️ 銘柄コードを直接入力": scanner.ScanMode.CUSTOM,
    }
    
    selected_mode_label = st.selectbox(
        "スキャン対象を選択",
        options=list(scan_mode_options.keys()),
        index=0,
        help="クイックスキャンは出来高が急増している銘柄を優先的にスキャンします"
    )
    
    selected_mode = scan_mode_options[selected_mode_label]
    scan_option = scanner.SCAN_OPTIONS[selected_mode]
    
    # 選択したモードの説明を表示
    info_col1, info_col2 = st.columns([2, 1])
    with info_col1:
        st.markdown(f"""
        <div style="background: #F8F9FA; padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem;">
            📋 <strong>{scan_option.description}</strong><br>
            <span style="color: #666;">対象: 約{scan_option.estimated_count}銘柄 / 所要時間: {scan_option.estimated_time}</span>
        </div>
        """, unsafe_allow_html=True)
    
    # 警告表示
    if scan_option.warning:
        st.warning(scan_option.warning)
    
    # カスタム入力（モードがCUSTOMの場合のみ表示）
    custom_codes = []
    if selected_mode == scanner.ScanMode.CUSTOM:
        custom_input = st.text_input(
            "銘柄コードを入力（スペース区切り）",
            placeholder="例: 7203 9984 6758 8306",
            help="スキャンしたい銘柄コードをスペースで区切って入力してください"
        )
        if custom_input:
            custom_codes = [c.strip() for c in custom_input.split() if c.strip()]
            st.info(f"📝 {len(custom_codes)}銘柄を入力済み")
    
    # スキャン実行ボタン
    st.markdown("")  # スペーサー
    scan_btn = st.button("🚀 スキャン開始", type="primary", use_container_width=True)
    
    # スキャン実行
    if scan_btn:
        # 対象銘柄を取得
        if selected_mode == scanner.ScanMode.CUSTOM:
            if not custom_codes:
                st.error("銘柄コードを入力してください")
                st.stop()
            codes = custom_codes
        else:
            with st.spinner("📋 銘柄リストを取得中..."):
                codes = scanner.get_scan_targets(selected_mode, custom_codes)
        
        if not codes:
            st.error("スキャン対象の銘柄が見つかりませんでした")
            st.stop()
        
        st.info(f"🎯 {len(codes)}銘柄をスキャンします")
        
        # プログレスバー
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        def update_progress(current, total, code):
            progress_bar.progress(current / total)
            status_text.text(f"スキャン中... {current}/{total} - {code}")
        
        with st.spinner("🔍 ハゲタカの足跡を探索中..."):
            # ==========================================
            # 【アプローチA】夜間生成キャッシュからの負荷ゼロ高速読み込み
            # ==========================================
            import os
            import pickle
            cache_path = "data/daily_hagetaka_cache.pkl"
            
            if selected_mode == scanner.ScanMode.ALL and os.path.exists(cache_path):
                try:
                    with open(cache_path, 'rb') as f:
                        results = pickle.load(f)
                    
                    # 万が一キャッシュのデータが極端に少ない場合の安全装置
                    if len(results) >= len(codes) * 0.9:
                        progress_bar.progress(1.0)
                        status_text.text("✅ 夜間生成キャッシュからの高速読み込み完了")
                        st.session_state["scan_results"] = results
                        st.session_state["last_scan_time"] = datetime.now()
                        st.session_state["scan_target_count"] = len(results)
                    else:
                        # フォールバック処理（通常取得）
                        results = scanner.scan_all_stocks(codes, progress_callback=update_progress)
                        st.session_state["scan_results"] = results
                        st.session_state["last_scan_time"] = datetime.now()
                        st.session_state["scan_target_count"] = len(codes)
                except Exception as e:
                    print(f"キャッシュ読み込みエラー: {e}")
                    results = scanner.scan_all_stocks(codes, progress_callback=update_progress)
                    st.session_state["scan_results"] = results
                    st.session_state["last_scan_time"] = datetime.now()
                    st.session_state["scan_target_count"] = len(codes)
            else:
                # 全銘柄以外、またはキャッシュ未生成時は通常取得
                results = scanner.scan_all_stocks(codes, progress_callback=update_progress)
                st.session_state["scan_results"] = results
                st.session_state["last_scan_time"] = datetime.now()
                st.session_state["scan_target_count"] = len(codes)
        
        progress_bar.empty()
        status_text.empty()
        
        # 結果サマリー
        if results:
            lockons = [s for s in results if s.signal_level == scanner.SignalLevel.LOCKON]
            high_alerts = [s for s in results if s.signal_level == scanner.SignalLevel.HIGH]
            medium_alerts = [s for s in results if s.signal_level == scanner.SignalLevel.MEDIUM]
            
            st.success(f"""
            ✅ スキャン完了！
            - 🔴 ロックオン: {len(lockons)}件
            - 🟠 高警戒: {len(high_alerts)}件
            - 🟡 監視中: {len(medium_alerts)}件
            - 📊 分析完了: {len(results)}件 / 対象: {len(codes)}件
            """)
            
            # 通知チェック
            config = st.session_state.get("notification_config", notifier.NotificationConfig())
            if config.enabled and config.email_enabled and lockons:
                st.info(f"📧 {len(lockons)}件のロックオン銘柄を検知しました！")
        else:
            st.error(f"""
            ⚠️ スキャン結果が0件でした
            - 対象銘柄数: {len(codes)}件
            - データ取得に失敗した可能性があります
            - 時間をおいて再度お試しください
            """)
        
        st.rerun()
    
    # 結果表示
    results = st.session_state.get("scan_results", [])
    
    if results:
        st.divider()
        
        # フィルター
        col1, col2 = st.columns([1, 1])
        with col1:
            min_score_filter = st.slider("最低スコア", 0, 100, 0, key="filter_score")
        with col2:
            sort_option = st.selectbox("並び順", ["スコア順", "出来高倍率順", "回転率順"])
        
        # フィルタリング
        filtered = [s for s in results if s.total_score >= min_score_filter]
        
        # ソート
        if sort_option == "出来高倍率順":
            filtered.sort(key=lambda x: x.volume_ratio, reverse=True)
        elif sort_option == "回転率順":
            filtered.sort(key=lambda x: x.turnover_pct, reverse=True)
        else:
            filtered.sort(key=lambda x: x.total_score, reverse=True)
        
        st.markdown(f"### 📋 厳選・監視リスト（{len(filtered)}件）")
        
        if not filtered:
            st.info("条件に合致する銘柄がありません。フィルターを調整してください。")
        else:
            for signal in filtered[:20]:  # 上位20件
                render_stock_card(signal)
                
                # 詳細展開
                with st.expander(f"📊 {signal.code} の詳細分析"):
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("🥷 ステルス集積", f"{signal.stealth_score}/35点")
                    with col2:
                        st.metric("🧱 板の違和感", f"{signal.board_score}/35点")
                    with col3:
                        st.metric("🔥 出来高臨界点", f"{signal.volume_score}/30点")
                    with col4:
                        st.metric("🌟 ボーナス", f"+{signal.bonus_score}点")
                    
                    st.markdown("**検知シグナル:**")
                    for s in signal.signals:
                        st.markdown(f"- {s}")
    elif st.session_state.get("last_scan_time"):
        st.warning("⚠️ スキャン結果が0件でした。データ取得に失敗した可能性があります。時間をおいて再度お試しください。")
    else:
        st.info("👆 「スキャン開始」ボタンを押して、ハゲタカの足跡を探索してください。")
    
    # 説明セクション
    st.divider()
    with st.expander("📚 ハゲタカスコープの仕組み"):
        st.markdown("""
        ### 🦅 3つの検知ロジック
        
        #### 1. 🥷 ステルス集積（最大35点）
        目立たないように株を買い集めている動きを検知します。
        - 出来高が徐々に増加しているか
        - 価格変動が小さいのに出来高が増えているか
        - 時価総額が買収適正サイズか
        
        #### 2. 🧱 板の違和感（最大35点）
        気配値（板）に現れる不自然な並びや歪みを検知します。
        - 需給の壁（価格帯別出来高の偏り）の位置
        - 52週高値・安値との位置関係
        - ボリンジャーバンドの位置
        
        #### 3. 🔥 出来高の臨界点（最大30点）
        爆発直前に見られる取引量の異常な変化を検知します。
        - 出来高倍率（20日平均比）
        - 浮動株回転率
        
        ---
        
        ### 🎯 シグナルレベル
        
        | レベル | スコア | 意味 |
        |--------|--------|------|
        | 🔴 ロックオン | 70点以上 | 複数の兆候が重なった最注目銘柄 |
        | 🟠 高警戒 | 50〜69点 | 要注目、監視リスト入り推奨 |
        | 🟡 監視中 | 30〜49点 | 一部兆候あり、継続監視 |
        | 🟢 平常 | 29点以下 | 現時点で特に異常なし |
        """)


# ==========================================
# タブ2: ハゲタカ監視（M&A予兆）
# ==========================================
with tab2:
    st.markdown("""
    <div class="hero-section">
        <h2>📊 M&A予兆監視システム</h2>
        <p>TOB・完全子会社化・MBOなど、M&Aの可能性が高い銘柄を自動検知</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 監視リスト管理
    st.markdown("### 📋 監視リスト")
    
    watchlist = st.session_state.get("watchlist", [])
    
    col1, col2 = st.columns([3, 1])
    with col1:
        new_codes = st.text_input("銘柄を追加", placeholder="例: 7203 9984 6758", key="add_watch")
    with col2:
        if st.button("➕ 追加", key="add_watch_btn", use_container_width=True):
            if new_codes:
                new_list = [c.strip() for c in new_codes.split() if c.strip()]
                for code in new_list:
                    if code not in watchlist:
                        watchlist.append(code)
                st.session_state["watchlist"] = watchlist
                notifier.save_watchlist(watchlist)
                st.success(f"{len(new_list)}件追加しました")
                st.rerun()
    
    if watchlist:
        st.markdown(f"**現在の監視銘柄** ({len(watchlist)}件): {', '.join(watchlist)}")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("🔍 M&A分析実行", type="primary", key="ma_analyze"):
                with st.spinner("🎯 M&A予兆分析中..."):
                    try:
                        import fair_value_calc_y4 as fv
                        # ==========================================
                        # 【アプローチA】ハイブリッド取得関数へ差し替え
                        # ==========================================
                        bundle = scanner.get_cached_or_fetch(watchlist)
                        stock_data_list = [bundle.get(code, {}) for code in watchlist]
                        ma_results = ma.batch_analyze_ma(stock_data_list, with_news=True)
                        st.session_state["ma_results"] = ma_results
                        
                        # 通知
                        config = st.session_state.get("notification_config", notifier.NotificationConfig())
                        if config.enabled and config.email_enabled:
                            alerts = [s for s in ma_results if s.total_score >= config.min_score_threshold]
                            if alerts:
                                notifier.send_ma_alert(config, alerts)
                                st.success(f"📧 {len(alerts)}件のアラートを送信しました")
                    except Exception as e:
                        st.error(f"エラー: {e}")
        
        with col2:
            if st.button("🗑️ リストをクリア", key="clear_watch"):
                st.session_state["watchlist"] = []
                notifier.save_watchlist([])
                st.rerun()
        
        # M&A分析結果表示
        if "ma_results" in st.session_state and st.session_state["ma_results"]:
            st.divider()
            st.markdown("### 📊 M&A予兆分析結果")
            
            for score in st.session_state["ma_results"]:
                if score.signal_level == ma.MASignalLevel.CRITICAL:
                    card_class, badge_class = "lockon", "lockon"
                elif score.signal_level == ma.MASignalLevel.HIGH:
                    card_class, badge_class = "high", "high"
                else:
                    card_class, badge_class = "medium", "medium"
                
                st.markdown(f"""
                <div class="stock-card {card_class}">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                        <div>
                            <span class="score-badge {badge_class}">{score.signal_level.value}</span>
                            <span style="font-size: 1.2rem; font-weight: 700; margin-left: 0.5rem;">{score.name}</span>
                            <span style="color: #666;">({score.code})</span>
                        </div>
                        <div style="font-size: 1.3rem; font-weight: 700; color: #C41E3A;">
                            {score.total_score}点
                        </div>
                    </div>
                    <div style="margin-top: 0.5rem;">
                        {''.join([f'<span class="signal-tag">{t}</span>' for t in score.reason_tags[:5]])}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander(f"📋 {score.code} 詳細"):
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("ニュース", f"{score.news_score}/40")
                    col2.metric("出来高", f"{score.volume_score}/30")
                    col3.metric("バリュエーション", f"{score.valuation_score}/20")
                    col4.metric("テクニカル", f"{score.technical_score}/10")
                    
                    if score.news_items:
                        st.markdown("**📰 関連ニュース**")
                        for news in score.news_items[:3]:
                            st.markdown(f"- {news.title}")
    else:
        st.info("監視銘柄を追加してください。")


# ==========================================
# タブ3: 通知設定
# ==========================================
with tab3:
    st.markdown("""
    <div class="hero-section">
        <h2>🔔 ロックオン通知設定</h2>
        <p>条件合致の「標的」を検知した瞬間、スマホに通知が届きます</p>
    </div>
    """, unsafe_allow_html=True)
    
    config = st.session_state.get("notification_config", notifier.NotificationConfig())
    
    st.markdown("### ⚙️ 基本設定")
    enabled = st.toggle("通知を有効にする", value=config.enabled, key="notify_enabled")
    
    min_score = st.slider(
        "通知する最低スコア", 0, 100, config.min_score_threshold, 
        key="min_score",
        help="このスコア以上の銘柄が検知された場合に通知されます"
    )
    
    st.divider()
    
    st.markdown("### 📧 メール通知設定")
    st.markdown("""
    **Gmailの場合:**
    1. [Googleアカウント](https://myaccount.google.com/)で2段階認証を有効化
    2. [アプリパスワード](https://myaccount.google.com/apppasswords)を生成
    3. 生成された16桁のパスワードを「SMTPパスワード」に入力
    """)
    
    email_enabled = st.toggle("メール通知を有効にする", value=config.email_enabled, key="email_enabled")
    
    if email_enabled:
        col1, col2 = st.columns(2)
        with col1:
            email_address = st.text_input("送信先メールアドレス", value=config.email_address, key="email_address")
            smtp_server = st.text_input("SMTPサーバー", value=config.smtp_server, key="smtp_server")
        with col2:
            smtp_user = st.text_input("SMTPユーザー", value=config.smtp_user, key="smtp_user")
            smtp_password = st.text_input("SMTPパスワード", value=config.smtp_password, type="password", key="smtp_password")
        
        smtp_port = st.number_input("SMTPポート", value=config.smtp_port, key="smtp_port")
        
        if email_address and smtp_user and smtp_password:
            if st.button("📧 テスト送信", key="test_email"):
                result = notifier.send_email(
                    to_address=email_address,
                    subject="🎯 ハゲタカSCOPE テスト通知",
                    body="ロックオン通知のテストです。\n\n設定が正常に機能しています。",
                    smtp_server=smtp_server,
                    smtp_port=int(smtp_port),
                    smtp_user=smtp_user,
                    smtp_password=smtp_password
                )
                if result.success:
                    st.success("✅ テスト送信成功！")
                else:
                    st.error(f"❌ {result.message}")
    else:
        email_address = config.email_address
        smtp_server = config.smtp_server
        smtp_user = config.smtp_user
        smtp_password = config.smtp_password
        smtp_port = config.smtp_port
    
    st.divider()
    
    if st.button("💾 設定を保存", type="primary", key="save_config"):
        new_config = notifier.NotificationConfig(
            enabled=enabled,
            email_enabled=email_enabled,
            email_address=email_address if email_enabled else config.email_address,
            smtp_server=smtp_server if email_enabled else config.smtp_server,
            smtp_port=int(smtp_port) if email_enabled else config.smtp_port,
            smtp_user=smtp_user if email_enabled else config.smtp_user,
            smtp_password=smtp_password if email_enabled else config.smtp_password,
            line_enabled=False,
            line_token="",
            min_score_threshold=min_score,
            notify_critical_only=False,
        )
        notifier.save_notification_config(new_config)
        st.session_state["notification_config"] = new_config
        st.success("✅ 設定を保存しました！")


# ==========================================
# フッター
# ==========================================
st.divider()
st.markdown("""
<div style="text-align: center; color: #888; font-size: 0.85rem; padding: 1rem;">
    ⚠️ 投資は自己責任でお願いします。本ツールは情報提供を目的としており、投資助言ではありません。<br>
    © 先乗り株カレッジ - 源太AI ハゲタカSCOPE
</div>
""", unsafe_allow_html=True)


# ==========================================
# 管理者メニュー
# ==========================================
with st.expander("🔧 管理者メニュー"):
    admin_input = st.text_input("管理者コード", type="password", key="admin_pass")
    if admin_input == ADMIN_CODE:
        st.success("認証OK")
        if st.button("🗑️ キャッシュ削除"):
            st.cache_data.clear()
            st.success("削除完了！")
            time.sleep(1)
            st.rerun()
