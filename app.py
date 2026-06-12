"""
app.py - 献立アプリ メインファイル
"""
import streamlit as st
import datetime
import hmac
import io
import os
import urllib.parse
import qrcode
from PIL import Image

import db
import ai
import app_rules
import importlib
importlib.reload(db)
importlib.reload(ai)

# ============================================================
# 初期設定
# ============================================================
st.set_page_config(
    page_title="🍳 献立アプリ",
    page_icon="🍳",
    layout="wide",
)


def _get_secret_value(*keys):
    for key in keys:
        try:
            if key in st.secrets and st.secrets[key]:
                return str(st.secrets[key])
        except Exception:
            pass
        value = os.environ.get(key)
        if value:
            return str(value)
    return ""


def require_app_password():
    password = _get_secret_value("KONDATE_APP_PASSWORD", "APP_PASSWORD")
    if not password:
        st.error("アプリパスワードが未設定です。Streamlit Secrets に KONDATE_APP_PASSWORD を設定してください。")
        st.stop()

    lock_until = st.session_state.get("login_lock_until")
    if lock_until and datetime.datetime.now() < lock_until:
        remaining = int((lock_until - datetime.datetime.now()).total_seconds() // 60) + 1
        st.error(f"ログイン失敗が続いたため、あと約{remaining}分待ってから再試行してください。")
        st.stop()

    if st.session_state.get("app_authenticated"):
        with st.sidebar:
            if st.button("ログアウト"):
                st.session_state.pop("app_authenticated", None)
                st.rerun()
        return

    st.title("献立アプリ")
    with st.form("app_login_form"):
        entered = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン")

    if submitted:
        if hmac.compare_digest(entered, password):
            st.session_state["app_authenticated"] = True
            st.session_state.pop("login_fail_count", None)
            st.session_state.pop("login_lock_until", None)
            st.rerun()
        fail_count = st.session_state.get("login_fail_count", 0) + 1
        st.session_state["login_fail_count"] = fail_count
        if fail_count >= 5:
            st.session_state["login_lock_until"] = datetime.datetime.now() + datetime.timedelta(minutes=5)
            st.error("ログイン失敗が続いたため、5分後に再試行してください。")
            st.stop()
        st.error("パスワードが違います。")

    st.stop()


require_app_password()

# DB初期化
db.init_db()

# APIキー取得
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except Exception:
    st.error("APIキーが設定されていません。`.streamlit/secrets.toml` に `GOOGLE_API_KEY` を設定してください。")
    st.stop()

# ============================================================
# カスタムCSS
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans JP', sans-serif;
}

