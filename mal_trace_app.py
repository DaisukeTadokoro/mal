# app.py
import streamlit as st
import time
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
import uuid

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "db.json"

WORDS = ["沈む", "浮遊", "緊張", "空白", "澄む", "違和感", "温かい", "冷たい"]
COLORS = ["#111111", "#6B7280", "#F59E0B", "#10B981", "#3B82F6", "#EC4899"]

def load_db() -> Dict[str, Any]:
    if DB_PATH.exists():
        return json.loads(DB_PATH.read_text(encoding="utf-8"))
    return {"works": {}, "traces": []}

def save_db(db: Dict[str, Any]) -> None:
    DB_PATH.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

@dataclass
class Work:
    work_id: str
    title: str
    creator: str  # e.g., "Tadokoro"
    audio_path: str
    note: str
    created_at: float

@dataclass
class Trace:
    trace_id: str
    work_id: str
    responder: str  # e.g., "Minseo"
    word: str
    density: float
    color: str
    reverb: int
    dwell_sec: float
    section_memo: str
    created_at: float

def cluster_key(t: Trace) -> str:
    # 超簡易クラスタ：まずは言葉×残響で束ねる（後で距離ベースに拡張）
    return f"{t.word}|rv{t.reverb}"

st.set_page_config(page_title="MAL Trace Prototype", layout="wide")
db = load_db()

st.sidebar.title("MAL Trace")
page = st.sidebar.radio("Menu", ["Home", "Upload (Originator)", "Work Page (Responder)", "Dashboard (Originator)"])

# -----------------------------
# Home
# -----------------------------
if page == "Home":
    st.title("Works")
    if not db["works"]:
        st.info("まだ作品がありません。Uploadから追加してください。")
    else:
        for w in db["works"].values():
            st.subheader(w["title"])
            st.caption(f'Creator: {w["creator"]} / id={w["work_id"]}')
            st.write(w.get("note", ""))

# -----------------------------
# Upload
# -----------------------------
elif page == "Upload (Originator)":
    st.title("Upload (Originator)")
    creator = st.text_input("Creator", value="Tadokoro")
    title = st.text_input("Title", value="Tadokoro Piano #1")
    note = st.text_area("1-line note (optional)", value="(制作メモを一行だけ)")

    audio = st.file_uploader("Audio file (mp3/wav)", type=["mp3", "wav"])
    if st.button("Upload"):
        if not audio or not title.strip():
            st.error("音声ファイルとタイトルは必須です。")
        else:
            work_id = str(uuid.uuid4())[:8]
            out_path = DATA_DIR / f"{work_id}_{audio.name}"
            out_path.write_bytes(audio.getbuffer())

            w = Work(
                work_id=work_id,
                title=title.strip(),
                creator=creator.strip() or "Unknown",
                audio_path=str(out_path),
                note=note.strip(),
                created_at=time.time(),
            )
            db["works"][work_id] = asdict(w)
            save_db(db)
            st.success(f"Uploaded: {title} (work_id={work_id})")

# -----------------------------
# Work Page (Responder)
# -----------------------------
elif page == "Work Page (Responder)":
    st.title("Work Page (Responder)")
    if not db["works"]:
        st.warning("作品がありません。先にUploadしてください。")
        st.stop()

    responder = st.text_input("Responder", value="Minseo")

    work_id = st.selectbox("Select work", list(db["works"].keys()))
    w = db["works"][work_id]
    st.subheader(w["title"])
    st.caption(f'Creator: {w["creator"]}')

    # Audio player
    audio_bytes = Path(w["audio_path"]).read_bytes()
    st.audio(audio_bytes)

    # Dwell timer (manual start/stop for MVP)
    if "dwell_start" not in st.session_state:
        st.session_state.dwell_start = None
        st.session_state.dwell_sec = 0.0

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Start dwell"):
            st.session_state.dwell_start = time.time()
    with c2:
        if st.button("Stop dwell"):
            if st.session_state.dwell_start is not None:
                st.session_state.dwell_sec += time.time() - st.session_state.dwell_start
                st.session_state.dwell_start = None
    with c3:
        if st.button("Reset dwell"):
            st.session_state.dwell_start = None
            st.session_state.dwell_sec = 0.0

    dwell_live = st.session_state.dwell_sec
    if st.session_state.dwell_start is not None:
        dwell_live += time.time() - st.session_state.dwell_start
    st.metric("Dwell (sec)", f"{dwell_live:.1f}")

    st.divider()
    st.subheader("Micro Sensation Input (5–10 sec)")

    word = st.selectbox("1 word", WORDS)
    density = st.slider("density (light ↔ heavy)", 0.0, 1.0, 0.5, 0.01)
    color = st.selectbox("color", COLORS, format_func=lambda x: x)
    reverb = st.select_slider("reverb", options=[0, 1, 2], value=1)
    section_memo = st.text_input("section memo (optional)", value="例: 1:12〜1:28が刺さった")

    if st.button("Send Trace"):
        t = Trace(
            trace_id=str(uuid.uuid4())[:10],
            work_id=work_id,
            responder=responder.strip() or "Anonymous",
            word=word,
            density=float(density),
            color=color,
            reverb=int(reverb),
            dwell_sec=float(dwell_live),
            section_memo=section_memo.strip(),
            created_at=time.time(),
        )
        db["traces"].append(asdict(t))
        save_db(db)
        st.success("Trace sent.")

# -----------------------------
# Dashboard (Originator)
# -----------------------------
else:
    st.title("Dashboard (Originator)")
    if not db["works"]:
        st.warning("作品がありません。")
        st.stop()

    creator = st.text_input("Creator filter", value="Tadokoro")
    works = [w for w in db["works"].values() if w["creator"] == creator] or list(db["works"].values())
    work_titles = {w["title"]: w["work_id"] for w in works}

    sel_title = st.selectbox("Select work", list(work_titles.keys()))
    work_id = work_titles[sel_title]

    traces = [Trace(**t) for t in db["traces"] if t["work_id"] == work_id]
    st.caption(f"Traces: {len(traces)}")

    # Cluster
    clusters: Dict[str, List[Trace]] = {}
    for t in traces:
        clusters.setdefault(cluster_key(t), []).append(t)

    st.subheader("Texture Map (clusters)")
    if not clusters:
        st.info("まだTraceがありません。Responderから送ってください。")
        st.stop()

    # Show top 4 clusters
    top = sorted(clusters.items(), key=lambda kv: len(kv[1]), reverse=True)[:4]
    cols = st.columns(len(top))
    for i, (k, items) in enumerate(top):
        with cols[i]:
            st.markdown(f"### {k}")
            st.write(f"count: {len(items)}")
            avg_dwell = sum(t.dwell_sec for t in items) / len(items)
            st.write(f"avg dwell: {avg_dwell:.1f}s")
            st.write("examples:")
            for ex in items[:3]:
                st.caption(f'- {ex.responder}: {ex.word}, d={ex.density:.2f}, rv={ex.reverb}, {ex.section_memo}')

    st.divider()
    st.subheader("Raw Traces")
    for t in sorted(traces, key=lambda x: x.created_at, reverse=True):
        st.write(f'**{t.responder}** | {t.word} | density={t.density:.2f} | {t.color} | rv={t.reverb} | dwell={t.dwell_sec:.1f}s')
        if t.section_memo:
            st.caption(t.section_memo)

