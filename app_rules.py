"""
app_rules.py - Excel rulebook loader for the menu app.
"""
from __future__ import annotations

import os
import zipfile

import cloud_store
import xml.etree.ElementTree as ET

RULEBOOK_PATH = os.path.join(os.path.dirname(__file__), "rules.xlsx")

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
NS_DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _bool(value) -> bool:
    return str(value or "").strip().upper() in {"TRUE", "1", "YES", "Y", "ON", "有効"}


def _read_sheet_rows(xlsx_path: str, sheet_name: str) -> list[list[str]]:
    with zipfile.ZipFile(xlsx_path) as z:
        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))

        rel_map = {}
        for rel in rels:
            rid = rel.attrib.get("Id")
            target = rel.attrib.get("Target", "")
            rel_map[rid] = "xl/" + target.lstrip("/")

        target_path = None
        for sheet in workbook.findall(f".//{NS_MAIN}sheet"):
            if sheet.attrib.get("name") == sheet_name:
                rid = sheet.attrib.get(f"{NS_DOC_REL}id")
                target_path = rel_map.get(rid)
                break
        if not target_path:
            return []

        shared_strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in sst.findall(f"{NS_MAIN}si"):
                texts = [t.text or "" for t in si.findall(f".//{NS_MAIN}t")]
                shared_strings.append("".join(texts))

        ws = ET.fromstring(z.read(target_path))
        rows = []
        for row in ws.findall(f".//{NS_MAIN}row"):
            values = []
            current_col = 0
            for cell in row.findall(f"{NS_MAIN}c"):
                ref = cell.attrib.get("r", "")
                col_letters = "".join(ch for ch in ref if ch.isalpha())
                if col_letters:
                    col_idx = 0
                    for ch in col_letters:
                        col_idx = col_idx * 26 + ord(ch.upper()) - 64
                    while current_col < col_idx - 1:
                        values.append("")
                        current_col += 1
                ctype = cell.attrib.get("t")
                if ctype == "inlineStr":
                    text_node = cell.find(f".//{NS_MAIN}t")
                    value = text_node.text if text_node is not None else ""
                elif ctype == "s":
                    v = cell.find(f"{NS_MAIN}v")
                    value = shared_strings[int(v.text)] if v is not None and v.text else ""
                else:
                    v = cell.find(f"{NS_MAIN}v")
                    value = v.text if v is not None else ""
                values.append(value or "")
                current_col += 1
            rows.append(values)
        return rows


def _records(rows: list[list[str]]) -> list[dict]:
    if not rows:
        return []
    headers = [str(h).strip() for h in rows[0]]
    result = []
    for row in rows[1:]:
        if not any(str(v).strip() for v in row):
            continue
        result.append({headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))})
    return result


def public_sample_rulebook() -> dict:
    framework = {
        "月": "カレー・シチュー・ハヤシライスなど",
        "火": "パスタ・洋風麺",
        "水": "新しい料理・食材に挑戦",
        "木": "どんぶり",
        "金": "うどん・そば・ラーメンなど",
    }
    return {
        "path": "",
        "rules": [
            {
                "priority": "絶対",
                "category": "安全",
                "rule": "食品アレルギーや医師から避けるよう指示された食材は使わない。実運用ではGoogle SheetのRulesで具体名を管理する。",
                "override_allowed": "FALSE",
            },
            {
                "priority": "基本",
                "category": "日数",
                "rule": "平日5日分を基本に作る。ただし週次指示で3日分・4日分・曜日指定がある場合は従う。",
                "override_allowed": "TRUE",
            },
            {
                "priority": "基本",
                "category": "献立構成",
                "rule": "各日はメイン1品と副菜または汁物1品にする。",
                "override_allowed": "TRUE",
            },
        ],
        "framework_rows": [{"day": day, "genre": genre, "active": "TRUE"} for day, genre in framework.items()],
        "framework": framework,
        "legacy_rules": {
            "prep_days": [],
            "prep_instruction": "",
            "prep_instructions": {},
            "shared_side_dishes": [],
        },
    }


