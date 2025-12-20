import streamlit as st
import json
import time
from datetime import datetime
from collections import Counter, defaultdict
import math

st.set_page_config(page_title="MAL Trace Prototype", layout="wide")

# ----------------------------
# Data store (session only)
# ----------------------------
if "work" not in st.session_state:
    st.session_state.work = {
        "title": "Untitled",
        "creator_note": "",
        "audio_bytes": None,
        "audio_name": None,
        "image_bytes": None,
        "image_name": None,
        "text_body": "",
        "created_at": None,
    }

if "traces" not in st.session_state:
    # each trace: {ts, word, density, color, echo, hook_seconds, free_text(optional)}
    st.session_state.traces = []

# ----------------------------
# Helpers
# ----------------------------
SENSATION_WORDS = [
    "重い", "澄んだ", "違和感", "温かい", "空白", "緊張", "浮遊", "荒い", "優しい", "痛い",
    "甘い", "冷たい", "懐かしい", "不穏", "透明", "ざらつく"
]
COLOR_CHOICES = ["黒", "濃紺", "青", "水色", "緑", "黄", "橙", "赤", "紫", "白", "灰"]

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def safe_float(x, default=None):
    try:
        return float(x)
    except Exception:
        return default

def simple_distance(a, b):
    """Very rough distance for clustering traces into textures."""
    # a,b are dicts with word,density,color,echo,hook_seconds
    d = 0.0
    d += 0.0 if a["word"] == b["word"] else 1.0
    d += 0.0 if a["color"] == b["color"] else 0.6
    d += abs(a["density"] - b["density"]) / 100.0
    d += abs(a["echo"] - b["echo"]) / 2.0
    # hook seconds: normalize by 60 sec
    hs_a = a.get("hook_seconds")
    hs_b = b.get("hook_seconds")
    if hs_a is not None and hs_b is not None:
        d += min(abs(hs_a - hs_b) / 60.0, 2.0) * 0.4
    return d

def cluster_traces(traces, threshold=1.2):
    """Greedy clustering: build clusters if close enough."""
    clusters = []
    for t in traces:
        placed = False
        for c in clusters:
            # compare to cluster "centroid" as first element (simple)
            if simple_distance(t, c[0]) <= threshold:
                c.append(t)
                placed = True
                break
        if not placed:
            clusters.append([t])
    # sort clusters by size desc
    clusters.sort(key=len, reverse=True)
    return clusters

