# Streamlit Community Cloud 移行メモ

## 目標

PCを起動していなくても、携帯から献立アプリを使えるようにする。

## 構成

- アプリ本体: Streamlit Community Cloud
- データ保存: Google Sheets
- APIキー: Streamlit Cloud Secrets
- ローカル実行時: SQLiteに自動フォールバック

## Google Sheets 側で作るもの

1. Google Sheetを1つ作成する
2. Google Cloudでサービスアカウントを作成する
3. Google Sheets APIを有効化する
4. サービスアカウントのメールアドレスをGoogle Sheetに編集者として共有する

## Streamlit Secrets 例

```toml
GOOGLE_API_KEY = "your-gemini-api-key"
GOOGLE_SHEETS_ID = "your-google-sheet-id"
KONDATE_APP_PASSWORD = "your-app-login-password"

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

Gmail送信を使う場合だけ、既存と同じ `GMAIL_USER` と `GMAIL_APP_PASSWORD` も追加する。

## 移行手順

1. `requirements.txt` の依存をインストールする
2. `.streamlit/secrets.toml` に `GOOGLE_SHEETS_ID`、`KONDATE_APP_PASSWORD`、サービスアカウント情報を入れる
3. `python migrate_to_google_sheets.py` を実行する
4. GitHubにアプリをアップロードする
5. Streamlit Community Cloudで `app.py` を指定してデプロイする

## 注意

- `.streamlit/secrets.toml` は絶対にGitHubへ上げない
- 公開アプリでは `KONDATE_APP_PASSWORD` を必ず設定する
- `kondate.db` はクラウドでは使わない
- Google Sheets設定がない場合、アプリは今まで通りSQLiteで動く
