from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import tomllib

APP_DIR = Path(__file__).resolve().parent
SECRETS_PATH = APP_DIR / ".streamlit" / "secrets.toml"


def toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def extract_sheet_id(value: str) -> str:
    value = value.strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", value)
    if match:
        return match.group(1)
    return value


def latest_service_account_json() -> Path | None:
    downloads = Path.home() / "Downloads"
    if not downloads.exists():
        return None
    candidates = sorted(downloads.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("type") == "service_account" and data.get("client_email"):
            return path
    return None


def load_existing_scalars() -> dict:
    if not SECRETS_PATH.exists():
        return {}
    try:
        with SECRETS_PATH.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return {}
    keep = {}
    for key in ["GOOGLE_API_KEY", "KONDATE_APP_PASSWORD", "APP_PASSWORD", "GMAIL_USER", "GMAIL_APP_PASSWORD"]:
        if key in data:
            keep[key] = data[key]
    return keep


def main() -> int:
    parser = argparse.ArgumentParser(description="Create .streamlit/secrets.toml for Google Sheets backend.")
    parser.add_argument("--sheet", help="Google Sheet URL or ID")
    parser.add_argument("--json", help="Path to downloaded service account JSON key")
    args = parser.parse_args()

    sheet = args.sheet or input("Google Sheet URL or ID: ").strip()
    sheet_id = extract_sheet_id(sheet)
    json_path = Path(args.json) if args.json else latest_service_account_json()
    if not json_path:
        raw = input("Service account JSON path: ").strip().strip('"')
        json_path = Path(raw)
    if not json_path.exists():
        raise SystemExit(f"JSON file not found: {json_path}")

    service_account = json.loads(json_path.read_text(encoding="utf-8"))
    if service_account.get("type") != "service_account":
        raise SystemExit("The JSON file does not look like a service account key.")

    secrets = load_existing_scalars()
    if "GOOGLE_API_KEY" not in secrets:
        google_api_key = input("Gemini GOOGLE_API_KEY: ").strip()
        secrets["GOOGLE_API_KEY"] = google_api_key
    secrets["GOOGLE_SHEETS_ID"] = sheet_id

    SECRETS_PATH.parent.mkdir(exist_ok=True)
    lines = []
    for key in ["GOOGLE_API_KEY", "GOOGLE_SHEETS_ID", "KONDATE_APP_PASSWORD", "APP_PASSWORD", "GMAIL_USER", "GMAIL_APP_PASSWORD"]:
        if key in secrets and str(secrets[key]).strip():
            lines.append(f"{key} = {toml_string(secrets[key])}")
    lines.append("")
    lines.append("[gcp_service_account]")
    for key, value in service_account.items():
        if isinstance(value, str):
            lines.append(f"{key} = {toml_string(value)}")
    SECRETS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Secrets written:", SECRETS_PATH)
    print("Service account email:", service_account.get("client_email"))
    print("Share the Google Sheet with this email as Editor before running migration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
