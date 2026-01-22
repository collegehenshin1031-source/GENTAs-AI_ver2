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
# 🔑 パスワード設定
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
            
            /* 文字色を黒(#31333F)に固定 */
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
            
            /* ★スマホ対策：プレースホルダー（入力例）の色を強制的に濃くする */
            ::placeholder {
                color: #888888 !important;
                opacity: 1; /* Firefox対策 */
            }
            :-ms-input-placeholder {
                color: #888888 !important;
            }
            ::-ms-input-placeholder {
                color: #888888 !important;
            }
            
            /* M&Aスコア用のカスタムスタイル */
            .ma-critical { background-color: #fee2e2; border-left: 4px solid #ef4444; padding: 10px; margin: 5px 0; border-radius: 4px; }
            .ma-high { background-color: #ffedd5; border-left: 4px solid #f97316; padding: 10px; margin: 5px 0; border-radius: 4px; }
            .ma-medium { background-color: #fef9c3; border-left: 4px solid #eab308; padding: 10px; margin: 5px 0; border-radius: 4px; }
            .ma-low { background-color: #dcfce7; border-left: 4px solid #22c55e; padding: 10px; margin: 5px 0; border-radius: 4px; }
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# -----------------------------
# 🔐 認証
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
# 📈 チャート描画関数
# -----------------------------
def draw_wall_chart(ticker_data: Dict[str, Any]):
    hist = ticker_data.get("hist_data")
    if hist is None or hist.empty:
        st.warning("チャートデータがありません（取得失敗）")
        return

    name = ticker_data.get("name", "Unknown")
    code = ticker_data.get("code", "----")
    current_price = ticker_data.get("price", 0)

    hist = hist.reset_index()
    hist['Date'] = pd.to_datetime(hist.iloc[:, 0]).dt.tz_localize(None)

    # --- 1. 価格帯別出来高の集計 ---
    bins = 50
    p_min = min(hist['Close'].min(), current_price * 0.9)
    p_max = max(hist['Close'].max(), current_price * 1.1)
    bin_edges = np.linspace(p_min, p_max, bins)
    hist['bin'] = pd.cut(hist['Close'], bins=bin_edges)
    vol_profile = hist.groupby('bin', observed=False)['Volume'].sum()

    # --- 2. 抵抗線・支持線のロジック ---
    upper_candidates = []
    lower_candidates = []

    for interval, volume in vol_profile.items():
        mid_price = interval.mid
        if volume == 0: continue
        
        if mid_price > current_price:
            upper_candidates.append({'vol': volume, 'price': mid_price})
        else:
            lower_candidates.append({'vol': volume, 'price': mid_price})

    # 赤（上値抵抗線）：出来高最大 > 価格低い方
    if upper_candidates:
        best_red = sorted(upper_candidates, key=lambda x: (-x['vol'], x['price']))[0]
        resistance_price = best_red['price']
    else:
        resistance_price = hist['High'].max()

    # 青（下値支持線）：出来高最大 > 価格高い方
    if lower_candidates:
        best_blue = sorted(lower_candidates, key=lambda x: (-x['vol'], -x['price']))[0]
        support_price = best_blue['price']
    else:
        support_price = hist['Low'].min()

    # --- バーの色分け ---
    bar_colors = []
    for interval in vol_profile.index:
        if interval.mid > current_price:
            bar_colors.append('rgba(255, 82, 82, 0.4)')
        else:
            bar_colors.append('rgba(33, 150, 243, 0.4)')

    fig = make_subplots(
        rows=1, cols=2, 
        shared_yaxes=True, 
        column_widths=[0.75, 0.25], 
        horizontal_spacing=0.02,
        subplot_titles=("📉 トレンド分析", "🧱 需給の壁（価格帯別出来高）")
    )

    # 1. ローソク足
    fig.add_trace(go.Candlestick(
        x=hist['Date'], open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], 
        name='株価'
    ), row=1, col=1)

    # 2. 出来高プロファイル
    fig.add_trace(go.Bar(
        x=vol_profile.values, y=[i.mid for i in vol_profile.index], 
        orientation='h', marker_color=bar_colors, name='出来高'
    ), row=1, col=2)

    # --- ライン描画 ---
    fig.add_hline(
        y=resistance_price, 
        line_color="#ef4444", 
        line_width=2,
        annotation_text="🟥 上値抵抗線（抜ければ激アツ）", 
        annotation_position="top left",
        annotation_font_color="#ef4444",
        row=1, col=1
    )

    fig.add_hline(
        y=support_price, 
        line_color="#3b82f6", 
        line_width=2,
        annotation_text="🟦 下値支持線（割れれば即逃げ）", 
        annotation_position="bottom left",
        annotation_font_color="#3b82f6",
        row=1, col=1
    )

    # レイアウトで「強制ホワイト化」を指定
    fig.update_layout(
        title=f"📊 {name} ({code})", 
        height=450, 
        showlegend=False, 
        xaxis_rangeslider_visible=False, 
        margin=dict(l=10, r=10, t=60, b=10), 
        dragmode=False,
        template="plotly_white",
        paper_bgcolor='white',
        plot_bgcolor='white',
        font=dict(color='black')
    )
    fig.update_xaxes(fixedrange=True) 
    fig.update_yaxes(fixedrange=True)

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'staticPlot': False, 'scrollZoom': False}, theme=None)

# ==========================================
# メイン処理
# ==========================================
def sanitize_codes(raw_codes: List[str]) -> List[str]:
    cleaned: List[str] = []
    for x in raw_codes:
        if x is None: continue
        s = str(x).strip()
        s = unicodedata.normalize('NFKC', s)
        s = s.upper().replace(" ", "").replace(",", "")
        if not s: continue
        m = re.search(r"[0-9A-Z]{4}", s)
        if m: cleaned.append(m.group(0))
    uniq: List[str] = []
    for c in cleaned:
        if c not in uniq: uniq.append(c)
    return uniq

# ★フォーマット関数
def fmt_yen(x):
    if x is None or pd.isna(x) or str(x).lower() == 'nan': return "—"
    try: return f"{float(x):,.0f} 円"
    except: return "—"
def fmt_pct(x):
    if x is None or pd.isna(x) or str(x).lower() == 'nan': return "—"
    try: return f"{float(x):.2f}%"
    except: return "—"
def fmt_market_cap(x):
    if x is None or pd.isna(x) or str(x).lower() == 'nan': return "—"
    try:
        v = float(x)
        if v >= 1e12: return f"{v/1e12:.2f} 兆円"
        elif v >= 1e8: return f"{v/1e8:.0f} 億円"
        else: return f"{v:,.0f} 円"
    except: return "—"
def fmt_big_prob(x):
    if x is None or pd.isna(x) or str(x).lower() == 'nan': return "—"
    try:
        v = float(x)
        if v >= 80: return f"🔥 {v:.0f}%" 
        if v >= 60: return f"⚡ {v:.0f}%" 
        if v >= 40: return f"👀 {v:.0f}%" 
        return f"{v:.0f}%"
    except: return "—"

# ★フォーマット＆状態判定：浮動株・激動率（回転率）
def fmt_turnover(x):
    if x is None or pd.isna(x): return "—"
    try:
        v = float(x)
        if v >= 10.0: return f"🌪️ {v:.1f}% (激震)"
        if v >= 5.0: return f"⚡ {v:.1f}% (活況)"
        if v < 1.0: return f"☁ {v:.1f}% (閑散)"
        return f"{v:.1f}% (通常)"
    except: return "—"

# ★フォーマット＆状態判定：異常・着火倍率（出来高倍率）
def fmt_vol_ratio(x):
    if x is None or pd.isna(x): return "—"
    try:
        v = float(x)
        if v >= 5.0: return f"🔥 {v:.1f}倍 (緊急)"
        if v >= 3.0: return f"🚀 {v:.1f}倍 (着火)"
        if v >= 2.0: return f"⚡ {v:.1f}倍 (予兆)"
        return f"{v:.1f}倍 (通常)"
    except: return "—"

# ★M&Aスコアのフォーマット
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

# ★ランクの色分け関数
def highlight_rank_color(val):
    if val == "SSS":
        return 'background-color: #FFD700; color: #000000; font-weight: bold;'
    elif val == "SS":
        return 'background-color: #FF4500; color: #ffffff; font-weight: bold;'
    elif val == "S":
        return 'background-color: #FF69B4; color: #ffffff; font-weight: bold;'
    elif val == "A":
        return 'background-color: #22c55e; color: #ffffff; font-weight: bold;'
    elif val == "B":
        return 'background-color: #3b82f6; color: #ffffff; font-weight: bold;'
    elif val == "C":
        return 'background-color: #94a3b8; color: #ffffff; font-weight: bold;'
    elif val in ["D", "E"]:
        return 'background-color: #a855f7; color: #ffffff; font-weight: bold;'
    return ''

# ★M&Aスコアの色分け関数
def highlight_ma_score(val):
    if "🔴" in str(val):
        return 'background-color: #fee2e2; color: #dc2626; font-weight: bold;'
    elif "🟠" in str(val):
        return 'background-color: #ffedd5; color: #ea580c; font-weight: bold;'
    elif "🟡" in str(val):
        return 'background-color: #fef9c3; color: #ca8a04; font-weight: bold;'
    elif "🟢" in str(val):
        return 'background-color: #dcfce7; color: #16a34a; font-weight: bold;'
    return ''

# ★ランク付け用のスコア計算関数
def calculate_score_and_rank(row):
    score = 0
    up = row.get('upside_pct_num', 0)
    if pd.isna(up): up = 0
    if up >= 50: score += 40
    elif up >= 30: score += 30
    elif up >= 15: score += 20
    elif up > 0: score += 10
    
    prob = row.get('prob_num', 0)
    if pd.isna(prob): prob = 0
    if prob >= 80: score += 30
    elif prob >= 60: score += 20
    elif prob >= 40: score += 10
    
    growth = row.get('growth_num', 0)
    if pd.isna(growth): growth = 0
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
    rows: List[Dict[str, Any]] = []
    if isinstance(bundle, dict):
        for code in codes:
            v = bundle.get(code)
            if isinstance(v, dict):
                if v.get("note") == "データ取得不可(Yahoo拒否)" or v.get("name") == "エラー" or v.get("name") == "計算エラー":
                      v["name"] = "存在しない銘柄"
                      v["note"] = "—"
                      v["volume_wall"] = "—"
                      v["signal_icon"] = "—"
                      v["weather"] = "—"
                      v["turnover_pct"] = None
                      v["volume_ratio"] = None
                if v.get("note") == "ETF/REIT対象外":
                      v["note"] = "ETF/REITのため対象外"
                row = {"ticker": code, **v}
                
                # M&Aスコアを追加
                if ma_scores and code in ma_scores:
                    ma_score = ma_scores[code]
                    row["ma_score"] = ma_score.total_score
                    row["ma_signal"] = ma_score.signal_level.value
                    row["ma_tags"] = " ".join(ma_score.reason_tags) if ma_score.reason_tags else ""
                else:
                    row["ma_score"] = None
                    row["ma_signal"] = ""
                    row["ma_tags"] = ""
            else:
                row = {"ticker": code, "name": "存在しない銘柄", "note": "—", "value": v, 
                       "ma_score": None, "ma_signal": "", "ma_tags": ""}
            rows.append(row)
    else:
        rows.append({"ticker": ",".join(codes), "name": "存在しない銘柄", "note": "—", "value": bundle,
                     "ma_score": None, "ma_signal": "", "ma_tags": ""})

    df = pd.DataFrame(rows)
    # ★カラム追加
    cols = ["name", "weather", "price", "fair_value", "upside_pct", "dividend", "dividend_amount", 
            "growth", "market_cap", "big_prob", "note", "signal_icon", "volume_wall",
            "turnover_pct", "volume_ratio", "ma_score", "ma_signal", "ma_tags"]
            
    for col in cols:
        if col not in df.columns: df[col] = None

    def _as_float(x):
        try: return float(x)
        except: return None
        
    df["price_num"] = df["price"].apply(_as_float)
    df["fair_value_num"] = df["fair_value"].apply(_as_float)
    df["upside_pct_num"] = df["upside_pct"].apply(_as_float)
    df["upside_yen_num"] = df["fair_value_num"] - df["price_num"]
    df["div_num"] = df["dividend"].apply(_as_float)
    df["div_amount_num"] = df["dividend_amount"].apply(_as_float)
    df["growth_num"] = df["growth"].apply(_as_float)
    df["mc_num"] = df["market_cap"].apply(_as_float)
    df["prob_num"] = df["big_prob"].apply(_as_float)
    
    df["rating"] = df["upside_pct_num"].apply(calc_rating_from_upside)
    df["stars"] = df["rating"].apply(to_stars)
    
    error_mask = df["name"] == "存在しない銘柄"
    df.loc[error_mask, "stars"] = "—"
    df.loc[error_mask, "price"] = None
    df.loc[error_mask, "fair_value"] = None 
    df.loc[error_mask, "note"] = "—"

    df["ランク"] = df.apply(calculate_score_and_rank, axis=1)
    df.loc[error_mask, "ランク"] = "—"
    
    df["根拠【グレアム数】"] = df["note"].fillna("—")

    df["証券コード"] = df["ticker"]
    df["銘柄名"] = df["name"].fillna("—")
    df["業績"] = df["weather"].fillna("—")
    df["現在値"] = df["price"].apply(fmt_yen)
    df["理論株価"] = df["fair_value"].apply(fmt_yen)
    df["上昇余地"] = df["upside_pct_num"].apply(fmt_pct)
    df["評価"] = df["stars"]
    df["売買"] = df["signal_icon"].fillna("—")
    df["需給の壁 (価格帯別出来高)"] = df["volume_wall"].fillna("—")
    df["配当利回り"] = df["div_num"].apply(fmt_pct)
    df["年間配当"] = df["div_amount_num"].apply(fmt_yen)
    df["事業の勢い"] = df["growth_num"].apply(fmt_pct)
    df["時価総額"] = df["mc_num"].apply(fmt_market_cap)
    df["大口介入"] = df["prob_num"].apply(fmt_big_prob)
    
    # ★名称変更とフォーマット適用
    df["浮動株・激動率"] = df["turnover_pct"].apply(fmt_turnover)
    df["異常・着火倍率"] = df["volume_ratio"].apply(fmt_vol_ratio)
    
    # ★M&Aスコア
    df["M&A予兆"] = df["ma_score"].apply(fmt_ma_score)
    df["M&Aタグ"] = df["ma_tags"].fillna("")

    df.index = df.index + 1
    df["詳細"] = False
    
    # ★カラム配置の変更（M&A予兆を追加）
    show_cols = [
        "ランク", "証券コード", "銘柄名", "現在値", "理論株価", "上昇余地", "評価", "売買", 
        "M&A予兆", "M&Aタグ",
        "需給の壁 (価格帯別出来高)", "詳細", 
        "配当利回り", "年間配当", "事業の勢い", "業績", 
        "時価総額", "大口介入", "浮動株・激動率", "異常・着火倍率", "根拠【グレアム数】"
    ]
    
    return df[show_cols]

# ==========================================
# 通知設定の初期化
# ==========================================
def init_notification_config():
    if "notification_config" not in st.session_state:
        st.session_state["notification_config"] = notifier.load_notification_config()
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = notifier.load_watchlist()

init_notification_config()

# ==========================================
# メイン画面構築
# ==========================================
st.title("源太ＡＩ🤖ハゲタカＳＣＯＰＥ")

# タブを作成
tab1, tab2, tab3 = st.tabs(["📈 銘柄分析", "🎯 M&A予兆監視", "🔔 通知設定"])

# ==========================================
# タブ1: 銘柄分析（既存機能）
# ==========================================
with tab1:
    with st.expander("★ ランク・評価基準の見方（クリックで詳細を表示）", expanded=False):
        st.markdown("""
### 👑 総合ランク（SSS〜E）
理論株価の上昇余地だけでなく、**「大口の動き」「事業の成長性」「財務の安全性」**を総合的にスコア化（100点満点）した格付けです。
- 🟨 **SSS (95-100点)**：**神**。全ての条件が揃った奇跡の銘柄。
- 🟧 **SS (90-94点)**：**最強**。ほぼ死角なし。
- 🟪 **S (85-89点)**：**超優秀**。文句なしの買い候補。
- 🟩 **A (75-84点)**：**優良**。合格点。
- 🟦 **B (60-74点)**：**普通**。悪くはない。
- 🟪 **C〜E**：**微妙〜注意**。

### 1. 割安度評価（★）
**理論株価**（本来の実力）と **現在値** を比較した「お得度」です。
- :red[★★★★★：**お宝**（上昇余地 **+50%** 以上）]
- ★★★★☆：**激アツ**（上昇余地 **+30%** 〜 +50%）
- ★★★☆☆：**有望**（上昇余地 **+15%** 〜 +30%）
- ★★☆☆☆：**普通**（上昇余地 **+5%** 〜 +15%）
- ★☆☆☆☆：**トントン**（上昇余地 **0%** 〜 +5%）
- ☆☆☆☆☆：**割高**（上昇余地 **0% 未満**）

### 2. 売買シグナル（矢印）
| 表示 | 意味 | 判定ロジック |
| :--- | :--- | :--- |
| **↑◎** | **激熱** | **「底値圏」＋「売られすぎ」＋「上昇トレンド」** 等の好条件が3つ以上重なった最強の買い場！ |
| **↗〇** | **買い** | 複数のプラス要素あり。打診買いのチャンス。 |
| **→△** | **様子見** | 可もなく不可もなく。方向感が出るまで待つのが無難。 |
| **↘▲** | **売り** | 天井圏や下落トレンド入り。利益確定や損切りの検討を。 |
| **↓✖** | **危険** | **「買われすぎ」＋「暴落シグナル」** 等が点灯。手を出してはいけない。 |

### 3. 需給の壁（突破力）
**過去6ヶ月間で最も取引が活発だった価格帯（しこり玉・岩盤）** です。
この壁は**「跳ね返される場所（反転）」**であると同時に、**「抜けた後の加速装置（突破）」**でもあります。
- **🚧 上壁（戻り売り圧力）**
    - **【基本】** ここまでは上がっても叩き落とされやすい（抵抗線）。
    - **【突破】** しかしここを食い破れば、売り手不在の**「青天井」**モード突入！
- **🛡️ 下壁（押し目買い支持）**
    - **【基本】** ここで下げ止まって反発しやすい（支持線）。
    - **【割込】** しかしここを割り込むと、ガチホ勢が全員含み損になり**「パニック売り」**が連鎖する恐れあり。
- **🔥 激戦中（分岐点）**
    - まさに今、その壁の中で戦っている。突破するか、跳ね返されるか、要注目！

### 4. ハゲタカ・ハント指標（大口検知）
- **🌪️ 「浮動株・激動率」とは？**
    - ただの出来高ではありません。**「市場で実際に売買可能な株（浮動株）」**に対して、どれだけ注文が殺到したかを監視します。
    - **数値が高い（10%以上）**：たった1日で浮動株の1割以上が持ち主を変えた異常事態。**「大口が根こそぎ集めている」**可能性大！
- **🔥 「異常・着火倍率」とは？**
    - 「普段の静かな状態（過去20日平均）」と比べて、今日どれだけ突然取引が増えたかを表します。
    - **倍率が高い（3倍〜5倍）**：今まで見向きもされなかった銘柄に、突如として資金が流入した**「初動（着火）」**の合図です。

### 5. 🆕 M&A予兆スコア
**「親会社による完全子会社化」「TOB」「MBO」等のM&Aの可能性**を数値化したスコアです。
- 🔴 **70点以上**：**緊急**。M&A関連ニュースが検知されています！
- 🟠 **50〜69点**：**高**。要注目。出来高異常や割安評価が重なっています。
- 🟡 **30〜49点**：**中**。一部シグナルあり。継続監視推奨。
- 🟢 **15〜29点**：**低**。現時点では目立ったシグナルなし。
- ⚪ **14点以下**：**なし**。M&A兆候は検出されていません。
""", unsafe_allow_html=True) 

    st.subheader("🔢 銘柄入力")
    raw_text = st.text_area("分析したい証券コードを入力してください（※記入例：7203 9984）", height=100, placeholder="例：\n7203\n9984\n285A", key="analysis_input")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        run_btn = st.button("🚀 AIで分析開始！", type="primary", key="run_analysis")
    with col2:
        run_with_ma = st.checkbox("M&A予兆分析も実行（時間がかかります）", value=False, key="with_ma")
    
    st.divider()

    if "analysis_bundle" not in st.session_state:
        st.session_state["analysis_bundle"] = None
    if "analysis_codes" not in st.session_state:
        st.session_state["analysis_codes"] = []
    if "ma_scores" not in st.session_state:
        st.session_state["ma_scores"] = {}

    if run_btn:
        raw_codes = raw_text.split()
        codes = sanitize_codes(raw_codes)
        if not codes:
            st.error("証券コードが入力されていません。")
            st.stop()

        with st.spinner(f"🚀 高速分析中..."):
            try:
                bundle = fv.calc_genta_bundle(codes)
                st.session_state["analysis_bundle"] = bundle
                st.session_state["analysis_codes"] = codes
                
                # M&A予兆分析
                if run_with_ma:
                    with st.spinner("🎯 M&A予兆分析中...（ニュース取得のため時間がかかります）"):
                        ma_scores_dict = {}
                        stock_data_list = [bundle.get(code, {}) for code in codes]
                        ma_results = ma.batch_analyze_ma(stock_data_list, with_news=True)
                        for score in ma_results:
                            ma_scores_dict[score.code] = score
                        st.session_state["ma_scores"] = ma_scores_dict
                else:
                    # ニュースなしで簡易M&A分析
                    ma_scores_dict = {}
                    for code in codes:
                        data = bundle.get(code, {})
                        if data.get("name") != "存在しない銘柄":
                            score = ma.analyze_ma_potential(
                                code=code,
                                name=data.get("name", ""),
                                price=data.get("price"),
                                pbr=None,
                                upside_pct=data.get("upside_pct"),
                                market_cap=data.get("market_cap"),
                                volume_ratio=data.get("volume_ratio"),
                                turnover_pct=data.get("turnover_pct"),
                                turnover_5d_pct=None,
                                signal_icon=data.get("signal_icon", "—"),
                                skip_news=True
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
        st.info("💡 **「詳細」** 列のチェックボックスをONにすると、下に詳細チャートが表示されます！（複数選択OK）")
        
        styled_df = df.style.map(highlight_errors, subset=["銘柄名"])\
                            .map(highlight_rank_color, subset=["ランク"])\
                            .map(highlight_ma_score, subset=["M&A予兆"])
        
        edited_df = st.data_editor(
            styled_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "詳細": st.column_config.CheckboxColumn(
                    "詳細",
                    help="チャートを表示",
                    default=False,
                ),
                "ランク": st.column_config.TextColumn(
                    "ランク",
                    help="総合スコア評価（SSS〜E）",
                    width="small"
                ),
                "M&A予兆": st.column_config.TextColumn(
                    "M&A予兆",
                    help="M&A予兆スコア（0-100点）",
                    width="small"
                ),
                "証券コード": st.column_config.TextColumn(disabled=True),
                "銘柄名": st.column_config.TextColumn(disabled=True),
            },
            disabled=["ランク", "証券コード", "銘柄名", "現在値", "理論株価", "上昇余地", "評価", "売買", 
                     "M&A予兆", "M&Aタグ", "需給の壁 (価格帯別出来高)", "配当利回り", "年間配当", 
                     "事業の勢い", "業績", "時価総額", "大口介入", "根拠【グレアム数】", "浮動株・激動率", "異常・着火倍率"]
        )
        
        selected_rows = edited_df[edited_df["詳細"] == True]
        
        if not selected_rows.empty:
            for _, row in selected_rows.iterrows():
                selected_code = row["証券コード"]
                ticker_data = bundle.get(selected_code)
                
                if ticker_data and ticker_data.get("name") != "存在しない銘柄" and ticker_data.get("hist_data") is not None:
                    st.divider()
                    st.markdown(f"### 📉 詳細分析チャート：{ticker_data.get('name')}")
                    draw_wall_chart(ticker_data)
                    
                    # M&A詳細情報を表示
                    if selected_code in ma_scores:
                        ma_score = ma_scores[selected_code]
                        if ma_score.total_score >= 30:
                            st.markdown(f"#### 🎯 M&A予兆詳細")
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("ニュース", f"{ma_score.news_score}/40点")
                            with col2:
                                st.metric("出来高異常", f"{ma_score.volume_score}/30点")
                            with col3:
                                st.metric("バリュエーション", f"{ma_score.valuation_score}/20点")
                            with col4:
                                st.metric("テクニカル", f"{ma_score.technical_score}/10点")
                            
                            if ma_score.news_items:
                                st.markdown("**📰 関連ニュース**")
                                for news in ma_score.news_items[:5]:
                                    st.markdown(f"- {news.title}")

        st.info("""
        **※ 評価が表示されない（—）銘柄について**
        赤字決算や財務データが不足している銘柄は、投資リスクの観点から自動的に **「評価対象外」** としています。
        ただし、**「今は赤字だが来期は黒字予想」の場合は、自動的に『予想EPS』を使って理論株価を算出**しています。
        """)

# ==========================================
# タブ2: M&A予兆監視
# ==========================================
with tab2:
    st.subheader("🎯 M&A予兆監視")
    
    st.markdown("""
    **M&A予兆検知の仕組み**
    
    以下の要素を組み合わせて、M&A（完全子会社化・TOB・MBO等）の可能性をスコアリングします：
    
    | 要素 | 配点 | 検知内容 |
    |------|------|----------|
    | 📰 ニュース分析 | 最大40点 | 「TOB」「完全子会社化」等のキーワード検知 |
    | 📈 出来高異常 | 最大30点 | 出来高急増、浮動株回転率の異常 |
    | 💰 バリュエーション | 最大20点 | PBR低位、買収適正サイズ、割安度 |
    | 📊 テクニカル | 最大10点 | RSI、移動平均線、ボリンジャーバンド |
    """)
    
    st.divider()
    
    # 監視リスト管理
    st.markdown("### 📋 監視リスト")
    
    watchlist = st.session_state.get("watchlist", [])
    
    col1, col2 = st.columns([3, 1])
    with col1:
        new_codes = st.text_input("監視銘柄を追加（スペース区切り）", placeholder="例: 7203 9984 6758", key="add_watchlist")
    with col2:
        if st.button("➕ 追加", key="add_btn"):
            if new_codes:
                new_list = sanitize_codes(new_codes.split())
                for code in new_list:
                    if code not in watchlist:
                        watchlist.append(code)
                st.session_state["watchlist"] = watchlist
                notifier.save_watchlist(watchlist)
                st.success(f"{len(new_list)}件追加しました")
                st.rerun()
    
    if watchlist:
        st.markdown(f"**現在の監視銘柄**: {', '.join(watchlist)}")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("🔍 監視銘柄をM&A分析", type="primary", key="analyze_watchlist"):
                with st.spinner("🎯 M&A予兆分析中..."):
                    try:
                        # まず基本データを取得
                        bundle = fv.calc_genta_bundle(watchlist)
                        
                        # M&A分析
                        stock_data_list = [bundle.get(code, {}) for code in watchlist]
                        ma_results = ma.batch_analyze_ma(stock_data_list, with_news=True)
                        
                        st.session_state["watchlist_results"] = ma_results
                        st.session_state["watchlist_bundle"] = bundle
                        
                        # 通知条件チェック
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
            if st.button("🗑️ リストをクリア", key="clear_watchlist"):
                st.session_state["watchlist"] = []
                notifier.save_watchlist([])
                st.rerun()
    else:
        st.info("監視銘柄がありません。上のフォームから追加してください。")
    
    # 分析結果の表示
    if "watchlist_results" in st.session_state and st.session_state["watchlist_results"]:
        st.divider()
        st.markdown("### 📊 M&A予兆分析結果")
        
        results = st.session_state["watchlist_results"]
        
        for score in results:
            # シグナルレベルに応じたスタイル
            if score.signal_level == ma.MASignalLevel.CRITICAL:
                st.markdown(f"""
                <div class="ma-critical">
                    <strong>🔴 {score.name}（{score.code}）- {score.total_score}点【緊急】</strong><br>
                    {' '.join(score.reason_tags)}
                </div>
                """, unsafe_allow_html=True)
            elif score.signal_level == ma.MASignalLevel.HIGH:
                st.markdown(f"""
                <div class="ma-high">
                    <strong>🟠 {score.name}（{score.code}）- {score.total_score}点【高】</strong><br>
                    {' '.join(score.reason_tags)}
                </div>
                """, unsafe_allow_html=True)
            elif score.signal_level == ma.MASignalLevel.MEDIUM:
                st.markdown(f"""
                <div class="ma-medium">
                    <strong>🟡 {score.name}（{score.code}）- {score.total_score}点【中】</strong><br>
                    {' '.join(score.reason_tags)}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="ma-low">
                    <strong>🟢 {score.name}（{score.code}）- {score.total_score}点【低】</strong>
                </div>
                """, unsafe_allow_html=True)
            
            # 詳細展開
            with st.expander(f"📋 {score.code} の詳細を見る"):
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("ニュース", f"{score.news_score}/40点")
                with col2:
                    st.metric("出来高異常", f"{score.volume_score}/30点")
                with col3:
                    st.metric("バリュエーション", f"{score.valuation_score}/20点")
                with col4:
                    st.metric("テクニカル", f"{score.technical_score}/10点")
                
                if score.matched_keywords:
                    st.markdown(f"**検知キーワード**: {', '.join(score.matched_keywords)}")
                
                if score.news_items:
                    st.markdown("**📰 関連ニュース**")
                    for news in score.news_items[:5]:
                        st.markdown(f"- {news.title}")
                
                if score.exclusion_flags:
                    st.warning(f"⚠️ M&A阻害要因検出: {', '.join(score.exclusion_flags)}")

# ==========================================
# タブ3: 通知設定
# ==========================================
with tab3:
    st.subheader("🔔 通知設定")
    
    st.markdown("""
    M&A予兆が検知された際に、メールで通知を受け取ることができます。
    """)
    
    config = st.session_state.get("notification_config", notifier.NotificationConfig())
    
    # 通知ON/OFF
    st.markdown("### ⚙️ 基本設定")
    enabled = st.toggle("通知を有効にする", value=config.enabled, key="notify_enabled")
    
    col1, col2 = st.columns(2)
    with col1:
        min_score = st.slider("通知する最低スコア", 0, 100, config.min_score_threshold, key="min_score")
    with col2:
        critical_only = st.checkbox("緊急レベルのみ通知", value=config.notify_critical_only, key="critical_only")
    
    st.divider()
    
    # メール設定
    st.markdown("### 📧 メール通知設定")
    st.markdown("""
    Gmailを使用する場合は、[アプリパスワード](https://myaccount.google.com/apppasswords)を設定してください。
    ※通常のGmailパスワードでは送信できません。
    
    **設定手順（Gmail）:**
    1. Googleアカウントの「セキュリティ」→「2段階認証」を有効化
    2. 「アプリパスワード」を生成
    3. 生成された16桁のパスワードを下の「SMTPパスワード」に入力
    """)
    
    email_enabled = st.toggle("メール通知を有効にする", value=config.email_enabled, key="email_enabled")
    
    if email_enabled:
        col1, col2 = st.columns(2)
        with col1:
            email_address = st.text_input("送信先メールアドレス", value=config.email_address, key="email_address")
            smtp_server = st.text_input("SMTPサーバー", value=config.smtp_server, key="smtp_server")
        with col2:
            smtp_user = st.text_input("SMTPユーザー（送信元メールアドレス）", value=config.smtp_user, key="smtp_user")
            smtp_password = st.text_input("SMTPパスワード（Gmailはアプリパスワード）", value=config.smtp_password, type="password", key="smtp_password")
        
        smtp_port = st.number_input("SMTPポート", value=config.smtp_port, key="smtp_port")
        
        if email_address and smtp_user and smtp_password:
            if st.button("📧 メール通知テスト", key="test_email"):
                result = notifier.send_email(
                    to_address=email_address,
                    subject="🔔 源太AI ハゲタカSCOPE テスト通知",
                    body="これはテスト通知です。\n\n通知設定が正常に機能しています。",
                    smtp_server=smtp_server,
                    smtp_port=int(smtp_port),
                    smtp_user=smtp_user,
                    smtp_password=smtp_password
                )
                if result.success:
                    st.success("✅ メール通知テスト成功！")
                else:
                    st.error(f"❌ {result.message}")
    else:
        email_address = config.email_address
        smtp_server = config.smtp_server
        smtp_user = config.smtp_user
        smtp_password = config.smtp_password
        smtp_port = config.smtp_port
    
    st.divider()
    
    # 設定保存
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
            notify_critical_only=critical_only,
        )
        notifier.save_notification_config(new_config)
        st.session_state["notification_config"] = new_config
        st.success("✅ 設定を保存しました！")

