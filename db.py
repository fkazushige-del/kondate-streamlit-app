"""
db.py - SQLite データ管理モジュール
"""
import sqlite3
import json
import datetime
import os

import cloud_store

DB_PATH = os.path.join(os.path.dirname(__file__), "kondate.db")


def _use_cloud_store():
    return cloud_store.is_enabled()

# ============================================================
# 初期化
# ============================================================

def init_db():
    if _use_cloud_store():
        cloud_store.init_store()
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 献立テーブル
    c.execute("""
        CREATE TABLE IF NOT EXISTS menus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            day TEXT NOT NULL,
            main_dish TEXT,
            side_dish TEXT,
            seasonal_ingredient TEXT,
            cook_time TEXT,
            explore_reason TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # フィードバックテーブル
    c.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            dish_name TEXT NOT NULL,
            rating TEXT NOT NULL,
            saved_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # 買い物リストテーブル
    c.execute("""
        CREATE TABLE IF NOT EXISTS shopping_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            category TEXT NOT NULL,
            item_name TEXT NOT NULL,
            checked INTEGER DEFAULT 0
        )
    """)

    # 週フレームワーク設定テーブル
    c.execute("""
        CREATE TABLE IF NOT EXISTS framework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL UNIQUE,
            genre TEXT NOT NULL
        )
    """)

    # レシピテーブル
    c.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_name TEXT NOT NULL UNIQUE,
            recipe_text TEXT NOT NULL,
            is_favorite INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    # デフォルトフレームワーク挿入
    default_fw = [
        ("月", "カレー・シチュー・ハヤシライスなど"),
        ("火", "パスタ・洋風麺"),
        ("水", "開拓デー（子供向けの新しい料理・食材に挑戦）"),
        ("木", "どんぶり"),
        ("金", "うどん・そば・ラーメンなど"),
    ]
    for day, genre in default_fw:
        c.execute("INSERT OR IGNORE INTO framework (day, genre) VALUES (?, ?)", (day, genre))

    conn.commit()
    conn.close()


# ============================================================
# フレームワーク
# ============================================================

def get_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_framework():
    config = get_config()
    return config.get("framework", {})

def save_framework(fw_dict):
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    config = get_config()
    config["framework"] = fw_dict
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ============================================================
# 献立
# ============================================================

def get_current_week_start():
    today = datetime.date.today()
    # 直近の月曜日
    monday = today - datetime.timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")

def save_menu(week_start, day_menus: list):
    if _use_cloud_store():
        return cloud_store.save_menu(week_start, day_menus)
    """
    day_menus: [{"day": "月", "main_dish": ..., "side_dish": ..., 
                 "seasonal_ingredient": ..., "cook_time": ..., "explore_reason": ...}, ...]
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 既存の同週データを削除
    c.execute("DELETE FROM menus WHERE week_start = ?", (week_start,))
    for m in day_menus:
        c.execute("""
            INSERT INTO menus (week_start, day, main_dish, side_dish, seasonal_ingredient, cook_time, explore_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            week_start,
            m.get("day", ""),
            m.get("main_dish", ""),
            m.get("side_dish", ""),
            m.get("seasonal_ingredient", ""),
            m.get("cook_time", ""),
            m.get("explore_reason", ""),
        ))
    conn.commit()
    conn.close()

def load_menus(week_start=None):
    if _use_cloud_store():
        return cloud_store.load_menus(week_start)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if week_start:
        c.execute("SELECT * FROM menus WHERE week_start = ? ORDER BY id", (week_start,))
    else:
        c.execute("SELECT * FROM menus ORDER BY week_start DESC, id")
    rows = c.fetchall()
    conn.close()
    cols = ["id","week_start","day","main_dish","side_dish","seasonal_ingredient","cook_time","explore_reason","created_at"]
    return [dict(zip(cols, r)) for r in rows]

def load_all_week_starts():
    if _use_cloud_store():
        return cloud_store.load_all_week_starts()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT week_start FROM menus ORDER BY week_start DESC")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def load_recent_menus_for_prompt(weeks=3):
    if _use_cloud_store():
        return cloud_store.load_recent_menus_for_prompt(weeks)
    """直近3週間の献立を取得（ローテーション制御用）"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    cutoff = (datetime.date.today() - datetime.timedelta(weeks=weeks)).strftime("%Y-%m-%d")
    c.execute("""
        SELECT m.week_start, m.day, m.main_dish, m.side_dish, f.rating
        FROM menus m
        LEFT JOIN feedback f ON m.week_start = f.week_start AND (m.main_dish = f.dish_name OR m.side_dish = f.dish_name)
        WHERE m.week_start >= ?
        ORDER BY m.week_start DESC, m.id
    """, (cutoff,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_high_rated_dishes():
    if _use_cloud_store():
        return cloud_store.get_high_rated_dishes()
    """◎評価の料理リストを取得"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT dish_name FROM feedback WHERE rating = '◎' ORDER BY saved_at DESC LIMIT 20")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_recent_dishes(weeks=3):
    if _use_cloud_store():
        return cloud_store.get_recent_dishes(weeks)
    """直近3週間に登場した料理（除外リスト用）"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    cutoff = (datetime.date.today() - datetime.timedelta(weeks=weeks)).strftime("%Y-%m-%d")
    c.execute("""
        SELECT DISTINCT main_dish FROM menus WHERE week_start >= ?
        UNION
        SELECT DISTINCT side_dish FROM menus WHERE week_start >= ?
    """, (cutoff, cutoff))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]


# ============================================================
# フィードバック
# ============================================================

def save_feedback(week_start, feedbacks: list):
    if _use_cloud_store():
        return cloud_store.save_feedback(week_start, feedbacks)
    """
    feedbacks: [{"dish_name": ..., "rating": "◎"/"○"/"△"/"✕"}, ...]
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 同週のフィードバックを削除して上書き
    c.execute("DELETE FROM feedback WHERE week_start = ?", (week_start,))
    for fb in feedbacks:
        c.execute("INSERT INTO feedback (week_start, dish_name, rating) VALUES (?, ?, ?)",
                  (week_start, fb["dish_name"], fb["rating"]))
    conn.commit()
    conn.close()

def load_feedback(week_start=None):
    if _use_cloud_store():
        return cloud_store.load_feedback(week_start)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if week_start:
        c.execute("SELECT * FROM feedback WHERE week_start = ? ORDER BY id", (week_start,))
    else:
        c.execute("SELECT * FROM feedback ORDER BY week_start DESC, id")
    rows = c.fetchall()
    conn.close()
    cols = ["id","week_start","dish_name","rating","saved_at"]
    return [dict(zip(cols, r)) for r in rows]

def get_ng_dishes():
    if _use_cloud_store():
        return cloud_store.get_ng_dishes()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT dish_name FROM feedback WHERE rating = '✕'")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]


# ============================================================
# 買い物リスト
# ============================================================

def save_shopping_items(week_start, items: list):
    if _use_cloud_store():
        return cloud_store.save_shopping_items(week_start, items)
    """
    items: [{"category": ..., "item_name": ...}, ...]
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM shopping_items WHERE week_start = ?", (week_start,))
    for item in items:
        c.execute("INSERT INTO shopping_items (week_start, category, item_name) VALUES (?, ?, ?)",
                  (week_start, item["category"], item["item_name"]))
    conn.commit()
    conn.close()

def load_shopping_items(week_start):
    if _use_cloud_store():
        return cloud_store.load_shopping_items(week_start)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, category, item_name, checked FROM shopping_items WHERE week_start = ? ORDER BY category, id", (week_start,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "category": r[1], "item_name": r[2], "checked": bool(r[3])} for r in rows]

def toggle_shopping_item(item_id, checked: bool):
    if _use_cloud_store():
        return cloud_store.toggle_shopping_item(item_id, checked)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE shopping_items SET checked = ? WHERE id = ?", (1 if checked else 0, item_id))
    conn.commit()
    conn.close()

def reset_shopping_checks(week_start):
    if _use_cloud_store():
        return cloud_store.reset_shopping_checks(week_start)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE shopping_items SET checked = 0 WHERE week_start = ?", (week_start,))
    conn.commit()
    conn.close()


# ============================================================
# レシピ＆お気に入り
# ============================================================

def save_recipe(dish_name: str, recipe_text: str):
    if _use_cloud_store():
        return cloud_store.save_recipe(dish_name, recipe_text)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 既存のis_favoriteを保持するため、INSERT OR IGNORE で一度いれ、UPDATEする
    c.execute("INSERT OR IGNORE INTO recipes (dish_name, recipe_text, is_favorite) VALUES (?, ?, 0)", (dish_name, recipe_text))
    c.execute("UPDATE recipes SET recipe_text = ? WHERE dish_name = ?", (recipe_text, dish_name))
    conn.commit()
    conn.close()

def get_recipe(dish_name: str):
    if _use_cloud_store():
        return cloud_store.get_recipe(dish_name)
    """" 存在する場合は {"recipe_text": "...", "is_favorite": 1/0} を返す """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT recipe_text, is_favorite FROM recipes WHERE dish_name = ?", (dish_name,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"recipe_text": row[0], "is_favorite": row[1]}
    return None

def toggle_favorite_recipe(dish_name: str, is_favorite: bool):
    if _use_cloud_store():
        return cloud_store.toggle_favorite_recipe(dish_name, is_favorite)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE recipes SET is_favorite = ? WHERE dish_name = ?", (1 if is_favorite else 0, dish_name))
    conn.commit()
    conn.close()

def get_favorite_recipes():
    if _use_cloud_store():
        return cloud_store.get_favorite_recipes()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT dish_name, recipe_text, created_at FROM recipes WHERE is_favorite = 1 ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return [{"dish_name": r[0], "recipe_text": r[1], "created_at": r[2]} for r in rows]

def get_all_recipes():
    if _use_cloud_store():
        return cloud_store.get_all_recipes()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT dish_name, recipe_text, is_favorite, created_at FROM recipes ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return [{"dish_name": r[0], "recipe_text": r[1], "is_favorite": bool(r[2]), "created_at": r[3]} for r in rows]

def get_all_dishes_from_menus():
    if _use_cloud_store():
        return cloud_store.get_all_dishes_from_menus()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT main_dish FROM menus WHERE main_dish != '' AND main_dish IS NOT NULL
        UNION
        SELECT DISTINCT side_dish FROM menus WHERE side_dish != '' AND side_dish IS NOT NULL
    """)
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0] != "なし" and r[0].strip()]
