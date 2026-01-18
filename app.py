import re
import math
import unicodedata
import time
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np
import streamlit as st
import fair_value_calc_y4 as fv
import ma_detector as ma
import notifier
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# ==========================================
# パスワード設定
# ==========================================
LOGIN_PASSWORD = "88888"
ADMIN_CODE = "888888"

# ==========================================
# UI設定
# ==========================================
st.set_page_config(page_title="源太ＡＩ🤖ハゲタカＳＣＯＰＥ", page_icon="📈", layout="wide")

hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
.stDeployButton {display:none;}

div.stButton > button:first-child {
    background-color: #ff4b4b;
    color: white;
    font-weight: bold;
    border-radius: 12px;
    border: none;
    padding: 0.8rem 2rem;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}
div.stButton > button:hover {
    background-color: #e63e3e;
}

details {
    background-color: #f9f9f9;
    padding: 10px;
    border-radius: 5px;
    border: 1px solid #eee;
    margin-top: 10px;
    margin-bottom: 20px;
}
summary {
    cursor: pointer;
    font-weight: bold;
    color: #31333F;
}

.stApp, .stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown span, .stMarkdown div, .stDataFrame {
    color: #31333F !important;
    background-color: #ffffff !important;
}
div[data-testid="stAppViewContainer"] {
    background-color: #ffffff !important;
}
.stTextInput input, .stTextArea textarea {
    color: #31333F !important;
    background-color: #f0f2f6 !important;
}

::placeholder {
    color: #888888 !important;
    opacity: 1;
}

