"""
cloud_store.py - Google Sheets persistence backend for the menu app.

The local SQLite backend remains the default. This module is used only when
Google Sheets credentials and a spreadsheet id are configured.
"""
from __future__ import annotations

import datetime
import json
import os
import time


DATA_HEADERS = {
    "menus": ["id", "week_start", "day", "main_dish", "side_dish", "seasonal_ingredient", "cook_time", "explore_reason", "created_at"],
    "feedback": ["id", "week_start", "dish_name", "rating", "saved_at"],
    "shopping_items": ["id", "week_start", "category", "item_name", "checked"],
    "recipes": ["id", "dish_name", "recipe_text", "is_favorite", "created_at"],
    "Rules": ["id", "active", "priority", "category", "rule", "override_allowed", "notes"],
    "Framework": ["day", "genre", "prep_day", "prep_instruction", "shared_side_group", "active"],
}

_SPREADSHEET = None
_WORKSHEETS = {}
_RECORD_CACHE = {}
_CACHE_TTL_SECONDS = 120


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _as_bool(value) -> bool:
    return str(value or "").strip().upper() in {"TRUE", "1", "YES", "Y", "ON", "有効"}


def _as_int(value, default=0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def _streamlit_secrets():
    try:
        import streamlit as st
        return st.secrets
    except Exception:
        return {}


def _secret_get(secrets, key, default=None):
    try:
        if key in secrets:
            return secrets[key]
    except Exception:
        pass
    return default


def _sheet_id_from_config():
    for key in ["GOOGLE_SHEETS_ID", "KONDATE_SHEET_ID", "SPREADSHEET_ID"]:
        value = os.environ.get(key)
        if value:
            return value

    secrets = _streamlit_secrets()
    for key in ["GOOGLE_SHEETS_ID", "KONDATE_SHEET_ID", "SPREADSHEET_ID"]:
        value = _secret_get(secrets, key)
        if value:
            return str(value)
    return None


def _credentials_from_config():
    raw_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw_json:
        data = json.loads(raw_json)
        if "private_key" in data:
            data["private_key"] = data["private_key"].replace("\\n", "\n")
        return data

    secrets = _streamlit_secrets()
    for key in ["gcp_service_account", "google_service_account", "GOOGLE_SERVICE_ACCOUNT"]:
        value = _secret_get(secrets, key)
        if value:
            data = dict(value)
            if "private_key" in data:
                data["private_key"] = str(data["private_key"]).replace("\\n", "\n")
            return data

    value = _secret_get(secrets, "GOOGLE_SERVICE_ACCOUNT_JSON")
    if value:
        data = json.loads(str(value))
        if "private_key" in data:
            data["private_key"] = data["private_key"].replace("\\n", "\n")
        return data

    return None


def is_configured() -> bool:
    return bool(_sheet_id_from_config() and _credentials_from_config())


def is_enabled() -> bool:
    if not is_configured():
        return False
    try:
        import gspread  # noqa: F401
        return True
    except Exception:
        return False


def _spreadsheet():
    global _SPREADSHEET
    if _SPREADSHEET is not None:
        return _SPREADSHEET
    if not is_configured():
        raise RuntimeError("Google Sheets backend is not configured.")

    import gspread

    credentials = _credentials_from_config()
    client = gspread.service_account_from_dict(credentials)
    _SPREADSHEET = client.open_by_key(_sheet_id_from_config())
    return _SPREADSHEET


def _worksheet(name: str):
    if name in _WORKSHEETS:
        return _WORKSHEETS[name]
    book = _spreadsheet()
    try:
        ws = book.worksheet(name)
    except Exception:
        ws = book.add_worksheet(title=name, rows=200, cols=max(len(DATA_HEADERS.get(name, [])), 8))
    headers = DATA_HEADERS.get(name)
    if headers:
        current = ws.row_values(1)
        if current[: len(headers)] != headers:
            _update_sheet(ws, [headers])
    _WORKSHEETS[name] = ws
    return ws


def _update_sheet(ws, values):
    try:
        ws.clear()
        ws.update(values, "A1")
    except TypeError:
        ws.clear()
        ws.update(range_name="A1", values=values)


def _records(name: str) -> list[dict]:
    cached = _RECORD_CACHE.get(name)
    if cached:
        cached_at, records = cached
        if time.monotonic() - cached_at < _CACHE_TTL_SECONDS:
            return [dict(row) for row in records]

    ws = _worksheet(name)
    rows = ws.get_all_records()
    records = [{str(k): v for k, v in row.items()} for row in rows]
    _RECORD_CACHE[name] = (time.monotonic(), [dict(row) for row in records])
    return [dict(row) for row in records]


def _write_records(name: str, records: list[dict]) -> None:
    headers = DATA_HEADERS[name]
    values = [headers]
    for record in records:
        values.append([record.get(header, "") for header in headers])
    _update_sheet(_worksheet(name), values)
    _RECORD_CACHE[name] = (time.monotonic(), [dict(row) for row in records])


def _next_id(records: list[dict]) -> int:
    max_id = 0
    for record in records:
        max_id = max(max_id, _as_int(record.get("id")))
    return max_id + 1


def init_store() -> None:
    # Sheets are created and validated lazily. Eagerly checking every sheet on
    # each Streamlit rerun burns Google Sheets quota and can trigger 429 errors.
    return None


def save_menu(week_start, day_menus: list):
    records = [r for r in _records("menus") if str(r.get("week_start", "")) != str(week_start)]
    next_id = _next_id(records)
    for menu in day_menus:
        records.append({
            "id": next_id,
            "week_start": week_start,
            "day": menu.get("day", ""),
            "main_dish": menu.get("main_dish", ""),
            "side_dish": menu.get("side_dish", ""),
            "seasonal_ingredient": menu.get("seasonal_ingredient", ""),
            "cook_time": menu.get("cook_time", ""),
            "explore_reason": menu.get("explore_reason", ""),
            "created_at": _now(),
        })
        next_id += 1
    _write_records("menus", records)


def load_menus(week_start=None):
    records = _records("menus")
    if week_start:
        records = [r for r in records if str(r.get("week_start", "")) == str(week_start)]
        return sorted(records, key=lambda r: _as_int(r.get("id")))
    return sorted(records, key=lambda r: (str(r.get("week_start", "")), _as_int(r.get("id"))), reverse=True)


def load_all_week_starts():
    weeks = sorted({str(r.get("week_start", "")) for r in _records("menus") if str(r.get("week_start", "")).strip()}, reverse=True)
    return weeks


def load_recent_menus_for_prompt(weeks=3):
    cutoff = (datetime.date.today() - datetime.timedelta(weeks=weeks)).strftime("%Y-%m-%d")
    feedback = load_feedback()
    rating_by_dish = {(f.get("week_start"), f.get("dish_name")): f.get("rating") for f in feedback}
    rows = []
    for menu in load_menus():
        if str(menu.get("week_start", "")) >= cutoff:
            rating = rating_by_dish.get((menu.get("week_start"), menu.get("main_dish"))) or rating_by_dish.get((menu.get("week_start"), menu.get("side_dish")))
            rows.append((menu.get("week_start"), menu.get("day"), menu.get("main_dish"), menu.get("side_dish"), rating))
    return rows


def get_high_rated_dishes():
    seen = []
    for fb in sorted(_records("feedback"), key=lambda r: str(r.get("saved_at", "")), reverse=True):
        dish = str(fb.get("dish_name", "")).strip()
        if fb.get("rating") == "◎" and dish and dish not in seen:
            seen.append(dish)
        if len(seen) >= 20:
            break
    return seen


def get_recent_dishes(weeks=3):
    cutoff = (datetime.date.today() - datetime.timedelta(weeks=weeks)).strftime("%Y-%m-%d")
    dishes = []
    for menu in load_menus():
        if str(menu.get("week_start", "")) >= cutoff:
            for field in ["main_dish", "side_dish"]:
                dish = str(menu.get(field, "")).strip()
                if dish and dish not in dishes:
                    dishes.append(dish)
    return dishes


def save_feedback(week_start, feedbacks: list):
    records = [r for r in _records("feedback") if str(r.get("week_start", "")) != str(week_start)]
    next_id = _next_id(records)
    for fb in feedbacks:
        records.append({
            "id": next_id,
            "week_start": week_start,
            "dish_name": fb["dish_name"],
            "rating": fb["rating"],
            "saved_at": _now(),
        })
        next_id += 1
    _write_records("feedback", records)


def load_feedback(week_start=None):
    records = _records("feedback")
    if week_start:
        records = [r for r in records if str(r.get("week_start", "")) == str(week_start)]
    return sorted(records, key=lambda r: (str(r.get("week_start", "")), _as_int(r.get("id"))), reverse=week_start is None)


def get_ng_dishes():
    return sorted({str(r.get("dish_name", "")).strip() for r in _records("feedback") if r.get("rating") == "✕" and str(r.get("dish_name", "")).strip()})


def save_shopping_items(week_start, items: list):
    records = [r for r in _records("shopping_items") if str(r.get("week_start", "")) != str(week_start)]
    next_id = _next_id(records)
    for item in items:
        records.append({
            "id": next_id,
            "week_start": week_start,
            "category": item["category"],
            "item_name": item["item_name"],
            "checked": 0,
        })
        next_id += 1
    _write_records("shopping_items", records)


def load_shopping_items(week_start):
    records = [r for r in _records("shopping_items") if str(r.get("week_start", "")) == str(week_start)]
    records = sorted(records, key=lambda r: (str(r.get("category", "")), _as_int(r.get("id"))))
    return [{
        "id": _as_int(r.get("id")),
        "category": r.get("category", ""),
        "item_name": r.get("item_name", ""),
        "checked": _as_bool(r.get("checked")),
    } for r in records]


def toggle_shopping_item(item_id, checked: bool):
    records = _records("shopping_items")
    for record in records:
        if _as_int(record.get("id")) == _as_int(item_id):
            record["checked"] = 1 if checked else 0
            break
    _write_records("shopping_items", records)


def reset_shopping_checks(week_start):
    records = _records("shopping_items")
    for record in records:
        if str(record.get("week_start", "")) == str(week_start):
            record["checked"] = 0
    _write_records("shopping_items", records)


def save_recipe(dish_name: str, recipe_text: str):
    records = _records("recipes")
    target = None
    for record in records:
        if str(record.get("dish_name", "")) == dish_name:
            target = record
            break
    if target:
        target["recipe_text"] = recipe_text
    else:
        records.append({
            "id": _next_id(records),
            "dish_name": dish_name,
            "recipe_text": recipe_text,
            "is_favorite": 0,
            "created_at": _now(),
        })
    _write_records("recipes", records)


def get_recipe(dish_name: str):
    for record in _records("recipes"):
        if str(record.get("dish_name", "")) == dish_name:
            return {"recipe_text": record.get("recipe_text", ""), "is_favorite": 1 if _as_bool(record.get("is_favorite")) else 0}
    return None


def toggle_favorite_recipe(dish_name: str, is_favorite: bool):
    records = _records("recipes")
    for record in records:
        if str(record.get("dish_name", "")) == dish_name:
            record["is_favorite"] = 1 if is_favorite else 0
            break
    _write_records("recipes", records)


def get_favorite_recipes():
    records = [r for r in _records("recipes") if _as_bool(r.get("is_favorite"))]
    records = sorted(records, key=lambda r: _as_int(r.get("id")), reverse=True)
    return [{"dish_name": r.get("dish_name", ""), "recipe_text": r.get("recipe_text", ""), "created_at": r.get("created_at", "")} for r in records]


def get_all_recipes():
    records = sorted(_records("recipes"), key=lambda r: _as_int(r.get("id")), reverse=True)
    return [{
        "dish_name": r.get("dish_name", ""),
        "recipe_text": r.get("recipe_text", ""),
        "is_favorite": _as_bool(r.get("is_favorite")),
        "created_at": r.get("created_at", ""),
    } for r in records]


def get_all_dishes_from_menus():
    dishes = []
    for menu in _records("menus"):
        for field in ["main_dish", "side_dish"]:
            dish = str(menu.get(field, "")).strip()
            if dish and dish != "なし" and dish not in dishes:
                dishes.append(dish)
    return dishes


def _rulebook_from_records(rules_records: list[dict], framework_rows: list[dict]) -> dict:
    active_rules = [r for r in rules_records if _as_bool(r.get("active"))]
    active_fw = [r for r in framework_rows if _as_bool(r.get("active"))]
    framework = {r.get("day", ""): r.get("genre", "") for r in active_fw if r.get("day")}
    prep_days = [r.get("day", "") for r in active_fw if _as_bool(r.get("prep_day")) and r.get("day")]
    prep_instructions = {
        r.get("day", ""): r.get("prep_instruction", "")
        for r in active_fw
        if _as_bool(r.get("prep_day")) and r.get("day")
    }
    groups = {}
    for row in active_fw:
        group = str(row.get("shared_side_group", "")).strip()
        day = row.get("day", "")
        if group and day:
            groups.setdefault(group, []).append(day)
    shared_side_dishes = [days for _, days in sorted(groups.items()) if len(days) >= 2]
    unique_prep = []
    for value in prep_instructions.values():
        if value and value not in unique_prep:
            unique_prep.append(value)
    return {
        "path": "Google Sheets",
        "rules": active_rules,
        "framework_rows": active_fw,
        "framework": framework,
        "legacy_rules": {
            "prep_days": prep_days,
            "prep_instruction": " / ".join(unique_prep),
            "prep_instructions": prep_instructions,
            "shared_side_dishes": shared_side_dishes,
        },
    }


def load_rulebook() -> dict:
    return _rulebook_from_records(_records("Rules"), _records("Framework"))


def write_rulebook_rows(rules_rows: list[list[str]], framework_rows: list[list[str]]) -> None:
    rules_headers = DATA_HEADERS["Rules"]
    framework_headers = DATA_HEADERS["Framework"]

    def to_records(rows, headers):
        source_headers = rows[0]
        records = []
        for row in rows[1:]:
            if not any(str(v).strip() for v in row):
                continue
            records.append({
                header: row[source_headers.index(header)] if header in source_headers and source_headers.index(header) < len(row) else ""
                for header in headers
            })
        return records

    _write_records("Rules", to_records(rules_rows, rules_headers))
    _write_records("Framework", to_records(framework_rows, framework_headers))