/* ヘッダー */
.app-header {
    background: linear-gradient(135deg, #FF6B35 0%, #F7C59F 50%, #EFEFD0 100%);
    padding: 1.5rem 2rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 20px rgba(255,107,53,0.2);
}
.app-header h1 {
    color: #2D3436;
    font-size: 2rem;
    font-weight: 700;
    margin: 0;
}
.app-header p {
    color: #636E72;
    margin: 0.3rem 0 0 0;
    font-size: 0.9rem;
}

/* 料理カード */
.dish-card {
    background: white;
    border: 1px solid #F0F0F0;
    border-radius: 12px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.8rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    transition: transform 0.2s, box-shadow 0.2s;
}
.dish-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(0,0,0,0.1);
}
.dish-card .day-badge {
    display: inline-block;
    background: linear-gradient(135deg, #FF6B35, #FF8E53);
    color: white;
    border-radius: 20px;
    padding: 0.2rem 0.8rem;
    font-size: 0.85rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
}
.dish-card .main {
    font-size: 1.1rem;
    font-weight: 700;
    color: #2D3436;
}
.dish-card .side {
    font-size: 0.9rem;
    color: #636E72;
    margin-top: 0.2rem;
}
.dish-card .meta {
    font-size: 0.8rem;
    color: #B2BEC3;
    margin-top: 0.4rem;
}
.dish-card .explore {
    background: #FFF3E0;
    border-left: 3px solid #FF6B35;
    border-radius: 4px;
    padding: 0.4rem 0.8rem;
    font-size: 0.85rem;
    color: #E55A00;
    margin-top: 0.5rem;
}

/* 評価ボタン */
.rating-◎ { background: #00B894 !important; color: white !important; }
.rating-○ { background: #74B9FF !important; color: white !important; }
.rating-△ { background: #FDCB6E !important; color: #2D3436 !important; }
.rating-✕ { background: #FF7675 !important; color: white !important; }

/* 買い物リスト */
.category-header {
    font-weight: 700;
    color: #FF6B35;
    font-size: 1rem;
    border-bottom: 2px solid #FF6B35;
    margin: 1rem 0 0.5rem 0;
    padding-bottom: 0.3rem;
}

/* サマリーカード */
.summary-card {
    background: linear-gradient(135deg, #FF6B35 0%, #FF8E53 100%);
    color: white;
    border-radius: 12px;
    padding: 1rem 1.5rem;
    display: inline-block;
    margin-right: 1rem;
    margin-bottom: 1rem;
    box-shadow: 0 4px 12px rgba(255,107,53,0.3);
}
.summary-card .label { font-size: 0.8rem; opacity: 0.9; }
.summary-card .value { font-size: 1.3rem; font-weight: 700; }

/* タブスタイル */
.stTabs [data-baseweb="tab"] {
    font-size: 1rem;
    font-weight: 500;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# ヘッダー
# ============================================================
st.markdown("""
<div class="app-header">
    <h1>🍳 献立アプリ</h1>
    <p>4人家族の週5日分の献立をAIが自動作成。土曜日の作り置きをサポート！</p>
</div>
""", unsafe_allow_html=True)

# ============================================================
# タブ
# ============================================================
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🍳 献立を作る",
    "📝 フィードバック",
    "🛒 買い物リスト",
    "📅 履歴",
    "⚙️ 設定",
    "📖 レシピ一覧",
    "📅 週別一覧"
])

# ヘルパー
def render_recipe_expander(dish_name, key_prefix):
    if not dish_name or dish_name == "なし" or dish_name == "":
        return
    with st.expander(f"📖 {dish_name} のレシピ"):
        recipe_data = db.get_recipe(dish_name)
        if recipe_data:
            is_fav = recipe_data["is_favorite"] == 1
            new_fav = st.checkbox("⭐ お気に入りに登録", value=is_fav, key=f"fav_{key_prefix}_{dish_name}")
            if new_fav != is_fav:
                db.toggle_favorite_recipe(dish_name, new_fav)
                st.rerun()
            st.markdown(recipe_data["recipe_text"])
        else:
            if st.button(f"✨ AIでレシピを生成", key=f"gen_{key_prefix}_{dish_name}"):
                with st.spinner("レシピ生成中..."):
                    res = ai.generate_recipe(GOOGLE_API_KEY, dish_name)
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        db.save_recipe(dish_name, res["recipe"])
                        st.rerun()

# ヘルパー
def get_week_start():
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")

def week_label(ws: str) -> str:
    d = datetime.datetime.strptime(ws, "%Y-%m-%d").date()
    end = d + datetime.timedelta(days=4)
    return f"{d.strftime('%Y/%m/%d')}（月）〜 {end.strftime('%m/%d')}（金）"

# セッション初期化ヘルパー
def init_session():
    if "generated_menu" not in st.session_state:
        st.session_state.generated_menu = None
    if "feedback_ratings" not in st.session_state:
        st.session_state.feedback_ratings = {}
    if "checked_items" not in st.session_state:
        st.session_state.checked_items = {}

init_session()


def menu_items_from_shopping_list(shopping_list):
    items = []
    if isinstance(shopping_list, dict):
        for cat, item_list in shopping_list.items():
            if not isinstance(item_list, list):
                continue
            for item in item_list:
                if str(item).strip():
                    items.append({"category": cat, "item_name": item})
    return items


def save_generated_menu_result(week_start, result):
    db.save_menu(week_start, result.get("menus", []))
    db.save_shopping_items(week_start, menu_items_from_shopping_list(result.get("shopping_list", {})))


def show_validation_result(validation):
    for error in validation.get("errors", []):
        st.error(f"保存不可: {error}")
    warnings = validation.get("warnings", [])
    if warnings:
        st.warning("⚠️ 確認が必要な点があります。")
        for warning in warnings:
            st.write(f"- {warning}")


def prepare_validated_save(pending_key, week_start, result, validation, success_message, rerun_after_save=False):
    st.session_state[pending_key] = {
        "week_start": week_start,
        "result": result,
        "validation": validation,
        "success_message": success_message,
        "rerun_after_save": rerun_after_save,
    }


def render_pending_validated_save(pending_key):
    pending = st.session_state.get(pending_key)
    if not pending:
        return False
    validation = pending.get("validation", {})
    show_validation_result(validation)
    if validation.get("errors"):
        return False
    if st.button("⚠️ 警告あり。保存する", key=f"save_{pending_key}", type="primary", use_container_width=True):
        result = pending["result"]
        week_start = pending["week_start"]
        save_generated_menu_result(week_start, result)
        st.session_state.generated_menu = result
        st.session_state.pop(pending_key, None)
        st.success(pending.get("success_message", "警告付きで保存しました。"))
        if pending.get("rerun_after_save"):
            st.rerun()
        return True
    return False


def handle_validated_generated_result(pending_key, week_start, result, validation, success_message, rerun_after_save=False):
    if validation.get("errors"):
        show_validation_result(validation)
        return False
    if validation.get("warnings"):
        prepare_validated_save(pending_key, week_start, result, validation, success_message, rerun_after_save)
        return False
    save_generated_menu_result(week_start, result)
    st.session_state.pop(pending_key, None)
    st.success(success_message)
    if rerun_after_save:
        st.rerun()
    return True

# ============================================================
# タブ1: 献立を作る
# ============================================================
with tab1:
    st.markdown("### 🎯 対象週の選択と指示")
    
    today = datetime.date.today()
    this_monday = today - datetime.timedelta(days=today.weekday())
    next_monday = this_monday + datetime.timedelta(days=7)
    week_after_next = next_monday + datetime.timedelta(days=7)
    
    options = {
        f"今週 ({this_monday.strftime('%m/%d')}〜)": this_monday,
        f"来週 ({next_monday.strftime('%m/%d')}〜)": next_monday,
        f"再来週 ({week_after_next.strftime('%m/%d')}〜)": week_after_next,
    }
    
    # 金(4), 土(5), 日(6) の場合はデフォルトを来週にする
    default_index = 1 if today.weekday() >= 4 else 0
    
    selected_label = st.radio("献立の対象週", options=list(options.keys()), index=default_index, horizontal=True)
    target_date = options[selected_label]
    target_week_start = target_date.strftime("%Y-%m-%d")
    st.session_state.target_week_start = target_week_start
    
    # 既存献立の上書き警告
    existing_menus = db.load_menus(target_week_start)
    if existing_menus:
        st.warning("⚠️ **この週の献立はすでに作成済みです。**\n「献立を生成する」ボタンを押すと、既存の献立や買い物リストは完全に上書きされます。手動で一部だけ直したい場合は「週別一覧」タブをご利用ください。")
        

    st.markdown("### 📋 今週の追加指示")
    st.caption("曜日のジャンル変更や、特別なリクエスト（『来週の献立にして』『調理時間を短くして』等）を入力してください。※AIが必ず守ります。")

    custom_instruction = st.text_area(
        "追加指示（任意）",
        placeholder="例：4/16の献立をお願いします\n水曜は子供のリクエストでハンバーグに\n調理時間を2時間以内にしてください",
        height=100,
        label_visibility="collapsed",
    )

    col_btn, col_info = st.columns([2, 3])
    with col_btn:
        generate_btn = st.button("✨ 献立を生成する", type="primary", use_container_width=True)
    with col_info:
        season = ai.get_season()
        st.info(f"🌸 現在の季節: **{season}** | 旬の食材を優先的に使用します")

    if generate_btn:
        rulebook = app_rules.load_rulebook()
        framework = rulebook.get("framework", {})
        rules = rulebook.get("legacy_rules", {})
        
        # --- 検査官AIによるバリデーション ---
        val_res = ai.validate_instruction(GOOGLE_API_KEY, framework, rules, custom_instruction)
        if not val_res.get("valid"):
            st.error(f"⚠️ **指示内容の矛盾を検知しました**\n\n{val_res.get('reason')}")
            st.stop()

        with st.spinner("AIが献立を考えています... しばらくお待ちください🍳"):
            recent_dishes = db.get_recent_dishes(weeks=3)
            high_rated = db.get_high_rated_dishes()
            ng_dishes = db.get_ng_dishes()

            # フィードバックサマリー作成
            all_fb = db.load_feedback()
            fb_lines = []
            for fb in all_fb[-20:]:
                fb_lines.append(f"・{fb['dish_name']}：{fb['rating']}")
            feedback_summary = "\n".join(fb_lines) if fb_lines else ""
            
            target_week_label = week_label(target_week_start)

            result = ai.generate_menu(
                api_key=GOOGLE_API_KEY,
                target_week_label=target_week_label,
                framework=framework,
                custom_instruction=custom_instruction,
                recent_dishes=recent_dishes,
                high_rated=high_rated,
                feedback_summary=feedback_summary,
                ng_dishes=ng_dishes,
                rules=rules
            )

        if "error" in result:
            st.error(f"エラーが発生しました:\n{result['error']}")
        else:
            # UIの操作ミスに影響されないよう、対象週をデータにロックする
            result["week_start"] = target_week_start
            st.session_state.generated_menu = result
            # テキスト入力のUIキャッシュを強制破棄するためのID
            st.session_state.gen_id = st.session_state.get("gen_id", 0) + 1

            with st.spinner("生成結果を保存前チェック中..."):
                validation = ai.validate_generated_menu(
                    GOOGLE_API_KEY,
                    result,
                    target_week_label,
                    custom_instruction,
                    ng_dishes,
                    framework,
                    rules,
                )
            handle_validated_generated_result(
                "pending_save_t1_generate",
                target_week_start,
                result,
                validation,
                "献立が生成され、週別一覧に自動保存されました！",
            )

    render_pending_validated_save("pending_save_t1_generate")

    # 生成済み献立の表示
    if st.session_state.generated_menu:
        data = st.session_state.generated_menu
        menus = data.get("menus", [])

        st.markdown("---")
        st.markdown("### 📅 今週の献立")

        # サマリー表示
        total_time = data.get("total_cook_time", "")
        est_cost = data.get("estimated_cost", "")
        if total_time or est_cost:
            cols = st.columns(2)
            with cols[0]:
                st.markdown(f"""<div class="summary-card">
                    <div class="label">⏱️ 合計調理時間</div>
                    <div class="value">{total_time}</div>
                </div>""", unsafe_allow_html=True)
            with cols[1]:
                st.markdown(f"""<div class="summary-card">
                    <div class="label">💰 食材費の目安</div>
                    <div class="value">{est_cost}</div>
                </div>""", unsafe_allow_html=True)

        # 献立カード表示
        for m in menus:
            explore_html = ""
            if m.get("explore_reason"):
                explore_html = f'<div class="explore">🔍 開拓デー: {m["explore_reason"]}</div>'
            st.markdown(f"""
            <div class="dish-card">
                <div class="day-badge">{m.get("day", "")}曜日</div>
                <div class="main">🍽️ {m.get("main_dish", "")}</div>
                <div class="side">🥗 {m.get("side_dish", "")}</div>
                <div class="meta">🌿 旬食材: {m.get("seasonal_ingredient", "")} ｜ ⏱️ {m.get("cook_time", "")}</div>
                {explore_html}
            </div>
            """, unsafe_allow_html=True)
            
            rc1, rc2 = st.columns(2)
            with rc1:
                render_recipe_expander(m.get("main_dish", ""), f"t1_main_{m.get('day','')}")
            with rc2:
                render_recipe_expander(m.get("side_dish", ""), f"t1_side_{m.get('day','')}")

        st.markdown("---")

        with st.expander("✨ 一部だけ再生成 / ✏️ 手動で修正"):
            st.markdown("#### 🤖 特定の曜日だけAIで再生成")
            st.caption("「この日だけ別のメニューがいい」という場合、その曜日のメニューと買い物リストを自動で再計算します。")
            rc1, rc2 = st.columns([2, 1])
            with rc1:
                regen_day = st.selectbox("再生成する曜日", options=["月", "火", "水", "木", "金"], key="regen_day_t1")
            with rc2:
                st.markdown("<div style='margin-top: 1.8rem;'></div>", unsafe_allow_html=True)
                if st.button("✨ この曜日を再生成", use_container_width=True):
                    with st.spinner(f"{regen_day}曜日の献立を再生成中..."):
                        rulebook = app_rules.load_rulebook()
                        framework = rulebook.get("framework", {})
                        rules = rulebook.get("legacy_rules", {})
                        recent_dishes = db.get_recent_dishes(weeks=4)
                        high_rated = db.get_high_rated_dishes()
                        ng_dishes = db.get_ng_dishes()
                        all_fb = db.load_feedback()
                        fb_lines = [f"・{fb['dish_name']}：{fb['rating']}" for fb in all_fb[-20:]]
                        feedback_summary = "\n".join(fb_lines) if fb_lines else ""
                        target_week_label = week_label(st.session_state.get("target_week_start", get_week_start()))
                        
                        res = ai.generate_replacement_menu(
                            GOOGLE_API_KEY, target_week_label, regen_day, 
                            st.session_state.generated_menu["menus"], 
                            framework, custom_instruction, recent_dishes, high_rated, feedback_summary, ng_dishes, rules
                        )
                        if "error" in res:
                            st.error(res["error"])
                        else:
                            # ロック済みの週を維持
                            locked_week_start = st.session_state.generated_menu.get("week_start", target_week_start)
                            previous_menus = st.session_state.generated_menu.get("menus", [])
                            res["week_start"] = locked_week_start
                            st.session_state.generated_menu = res
                            st.session_state.gen_id = st.session_state.get("gen_id", 0) + 1

                            with st.spinner("再生成結果を保存前チェック中..."):
                                validation = ai.validate_generated_menu(
                                    GOOGLE_API_KEY,
                                    res,
                                    target_week_label,
                                    custom_instruction,
                                    ng_dishes,
                                    framework,
                                    rules,
                                    previous_menus,
                                    regen_day,
                                )
                            handle_validated_generated_result(
                                "pending_save_t1_regen",
                                locked_week_start,
                                res,
                                validation,
                                f"{regen_day}曜日を再生成し、保存しました！",
                                rerun_after_save=True,
                            )

                render_pending_validated_save("pending_save_t1_regen")

            st.markdown("---")
            st.markdown("#### ✏️ 手動でテキスト修正")
            st.caption("AIが作成した献立のテキストを自分で書き換えたい場合は、ここで変更してください。\n※枠内のテキストを変更するとリアルタイムで反映されます。修正後、下の「手動修正を保存してメール送信」を押してください。")
            st.warning("⚠️ 料理名を手動で変更した場合、**「買い物リスト」は自動的には更新されません**。買い物リストも修正したい場合は、上の「✨ この曜日を再生成」を利用してください。")
            
            locked_week = data.get("week_start", target_week_start)
            gen_id = st.session_state.get("gen_id", 0)
            
            new_menus = []
            for i, m in enumerate(menus):
                st.markdown(f"**{m.get('day', '')}曜日**")
                col1, col2 = st.columns(2)
                with col1:
                    new_main = st.text_input("主菜", value=m.get("main_dish", ""), key=f"edit_main_{locked_week}_{gen_id}_{i}")
                with col2:
                    new_side = st.text_input("副菜", value=m.get("side_dish", ""), key=f"edit_side_{locked_week}_{gen_id}_{i}")
                
                new_menu = m.copy()
                new_menu["main_dish"] = new_main
                new_menu["side_dish"] = new_side
                new_menus.append(new_menu)
            
            # 入力された内容をすぐセッションに反映
            st.session_state.generated_menu["menus"] = new_menus

        st.markdown("---")
        col_save, col_reset = st.columns([2, 1])
        with col_save:
            if st.button("💾 確定してメール送信（手動修正も保存）", type="primary", use_container_width=True):
                # UIの現在値ではなく、生成時にロックした週を使う（混入防止）
                week_start_locked = data.get("week_start", target_week_start)
                # menus（古い変数）ではなく、最新のnew_menusを保存する
                db.save_menu(week_start_locked, new_menus)

                # 買い物リストも保存
                shopping_list = data.get("shopping_list", {})
                items = []
                for cat, item_list in shopping_list.items():
                    for item in item_list:
                        items.append({"category": cat, "item_name": item})
                db.save_shopping_items(week_start_locked, items)
                
                email_status = "（メールは未設定のため送信されませんでした）"
                if "GMAIL_USER" in st.secrets and "GMAIL_APP_PASSWORD" in st.secrets:
                    try:
                        import smtplib
                        from email.mime.text import MIMEText
                        from email.mime.multipart import MIMEMultipart
                        
                        gmail_user = st.secrets["GMAIL_USER"]
                        gmail_password = st.secrets["GMAIL_APP_PASSWORD"]
                        to_email = "f.kazushige@gmail.com"
                        
                        msg = MIMEMultipart()
                        msg["Subject"] = f"【献立アプリ】{week_label(week_start_locked)}の献立と買い物リスト"
                        msg["From"] = gmail_user
                        msg["To"] = to_email
                        
                        body = f"{week_label(week_start_locked)}の献立です。\n\n【献立】\n"
                        # メールにも最新のnew_menusを使用
                        for m in new_menus:
                            body += f"・{m.get('day')}曜：{m.get('main_dish')} / {m.get('side_dish')}（調理目安: {m.get('cook_time')}）\n"
                            if m.get('explore_reason'):
                                body += f"  ※開拓: {m.get('explore_reason')}\n"
                        
                        body += "\n【買い物リスト】\n"
                        for cat, item_list in shopping_list.items():
                            body += f"\n■ {cat}\n"
                            body += "、".join(item_list) + "\n"
                        
                        msg.attach(MIMEText(body, "plain"))
                        
                        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
                        server.login(gmail_user, gmail_password)
                        server.send_message(msg)
                        server.quit()
                        email_status = "（✉️ f.kazushige@gmail.comへ自動送信しました）"
                    except smtplib.SMTPAuthenticationError as e:
                        email_status = "（⚠️ メール送信エラー: Gmailのアプリパスワードが設定されていないか、間違っています。`.streamlit/secrets.toml` に正しいパスワードを設定してください）"
                    except Exception as e:
                        email_status = f"（⚠️ メール送信エラー: {e}）"

                st.success(f"✅ 献立と買い物リストを保存しました！「買い物リスト」タブで確認できます\n{email_status}")
                st.balloons()

        with col_reset:
            if st.button("🔄 再生成する", use_container_width=True):
                st.session_state.generated_menu = None
                st.rerun()


# ============================================================
# タブ2: フィードバック
# ============================================================
with tab2:
    st.markdown("### 📝 今週の料理フィードバック")
    st.caption("子供たちの反応を評価してください。次回の献立に自動反映されます。")

    week_starts = db.load_all_week_starts()
    if not week_starts:
        st.info("まだ献立が保存されていません。「献立を作る」タブで献立を生成・保存してください。")
    else:
        selected_week = st.selectbox(
            "対象週を選択",
            options=week_starts,
            format_func=week_label,
        )

        menus = db.load_menus(selected_week)
        existing_fb = db.load_feedback(selected_week)
        existing_map = {fb["dish_name"]: fb["rating"] for fb in existing_fb}

        if not menus:
            st.warning("この週の献立データが見つかりません。")
        else:
            ratings = {}
            rating_options = ["◎ 大好評", "○ 食べた", "△ 少し食べた", "✕ 食べなかった"]
            rating_map = {
                "◎ 大好評": "◎", "○ 食べた": "○",
                "△ 少し食べた": "△", "✕ 食べなかった": "✕"
            }
            reverse_map = {v: k for k, v in rating_map.items()}

            st.markdown("---")
            for m in menus:
                st.markdown(f"**{m['day']}曜日**")
                c1, c2 = st.columns(2)
                # メイン料理
                with c1:
                    def_main = reverse_map.get(existing_map.get(m["main_dish"], ""), "○ 食べた")
                    sel_main = st.selectbox(
                        f"🍽️ {m['main_dish']}",
                        options=rating_options,
                        index=rating_options.index(def_main),
                        key=f"fb_main_{selected_week}_{m['day']}",
                    )
                    ratings[m["main_dish"]] = rating_map[sel_main]
                # 副菜
                with c2:
                    def_side = reverse_map.get(existing_map.get(m["side_dish"], ""), "○ 食べた")
                    sel_side = st.selectbox(
                        f"🥗 {m['side_dish']}",
                        options=rating_options,
                        index=rating_options.index(def_side),
                        key=f"fb_side_{selected_week}_{m['day']}",
                    )
                    ratings[m["side_dish"]] = rating_map[sel_side]
                st.markdown("---")

            if st.button("💾 フィードバックを保存", type="primary", use_container_width=True):
                fb_list = [{"dish_name": dish, "rating": rating}
                           for dish, rating in ratings.items() if dish]
                db.save_feedback(selected_week, fb_list)
                st.success("✅ フィードバックを保存しました！次回の献立生成に反映されます。")

            # フィードバック凡例
            with st.expander("評価の目安"):
                st.markdown("""
                | 評価 | 意味 | 次回の扱い |
                |------|------|-----------|
                | ◎ 大好評 | 子供たちが喜んで食べた | 優先的に再登場 |
                | ○ 食べた | 普通に食べた | 通常ローテーション |
                | △ 少し食べた | 食べ渋ったが完食 | 調理法を変えて再挑戦 |
                | ✕ 食べなかった | ほぼ食べなかった | しばらく除外 |
                """)


# ============================================================
# タブ3: 買い物リスト
# ============================================================
with tab3:
    st.markdown("### 🛒 買い物リスト")
    st.caption("土曜日のお買い物に。チェックしながら使えます。")

    week_starts_shop = db.load_all_week_starts()
    if not week_starts_shop:
        st.info("まだ献立が保存されていません。")
    else:
        selected_week_shop = st.selectbox(
            "対象週を選択",
            options=week_starts_shop,
            format_func=week_label,
            key="shop_week_select",
        )

        items = db.load_shopping_items(selected_week_shop)
        if not items:
            st.warning("この週の買い物リストが見つかりません。")
        else:
            # カテゴリ別グループ化
            categories = {}
            for item in items:
                cat = item["category"]
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(item)

            # チェック状態をセッションから取得
            check_key = f"check_{selected_week_shop}"
            if check_key not in st.session_state:
                st.session_state[check_key] = {item["id"]: item["checked"] for item in items}

            # カテゴリアイコン
            cat_icons = {
                "肉類": "🥩", "魚介類": "🐟", "野菜": "🥦",
                "乳製品・卵": "🥛", "調味料・乾物": "🧂", "その他": "📦"
            }

            col_list, col_qr = st.columns([2, 1])

            with col_list:
                total = sum(len(v) for v in categories.values())
                checked_count = sum(1 for v in st.session_state[check_key].values() if v)
                st.progress(checked_count / total if total > 0 else 0,
                           text=f"✅ {checked_count}/{total} 品 チェック済み")

                for cat, cat_items in categories.items():
                    icon = cat_icons.get(cat, "📦")
                    st.markdown(f'<div class="category-header">{icon} {cat}</div>', unsafe_allow_html=True)
                    for item in cat_items:
                        item_id = item["id"]
                        checked = st.session_state[check_key].get(item_id, False)
                        new_checked = st.checkbox(
                            item["item_name"],
                            value=checked,
                            key=f"item_{item_id}",
                        )
                        if new_checked != checked:
                            st.session_state[check_key][item_id] = new_checked
                            db.toggle_shopping_item(item_id, new_checked)

                st.markdown("---")
                if st.button("🔄 チェックをすべてリセット", use_container_width=True):
                    st.session_state[check_key] = {item["id"]: False for item in items}
                    db.reset_shopping_checks(selected_week_shop)
                    st.rerun()

            with col_qr:
                st.markdown("### 📱 スマホで確認")

                # テキスト形式で買い物リストを作成
                list_text = f"🛒 買い物リスト\n{week_label(selected_week_shop)}\n\n"
                for cat, cat_items in categories.items():
                    list_text += f"【{cat}】\n"
                    for item in cat_items:
                        list_text += f"{item['item_name']}\n"
                    list_text += "\n"

                # LINEシェアボタン
                line_text = urllib.parse.quote(list_text)
                line_url = f"https://line.me/R/msg/text/?{line_text}"
                st.markdown(f"""
                <a href="{line_url}" target="_blank">
                    <button style="
                        background: #06C755;
                        color: white;
                        border: none;
                        border-radius: 8px;
                        padding: 0.6rem 1.5rem;
                        font-size: 1rem;
                        font-weight: 700;
                        cursor: pointer;
                        width: 100%;
                        margin-bottom: 1rem;
                    ">💬 LINEで共有</button>
                </a>
                """, unsafe_allow_html=True)

                # QRコード生成
                if st.button("📷 QRコードを生成", use_container_width=True):
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=6,
                        border=4,
                    )
                    qr.add_data(line_url)
                    qr.make(fit=True)
                    qr_img = qr.make_image(fill_color="#2D3436", back_color="white")

                    buf = io.BytesIO()
                    qr_img.save(buf, format="PNG")
                    buf.seek(0)
                    st.image(buf, caption="スマホでスキャンするとLINEで共有できます", use_container_width=True)

                # メモアプリ・Google Keep用
                with st.expander("📝 メモアプリにコピーする"):
                    st.caption("右上のコピーボタンを押して、Google Keepなどに貼り付けてください。")
                    st.code(list_text, language="")
                    st.markdown("<a href='https://keep.google.com/' target='_blank'>🔗 Google Keepを開く</a>", unsafe_allow_html=True)


# ============================================================
# タブ4: 履歴
# ============================================================
with tab4:
    st.markdown("### 📅 献立履歴")
    st.caption("過去の献立と子供たちの反応を確認できます")

    all_week_starts = db.load_all_week_starts()
    if not all_week_starts:
        st.info("まだ献立が保存されていません。")
    else:
        for ws in all_week_starts:
            menus = db.load_menus(ws)
            feedbacks = db.load_feedback(ws)
            fb_map = {fb["dish_name"]: fb["rating"] for fb in feedbacks}

            with st.expander(f"📅 {week_label(ws)}", expanded=(ws == all_week_starts[0])):
                for m in menus:
                    main_rating = fb_map.get(m["main_dish"], "―")
                    side_rating = fb_map.get(m["side_dish"], "―")

                    rating_colors = {"◎": "#00B894", "○": "#74B9FF", "△": "#FDCB6E", "✕": "#FF7675", "―": "#B2BEC3"}

                    cols = st.columns([1, 3, 3, 1, 1])
                    with cols[0]:
                        st.markdown(f"**{m['day']}曜**")
                    with cols[1]:
                        st.markdown(f"🍽️ {m['main_dish']}")
                    with cols[2]:
                        st.markdown(f"🥗 {m['side_dish']}")
                    with cols[3]:
                        color = rating_colors.get(main_rating, "#B2BEC3")
                        st.markdown(f"<span style='color:{color};font-weight:700;font-size:1.2rem'>{main_rating}</span>",
                                   unsafe_allow_html=True)
                    with cols[4]:
                        color = rating_colors.get(side_rating, "#B2BEC3")
                        st.markdown(f"<span style='color:{color};font-weight:700;font-size:1.2rem'>{side_rating}</span>",
                                   unsafe_allow_html=True)

                    rc1, rc2 = st.columns(2)
                    with rc1:
                        render_recipe_expander(m["main_dish"], f"t4_m_{ws}_{m['day']}")
                    with rc2:
                        render_recipe_expander(m["side_dish"], f"t4_s_{ws}_{m['day']}")
                    st.markdown("---")

                # 高評価料理まとめ
                excellent = [d for d, r in fb_map.items() if r == "◎"]
                if excellent:
                    st.success(f"⭐ この週の大好評: {' / '.join(excellent)}")

                poor = [d for d, r in fb_map.items() if r == "✕"]
                if poor:
                    st.warning(f"⚠️ 食べなかった料理: {' / '.join(poor)}")


# ============================================================
# タブ5: 設定
# ============================================================
with tab5:
    st.markdown("### ⚙️ 設定")

    # ルール台帳
    st.markdown("#### 📘 ルール台帳")
    st.caption("基本ルール・曜日別フレーム・作り置き・副菜共有は `rules.xlsx` に一元化されています。変更すると次回の献立生成から反映されます。")
    st.code(app_rules.RULEBOOK_PATH, language="")
    try:
        rulebook = app_rules.load_rulebook()
        st.markdown("##### 曜日別フレーム")
        st.dataframe(rulebook.get("framework_rows", []), use_container_width=True)
        st.markdown("##### 有効なルール")
        st.dataframe(rulebook.get("rules", []), use_container_width=True)
    except Exception as e:
        st.error(f"ルール台帳を読み込めませんでした: {e}")

    st.markdown("---")

    # APIキー確認
    st.markdown("#### 🔑 API設定")
    st.success("✅ Gemini APIキー: 設定済み")
    st.caption("APIキーを変更したい場合は `.streamlit/secrets.toml` を直接編集してください。")

    st.markdown("---")

    # データ管理
    st.markdown("#### 🗄️ データ管理")
    col_a, col_b = st.columns(2)
    with col_a:
        all_menus = db.load_menus()
        st.metric("保存済み献立", f"{len(db.load_all_week_starts())} 週分")
    with col_b:
        all_fb = db.load_feedback()
        st.metric("フィードバック件数", f"{len(all_fb)} 件")


# ============================================================
# タブ6: レシピ一覧
# ============================================================
with tab6:
    st.markdown("### 📖 レシピ一覧")
    
    rtab1, rtab2, rtab3 = st.tabs(["🔍 登録済みレシピ", "➕ レシピを自分で登録", "✨ 過去の献立からAI作成"])
    
    with rtab1:
        st.markdown("#### 🔍 登録済みレシピ一覧")
        
        all_recipes = db.get_all_recipes()
        if not all_recipes:
            st.info("まだ登録されたレシピがありません。")
        else:
            col_search, col_filter = st.columns([3, 1])
            with col_search:
                search_query = st.text_input("料理名で検索", key="search_recipe")
            with col_filter:
                only_fav = st.checkbox("⭐ お気に入りのみ", key="filter_fav")
            
            filtered_recipes = all_recipes
            if search_query:
                filtered_recipes = [r for r in filtered_recipes if search_query.lower() in r["dish_name"].lower()]
            if only_fav:
                filtered_recipes = [r for r in filtered_recipes if r["is_favorite"]]
                
            st.caption(f"全 {len(filtered_recipes)} 件表示")
            for r in filtered_recipes:
                icon = "⭐" if r["is_favorite"] else "📖"
                with st.expander(f"{icon} {r['dish_name']}"):
                    is_fav = st.checkbox("お気に入り登録", value=r["is_favorite"], key=f"fav_rt1_{r['dish_name']}")
                    if is_fav != r["is_favorite"]:
                        db.toggle_favorite_recipe(r['dish_name'], is_fav)
                        st.rerun()
                    st.markdown(r["recipe_text"])

    with rtab2:
        st.markdown("#### ➕ レシピを自分で登録")
        st.caption("オリジナルのレシピや、Youtube・クックパッド等のお気に入りURLメモなどを自由に登録できます。")
        
        with st.form("manual_recipe_form"):
            new_dish_name = st.text_input("料理名（献立アプリで使う名前と同じにすると紐づきます）", max_chars=100)
            new_recipe_text = st.text_area("レシピ内容やURLなど", height=200)
            submitted = st.form_submit_button("💾 保存する", type="primary")
            if submitted:
                if new_dish_name.strip() and new_recipe_text.strip():
                    db.save_recipe(new_dish_name.strip(), new_recipe_text.strip())
                    st.success(f"「{new_dish_name}」のレシピを保存しました！「登録済みレシピ」タブで確認・編集できます。")
                else:
                    st.error("料理名とレシピ内容の両方を入力してください。")

    with rtab3:
        st.markdown("#### ✨ 過去の献立からAI作成")
        st.caption("今まで提案された献立の中で、まだレシピが存在しない料理の一覧です。気になるものを選んでAIでレシピを生成できます。")
        
        all_dishes = db.get_all_dishes_from_menus()
        existing_dish_names = [r["dish_name"] for r in db.get_all_recipes()]
        missing_dishes = [d for d in all_dishes if d not in existing_dish_names]
        
        if not missing_dishes:
            st.info("過去の献立に含まれるすべての料理のレシピがすでに登録されています！🎉")
        else:
            search_missing = st.text_input("未登録料理の検索", key="search_missing")
            if search_missing:
                missing_dishes = [d for d in missing_dishes if search_missing.lower() in d.lower()]
                
            st.caption(f"未登録の料理: {len(missing_dishes)}件")
            for dish in missing_dishes:
                col_name, col_btn = st.columns([3, 1])
                with col_name:
                    st.write(f"🍽️ {dish}")
                with col_btn:
                    if st.button("✨ AIでレシピ生成", key=f"gen_missing_{dish}"):
                        with st.spinner(f"「{dish}」のレシピを生成中..."):
                            res = ai.generate_recipe(GOOGLE_API_KEY, dish)
                            if "error" in res:
                                st.error(res["error"])
                            else:
                                db.save_recipe(dish, res["recipe"])
                                st.success(f"「{dish}」のレシピを生成しました！")
                                st.rerun()
                st.markdown("---")

# ============================================================
# タブ7: 週別一覧
# ============================================================
with tab7:
    st.markdown("### 📅 週別一覧（編集可）")
    st.caption("保存済みの献立を手動で修正できます。保存時、最新の献立と買い物リストがメールで送信されます。")
    all_week_starts = db.load_all_week_starts()
    if not all_week_starts:
        st.info("まだ献立が登録されていません。")
    else:
        selected_week_t7 = st.selectbox(
            "編集する週を選択",
            options=all_week_starts,
            format_func=week_label,
            key="sel_week_t7"
        )
        menus_t7 = db.load_menus(selected_week_t7)
        
        st.markdown("---")
        st.markdown("#### 🤖 特定の曜日だけAIで再生成")
        st.caption("指定した曜日だけのメニューを差し替え、必要に応じて買い物リストも最新化します。\n（※再生成した内容は自動で保存されます）")
        rc1, rc2 = st.columns([2, 1])
        with rc1:
            regen_day_t7 = st.selectbox("再生成する曜日", options=["月", "火", "水", "木", "金"], key="regen_day_t7")
        with rc2:
            st.markdown("<div style='margin-top: 1.8rem;'></div>", unsafe_allow_html=True)
            if st.button("✨ この曜日を再生成して保存", use_container_width=True):
                with st.spinner(f"{regen_day_t7}曜日の献立を再生成中..."):
                    rulebook = app_rules.load_rulebook()
                    framework = rulebook.get("framework", {})
                    rules = rulebook.get("legacy_rules", {})
                    recent_dishes = db.get_recent_dishes(weeks=4)
                    high_rated = db.get_high_rated_dishes()
                    ng_dishes = db.get_ng_dishes()
                    all_fb = db.load_feedback()
                    fb_lines = [f"・{fb['dish_name']}：{fb['rating']}" for fb in all_fb[-20:]]
                    feedback_summary = "\n".join(fb_lines) if fb_lines else ""
                    target_week_label = week_label(selected_week_t7)
                    
                    res = ai.generate_replacement_menu(
                        GOOGLE_API_KEY, target_week_label, regen_day_t7, 
                        menus_t7, 
                        framework, "特になし", recent_dishes, high_rated, feedback_summary, ng_dishes, rules
                    )
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        with st.spinner("再生成結果を保存前チェック中..."):
                            validation = ai.validate_generated_menu(
                                GOOGLE_API_KEY,
                                res,
                                target_week_label,
                                "特になし",
                                ng_dishes,
                                framework,
                                rules,
                                menus_t7,
                                regen_day_t7,
                            )
                        handle_validated_generated_result(
                            "pending_save_t7_regen",
                            selected_week_t7,
                            res,
                            validation,
                            f"{regen_day_t7}曜日を再生成し、保存しました！",
                            rerun_after_save=True,
                        )

            render_pending_validated_save("pending_save_t7_regen")

        st.markdown("---")
        st.markdown("#### ✏️ 手動でテキスト修正")
        with st.form("edit_menu_form_t7"):
            edited_menus_t7 = []
            for i, m in enumerate(menus_t7):
                st.markdown(f"**{m.get('day', '')}曜日**")
                col1, col2 = st.columns(2)
                with col1:
                    new_main = st.text_input(f"{m.get('day', '')}曜 主菜", value=m.get("main_dish", ""), key=f"t7_main_{selected_week_t7}_{i}", label_visibility="collapsed")
                with col2:
                    new_side = st.text_input(f"{m.get('day', '')}曜 副菜", value=m.get("side_dish", ""), key=f"t7_side_{selected_week_t7}_{i}", label_visibility="collapsed")
                
                new_m = m.copy()
                new_m["main_dish"] = new_main
                new_m["side_dish"] = new_side
                edited_menus_t7.append(new_m)
            
            st.markdown("---")
            if st.form_submit_button("💾 保存して最新の献立をメール送信", type="primary"):
                db.save_menu(selected_week_t7, edited_menus_t7)
                
                email_status = "（メールは未設定のため送信されませんでした）"
                if "GMAIL_USER" in st.secrets and "GMAIL_APP_PASSWORD" in st.secrets:
                    try:
                        import smtplib
                        from email.mime.text import MIMEText
                        from email.mime.multipart import MIMEMultipart
                        
                        gmail_user = st.secrets["GMAIL_USER"]
                        gmail_password = st.secrets["GMAIL_APP_PASSWORD"]
                        to_email = "f.kazushige@gmail.com"
                        
                        msg = MIMEMultipart()
                        msg["Subject"] = f"【献立アプリ】{week_label(selected_week_t7)}の献立（手動更新版）"
                        msg["From"] = gmail_user
                        msg["To"] = to_email
                        
                        body = f"{week_label(selected_week_t7)}の最新の献立です。\n\n【献立】\n"
                        for m in edited_menus_t7:
                            body += f"・{m.get('day')}曜：{m.get('main_dish')} / {m.get('side_dish')}（調理目安: {m.get('cook_time')}）\n"
                            if m.get('explore_reason'):
                                body += f"  ※開拓: {m.get('explore_reason')}\n"
                        
                        shopping_items = db.load_shopping_items(selected_week_t7)
                        if shopping_items:
                            body += "\n【買い物リスト】\n"
                            categories = {}
                            for item in shopping_items:
                                cat = item["category"]
                                if cat not in categories:
                                    categories[cat] = []
                                categories[cat].append(item["item_name"])
                            for cat, item_list in categories.items():
                                body += f"\n■ {cat}\n"
                                body += "、".join(item_list) + "\n"
                        
                        msg.attach(MIMEText(body, "plain"))
                        
                        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
                        server.login(gmail_user, gmail_password)
                        server.send_message(msg)
                        server.quit()
                        email_status = "（✉️ f.kazushige@gmail.comへ自動送信しました）"
                    except smtplib.SMTPAuthenticationError as e:
                        email_status = "（⚠️ メール送信エラー: Gmailのアプリパスワードが設定されていないか、間違っています。`.streamlit/secrets.toml` に正しいパスワードを設定してください）"
                    except Exception as e:
                        email_status = f"（⚠️ メール送信エラー: {e}）"
                
                st.success(f"✅ 献立を更新しました！\n{email_status}")

