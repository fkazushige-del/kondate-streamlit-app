$urls = @(
  "https://docs.google.com/spreadsheets/u/0/create",
  "https://console.cloud.google.com/apis/library/sheets.googleapis.com",
  "https://console.cloud.google.com/iam-admin/serviceaccounts",
  "https://github.com/login",
  "https://share.streamlit.io/"
)

foreach ($url in $urls) {
  Start-Process $url
}
