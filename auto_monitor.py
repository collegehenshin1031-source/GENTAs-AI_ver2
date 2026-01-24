"""
自動M&A予兆監視スクリプト
GitHub Actionsで定期実行され、スコア変化を検知してメール通知を送信する
"""

import os
import json
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import fair_value_calc_y4 as fv
import ma_detector as ma


# ==========================================
# 設定
# ==========================================
WATCHLIST_FILE = "data/watchlist.json"
SCORE_HISTORY_FILE = "data/score_history.json"
CONFIG_FILE = "data/notification_config.json"


@dataclass
class MonitorConfig:
    """監視設定"""
    enabled: bool = True
    email_enabled: bool = False
    email_address: str = ""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    min_score_threshold: int = 50
    notify_on_increase: bool = True  # スコア上昇時に通知
    increase_threshold: int = 15     # 何点以上上昇したら通知するか


def load_watchlist() -> List[str]:
    """監視リストを読み込む"""
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []


def load_score_history() -> Dict[str, Dict]:
    """スコア履歴を読み込む"""
    if os.path.exists(SCORE_HISTORY_FILE):
        try:
            with open(SCORE_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def save_score_history(history: Dict[str, Dict]):
    """スコア履歴を保存"""
    os.makedirs(os.path.dirname(SCORE_HISTORY_FILE), exist_ok=True)
    with open(SCORE_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def load_config() -> MonitorConfig:
    """設定を読み込む（環境変数優先）"""
    config = MonitorConfig()
    
    # ファイルから読み込み
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                config = MonitorConfig(**data)
        except:
            pass
    
    # 環境変数で上書き（GitHub Secrets用）
    if os.environ.get("EMAIL_ENABLED", "").lower() == "true":
        config.email_enabled = True
    if os.environ.get("EMAIL_ADDRESS"):
        config.email_address = os.environ["EMAIL_ADDRESS"]
    if os.environ.get("SMTP_SERVER"):
        config.smtp_server = os.environ["SMTP_SERVER"]
    if os.environ.get("SMTP_PORT"):
        config.smtp_port = int(os.environ["SMTP_PORT"])
    if os.environ.get("SMTP_USER"):
        config.smtp_user = os.environ["SMTP_USER"]
    if os.environ.get("SMTP_PASSWORD"):
        config.smtp_password = os.environ["SMTP_PASSWORD"]
    if os.environ.get("MIN_SCORE_THRESHOLD"):
        config.min_score_threshold = int(os.environ["MIN_SCORE_THRESHOLD"])
    if os.environ.get("INCREASE_THRESHOLD"):
        config.increase_threshold = int(os.environ["INCREASE_THRESHOLD"])
    
    return config


def send_email(config: MonitorConfig, subject: str, body: str) -> bool:
    """メール送信"""
    if not config.email_enabled or not config.email_address:
        print("メール通知が無効または設定されていません")
        return False
    
    try:
        msg = MIMEMultipart()
        msg["From"] = config.smtp_user
        msg["To"] = config.email_address
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        
        with smtplib.SMTP(config.smtp_server, config.smtp_port) as server:
            server.starttls()
            server.login(config.smtp_user, config.smtp_password)
            server.send_message(msg)
        
        print(f"✅ メール送信成功: {config.email_address}")
        return True
    except Exception as e:
        print(f"❌ メール送信失敗: {e}")
        return False


def analyze_watchlist(watchlist: List[str]) -> Dict[str, ma.MAScore]:
    """監視リストの全銘柄をM&A分析"""
    results = {}
    
    if not watchlist:
        print("監視リストが空です")
        return results
    
    print(f"📊 {len(watchlist)}銘柄を分析中...")
    
    try:
        # 基本データ取得
        bundle = fv.calc_genta_bundle(watchlist)
        
        # M&A分析
        stock_data_list = [bundle.get(code, {}) for code in watchlist]
        ma_results = ma.batch_analyze_ma(stock_data_list, with_news=True)
        
        for score in ma_results:
            results[score.code] = score
            print(f"  {score.code} {score.name}: {score.total_score}点 [{score.signal_level.value}]")
    
    except Exception as e:
        print(f"❌ 分析エラー: {e}")
    
    return results


def check_alerts(
    current_scores: Dict[str, ma.MAScore],
    history: Dict[str, Dict],
    config: MonitorConfig
) -> List[Dict]:
    """
    アラート条件をチェック
    1. 閾値を超えた銘柄
    2. スコアが大幅に上昇した銘柄
    """
    alerts = []
    now = datetime.now().isoformat()
    
    for code, score in current_scores.items():
        alert_reasons = []
        prev_score = history.get(code, {}).get("score", 0)
        score_change = score.total_score - prev_score
        
        # 条件1: 閾値超え（初めて超えた場合）
        if score.total_score >= config.min_score_threshold:
            if prev_score < config.min_score_threshold:
                alert_reasons.append(f"閾値{config.min_score_threshold}点を超えました")
        
        # 条件2: 大幅なスコア上昇
        if config.notify_on_increase and score_change >= config.increase_threshold:
            alert_reasons.append(f"スコアが{score_change}点上昇しました（{prev_score}→{score.total_score}）")
        
        # 条件3: 緊急レベル
        if score.signal_level == ma.MASignalLevel.CRITICAL:
            if history.get(code, {}).get("signal_level") != "🔴 緊急":
                alert_reasons.append("緊急レベルに達しました")
        
        if alert_reasons:
            alerts.append({
                "code": code,
                "name": score.name,
                "current_score": score.total_score,
                "previous_score": prev_score,
                "change": score_change,
                "signal_level": score.signal_level.value,
                "reasons": alert_reasons,
                "tags": score.reason_tags,
                "news_score": score.news_score,
                "volume_score": score.volume_score,
                "valuation_score": score.valuation_score,
                "technical_score": score.technical_score,
            })
        
        # 履歴を更新
        history[code] = {
            "score": score.total_score,
            "signal_level": score.signal_level.value,
            "name": score.name,
            "updated_at": now,
        }
    
    return alerts


def format_alert_email(alerts: List[Dict]) -> str:
    """アラートメールの本文を作成"""
    lines = [
        "=" * 50,
        "🎯 源太AI ハゲタカSCOPE - M&A予兆アラート",
        "=" * 50,
        f"検知時刻: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}",
        f"アラート件数: {len(alerts)}件",
        "",
    ]
    
    for i, alert in enumerate(alerts, 1):
        lines.extend([
            "-" * 50,
            f"【{i}】{alert['name']}（{alert['code']}）",
            "-" * 50,
            f"🚨 シグナル: {alert['signal_level']}",
            f"📊 スコア: {alert['current_score']}点（前回: {alert['previous_score']}点、変化: {alert['change']:+d}点）",
            "",
            "📋 アラート理由:",
        ])
        for reason in alert["reasons"]:
            lines.append(f"  • {reason}")
        
        lines.extend([
            "",
            "📈 スコア内訳:",
            f"  • ニュース: {alert['news_score']}/40点",
            f"  • 出来高: {alert['volume_score']}/30点",
            f"  • バリュエーション: {alert['valuation_score']}/20点",
            f"  • テクニカル: {alert['technical_score']}/10点",
        ])
        
        if alert["tags"]:
            lines.extend([
                "",
                "🏷️ タグ:",
                f"  {' '.join(alert['tags'])}",
            ])
        
        lines.append("")
    
    lines.extend([
        "=" * 50,
        "※ このメールは源太AI ハゲタカSCOPEから自動送信されています。",
        "※ 詳細はアプリにログインしてご確認ください。",
        "=" * 50,
    ])
    
    return "\n".join(lines)


def main():
    """メイン処理"""
    print("=" * 50)
    print("🎯 源太AI ハゲタカSCOPE - 自動M&A監視")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # 設定読み込み
    config = load_config()
    print(f"\n📧 メール通知: {'有効' if config.email_enabled else '無効'}")
    print(f"📊 閾値: {config.min_score_threshold}点")
    print(f"📈 上昇通知: {config.increase_threshold}点以上")
    
    # 監視リスト読み込み
    watchlist = load_watchlist()
    if not watchlist:
        print("\n⚠️ 監視リストが空です。処理を終了します。")
        return
    
    print(f"\n📋 監視銘柄: {len(watchlist)}件")
    print(f"  {', '.join(watchlist)}")
    
    # スコア履歴読み込み
    history = load_score_history()
    print(f"\n📜 履歴データ: {len(history)}件")
    
    # M&A分析実行
    print("\n" + "-" * 50)
    current_scores = analyze_watchlist(watchlist)
    print("-" * 50)
    
    if not current_scores:
        print("\n⚠️ 分析結果が空です。処理を終了します。")
        return
    
    # アラートチェック
    alerts = check_alerts(current_scores, history, config)
    
    # 履歴を保存
    save_score_history(history)
    print(f"\n💾 履歴を保存しました")
    
    # アラート処理
    if alerts:
        print(f"\n🚨 アラート: {len(alerts)}件検知")
        for alert in alerts:
            print(f"  • {alert['name']}（{alert['code']}）: {alert['current_score']}点")
            for reason in alert["reasons"]:
                print(f"    → {reason}")
        
        # メール送信
        if config.email_enabled:
            subject = f"🚨 M&A予兆アラート: {len(alerts)}件検知 - {datetime.now().strftime('%m/%d %H:%M')}"
            body = format_alert_email(alerts)
            send_email(config, subject, body)
    else:
        print("\n✅ アラートなし（条件を満たす銘柄はありませんでした）")
    
    print("\n" + "=" * 50)
    print("処理完了")
    print("=" * 50)


if __name__ == "__main__":
    main()
