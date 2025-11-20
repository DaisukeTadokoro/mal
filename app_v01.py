import streamlit as st
from datetime import datetime

st.set_page_config(page_title="MAL Group Prototype", layout="wide")

USERS = ["金", "黒瀬", "田所"]

# ---------- 初期化 ----------
if "group_log" not in st.session_state:
    st.session_state.group_log = []  # [{"time":..., "sender":..., "text":...}, ...]

if "mal_states" not in st.session_state:
    st.session_state.mal_states = {
        u: {"personal_log": [], "feedback_log": []} for u in USERS
    }

# ★ input_box もここで初期化しておく（ウィジェットを作る前）
if "input_box" not in st.session_state:
    st.session_state.input_box = ""

# ---------- ユーティリティ ----------
def mal_rewrite_for_group(user, text, group_context):
    """
    最小MALロジック：
    - グループ表示では sender が別枠で出るので、本文から名前は外す
    - ただしフィードバック文の中では「user：本文」としてプレビューを見せる
    """
    trimmed = text.strip()
    if len(trimmed) > 120:
        trimmed = trimmed[:120] + "…"

    # グループ板に出す本文（名前を含めない）
    group_msg = trimmed

    # MAL内部の「投稿イメージ」としては名前付きで持つ
    preview = f"{user}：{trimmed}"

    feedback = (
        "MALよりフィードバック：\n"
        f"・グループにはこう投稿しました → 「{preview}」\n"
        "・トーン：フラット\n"
        "・補足したいことがあれば、もう少し具体例を書いてみても良いかもしれません。"
    )
    return group_msg, feedback


def mal_group_summary():
    """
    MAL同士の“会話”の雰囲気を出すための簡易サマリー。
    本当はここにMALたちの内部対話を載せるイメージ。
    """
    logs = st.session_state.group_log
    if not logs:
        return "（まだグループでのやり取りはありません）"

    last = logs[-5:]
    users_involved = sorted({m["sender"] for m in last})
    return f"MAL総評：直近では {', '.join(users_involved)} が対話中です。"


# ---------- UI ----------
st.sidebar.title("MAL Group Prototype")
current_user = st.sidebar.selectbox("あなたは誰？", USERS)
st.sidebar.write(f"あなたには専用の MAL_{current_user} がいます。")

st.title("MAL付きグループチャット（最小プロトタイプ）")

col1, col2 = st.columns([2, 1])

# --- 左: グループ板 ---
with col1:
    st.subheader("グループ板（MAL経由のメッセージのみ表示）")
    if st.session_state.group_log:
        for msg in st.session_state.group_log:
            ts = msg["time"].strftime("%H:%M:%S")
            st.markdown(f"**[{ts}] {msg['sender']}**: {msg['text']}")
    else:
        st.info("まだMAL経由のメッセージはありません。")

    st.markdown("---")
    st.markdown(f"🧠 {mal_group_summary()}")

# --- 右: 自分 ↔ MAL のやり取り ---
with col2:
    st.subheader(f"あなたと {current_user} MALの対話")

    # ★ 送信処理をコールバック関数にまとめる
    def send_to_mal():
        text = st.session_state.input_box.strip()
        if not text:
            return

        # 個人ログに保存
        st.session_state.mal_states[current_user]["personal_log"].append(
            {"time": datetime.now(), "text": text}
        )

        # MALがグループ用に整形
        group_msg, feedback = mal_rewrite_for_group(
            current_user,
            text,
            st.session_state.group_log,
        )

        # グループ板に投稿
        st.session_state.group_log.append(
            {"time": datetime.now(), "sender": current_user, "text": group_msg}
        )

        # 個人フィードバック保存
        st.session_state.mal_states[current_user]["feedback_log"].append(
            {"time": datetime.now(), "text": feedback}
        )

        # 入力欄をクリア（←ここならOK）
        st.session_state.input_box = ""

    # 入力欄（値は session_state.input_box と同期）
    st.text_area(
        "MALにまず本音で書き込んでください（グループにはまだ出ません）",
        height=150,
        key="input_box",
    )

    # ボタン：押されたときだけ send_to_mal が呼ばれる
    st.button("MALに送る → MALが調整してグループに投稿", on_click=send_to_mal)

    # フィードバック表示
    st.markdown("#### MALからのフィードバック")
    feedback_log = st.session_state.mal_states[current_user]["feedback_log"]
    if feedback_log:
        last_fb = feedback_log[-1]
        st.code(last_fb["text"])
    else:
        st.caption("まだMALからのフィードバックはありません。")

