"""
ai.py - Gemini AI 献立生成モジュール
"""
import datetime
import json
import re
import google.generativeai as genai
import app_rules


def get_season() -> str:
    month = datetime.date.today().month
    if month in [3, 4, 5]:
        return "春"
    elif month in [6, 7, 8]:
        return "夏"
    elif month in [9, 10, 11]:
        return "秋"
    else:
        return "冬"


def validate_instruction(api_key: str, framework: dict, rules: dict, custom_instruction: str) -> dict:
    if not custom_instruction or not custom_instruction.strip():
        return {"valid": True}
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        rulebook = app_rules.load_rulebook()
        formatted_rules = app_rules.format_rulebook_for_prompt(rulebook)
        
        prompt = f"""あなたは献立生成システムの入力チェッカー（検査官AI）です。
以下の「ルール台帳」と「ユーザーの追加指示」を確認してください。

【ルール台帳】
絶対ルール（週次指示でも上書き不可）:
{formatted_rules["absolute"]}

基本ルール（週次指示で上書き可）:
{formatted_rules["base"]}

曜日別フレーム:
| 曜日 | ジャンル |
|------|----------|
{formatted_rules["framework"]}

【ユーザーの追加指示】
{custom_instruction}

【最重要ルール ★★★ 必ず守ること ★★★】
ユーザーの追加指示は「今週限りの一時的な上書き・カスタマイズ」です。
基本ルール・参考ルール・曜日別フレームとの違いは「矛盾」ではなく「今週の変更」です。
ただし、絶対ルールとの明確な衝突、または追加指示の中の自己矛盾だけは矛盾として扱ってください。

以下はすべて正当なリクエストであり、絶対に矛盾と判定しないでください：
- 曜日別ジャンルの変更（例：「水曜はカレーにして」）
- 作り置き対象日の追加・変更（例：「水曜と木曜も半作り置きで」）
- 副菜の共有ルールの変更（例：「火曜と水曜の副菜を同じにして」）
- その他、基本設定の一時的な変更・拡張

矛盾ありと判定してよいのは、追加指示の中で自己矛盾がある場合のみです。
例：「水曜はカレーにして」と「水曜にカレーは絶対だめ」が同時に書かれている場合。

【出力形式】
必ず以下のJSON形式のみで出力してください。
{{
  "is_conflict": true または false,
  "reason": "矛盾ありの場合、その理由を簡潔に"
}}
"""
        response = model.generate_content(prompt)
        text = response.text
        
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
        else:
            data = json.loads(text.strip())
            
        if data.get("is_conflict"):
            return {"valid": False, "reason": data.get("reason", "設定と追加指示の間に矛盾を検知しました。")}
        return {"valid": True}
        
    except Exception as e:
        # 判定エラー時は進行を妨げないよう通す
        return {"valid": True, "error": str(e)}

