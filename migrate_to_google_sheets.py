"""
Migrate local SQLite data and rules.xlsx into the configured Google Sheet.

Usage:
  1. Create a Google Sheet.
  2. Share it with your service account email.
  3. Put GOOGLE_SHEETS_ID and service account credentials in .streamlit/secrets.toml.
  4. Run: python migrate_to_google_sheets.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
import argparse

import app_rules
import cloud_store

APP_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(APP_DIR, "kondate.db")
RULEBOOK_PATH = os.path.join(APP_DIR, "rules.xlsx")


def rows_as_dicts(cursor, query, cols):
    cursor.execute(query)
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def main():
    parser = argparse.ArgumentParser(description="Migrate kondate SQLite data and rules.xlsx to Google Sheets.")
    parser.add_argument("--db", default=os.environ.get("KONDATE_SQLITE_DB", DB_PATH), help="Path to the source kondate.db")
    args = parser.parse_args()

    if not cloud_store.is_enabled():
        print("Google Sheets backend is not configured or gspread is not installed.", file=sys.stderr)
        print("Set GOOGLE_SHEETS_ID and gcp_service_account in .streamlit/secrets.toml, then install requirements.", file=sys.stderr)
        return 1

    if not os.path.exists(args.db):
        print(f"SQLite database not found: {args.db}", file=sys.stderr)
        return 1

    cloud_store.init_store()

    con = sqlite3.connect(args.db)
    cur = con.cursor()
    data = {
        "menus": rows_as_dicts(cur, "SELECT id, week_start, day, main_dish, side_dish, seasonal_ingredient, cook_time, explore_reason, created_at FROM menus ORDER BY id", cloud_store.DATA_HEADERS["menus"]),
        "feedback": rows_as_dicts(cur, "SELECT id, week_start, dish_name, rating, saved_at FROM feedback ORDER BY id", cloud_store.DATA_HEADERS["feedback"]),
        "shopping_items": rows_as_dicts(cur, "SELECT id, week_start, category, item_name, checked FROM shopping_items ORDER BY id", cloud_store.DATA_HEADERS["shopping_items"]),
        "recipes": rows_as_dicts(cur, "SELECT id, dish_name, recipe_text, is_favorite, created_at FROM recipes ORDER BY id", cloud_store.DATA_HEADERS["recipes"]),
    }
    con.close()

    for sheet_name, records in data.items():
        cloud_store._write_records(sheet_name, records)

    rules_rows = app_rules._read_sheet_rows(RULEBOOK_PATH, "Rules")
    framework_rows = app_rules._read_sheet_rows(RULEBOOK_PATH, "Framework")
    cloud_store.write_rulebook_rows(rules_rows, framework_rows)

    print("Migration completed.")
    for sheet_name, records in data.items():
        print(f"- {sheet_name}: {len(records)} rows")
    print(f"- Rules: {max(len(rules_rows) - 1, 0)} rows")
    print(f"- Framework: {max(len(framework_rows) - 1, 0)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
