"""
通知機能モジュール
- メール通知（Gmail SMTP）
- LINE Notify
"""
from __future__ import annotations
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import json
import os

# ==========================================
# 設定用データクラス
# ==========================================

@dataclass
class NotificationConfig:
    """通知設定"""
    enabled: bool = False
    
    # メール設定
    email_enabled: bool = False
    email_address: str = ""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""  # Gmailの場合はアプリパスワード
    
    # LINE Notify設定
    line_enabled: bool = False
    line_token: str = ""
    
    # 通知条件
    min_score_threshold: int = 50  # この点数以上で通知
    notify_critical_only: bool = False  # クリティカルレベルのみ通知


@dataclass
class NotificationResult:
    """通知結果"""
    success: bool
    method: str  # "email" or "line"
    message: str
    timestamp: datetime = field(default_factory=datetime.now)


# ==========================================
# LINE Notify
# ==========================================

def send_line_notify(token: str, message: str) -> NotificationResult:
    """
    LINE Notifyでメッセージを送信
    
    Args:
        token: LINE Notify アクセストークン
        message: 送信するメッセージ（最大1000文字）
    """
    if not token:
        return NotificationResult(
            success=False,
            method="line",
            message="LINE Notifyトークンが設定されていません"
        )
    
    try:
        url = "https://notify-api.line.me/api/notify"
        headers = {
            "Authorization": f"Bearer {token}"
        }
        data = {
            "message": message[:1000]  # 最大1000文字
        }
        
        response = requests.post(url, headers=headers, data=data, timeout=10)
        
        if response.status_code == 200:
            return NotificationResult(
                success=True,
                method="line",
                message="LINE通知を送信しました"
            )
        else:
            return NotificationResult(
                success=False,
                method="line",
                message=f"LINE通知エラー: {response.status_code}"
            )
            
    except Exception as e:
        return NotificationResult(
            success=False,
            method="line",
            message=f"LINE通知例外: {str(e)}"
        )


# ==========================================
# メール通知
# ==========================================

def send_email(
    to_address: str,
    subject: str,
    body: str,
    smtp_server: str = "smtp.gmail.com",
    smtp_port: int = 587,
    smtp_user: str = "",
    smtp_password: str = ""
) -> NotificationResult:
    """
    メールを送信
    
    Note:
        Gmailの場合、アプリパスワードの設定が必要
        https://myaccount.google.com/apppasswords
    """
    if not to_address or not smtp_user or not smtp_password:
        return NotificationResult(
            success=False,
            method="email",
            message="メール設定が不完全です"
        )
    
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = to_address
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        return NotificationResult(
            success=True,
            method="email",
            message=f"メールを送信しました: {to_address}"
        )
        
    except smtplib.SMTPAuthenticationError:
        return NotificationResult(
            success=False,
            method="email",
            message="SMTP認証エラー: ユーザー名/パスワードを確認してください（Gmailの場合はアプリパスワードが必要）"
        )
    except Exception as e:
        return NotificationResult(
            success=False,
            method="email",
            message=f"メール送信例外: {str(e)}"
        )


# ==========================================
# 通知メッセージ生成
# ==========================================