# -----------------------------
# ★豆知識コーナー（完全復活・新指標対応）
# -----------------------------
st.divider()
st.subheader("📚 投資の豆知識・用語解説")

with st.expander("📚 【豆知識】理論株価の計算根拠（グレアム数）とは？"):
    st.markdown("""
    ### 🧙‍♂️ "投資の神様"の師匠が考案した「割安株」の黄金式
    このツールで算出している理論株価は、**「グレアム数」** という計算式をベースにしています。
    これは、あの世界最強の投資家 **ウォーレン・バフェットの師匠** であり、「バリュー投資の父」と呼ばれる **ベンジャミン・グレアム** が考案した由緒ある指標です。

    ### 💡 何がすごいの？
    多くの投資家は「利益（PER）」だけで株を見がちですが、グレアム数は **「企業の利益（稼ぐ力）」** と **「純資産（持っている財産）」** の両面から、その企業が本来持っている **「真の実力値（適正価格）」** を厳しく割り出します。

    **今の株価 ＜ 理論株価（グレアム数）** となっていれば、それは **「実力よりも過小評価されている（バーゲンセール中）」** という強力なサインになります。
    """)

with st.expander("🚀 【注目】なぜ「事業の勢い（売上成長率）」を見るの？"):
    st.markdown("""
    ### 📈 株価を押し上げる"真のエンジン"は売上にあり！
    「利益」は経費削減などで一時的に作れますが、**「売上」** の伸びだけは誤魔化せません。売上が伸びているということは、**「その会社の商品が世の中でバカ売れしている」** という最強の証拠だからです。

    ### 📊 成長スピードの目安（より厳しめのプロ基準）
    - **🚀 +30% 以上： 【超・急成長】**
      驚異的な伸びです。将来のスター株候補の可能性がありますが、期待先行で株価が乱高下するリスクも高くなります。
    - **🏃 +10% 〜 +30%： 【成長軌道】**
      安定してビジネスが拡大しています。安心して見ていられる優良企業のラインです。
    - **🚶 0% 〜 +10%： 【安定・成熟】**
      急成長はしていませんが、堅実に稼いでいます。配当狙いの銘柄に多いです。
    - **📉 マイナス： 【衰退・縮小】**
      去年より売れていません。ビジネスモデルの転換期か、斜陽産業の可能性があります。

    ### 💡 分析のポイント 「赤字 × 急成長」の判断について
    本来、赤字企業は投資対象外ですが、「事業の勢い」が **+30%** を超えている場合は、**「将来のシェア獲得のために、あえて広告や研究に大金を投じている（＝今は赤字を掘っている）」** だけの可能性があります。
    ただし、黒字化できないまま倒産するリスクもあるため、上級者向けの「ハイリスク・ハイリターン枠」として慎重に見る必要があります。
    """)