def load_rulebook(path: str = RULEBOOK_PATH) -> dict:
    if path == RULEBOOK_PATH and cloud_store.is_enabled():
        try:
            cloud_rulebook = cloud_store.load_rulebook()
            if cloud_rulebook.get("rules") and cloud_rulebook.get("framework"):
                return cloud_rulebook
        except Exception:
            pass
    if not os.path.exists(path):
        return public_sample_rulebook()
    rules = _records(_read_sheet_rows(path, "Rules"))
    framework_rows = _records(_read_sheet_rows(path, "Framework"))

    active_rules = [r for r in rules if _bool(r.get("active"))]
    active_fw = [r for r in framework_rows if _bool(r.get("active"))]

    framework = {r.get("day", ""): r.get("genre", "") for r in active_fw if r.get("day")}
    prep_days = [r.get("day", "") for r in active_fw if _bool(r.get("prep_day")) and r.get("day")]
    prep_instructions = {
        r.get("day", ""): r.get("prep_instruction", "")
        for r in active_fw
        if _bool(r.get("prep_day")) and r.get("day")
    }

    groups = {}
    for row in active_fw:
        group = str(row.get("shared_side_group", "")).strip()
        day = row.get("day", "")
        if group and day:
            groups.setdefault(group, []).append(day)
    shared_side_dishes = [days for _, days in sorted(groups.items()) if len(days) >= 2]

    unique_prep_instructions = []
    for value in prep_instructions.values():
        if value and value not in unique_prep_instructions:
            unique_prep_instructions.append(value)

    return {
        "path": path,
        "rules": active_rules,
        "framework_rows": active_fw,
        "framework": framework,
        "legacy_rules": {
            "prep_days": prep_days,
            "prep_instruction": " / ".join(unique_prep_instructions),
            "prep_instructions": prep_instructions,
            "shared_side_dishes": shared_side_dishes,
        },
    }


def fallback_rulebook(framework: dict | None = None, rules: dict | None = None) -> dict:
    framework = framework or {}
    rules = rules or {}
    return {
        "path": "",
        "rules": [
            {"priority": "絶対", "category": "出力形式", "rule": "AI応答は指定JSON形式のみで返す。前後に説明文を入れない。", "override_allowed": "FALSE"},
            {"priority": "基本", "category": "献立構成", "rule": "各日はメイン1品＋副菜または汁物1品にする。", "override_allowed": "TRUE"},
        ],
        "framework_rows": [{"day": day, "genre": genre} for day, genre in framework.items()],
        "framework": framework,
        "legacy_rules": rules,
    }


def format_rulebook_for_prompt(rulebook: dict) -> dict:
    by_priority = {"絶対": [], "基本": [], "参考": []}
    for row in rulebook.get("rules", []):
        priority = row.get("priority", "基本")
        category = row.get("category", "")
        rule = row.get("rule", "")
        override = "週次指示で上書き可" if _bool(row.get("override_allowed")) else "週次指示でも上書き不可"
        if rule:
            by_priority.setdefault(priority, []).append(f"- [{category}] {rule}（{override}）")

    fw_rows = []
    legacy = rulebook.get("legacy_rules", {})
    prep_instructions = legacy.get("prep_instructions", {})
    prep_days = set(legacy.get("prep_days", []))
    for day, genre in rulebook.get("framework", {}).items():
        note = ""
        if day in prep_days:
            inst = prep_instructions.get(day) or legacy.get("prep_instruction") or "作り置きにする"
            note = f"（作り置き: {inst}）"
        fw_rows.append(f"| {day} | {genre}{note} |")

    shared_groups = legacy.get("shared_side_dishes", [])
    shared_text = "\n".join(f"- {'・'.join(days)} は副菜共有グループ" for days in shared_groups) or "- 指定なし"
    prep_text = "\n".join(
        f"- {day}: {prep_instructions.get(day) or legacy.get('prep_instruction') or '作り置きにする'}"
        for day in legacy.get("prep_days", [])
    ) or "- 指定なし"

    return {
        "absolute": "\n".join(by_priority.get("絶対", [])) or "- なし",
        "base": "\n".join(by_priority.get("基本", [])) or "- なし",
        "reference": "\n".join(by_priority.get("参考", [])) or "- なし",
        "framework": "\n".join(fw_rows) or "| 曜日 | ジャンル |\n|------|----------|",
        "shared_side_dishes": shared_text,
        "prep": prep_text,
    }