def format_ma_alert_message(
    scores: List[Any],  # List[MAScore]
    include_details: bool = True
) -> str:
    """
    M&Aアラート用のメッセージを生成
    """
    if not scores:
        return "検知された銘柄はありません。"
    
    lines = [
        "🚨 【M&A予兆検知アラート】",
        f"📅 {datetime.now().strftime('%Y/%m/%d %H:%M')}",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    
    for i, score in enumerate(scores, 1):
        signal_emoji = {
            "🔴 緊急": "🔴",
            "🟠 高": "🟠",
            "🟡 中": "🟡",
            "🟢 低": "🟢",
        }.get(score.signal_level.value, "⚪")
        
        lines.append(f"{signal_emoji} {i}. {score.name}（{score.code}）")
        lines.append(f"   📊 M&Aスコア: {score.total_score}点")
        
        if include_details and score.reason_tags:
            lines.append(f"   🏷️ {' '.join(score.reason_tags)}")
        
        if include_details and score.matched_keywords:
            kw_str = ', '.join(score.matched_keywords[:3])
            lines.append(f"   🔑 キーワード: {kw_str}")
        
        lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("※このアラートは源太AI🤖ハゲタカSCOPEから送信されました")
    
    return "\n".join(lines)


def format_ma_alert_email(
    scores: List[Any],  # List[MAScore]
) -> tuple[str, str]:
    """
    M&Aアラート用のメール（件名と本文）を生成
    
    Returns:
        (subject, body)
    """
    if not scores:
        return "M&A予兆検知なし", "検知された銘柄はありません。"
    
    top_score = scores[0]
    subject = f"🚨 M&A予兆検知: {top_score.name}（スコア{top_score.total_score}点）他{len(scores)-1}件"
    
    body_lines = [
        "=" * 50,
        "【M&A予兆検知レポート】",
        f"検知日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}",
        f"検知銘柄数: {len(scores)}件",
        "=" * 50,
        "",
    ]
    
    for i, score in enumerate(scores, 1):
        body_lines.append(f"【{i}】{score.name}（{score.code}）")
        body_lines.append("-" * 40)
        body_lines.append(f"  🎯 総合スコア: {score.total_score}点 / 100点")
        body_lines.append(f"  📊 シグナルレベル: {score.signal_level.value}")
        body_lines.append("")
        body_lines.append("  【スコア内訳】")
        body_lines.append(f"    ・ニュース分析: {score.news_score}点 / 40点")
        body_lines.append(f"    ・出来高異常: {score.volume_score}点 / 30点")
        body_lines.append(f"    ・バリュエーション: {score.valuation_score}点 / 20点")
        body_lines.append(f"    ・テクニカル: {score.technical_score}点 / 10点")
        body_lines.append("")
        
        if score.reason_tags:
            body_lines.append(f"  【検知理由】")
            body_lines.append(f"    {' '.join(score.reason_tags)}")
            body_lines.append("")
        
        if score.matched_keywords:
            body_lines.append(f"  【検知キーワード】")
            body_lines.append(f"    {', '.join(score.matched_keywords)}")
            body_lines.append("")
        
        if score.news_items:
            body_lines.append(f"  【関連ニュース（上位3件）】")
            for j, news in enumerate(score.news_items[:3], 1):
                body_lines.append(f"    {j}. {news.title}")
            body_lines.append("")
        
        if score.exclusion_flags:
            body_lines.append(f"  ⚠️ 【注意】M&A阻害要因検出: {', '.join(score.exclusion_flags)}")
            body_lines.append("")
        
        body_lines.append("")
    
    body_lines.append("=" * 50)
    body_lines.append("※このメールは「源太AI🤖ハゲタカSCOPE」から自動送信されています。")
    body_lines.append("※投資は自己責任でお願いします。")
    body_lines.append("=" * 50)
    
    return subject, "\n".join(body_lines)


# ==========================================
# 統合通知関数
# ==========================================

def send_ma_alert(
    config: NotificationConfig,
    scores: List[Any],  # List[MAScore]
) -> List[NotificationResult]:
    """
    M&Aアラートを設定に基づいて送信
    
    Args:
        config: 通知設定
        scores: M&Aスコアのリスト（閾値以上のもの）
    
    Returns:
        通知結果のリスト
    """
    results = []
    
    if not config.enabled:
        return results
    
    # 閾値でフィルタ
    filtered_scores = [s for s in scores if s.total_score >= config.min_score_threshold]
    
    # クリティカルのみモードの場合
    if config.notify_critical_only:
        filtered_scores = [s for s in filtered_scores if s.signal_level.value == "🔴 緊急"]
    
    if not filtered_scores:
        return results
    
    # LINE通知
    if config.line_enabled and config.line_token:
        message = format_ma_alert_message(filtered_scores, include_details=True)
        result = send_line_notify(config.line_token, message)
        results.append(result)
    
    # メール通知
    if config.email_enabled and config.email_address:
        subject, body = format_ma_alert_email(filtered_scores)
        result = send_email(
            to_address=config.email_address,
            subject=subject,
            body=body,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
            smtp_user=config.smtp_user,
            smtp_password=config.smtp_password
        )
        results.append(result)
    
    return results


# ==========================================
# 設定の保存・読み込み
# ==========================================

# データディレクトリ
DATA_DIR = "data"

def _ensure_data_dir():
    """データディレクトリを作成"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def save_notification_config(config: NotificationConfig, filepath: str = None):
    """通知設定をJSONファイルに保存"""
    _ensure_data_dir()
    if filepath is None:
        filepath = os.path.join(DATA_DIR, "notification_config.json")
    
    data = {
        "enabled": config.enabled,
        "email_enabled": config.email_enabled,
        "email_address": config.email_address,
        "smtp_server": config.smtp_server,
        "smtp_port": config.smtp_port,
        "smtp_user": config.smtp_user,
        "smtp_password": config.smtp_password,  # 本番環境では暗号化推奨
        "line_enabled": config.line_enabled,
        "line_token": config.line_token,  # 本番環境では暗号化推奨
        "min_score_threshold": config.min_score_threshold,
        "notify_critical_only": config.notify_critical_only,
    }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_notification_config(filepath: str = None) -> NotificationConfig:
    """通知設定をJSONファイルから読み込み"""
    if filepath is None:
        filepath = os.path.join(DATA_DIR, "notification_config.json")
    
    if not os.path.exists(filepath):
        return NotificationConfig()
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return NotificationConfig(
            enabled=data.get("enabled", False),
            email_enabled=data.get("email_enabled", False),
            email_address=data.get("email_address", ""),
            smtp_server=data.get("smtp_server", "smtp.gmail.com"),
            smtp_port=data.get("smtp_port", 587),
            smtp_user=data.get("smtp_user", ""),
            smtp_password=data.get("smtp_password", ""),
            line_enabled=data.get("line_enabled", False),
            line_token=data.get("line_token", ""),
            min_score_threshold=data.get("min_score_threshold", 50),
            notify_critical_only=data.get("notify_critical_only", False),
        )
    except Exception:
        return NotificationConfig()


# ==========================================
# 監視リスト管理
# ==========================================

def save_watchlist(codes: List[str], filepath: str = None):
    """監視リストを保存"""
    _ensure_data_dir()
    if filepath is None:
        filepath = os.path.join(DATA_DIR, "watchlist.json")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(codes, f, ensure_ascii=False, indent=2)


def load_watchlist(filepath: str = None) -> List[str]:
    """監視リストを読み込み"""
    if filepath is None:
        filepath = os.path.join(DATA_DIR, "watchlist.json")
    
    if not os.path.exists(filepath):
        return []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 互換性: 配列またはオブジェクト両方に対応
        if isinstance(data, list):
            return data
        return data.get("codes", [])
    except Exception:
        return []
