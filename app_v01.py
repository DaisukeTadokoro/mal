import streamlit as st
from datetime import datetime
import requests
import json
import base64

st.set_page_config(page_title="MAL Group Prototype", layout="wide")

USERS = ["金", "黒瀬", "田所"]

# ---------- GitHub設定 ----------
GITHUB_TOKEN = st.secrets["github"]["token"]
GITHUB_OWNER = st.secrets["github"]["owner"]
GITHUB_REPO = st.secrets["github"]["repo"]
GITHUB_FILE_PATH = st.secrets["github"]["file_path"]  # 例: "data/group_log.json"
GITHUB_BRANCH = st.secrets["github"].get("branch", "main")

GITHUB_API_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
)

# ---------- OpenAI設定 ----------
OPENAI_API_KEY = st.secrets["openai"]["api_key"]
OPENAI_MODEL = st.secrets["openai"].get("model", "gpt-4o-mini")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


# ---------- GitHubユーティリティ ----------
def load_group_log_from_github():
    """GitHub上の JSON から group_log を読み込む。なければ空リスト。"""
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(GITHUB_API_URL, headers=headers)

    if r.status_code == 404:
        # まだファイルが存在しない場合 → 空のログ
        st.session_state.github_file_sha = None
        return []

    r.raise_for_status()
    data = r.json()
    content_b64 = data["content"]
    content_str = base64.b64decode(content_b64).decode("utf-8")

    raw_list = json.loads(content_str)  # [{time: "...", sender: "...", text: "..."}]
    log = []
    for m in raw_list:
        try:
            t = datetime.fromisoformat(m["time"])
        except Exception:
            t = datetime.strptime(m["time"], "%Y-%m-%dT%H:%M:%S")
        log.append({"time": t, "sender": m["sender"], "text": m["text"]})

    # 後で更新するときに必要な sha
    st.session_state.github_file_sha = data["sha"]
    return log


