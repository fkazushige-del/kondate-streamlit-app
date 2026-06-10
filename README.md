# 献立アプリ Streamlit Cloud版

このフォルダは、Streamlit Community Cloudへデプロイするための公開用パッケージです。

## 先にやること

1. Google Sheetを1つ作成
2. Google CloudでGoogle Sheets APIを有効化
3. サービスアカウントを作成し、JSONキーをダウンロード
4. サービスアカウントの `client_email` をGoogle Sheetに編集者として共有
5. `configure_cloud_secrets.py` で `.streamlit/secrets.toml` を作成
6. `migrate_to_google_sheets.py` でSQLite/rules.xlsxをGoogle Sheetsへ移行
7. GitHubへpush
8. Streamlit Community Cloudで `app.py` を指定してデプロイ

## ローカルSecrets作成

```powershell
python configure_cloud_secrets.py
```

JSONキーはチャットに貼らず、ダウンロードしたファイルをこのスクリプトに読み込ませてください。

## データ移行

```powershell
python migrate_to_google_sheets.py
```

## GitHub公開

まずブラウザでGitHubにログインし、必要なら:

```powershell
gh auth login
.\publish_to_github.ps1
```

初期設定ではprivate repoを作ります。
