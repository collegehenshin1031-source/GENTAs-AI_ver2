# 源太AI🤖ハゲタカSCOPE - M&A予兆検知システム

## 🚀 機能

1. **銘柄分析**: グレアム数による理論株価、テクニカル指標、大口介入シグナル
2. **M&A予兆検知**: ニュース・出来高・バリュエーション・テクニカルの総合スコアリング
3. **自動監視**: GitHub Actionsによる1日2回の自動スコアチェック
4. **メール通知**: 閾値超え・スコア急上昇時に自動でメール送信

---

## 📁 ファイル構成

```
├── app.py                    # Streamlitメインアプリ
├── fair_value_calc_y4.py     # 理論株価計算エンジン
├── ma_detector.py            # M&A予兆検知エンジン
├── notifier.py               # 通知機能
├── auto_monitor.py           # 自動監視スクリプト
├── requirements.txt          # 依存パッケージ
├── data/
│   ├── watchlist.json        # 監視リスト
│   ├── score_history.json    # スコア履歴
│   └── notification_config.json  # 通知設定
└── .github/
    └── workflows/
        └── auto_monitor.yml  # GitHub Actions設定
```

---

## 🔧 セットアップ手順

### 1. リポジトリをPublicに設定

GitHub Actionsの無料枠を使うため、リポジトリをPublicにしてください。

### 2. GitHub Secretsの設定（メール通知用）

リポジトリの **Settings** → **Secrets and variables** → **Actions** → **New repository secret** で以下を追加：

| Secret名 | 値 | 必須 |
|----------|-----|------|
| `EMAIL_ENABLED` | `true` | ✅ |
| `EMAIL_ADDRESS` | 送信先メールアドレス | ✅ |
| `SMTP_SERVER` | `smtp.gmail.com` | ✅ |
| `SMTP_PORT` | `587` | ✅ |
| `SMTP_USER` | Gmailアドレス | ✅ |
| `SMTP_PASSWORD` | Gmailアプリパスワード | ✅ |
| `MIN_SCORE_THRESHOLD` | `50`（通知する最低スコア） | 任意 |
| `INCREASE_THRESHOLD` | `15`（何点上昇で通知） | 任意 |

### 3. Gmailアプリパスワードの取得

1. [Googleアカウント](https://myaccount.google.com/)にログイン
2. **セキュリティ** → **2段階認証プロセス** を有効化
3. **アプリパスワード** を生成（「メール」「Windows コンピュータ」等を選択）
4. 表示された16桁のパスワードを `SMTP_PASSWORD` に設定

### 4. 監視リストに銘柄を追加

Streamlitアプリの「M&A予兆監視」タブで銘柄を追加すると、`data/watchlist.json`に保存されます。

---

## ⏰ 自動実行スケジュール

GitHub Actionsは以下のタイミングで自動実行されます：

- **朝 8:00**（日本時間）
- **夜 20:00**（日本時間）

手動で実行したい場合は、GitHubリポジトリの **Actions** → **M&A予兆自動監視** → **Run workflow** をクリック。

---

## 📧 通知条件

以下のいずれかを満たすとメールが送信されます：

1. **閾値超え**: スコアが初めて設定した閾値（デフォルト50点）を超えた
2. **スコア急上昇**: 前回から15点以上上昇した
3. **緊急レベル**: シグナルレベルが「緊急」に達した

---

## 📊 M&Aスコアの内訳

| 要素 | 配点 | 検知内容 |
|------|------|----------|
| ニュース分析 | 最大40点 | TOB、完全子会社化等のキーワード |
| 出来高異常 | 最大30点 | 出来高急増、浮動株回転率 |
| バリュエーション | 最大20点 | PBR、時価総額、割安度 |
| テクニカル | 最大10点 | RSI、移動平均線 |

---

## ⚠️ 注意事項

- 投資は自己責任でお願いします
- M&A予兆スコアは参考情報であり、投資判断の最終決定は各自で行ってください
- ニューススクレイピングは各サイトの利用規約に従ってご利用ください

---

## 🛠️ トラブルシューティング

### GitHub Actionsが動かない

1. リポジトリがPublicになっているか確認
2. **Actions** タブで「I understand my workflows, go ahead and enable them」をクリック
3. Secretsが正しく設定されているか確認

### メールが届かない

1. `EMAIL_ENABLED` が `true` になっているか確認
2. Gmailの場合、2段階認証が有効でアプリパスワードを使っているか確認
3. 迷惑メールフォルダを確認

### スコアが更新されない

1. `data/watchlist.json` に銘柄が登録されているか確認
2. GitHub Actionsのログでエラーがないか確認