with st.expander("🌊 ファンドや機関（大口）の\"動き\"を検知する先乗り指標"):
    st.markdown("""
    時価総額や出来高の異常検知を組み合わせ、**「大口投資家が仕掛けやすい（買収や買い上げを狙いやすい）条件」** が揃っているかを%で表示します。

    ### 🔍 判定ロジック
    先乗り（先回り）理論、季節性、対角性、テーマ性、ファンド動向、アクティビスト検知、企業成長性など、ニッチ性、株大量保有条件、あらゆる大口介入シグナルを自動で検出する独自ロジックを各項目ごとにポイント制にしてパーセンテージを算出する次世代の指数

    ### 🎯 ゴールデンゾーン（時価総額 500億〜3000億円）
    機関投資家等が一番動きやすく、TOB（買収）のターゲットにもなりやすい「おいしい規模感」。

    ### 📉 PBR 1倍割れ（バーゲンセール）
    「会社を解散して現金を配った方がマシ」という超割安状態。買収の標的にされやすい。

    ### ⚡ 出来高急増（ボリュームスパイク）
    今日の出来高が、普段の平均より2倍以上ある場合、裏で何かが起きている（誰かが集めている）可能性大！
    **独自の先乗り（先回り）法を完全数値化に成功！ 🔥 80%以上は「激アツ」**
    何らかの材料（ニュース）が出る前触れか、水面下で大口が集めている可能性があります。 大口の買い上げこそ暴騰のチャンスです。この指標もしっかりご確認ください。
    """)