def build_prompt(target_week_label: str, framework: dict, custom_instruction: str,
                 recent_dishes: list, high_rated: list,
                 feedback_summary: str, ng_dishes: list = None, rules: dict = None) -> str:

    season = get_season()

    try:
        rulebook = app_rules.load_rulebook()
    except Exception:
        rulebook = app_rules.fallback_rulebook(framework, rules)
    formatted_rules = app_rules.format_rulebook_for_prompt(rulebook)

    recent_text = "、".join(recent_dishes) if recent_dishes else "なし"
    high_rated_text = "、".join(high_rated) if high_rated else "なし"
    ng_text = "、".join(ng_dishes) if ng_dishes else "特になし"

    prompt = f"""あなたは家庭料理の専門家です。以下の条件に基づき、対象週（{target_week_label}）の5日分の献立を提案してください。

**対象週：** {target_week_label}
**家族構成：** 4人家族（大人2人、6歳・3歳の子供2人）
**現在の季節：** {season}

**【超重要・絶対遵守：今週の追加指示】**
{custom_instruction if custom_instruction.strip() else "特になし"}
※上記の追加指示は今週限りの最優先指示です。下の「基本ルール」「参考ルール」「曜日別フレーム」と違う場合は、週次指示を優先して献立・調理時間・買い物リストに反映してください。
※ただし「絶対ルール」だけは週次指示でも破らないでください。

**絶対ルール（週次指示でも上書き不可）：**
{formatted_rules["absolute"]}

**基本ルール（週次指示で上書き可）：**
{formatted_rules["base"]}

**参考ルール（守れる範囲で考慮）：**
{formatted_rules["reference"]}

**曜日別フレームワーク（週次指示で上書き可）：**
| 曜日 | ジャンル |
|------|----------|
{formatted_rules["framework"]}

**作り置き設定（週次指示で上書き可）：**
{formatted_rules["prep"]}

**副菜共有グループ（週次指示で上書き可）：**
{formatted_rules["shared_side_dishes"]}

**【絶対禁止リスト（過去の低評価料理・食材）】**
- 以下の料理や類似の料理は絶対に提案しないでください。
{ng_text}

**直近で登場した料理（マンネリ防止の参考。週次指示で指定された場合は週次指示を優先）：**
{recent_text}

**過去に高評価（◎）だった料理（時々取り入れつつ、別アレンジも提案すること）：**
{high_rated_text}

**前週フィードバック：**
{feedback_summary if feedback_summary.strip() else "なし"}
- ✕の食材は調理法を変えて再挑戦、◎は継続候補へ

**出力形式：必ずJSON形式のみで返してください。前後に説明文を入れないでください。**

```json
{{
  "menus": [
    {{
      "day": "月",
      "main_dish": "料理名",
      "side_dish": "副菜または汁物名",
      "seasonal_ingredient": "使用する旬食材",
      "cook_time": "調理時間目安（例：30分）",
      "explore_reason": ""
    }},
    {{
      "day": "火",
      "main_dish": "料理名",
      "side_dish": "副菜または汁物名",
      "seasonal_ingredient": "使用する旬食材",
      "cook_time": "調理時間目安",
      "explore_reason": ""
    }},
    {{
      "day": "水",
      "main_dish": "料理名",
      "side_dish": "副菜または汁物名",
      "seasonal_ingredient": "使用する旬食材",
      "cook_time": "調理時間目安",
      "explore_reason": "水曜開拓デーのため、この料理を選んだ理由を1〜2文で説明"
    }},
    {{
      "day": "木",
      "main_dish": "料理名",
      "side_dish": "副菜または汁物名",
      "seasonal_ingredient": "使用する旬食材",
      "cook_time": "調理時間目安",
      "explore_reason": ""
    }},
    {{
      "day": "金",
      "main_dish": "料理名",
      "side_dish": "副菜または汁物名",
      "seasonal_ingredient": "使用する旬食材",
      "cook_time": "調理時間目安",
      "explore_reason": ""
    }}
  ],
  "shopping_list": {{
    "肉類": ["品名1", "品名2"],
    "魚介類": ["品名1"],
    "野菜": ["品名1", "品名2", "品名3"],
    "乳製品・卵": ["品名1"],
    "調味料・乾物": ["品名1", "品名2"],
    "その他": ["品名1"]
  }},
  "total_cook_time": "合計調理時間の目安（例：約3時間30分）",
  "estimated_cost": "食材費の目安（例：約8,000円）"
}}
```
"""
    return prompt


def generate_menu(api_key: str, target_week_label: str, framework: dict, custom_instruction: str,
                  recent_dishes: list, high_rated: list,
                  feedback_summary: str, ng_dishes: list = None, rules: dict = None) -> dict:
    """
    Gemini APIを使って献立を生成し、辞書形式で返す
    Returns: {"menus": [...], "shopping_list": {...}, ...} or {"error": "..."}
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = build_prompt(target_week_label, framework, custom_instruction, recent_dishes, high_rated, feedback_summary, ng_dishes, rules)
        response = model.generate_content(prompt)
        text = response.text

        # JSON抽出
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # コードブロックなしで直接JSONの場合
            json_str = text.strip()

        data = json.loads(json_str)
        return data

    except json.JSONDecodeError as e:
        return {"error": f"JSONパースエラー: {e}\n\nAI応答:\n{text}"}
    except Exception as e:
        return {"error": f"AI生成エラー: {e}"}


def generate_replacement_menu(api_key: str, target_week_label: str, target_day: str, current_menus: list, framework: dict, custom_instruction: str, recent_dishes: list, high_rated: list, feedback_summary: str, ng_dishes: list = None, rules: dict = None) -> dict:
    """
    指定された曜日の献立のみを再生成し、買い物リスト等を再計算して返す
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        current_data = {"menus": current_menus}
        current_menus_json = json.dumps(current_data, ensure_ascii=False, indent=2)
        season = get_season()
        try:
            rulebook = app_rules.load_rulebook()
        except Exception:
            rulebook = app_rules.fallback_rulebook(framework, rules)
        formatted_rules = app_rules.format_rulebook_for_prompt(rulebook)
        
        recent_text = "、".join(recent_dishes) if recent_dishes else "なし"
        ng_text = "、".join(ng_dishes) if ng_dishes else "特になし"
        
        prompt = f"""あなたは家庭料理の専門家です。
現在、以下の5日分の献立が提案されていますが、これらの中で「{target_day}曜日」のメニューだけを新しく再提案してください。

**現在の献立（JSON形式）：**
```json\n{current_menus_json}\n```

**【依頼事項】**
1. {target_day}曜日のメニュー（主菜、副菜、旬食材、調理時間、選定理由等）だけを、以前とは違う、新しい斬新な内容に書き換えてください。
2. {target_day}曜日以外（他の4日分）のメニューは、絶対に書き換えずに「現在の献立」の通りそのまま保持してください。
3. 5日分の確定したメニューをもとに、最終的な `shopping_list`、`total_cook_time`、`estimated_cost` を再計算して併せて出力してください。

**考慮すべき条件：**
- 季節：{season}
- 追加指示があれば最優先：{custom_instruction if custom_instruction.strip() else "特になし"}
- 絶対ルール（週次指示でも上書き不可）：
{formatted_rules["absolute"]}
- 基本ルール（週次指示で上書き可）：
{formatted_rules["base"]}
- 曜日別フレームワーク（週次指示で上書き可）：
{formatted_rules["framework"]}
- 作り置き設定：
{formatted_rules["prep"]}
- 副菜共有グループ：
{formatted_rules["shared_side_dishes"]}
- 直近メニュー（参考。週次指示で指定された場合は週次指示を優先）：{recent_text}
- 【絶対禁止リスト】過去の低評価料理：{ng_text}（絶対に提案しないでください）

**出力形式：必ず元の形式と同じJSON構造のみで出力してください。前後に説明文は不要です。**
"""
        response = model.generate_content(prompt)
        text = response.text
        
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = text.strip()
            
        data = json.loads(json_str)
        return data

    except json.JSONDecodeError as e:
        return {"error": f"JSONパースエラー: {e}\n\nAI応答:\n{text}"}
    except Exception as e:
        return {"error": f"部分再生成エラー: {e}"}