.ma-critical { background-color: #fee2e2; border-left: 4px solid #ef4444; padding: 10px; margin: 5px 0; border-radius: 4px; }
.ma-high { background-color: #ffedd5; border-left: 4px solid #f97316; padding: 10px; margin: 5px 0; border-radius: 4px; }
.ma-medium { background-color: #fef9c3; border-left: 4px solid #eab308; padding: 10px; margin: 5px 0; border-radius: 4px; }
.ma-low { background-color: #dcfce7; border-left: 4px solid #22c55e; padding: 10px; margin: 5px 0; border-radius: 4px; }
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# -----------------------------
# 認証
# -----------------------------
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

# -----------------------------
# チャート描画関数
# -----------------------------
def draw_wall_chart(ticker_data: Dict[str, Any]):
    hist = ticker_data.get("hist_data")
    if hist is None or hist.empty:
        st.warning("チャートデータがありません")
        return

    name = ticker_data.get("name", "Unknown")
    code = ticker_data.get("code", "----")
    current_price = ticker_data.get("price", 0)

    hist = hist.reset_index()
    hist['Date'] = pd.to_datetime(hist.iloc[:, 0]).dt.tz_localize(None)

    bins = 50
    p_min = min(hist['Close'].min(), current_price * 0.9)
    p_max = max(hist['Close'].max(), current_price * 1.1)
    bin_edges = np.linspace(p_min, p_max, bins)
    hist['bin'] = pd.cut(hist['Close'], bins=bin_edges)
    vol_profile = hist.groupby('bin', observed=False)['Volume'].sum()

    upper_candidates = []
    lower_candidates = []

    for interval, volume in vol_profile.items():
        mid_price = interval.mid
        if volume == 0: continue
        if mid_price > current_price:
            upper_candidates.append({'vol': volume, 'price': mid_price})
        else:
            lower_candidates.append({'vol': volume, 'price': mid_price})

    if upper_candidates:
        best_red = sorted(upper_candidates, key=lambda x: (-x['vol'], x['price']))[0]
        resistance_price = best_red['price']
    else:
        resistance_price = hist['High'].max()

    if lower_candidates:
        best_blue = sorted(lower_candidates, key=lambda x: (-x['vol'], -x['price']))[0]
        support_price = best_blue['price']
    else:
        support_price = hist['Low'].min()

    bar_colors = []
    for interval in vol_profile.index:
        if interval.mid > current_price:
            bar_colors.append('rgba(255, 82, 82, 0.4)')
        else:
            bar_colors.append('rgba(33, 150, 243, 0.4)')

    fig = make_subplots(
        rows=1, cols=2, shared_yaxes=True, column_widths=[0.75, 0.25], horizontal_spacing=0.02,
        subplot_titles=("📉 トレンド分析", "🧱 需給の壁")
    )

    fig.add_trace(go.Candlestick(
        x=hist['Date'], open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='株価'
    ), row=1, col=1)

    fig.add_trace(go.Bar(
        x=vol_profile.values, y=[i.mid for i in vol_profile.index], orientation='h', marker_color=bar_colors, name='出来高'
    ), row=1, col=2)

    fig.add_hline(y=resistance_price, line_color="#ef4444", line_width=2, annotation_text="🟥 上値抵抗線", annotation_position="top left", annotation_font_color="#ef4444", row=1, col=1)
    fig.add_hline(y=support_price, line_color="#3b82f6", line_width=2, annotation_text="🟦 下値支持線", annotation_position="bottom left", annotation_font_color="#3b82f6", row=1, col=1)

    fig.update_layout(
        title=f"📊 {name} ({code})", height=450, showlegend=False, xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=60, b=10), dragmode=False, template="plotly_white",
        paper_bgcolor='white', plot_bgcolor='white', font=dict(color='black')
    )
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'staticPlot': False, 'scrollZoom': False}, theme=None)

# ==========================================
# ヘルパー関数
# ==========================================
def sanitize_codes(raw_codes: List[str]) -> List[str]:
    cleaned = []
    for x in raw_codes:
        if x is None: continue
        s = str(x).strip()
        s = unicodedata.normalize('NFKC', s).upper().replace(" ", "").replace(",", "")
        if not s: continue
        m = re.search(r"[0-9A-Z]{4}", s)
        if m: cleaned.append(m.group(0))
    return list(dict.fromkeys(cleaned))

def fmt_yen(x):
    if x is None or pd.isna(x): return "—"
    try: return f"{float(x):,.0f} 円"
    except: return "—"

def fmt_pct(x):
    if x is None or pd.isna(x): return "—"
    try: return f"{float(x):.2f}%"
    except: return "—"

def fmt_market_cap(x):
    if x is None or pd.isna(x): return "—"
    try:
        v = float(x)
        if v >= 1e12: return f"{v/1e12:.2f} 兆円"
        elif v >= 1e8: return f"{v/1e8:.0f} 億円"
        else: return f"{v:,.0f} 円"
    except: return "—"

def fmt_big_prob(x):
    if x is None or pd.isna(x): return "—"
    try:
        v = float(x)
        if v >= 80: return f"🔥 {v:.0f}%"
        if v >= 60: return f"⚡ {v:.0f}%"
        if v >= 40: return f"👀 {v:.0f}%"
        return f"{v:.0f}%"
    except: return "—"

def fmt_turnover(x):
    if x is None or pd.isna(x): return "—"
    try:
        v = float(x)
        if v >= 10.0: return f"🌪️ {v:.1f}% (激震)"
        if v >= 5.0: return f"⚡ {v:.1f}% (活況)"
        if v < 1.0: return f"☁ {v:.1f}% (閑散)"
        return f"{v:.1f}% (通常)"
    except: return "—"

def fmt_vol_ratio(x):
    if x is None or pd.isna(x): return "—"
    try:
        v = float(x)
        if v >= 5.0: return f"🔥 {v:.1f}倍 (緊急)"
        if v >= 3.0: return f"🚀 {v:.1f}倍 (着火)"
        if v >= 2.0: return f"⚡ {v:.1f}倍 (予兆)"
        return f"{v:.1f}倍 (通常)"
    except: return "—"

def fmt_ma_score(x):
    if x is None or pd.isna(x): return "—"
    try:
        v = int(x)
        if v >= 70: return f"🔴 {v}点"
        if v >= 50: return f"🟠 {v}点"
        if v >= 30: return f"🟡 {v}点"
        if v >= 15: return f"🟢 {v}点"
        return f"⚪ {v}点"
    except: return "—"

def calc_rating_from_upside(upside_pct):
    if upside_pct is None or pd.isna(upside_pct): return 0
    if upside_pct >= 50: return 5
    if upside_pct >= 30: return 4
    if upside_pct >= 15: return 3
    if upside_pct >= 5: return 2
    if upside_pct >= 0: return 1
    return 0

def to_stars(n):
    n = max(0, min(5, int(n or 0)))
    return "★" * n + "☆" * (5 - n)

def highlight_errors(val):
    if val == "存在しない銘柄" or val == "エラー":
        return 'color: #ff4b4b; font-weight: bold;'
    return ''

def highlight_rank_color(val):
    rank_styles = {
        "SSS": 'background-color: #FFD700; color: #000000; font-weight: bold;',
        "SS": 'background-color: #FF4500; color: #ffffff; font-weight: bold;',
        "S": 'background-color: #FF69B4; color: #ffffff; font-weight: bold;',
        "A": 'background-color: #22c55e; color: #ffffff; font-weight: bold;',
        "B": 'background-color: #3b82f6; color: #ffffff; font-weight: bold;',
        "C": 'background-color: #94a3b8; color: #ffffff; font-weight: bold;',
    }
    if val in ["D", "E"]:
        return 'background-color: #a855f7; color: #ffffff; font-weight: bold;'
    return rank_styles.get(val, '')

def highlight_ma_score(val):
    if "🔴" in str(val): return 'background-color: #fee2e2; color: #dc2626; font-weight: bold;'
    elif "🟠" in str(val): return 'background-color: #ffedd5; color: #ea580c; font-weight: bold;'
    elif "🟡" in str(val): return 'background-color: #fef9c3; color: #ca8a04; font-weight: bold;'
    elif "🟢" in str(val): return 'background-color: #dcfce7; color: #16a34a; font-weight: bold;'
    return ''

def calculate_score_and_rank(row):
    score = 0
    up = row.get('upside_pct_num', 0) or 0
    if up >= 50: score += 40
    elif up >= 30: score += 30
    elif up >= 15: score += 20
    elif up > 0: score += 10
    
    prob = row.get('prob_num', 0) or 0
    if prob >= 80: score += 30
    elif prob >= 60: score += 20
    elif prob >= 40: score += 10
    
    growth = row.get('growth_num', 0) or 0
    if growth >= 30: score += 20
    elif growth >= 10: score += 10
    
    weather = row.get('weather', '')
    if weather == '☀': score += 10
    elif weather == '☁': score += 5
    
    if score >= 95: return "SSS"
    if score >= 90: return "SS"
    if score >= 85: return "S"
    if score >= 75: return "A"
    if score >= 60: return "B"
    if score >= 45: return "C"
    if score >= 30: return "D"
    return "E"

def bundle_to_df(bundle: Any, codes: List[str], ma_scores: Optional[Dict[str, ma.MAScore]] = None) -> pd.DataFrame:
    rows = []
    for code in codes:
        v = bundle.get(code, {})
        if isinstance(v, dict):
            if v.get("name") in ["エラー", "計算エラー"] or v.get("note") == "データ取得不可(Yahoo拒否)":
                v.update({"name": "存在しない銘柄", "note": "—", "volume_wall": "—", "signal_icon": "—", "weather": "—", "turnover_pct": None, "volume_ratio": None})
            row = {"ticker": code, **v}
            if ma_scores and code in ma_scores:
                ms = ma_scores[code]
                row.update({"ma_score": ms.total_score, "ma_signal": ms.signal_level.value, "ma_tags": " ".join(ms.reason_tags) if ms.reason_tags else ""})
            else:
                row.update({"ma_score": None, "ma_signal": "", "ma_tags": ""})
        else:
            row = {"ticker": code, "name": "存在しない銘柄", "note": "—", "ma_score": None, "ma_signal": "", "ma_tags": ""}
        rows.append(row)

    df = pd.DataFrame(rows)
    cols = ["name", "weather", "price", "fair_value", "upside_pct", "dividend", "dividend_amount", "growth", "market_cap", "big_prob", "note", "signal_icon", "volume_wall", "turnover_pct", "volume_ratio", "ma_score", "ma_signal", "ma_tags"]
    for col in cols:
        if col not in df.columns: df[col] = None

    def _as_float(x):
        try: return float(x)
        except: return None

    df["price_num"] = df["price"].apply(_as_float)
    df["fair_value_num"] = df["fair_value"].apply(_as_float)
    df["upside_pct_num"] = df["upside_pct"].apply(_as_float)
    df["div_num"] = df["dividend"].apply(_as_float)
    df["growth_num"] = df["growth"].apply(_as_float)
    df["mc_num"] = df["market_cap"].apply(_as_float)
    df["prob_num"] = df["big_prob"].apply(_as_float)
    df["rating"] = df["upside_pct_num"].apply(calc_rating_from_upside)
    df["stars"] = df["rating"].apply(to_stars)

    error_mask = df["name"] == "存在しない銘柄"
    df.loc[error_mask, ["stars", "price", "fair_value", "note"]] = "—"
    df["ランク"] = df.apply(calculate_score_and_rank, axis=1)
    df.loc[error_mask, "ランク"] = "—"

    df["証券コード"] = df["ticker"]
    df["銘柄名"] = df["name"].fillna("—")
    df["業績"] = df["weather"].fillna("—")
    df["現在値"] = df["price"].apply(fmt_yen)
    df["理論株価"] = df["fair_value"].apply(fmt_yen)
    df["上昇余地"] = df["upside_pct_num"].apply(fmt_pct)
    df["評価"] = df["stars"]
    df["売買"] = df["signal_icon"].fillna("—")
    df["M&A予兆"] = df["ma_score"].apply(fmt_ma_score)
    df["M&Aタグ"] = df["ma_tags"].fillna("")
    df["需給の壁"] = df["volume_wall"].fillna("—")
    df["配当利回り"] = df["div_num"].apply(fmt_pct)
    df["事業の勢い"] = df["growth_num"].apply(fmt_pct)
    df["時価総額"] = df["mc_num"].apply(fmt_market_cap)
    df["大口介入"] = df["prob_num"].apply(fmt_big_prob)
    df["浮動株・激動率"] = df["turnover_pct"].apply(fmt_turnover)
    df["異常・着火倍率"] = df["volume_ratio"].apply(fmt_vol_ratio)
    df["根拠"] = df["note"].fillna("—")

    df.index = df.index + 1
    df["詳細"] = False

    show_cols = ["ランク", "証券コード", "銘柄名", "現在値", "理論株価", "上昇余地", "評価", "売買", "M&A予兆", "M&Aタグ", "需給の壁", "詳細", "配当利回り", "事業の勢い", "業績", "時価総額", "大口介入", "浮動株・激動率", "異常・着火倍率", "根拠"]
    return df[show_cols]

# ==========================================
# 通知設定初期化
# ==========================================
def init_notification_config():
    if "notification_config" not in st.session_state:
        st.session_state["notification_config"] = notifier.load_notification_config()
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = notifier.load_watchlist()

init_notification_config()

# ==========================================
# メイン画面
# ==========================================
st.title("源太ＡＩ🤖ハゲタカＳＣＯＰＥ")

tab1, tab2, tab3 = st.tabs(["📈 銘柄分析", "🎯 M&A予兆監視", "🔔 通知設定"])

# ==========================================
# タブ1: 銘柄分析
# ==========================================
with tab1:
    with st.expander("★ ランク・評価基準の見方", expanded=False):
        st.markdown("""
### 👑 総合ランク（SSS〜E）
- 🟨 **SSS (95-100点)**：神
- 🟧 **SS (90-94点)**：最強
- 🟪 **S (85-89点)**：超優秀
- 🟩 **A (75-84点)**：優良
- 🟦 **B (60-74点)**：普通
- 🟪 **C〜E**：微妙〜注意

### 割安度評価（★）
- ★★★★★：お宝（上昇余地+50%以上）
- ★★★★☆：激アツ（+30%〜+50%）
- ★★★☆☆：有望（+15%〜+30%）
- ★★☆☆☆：普通（+5%〜+15%）
- ★☆☆☆☆：トントン（0%〜+5%）

### 🆕 M&A予兆スコア
- 🔴 **70点以上**：緊急
- 🟠 **50〜69点**：高
- 🟡 **30〜49点**：中
- 🟢 **15〜29点**：低
""")

    st.subheader("🔢 銘柄入力")
    raw_text = st.text_area("証券コードを入力（スペース区切り）", height=100, placeholder="例：7203 9984 285A", key="analysis_input")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        run_btn = st.button("🚀 AIで分析開始！", type="primary", key="run_analysis")
    with col2:
        run_with_ma = st.checkbox("M&A予兆分析も実行", value=False, key="with_ma")
    
    st.divider()

    if "analysis_bundle" not in st.session_state:
        st.session_state["analysis_bundle"] = None
    if "analysis_codes" not in st.session_state:
        st.session_state["analysis_codes"] = []
    if "ma_scores" not in st.session_state:
        st.session_state["ma_scores"] = {}

    if run_btn:
        codes = sanitize_codes(raw_text.split())
        if not codes:
            st.error("証券コードが入力されていません。")
            st.stop()

        with st.spinner("🚀 分析中..."):
            try:
                bundle = fv.calc_genta_bundle(codes)
                st.session_state["analysis_bundle"] = bundle
                st.session_state["analysis_codes"] = codes
                
                ma_scores_dict = {}
                if run_with_ma:
                    with st.spinner("🎯 M&A予兆分析中..."):
                        stock_data_list = [bundle.get(code, {}) for code in codes]
                        ma_results = ma.batch_analyze_ma(stock_data_list, with_news=True)
                        for score in ma_results:
                            ma_scores_dict[score.code] = score
                else:
                    for code in codes:
                        data = bundle.get(code, {})
                        if data.get("name") != "存在しない銘柄":
                            score = ma.analyze_ma_potential(
                                code=code, name=data.get("name", ""), price=data.get("price"), pbr=None,
                                upside_pct=data.get("upside_pct"), market_cap=data.get("market_cap"),
                                volume_ratio=data.get("volume_ratio"), turnover_pct=data.get("turnover_pct"),
                                turnover_5d_pct=None, signal_icon=data.get("signal_icon", "—"), skip_news=True
                            )
                            ma_scores_dict[code] = score
                st.session_state["ma_scores"] = ma_scores_dict
            except Exception as e:
                st.error(f"エラー: {e}")
                st.stop()

    if st.session_state["analysis_bundle"]:
        bundle = st.session_state["analysis_bundle"]
        codes = st.session_state["analysis_codes"]
        ma_scores = st.session_state.get("ma_scores", {})
        
        df = bundle_to_df(bundle, codes, ma_scores)
        
        st.subheader("📊 分析結果")
        st.info("💡 「詳細」列のチェックでチャート表示")
        
        styled_df = df.style.map(highlight_errors, subset=["銘柄名"]).map(highlight_rank_color, subset=["ランク"]).map(highlight_ma_score, subset=["M&A予兆"])
        
        edited_df = st.data_editor(
            styled_df, use_container_width=True, hide_index=True,
            column_config={
                "詳細": st.column_config.CheckboxColumn("詳細", help="チャート表示", default=False),
                "ランク": st.column_config.TextColumn("ランク", width="small"),
                "M&A予兆": st.column_config.TextColumn("M&A予兆", width="small"),
            },
            disabled=[c for c in df.columns if c != "詳細"]
        )
        
        selected_rows = edited_df[edited_df["詳細"] == True]
        if not selected_rows.empty:
            for _, row in selected_rows.iterrows():
                code = row["証券コード"]
                ticker_data = bundle.get(code)
                if ticker_data and ticker_data.get("name") != "存在しない銘柄" and ticker_data.get("hist_data") is not None:
                    st.divider()
                    st.markdown(f"### 📉 詳細：{ticker_data.get('name')}")
                    draw_wall_chart(ticker_data)
                    if code in ma_scores and ma_scores[code].total_score >= 30:
                        ms = ma_scores[code]
                        st.markdown("#### 🎯 M&A予兆詳細")
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("ニュース", f"{ms.news_score}/40")
                        c2.metric("出来高", f"{ms.volume_score}/30")
                        c3.metric("バリュエーション", f"{ms.valuation_score}/20")
                        c4.metric("テクニカル", f"{ms.technical_score}/10")
                        if ms.news_items:
                            st.markdown("**📰 関連ニュース**")
                            for news in ms.news_items[:5]:
                                st.markdown(f"- {news.title}")

# ==========================================
# タブ2: M&A予兆監視
# ==========================================
with tab2:
    st.subheader("🎯 M&A予兆監視")
    
    st.markdown("""
| 要素 | 配点 | 内容 |
|------|------|------|
| 📰 ニュース | 最大40点 | TOB、完全子会社化等のキーワード検知 |
| 📈 出来高 | 最大30点 | 出来高急増、浮動株回転率 |
| 💰 バリュエーション | 最大20点 | PBR、時価総額、割安度 |
| 📊 テクニカル | 最大10点 | RSI、移動平均、ボリンジャー |
""")
    
    st.divider()
    st.markdown("### 📋 監視リスト")
    
    watchlist = st.session_state.get("watchlist", [])
    
    col1, col2 = st.columns([3, 1])
    with col1:
        new_codes = st.text_input("監視銘柄を追加", placeholder="例: 7203 9984 6758", key="add_watchlist")
    with col2:
        if st.button("➕ 追加", key="add_btn"):
            if new_codes:
                new_list = sanitize_codes(new_codes.split())
                for code in new_list:
                    if code not in watchlist:
                        watchlist.append(code)
                st.session_state["watchlist"] = watchlist
                notifier.save_watchlist(watchlist)
                st.success(f"{len(new_list)}件追加")
                st.rerun()
    
    if watchlist:
        st.markdown(f"**監視中**: {', '.join(watchlist)}")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("🔍 M&A分析実行", type="primary", key="analyze_watchlist"):
                with st.spinner("🎯 分析中..."):
                    try:
                        bundle = fv.calc_genta_bundle(watchlist)
                        stock_data_list = [bundle.get(code, {}) for code in watchlist]
                        ma_results = ma.batch_analyze_ma(stock_data_list, with_news=True)
                        st.session_state["watchlist_results"] = ma_results
                        st.session_state["watchlist_bundle"] = bundle
                        
                        config = st.session_state.get("notification_config", notifier.NotificationConfig())
                        if config.enabled:
                            alert_scores = [s for s in ma_results if s.total_score >= config.min_score_threshold]
                            if alert_scores:
                                results = notifier.send_ma_alert(config, alert_scores)
                                for r in results:
                                    if r.success:
                                        st.success(f"✅ {r.message}")
                                    else:
                                        st.warning(f"⚠️ {r.message}")
                    except Exception as e:
                        st.error(f"エラー: {e}")
        with col2:
            if st.button("🗑️ クリア", key="clear_watchlist"):
                st.session_state["watchlist"] = []
                notifier.save_watchlist([])
                st.rerun()
    else:
        st.info("監視銘柄がありません")
    
    if "watchlist_results" in st.session_state and st.session_state["watchlist_results"]:
        st.divider()
        st.markdown("### 📊 分析結果")
        for score in st.session_state["watchlist_results"]:
            level_class = {"🔴 緊急": "ma-critical", "🟠 高": "ma-high", "🟡 中": "ma-medium"}.get(score.signal_level.value, "ma-low")
            st.markdown(f'<div class="{level_class}"><strong>{score.signal_level.value} {score.name}（{score.code}）- {score.total_score}点</strong><br>{" ".join(score.reason_tags)}</div>', unsafe_allow_html=True)
            with st.expander(f"📋 {score.code} 詳細"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("ニュース", f"{score.news_score}/40")
                c2.metric("出来高", f"{score.volume_score}/30")
                c3.metric("バリュエーション", f"{score.valuation_score}/20")
                c4.metric("テクニカル", f"{score.technical_score}/10")
                if score.matched_keywords:
                    st.markdown(f"**キーワード**: {', '.join(score.matched_keywords)}")
                if score.news_items:
                    st.markdown("**📰 ニュース**")
                    for news in score.news_items[:5]:
                        st.markdown(f"- {news.title}")

# ==========================================
# タブ3: 通知設定
# ==========================================
with tab3:
    st.subheader("🔔 通知設定")
    
    config = st.session_state.get("notification_config", notifier.NotificationConfig())
    
    st.markdown("### ⚙️ 基本設定")
    enabled = st.toggle("通知を有効にする", value=config.enabled, key="notify_enabled")
    
    col1, col2 = st.columns(2)
    with col1:
        min_score = st.slider("通知する最低スコア", 0, 100, config.min_score_threshold, key="min_score")
    with col2:
        critical_only = st.checkbox("緊急レベルのみ通知", value=config.notify_critical_only, key="critical_only")
    
    st.divider()
    
    st.markdown("### 📱 LINE Notify設定")
    st.markdown("[LINE Notify](https://notify-bot.line.me/ja/)でトークンを取得してください。")
    
    line_enabled = st.toggle("LINE通知を有効にする", value=config.line_enabled, key="line_enabled")
    line_token = st.text_input("LINE Notifyトークン", value=config.line_token, type="password", key="line_token")
    
    if line_enabled and line_token:
        if st.button("📱 LINE通知テスト", key="test_line"):
            result = notifier.send_line_notify(line_token, "🔔 源太AI テスト通知です！")
            if result.success:
                st.success("✅ 成功！")
            else:
                st.error(f"❌ {result.message}")
    
    st.divider()
    
    st.markdown("### 📧 メール通知設定")
    st.markdown("Gmailは[アプリパスワード](https://myaccount.google.com/apppasswords)が必要です。")
    
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
            if st.button("📧 メール通知テスト", key="test_email"):
                result = notifier.send_email(email_address, "🔔 源太AI テスト通知", "テスト通知です。", smtp_server, int(smtp_port), smtp_user, smtp_password)
                if result.success:
                    st.success("✅ 成功！")
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
            enabled=enabled, email_enabled=email_enabled,
            email_address=email_address if email_enabled else config.email_address,
            smtp_server=smtp_server if email_enabled else config.smtp_server,
            smtp_port=int(smtp_port) if email_enabled else config.smtp_port,
            smtp_user=smtp_user if email_enabled else config.smtp_user,
            smtp_password=smtp_password if email_enabled else config.smtp_password,
            line_enabled=line_enabled, line_token=line_token,
            min_score_threshold=min_score, notify_critical_only=critical_only,
        )
        notifier.save_notification_config(new_config)
        st.session_state["notification_config"] = new_config
        st.success("✅ 保存しました！")

# ==========================================
# 管理者メニュー
# ==========================================
st.divider()
with st.expander("🔧 管理者専用メニュー"):
    admin_input = st.text_input("管理者コード", type="password", key="admin_pass")
    if admin_input == ADMIN_CODE:
        st.success("認証OK")
        if st.button("🗑️ キャッシュ全削除", type="primary"):
            st.cache_data.clear()
            st.success("削除完了！")
            time.sleep(1)
            st.rerun()