with st.expander("🌪️ 【新指標】「浮動株・激動率」の読み方"):
    st.markdown("""
    ### 🌪️ 市場から株が消える前兆を見逃すな！
    「出来高」が多いだけでは意味がありません。重要なのは**「市場で実際に売買できる株（浮動株）」がどれだけ回転したか**です。

    - **🌪️ 10%以上：【激震】**
      たった1日で浮動株の1割以上が持ち主を変えた異常事態。**「大口が根こそぎ集めている」**か、とんでもない材料が出た可能性があります。
    - **⚡ 5%〜10%：【活況】**
      かなり注目されています。デイトレーダーや短期筋が集まっています。
    - **☁ 1%未満：【閑散】**
      誰も見ていません。
    """)

with st.expander("🔥 【新指標】「異常・着火倍率」の読み方"):
    st.markdown("""
    ### 🔥 平凡な日常からの「突然変異」を検知！
    「過去20日間の平均出来高」と「今日の出来高」を比較し、**静けさを破る爆発**を捉えます。

    - **🔥 5倍以上：【緊急事態】**
      普段の5倍以上の注文が殺到しています。何かとんでもないことが起きています（ニュース、仕手化、リーク等）。
    - **🚀 3倍〜5倍：【着火】**
      初動の可能性が高いゾーン。今まで眠っていた株が目覚めた合図です。
    - **⚡ 2倍〜3倍：【予兆】**
      ざわついています。監視リストに入れるべきタイミングです。
    """)