def _extract_json(text: str) -> dict:
    json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(1))
    return json.loads(text.strip())


def _dish_names(menu: dict) -> list:
    return [str(menu.get(key, "")).strip() for key in ("main_dish", "side_dish") if str(menu.get(key, "")).strip()]


def _instruction_allows_short_week(custom_instruction: str) -> bool:
    text = custom_instruction or ""
    short_week_patterns = [
        r"[1-4]\s*日分",
        r"[一二三四]\s*日分",
        r"(月|火|水|木|金)[・、,\s]*(月|火|水|木|金)",
        r"(だけ|のみ)",
    ]
    return any(re.search(pattern, text) for pattern in short_week_patterns)


def _machine_validate_generated_menu(result: dict, custom_instruction: str = "", ng_dishes: list = None,
                                     current_menus: list = None, target_day: str = None) -> dict:
    warnings = []
    errors = []
    ng_dishes = ng_dishes or []

    if not isinstance(result, dict):
        return {"warnings": warnings, "errors": ["AI応答が辞書形式ではないため保存できません。"]}

    menus = result.get("menus")
    if not isinstance(menus, list):
        return {"warnings": warnings, "errors": ["`menus` がリスト形式ではないため保存できません。"]}
    if not menus:
        return {"warnings": warnings, "errors": ["献立が0件のため保存できません。"]}

    expected_days = ["月", "火", "水", "木", "金"]
    days = []
    for idx, menu in enumerate(menus, start=1):
        if not isinstance(menu, dict):
            errors.append(f"{idx}件目の献立が辞書形式ではないため保存できません。")
            continue
        day = str(menu.get("day", "")).strip()
        days.append(day)
        for field in ["day", "main_dish", "side_dish", "seasonal_ingredient", "cook_time", "explore_reason"]:
            if field not in menu:
                warnings.append(f"{day or idx}件目に `{field}` がありません。")
        if not str(menu.get("main_dish", "")).strip():
            warnings.append(f"{day or idx}件目の主菜が空欄です。")
        if not str(menu.get("side_dish", "")).strip():
            warnings.append(f"{day or idx}件目の副菜が空欄です。")

    if len(menus) != 5:
        if _instruction_allows_short_week(custom_instruction):
            warnings.append(f"週次指示により、今回は通常の5日分ではなく{len(menus)}日分として生成されています。")
        else:
            warnings.append(f"通常は5日分ですが、今回は{len(menus)}日分です。内容を確認してから保存してください。")

    duplicate_days = sorted({day for day in days if day and days.count(day) > 1})
    if duplicate_days:
        warnings.append(f"曜日が重複しています: {', '.join(duplicate_days)}")

    unexpected_days = [day for day in days if day and day not in expected_days]
    if unexpected_days:
        warnings.append(f"想定外の曜日表記があります: {', '.join(unexpected_days)}")

    shopping_list = result.get("shopping_list")
    if not isinstance(shopping_list, dict) or not shopping_list:
        warnings.append("買い物リストが空、または辞書形式ではありません。")
    else:
        item_count = 0
        for category, items in shopping_list.items():
            if not isinstance(items, list):
                warnings.append(f"買い物リスト `{category}` がリスト形式ではありません。")
                continue
            item_count += len([item for item in items if str(item).strip()])
        if item_count == 0:
            warnings.append("買い物リストに品目がありません。")

    ng_hits = []
    for menu in menus:
        if not isinstance(menu, dict):
            continue
        for dish in _dish_names(menu):
            for ng in ng_dishes:
                ng_text = str(ng).strip()
                if ng_text and (ng_text in dish or dish in ng_text):
                    ng_hits.append(dish)
    if ng_hits:
        warnings.append(f"過去の低評価料理に近い料理が含まれている可能性があります: {', '.join(sorted(set(ng_hits)))}")

    if current_menus is not None and target_day:
        current_by_day = {str(m.get("day", "")).strip(): m for m in current_menus if isinstance(m, dict)}
        result_by_day = {str(m.get("day", "")).strip(): m for m in menus if isinstance(m, dict)}
        for day, current in current_by_day.items():
            if day == target_day:
                continue
            updated = result_by_day.get(day)
            if not updated:
                warnings.append(f"部分再生成で、対象外の{day}曜日が結果から消えています。")
                continue
            for field in ["main_dish", "side_dish", "seasonal_ingredient", "cook_time", "explore_reason"]:
                if str(current.get(field, "")) != str(updated.get(field, "")):
                    warnings.append(f"部分再生成で、対象外の{day}曜日の `{field}` が変更されています。")
                    break

    return {"warnings": warnings, "errors": errors}