def hook_histogram(traces, bin_sec=10):
    """Count hook points by time bins."""
    bins = Counter()
    for t in traces:
        hs = t.get("hook_seconds")
        if hs is None:
            continue
        b = int(hs // bin_sec) * bin_sec
        bins[b] += 1
    return bins

# ----------------------------
# UI
# ----------------------------
st.title("MAL Trace Prototype（最小：作品 → 痕跡 → 結 → 返却）")

tab_post, tab_view, tab_return = st.tabs(["A. Originator（投稿）", "B. Responder（鑑賞＆痕跡）", "C. Return（作家に返す）"])

with tab_post:
    st.subheader("作品を置く（あなたのピアノを最初の素材に）")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.session_state.work["title"] = st.text_input("作品タイトル（任意）", value=st.session_state.work["title"])
        st.session_state.work["creator_note"] = st.text_area("作家メモ（任意）", value=st.session_state.work["creator_note"], height=120)
        audio = st.file_uploader("音声アップロード（mp3/wav）", type=["mp3", "wav", "m4a"])
        if audio is not None:
            st.session_state.work["audio_bytes"] = audio.getvalue()
            st.session_state.work["audio_name"] = audio.name

        img = st.file_uploader("画像アップロード（任意）", type=["png", "jpg", "jpeg", "webp"])
        if img is not None:
            st.session_state.work["image_bytes"] = img.getvalue()
            st.session_state.work["image_name"] = img.name

    with col2:
        st.session_state.work["text_body"] = st.text_area("テキスト（詩／制作テキスト／Behind the Scenes）", value=st.session_state.work["text_body"], height=300)
        if st.button("この作品を保存（セッション内）"):
            st.session_state.work["created_at"] = now_iso()
            st.success("保存しました（セッション内）。次のタブで鑑賞できます。")

    st.markdown("---")
    st.caption("※ Streamlit Cloudに上げれば、これ自体が共有リンクになります（初期フェーズA向き）。")

with tab_view:
    st.subheader("作品を見る → 痕跡を残す（評価しない / 理由を聞かない）")

    # Display work
    st.markdown(f"### {st.session_state.work.get('title','Untitled')}")
    if st.session_state.work.get("creator_note"):
        with st.expander("作家メモ（任意）", expanded=False):
            st.write(st.session_state.work["creator_note"])

    left, right = st.columns([1.2, 1])
    with left:
        if st.session_state.work.get("audio_bytes"):
            st.audio(st.session_state.work["audio_bytes"])
            st.caption(f"Audio: {st.session_state.work.get('audio_name')}")
        else:
            st.info("音声がまだありません（投稿タブでアップロード）。")

        if st.session_state.work.get("image_bytes"):
            st.image(st.session_state.work["image_bytes"], caption=st.session_state.work.get("image_name"), use_container_width=True)

        if st.session_state.work.get("text_body"):
            st.markdown("**テキスト**")
            st.write(st.session_state.work["text_body"])

    with right:
        st.markdown("#### 痕跡（Trace）を5〜10秒で残す")

        # Hook point: Streamlitでは再生位置を自動取得しにくいので、まずは手入力でOK
        st.markdown("**引っかかり点（任意）**")
        hook_str = st.text_input("音声の何秒あたり？（例: 42.5）※分からなければ空でOK", value="")

        word = st.selectbox("感覚語を1つ", SENSATION_WORDS, index=0)
        density = st.slider("密度（軽い ↔ 重い）", 0, 100, 50)
        color = st.selectbox("色を1つ", COLOR_CHOICES, index=COLOR_CHOICES.index("灰") if "灰" in COLOR_CHOICES else 0)
        echo = st.select_slider("残響の強さ（3段階）", options=[0, 1, 2], value=1, format_func=lambda x: ["弱", "中", "強"][x])
        free = st.text_input("（任意）ひとことだけ残す ※理由説明は不要", value="")

        if st.button("痕跡を残す（いいね禁止）"):
            hook_seconds = safe_float(hook_str, default=None) if hook_str.strip() else None
            trace = {
                "ts": now_iso(),
                "word": word,
                "density": float(density),
                "color": color,
                "echo": float(echo),
                "hook_seconds": hook_seconds,
                "free_text": free.strip() if free.strip() else None,
            }
            st.session_state.traces.append(trace)
            st.success("痕跡を保存しました。")

        st.markdown("---")
        if st.session_state.traces:
            st.markdown("#### 最近の痕跡（最新5件）")
            for t in list(reversed(st.session_state.traces))[:5]:
                hs = t["hook_seconds"]
                hs_txt = f"{hs:.1f}s" if isinstance(hs, (int, float)) else "-"
                st.write(f"- {t['ts']} / {t['word']} / 密度{int(t['density'])} / {t['color']} / 残響{['弱','中','強'][int(t['echo'])]} / 引っかかり:{hs_txt}")

with tab_return:
    st.subheader("作家に返す（分析しすぎず、届いた形だけ返す）")

    if not st.session_state.traces:
        st.info("まだ痕跡がありません。鑑賞タブで痕跡を残してください。")
    else:
        # 1) texture clustering
        clusters = cluster_traces(st.session_state.traces, threshold=1.2)

        st.markdown("### 感覚地形図（粗い版：結の束）")
        top_k = min(4, len(clusters))
        for i in range(top_k):
            c = clusters[i]
            words = [x["word"] for x in c]
            colors = [x["color"] for x in c]
            dens = [x["density"] for x in c]
            echoes = [x["echo"] for x in c]
            hook_points = [x["hook_seconds"] for x in c if x.get("hook_seconds") is not None]

            word_top = Counter(words).most_common(1)[0][0]
            color_top = Counter(colors).most_common(1)[0][0]
            dens_avg = sum(dens)/len(dens)
            echo_top = Counter(echoes).most_common(1)[0][0]

            st.markdown(f"**結 {i+1}（{len(c)}件）**")
            st.write(f"- 主な感覚語: {word_top}")
            st.write(f"- 主な色: {color_top}")
            st.write(f"- 密度（平均）: {dens_avg:.1f}")
            st.write(f"- 残響: {['弱','中','強'][int(echo_top)]}")

            # show traces snippets
            with st.expander("痕跡（匿名原文）を見る"):
                for t in c[:20]:
                    hs = t.get("hook_seconds")
                    hs_txt = f"{hs:.1f}s" if isinstance(hs, (int, float)) else "-"
                    ft = t.get("free_text") or ""
                    st.write(f"- {t['word']} / {t['color']} / 密度{int(t['density'])} / 残響{['弱','中','強'][int(t['echo'])]} / 引っかかり:{hs_txt} {(' / '+ft) if ft else ''}")

            st.markdown("---")

        # 2) Hook points histogram
        st.markdown("### 引っかかり点（音声のどこで感覚が生じたか）")
        bins = hook_histogram(st.session_state.traces, bin_sec=10)
        if not bins:
            st.caption("引っかかり時刻の入力がまだありません（任意）。")
        else:
            # show top bins
            for b, cnt in bins.most_common(10):
                st.write(f"- {b:>4d}〜{b+10:>4d} 秒: {cnt} 件")

        st.markdown("### MALが許される一行要約（意味づけしない）")
        if len(clusters) >= 2:
            st.write("この作品は、複数の対照的な結で届いています。")
        else:
            st.write("この作品は、ひとつの結として静かに届いています。")

        st.markdown("---")
        st.markdown("### エクスポート（JSON）")
        export = {
            "work": st.session_state.work,
            "traces": st.session_state.traces,
            "generated_at": now_iso(),
        }
        st.download_button(
            "痕跡データをJSONで保存",
            data=json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="mal_traces_export.json",
            mime="application/json",
        )

        if st.button("痕跡を全消去（テスト用）"):
            st.session_state.traces = []
            st.success("消去しました。")