with st.expander("🎯 【新機能】M&A予兆検知の仕組み"):
    st.markdown("""
    ### 🎯 M&A予兆検知とは？
    「親会社による完全子会社化」「TOB（株式公開買付）」「MBO（経営陣による買収）」などの可能性が高い銘柄を自動検知する機能です。

    ### 📊 スコアリング要素
    | 要素 | 配点 | 内容 |
    |------|------|------|
    | **ニュース分析** | 最大40点 | Yahoo!ニュースから「TOB」「完全子会社化」「MBO」等のキーワードを検知 |
    | **出来高異常** | 最大30点 | 出来高急増（着火倍率）、浮動株回転率の異常を検知 |
    | **バリュエーション** | 最大20点 | PBR低位、買収適正サイズ（時価総額）、理論株価との乖離 |
    | **テクニカル** | 最大10点 | RSI・移動平均線・ボリンジャーバンドの総合判定 |

    ### 🚨 シグナルレベル
    - 🔴 **緊急（70点以上）**: M&A関連ニュースが検知されています。要警戒！
    - 🟠 **高（50〜69点）**: 複数の条件が重なっています。注視推奨。
    - 🟡 **中（30〜49点）**: 一部シグナルあり。継続監視を。
    - 🟢 **低（15〜29点）**: 現時点では目立ったシグナルなし。
    - ⚪ **なし（14点以下）**: M&A兆候は検出されていません。

    ### ⚠️ 減点要因
    「大規模自社株買い発表」「買収防衛策導入」などのニュースが検知された場合は、M&Aの障害となるため大幅減点されます。
    """)

# -----------------------------
# 🔧 管理者メニュー
# -----------------------------
st.divider()
with st.expander("🔧 管理者専用メニュー"):
    admin_input = st.text_input("管理者コード", type="password", key="admin_pass_bottom")
    if admin_input == ADMIN_CODE:
        st.success("認証OK")
        if st.button("🗑️ キャッシュ全削除", type="primary"):
            st.cache_data.clear()
            st.success("削除完了！再読み込みします...")
            time.sleep(1)
            st.rerun()