def validate_generated_menu(api_key: str, result: dict, target_week_label: str, custom_instruction: str = "",
                            ng_dishes: list = None, framework: dict = None, rules: dict = None,
                            current_menus: list = None, target_day: str = None) -> dict:
    """
    AI生成結果を保存前に検査する。
    Returns: {"ok": bool, "warnings": [...], "errors": [...]}
    """
    machine = _machine_validate_generated_menu(result, custom_instruction, ng_dishes, current_menus, target_day)
    warnings = list(machine["warnings"])
    errors = list(machine["errors"])

    if errors:
        return {"ok": False, "warnings": warnings, "errors": errors}

    try:
        try:
            rulebook = app_rules.load_rulebook()
        except Exception:
            rulebook = app_rules.fallback_rulebook(framework, rules)
        formatted_rules = app_rules.format_rulebook_for_prompt(rulebook)

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        result_json = json.dumps(result, ensure_ascii=False, indent=2)
        prompt = f"""あなたは献立アプリの保存前チェッカーです。
以下の週次指示、ルール、AI生成結果を確認してください。

【対象週】
{target_week_label}

【週次指示】
{custom_instruction if custom_instruction.strip() else "特になし"}

【絶対ルール】
{formatted_rules["absolute"]}

【基本ルール（週次指示で上書き可）】
{formatted_rules["base"]}

【生成結果JSON】
```json
{result_json}
```

【判定方針】
- 絶対ルール違反は error にしてください。
- 週次指示が弱くしか反映されていない、基本ルールと違う、3〜4日分など運用上保存できるものは warning にしてください。
- 週次指示で3日分・4日分・曜日指定がある場合、日数不足だけを強い問題にしないでください。
- 必ずJSONのみで返してください。

{{
  "warnings": ["警告文"],
  "errors": ["保存不可の理由"]
}}
"""
        response = model.generate_content(prompt)
        data = _extract_json(response.text)
        if isinstance(data.get("warnings"), list):
            warnings.extend(str(item) for item in data["warnings"] if str(item).strip())
        if isinstance(data.get("errors"), list):
            errors.extend(str(item) for item in data["errors"] if str(item).strip())
    except Exception as e:
        warnings.append(f"AI検査を完了できませんでした（機械チェックのみ実施）: {e}")

    warnings = list(dict.fromkeys(warnings))
    errors = list(dict.fromkeys(errors))
    return {"ok": not errors, "warnings": warnings, "errors": errors}


def generate_recipe(api_key: str, dish_name: str) -> dict:
    """
    料理名からレシピ（材料と手順）を生成する
    Returns: {"recipe": "Markdownテキスト"} or {"error": "..."}
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = f"""あなたは家庭料理の専門家です。
以下の料理について、4人家族（大人2人、子供子供2人）向けのレシピを作成してください。

**料理名:** {dish_name}

**出力形式:** Markdown形式で、以下の要素を含めてください。
- タイトル (料理名)
- 概要（1〜2文）
- 材料（4人分）
- 作り方・手順（4〜6ステップ程度で簡潔に）
- 子供が食べるための工夫ポイント（もしあれば1つ）
"""
        response = model.generate_content(prompt)
        text = response.text
        return {"recipe": text}

    except Exception as e:
        return {"error": f"レシピ生成エラー: {e}"}