def save_group_log_to_github(log):
    """group_log を GitHub 上の JSON に書き戻す。"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }

    # datetime を文字列に直してから JSON に
    serializable = [
        {
            "time": m["time"].isoformat(),
            "sender": m["sender"],
            "text": m["text"],
        }
        for m in log
    ]
    content_str = json.dumps(serializable, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("ascii")

    payload = {
        "message": "Update group_log from MAL app",
        "content": content_b64,
        "branch": GITHUB_BRANCH,
    }

    # 既存ファイルなら sha が必要
    sha = st.session_state.get("github_file_sha")
    if sha is not None:
        payload["sha"] = sha

    r = requests.put(GITHUB_API_URL, headers=headers, data=json.dumps(payload))
    r.raise_for_status()
    data = r.json()
    # 新しい sha を保存
    st.session_state.github_file_sha = data["content"]["sha"]


# ---------- GPT要約ユーティリティ ----------
def summarize_with_gpt(text: str, max_chars: int = 120) -> str:
    """
    OpenAI Chat Completions API を使って、
    text を max_chars 文字以内の日本語に要約する。
    """
    prompt = (
        f"次の文章を {max_chars} 文字以内で、自然に要約してください。そして英語に翻訳してください。"
        f"重要な情報はできるだけ残してください。\n\n"
        f"---\n{text}\n---"
    )

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "あなたはグループチャット用に文章を短くまとめるアシスタントです。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }

    try:
        r = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        summary = data["choices"][0]["message"]["content"].strip()
        # 念のため max_chars でカット
        if len(summary) > max_chars:
            summary = summary[:max_chars] + "…"
        return summary
    except Exception as e:
        # 失敗したときは、元文を120字カットして返す
        st.sidebar.error(f"要約APIエラー: {e}")
        trimmed = text.strip()
        if len(trimmed) > max_chars:
            trimmed = trimmed[:max_chars] + "…"
        return trimmed


# ---------- 初期化 ----------
# group_log は GitHub 上の JSON をソース・オブ・トゥルースにする
if "group_log" not in st.session_state:
    try:
        st.session_state.group_log = load_group_log_from_github()
    except Exception as e:
        st.session_state.group_log = []
        st.session_state.github_file_sha = None
        st.sidebar.error(f"GitHubからログを読み込めませんでした: {e}")

# 個人用 MAL 状態はローカルセッションでOK
if "mal_states" not in st.session_state:
    st.session_state.mal_states = {
        u: {"personal_log": [], "feedback_log": []} for u in USERS
    }

# input_box 初期化
if "input_box" not in st.session_state:
    st.session_state.input_box = ""


# ---------- MALロジック ----------
def mal_rewrite_for_group(user, text, group_context):
    """
    MALロジック（GPT要約版）:
    - ユーザーの本音テキストを GPT で120字以内に要約
    - グループ板には要約のみ（名前なし）
    - フィードバックでプレビューとアドバイスを返す
    """
    original = text.strip()
    summarized = summarize_with_gpt(original, max_chars=120)

    # グループ板に出す本文（名前を含めない）
    group_msg = summarized

    # MAL内部の「投稿イメージ」としては名前付きで持つ
    preview = f"{user}：{summarized}"

    feedback = (
        "MALよりフィードバック：\n"
        f"・グループにはこう投稿しました → 「{preview}」\n"
        "・元の文章のニュアンスをなるべく残しつつ、120字以内に要約しました。\n"
        "・もし伝わりきらない部分があれば、追加でMALに補足を書いてください。"
    )
    return group_msg, feedback


def mal_group_summary():
    logs = st.session_state.group_log
    if not logs:
        return "（まだグループでのやり取りはありません）"
    last = logs[-5:]
    users_involved = sorted({m["sender"] for m in last})
    return f"MAL総評：直近では {', '.join(users_involved)} が対話中です。"


# ---------- UI ----------
st.sidebar.title("MAL Group Prototype")
current_user = st.sidebar.selectbox("あなたは誰？", USERS)
st.sidebar.write(f"あなたには専用の {current_user} MALがいます。")

# 手動リロードボタン（GitHubの最新状態を取り込みたいとき用）
if st.sidebar.button("GitHubから最新グループログを再読み込み"):
    try:
        st.session_state.group_log = load_group_log_from_github()
        st.sidebar.success("最新のログを読み込みました。")
    except Exception as e:
        st.sidebar.error(f"再読み込みに失敗しました: {e}")

st.title("MAL付きグループチャット（GPT要約バージョン）")

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

    def send_to_mal():
        text = st.session_state.input_box.strip()
        if not text:
            return

        now = datetime.now()

        # 個人ログに保存
        st.session_state.mal_states[current_user]["personal_log"].append(
            {"time": now, "text": text}
        )

        # MALがグループ用に整形（GPT要約）
        group_msg, feedback = mal_rewrite_for_group(
            current_user,
            text,
            st.session_state.group_log,
        )

        # グループ板に投稿（ローカルの group_log を更新）
        st.session_state.group_log.append(
            {"time": now, "sender": current_user, "text": group_msg}
        )

        # GitHub に保存（ここがマルチユーザー同期のキモ）
        try:
            save_group_log_to_github(st.session_state.group_log)
        except Exception as e:
            st.error(f"GitHubへの保存に失敗しました: {e}")

        # 個人フィードバック保存
        st.session_state.mal_states[current_user]["feedback_log"].append(
            {"time": now, "text": feedback}
        )

        # 入力欄をクリア
        st.session_state.input_box = ""

    # 入力欄
    st.text_area(
        "MALにまず本音で書き込んでください（グループにはまだ出ません）",
        height=150,
        key="input_box",
    )

    # ボタン
    st.button("MALに送る → MALが要約してグループに投稿", on_click=send_to_mal)

    # フィードバック表示
    st.markdown("#### MALからのフィードバック")
    feedback_log = st.session_state.mal_states[current_user]["feedback_log"]
    if feedback_log:
        last_fb = feedback_log[-1]
        st.code(last_fb["text"])
    else:
        st.caption("まだMALからのフィードバックはありません。")


