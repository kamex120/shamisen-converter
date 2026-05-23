"""
app.py — 三味線文化譜変換 Web アプリ（Streamlit）
MusicXML → 三味線文化譜 HTML
"""

import streamlit as st
import streamlit.components.v1 as components
import yaml
import tempfile
import os
from pathlib import Path
from music21 import pitch as m21pitch

from shamisen_converter import (
    convert_musicxml,
    load_mapping,
    build_midi_to_position,
    to_intermediate_yaml,
)
from shamisen_renderer import render_html

# ===========================
# 定数
# ===========================
MAPPING_PATH = "shamisen_mapping.yaml"
TUNING_MAP = {
    "本調子": "honchoshi",
    "二上り": "niagari",
    "三下り": "sansagari",
}
CANDIDATES = list(range(-12, 13)) + [-24, 24]

# ===========================
# ページ設定
# ===========================
st.set_page_config(
    page_title="三味線文化譜変換",
    page_icon="🎵",
    layout="wide",
)

st.title("🎵 三味線文化譜変換")
st.caption("MusicXML → 三味線文化譜（横書き）　※ PDF は MuseScore などで MusicXML に変換してからアップロードしてください")

# ===========================
# サイドバー
# ===========================
with st.sidebar:
    st.header("⚙️ 設定")
    tuning_label = st.radio("調弦", list(TUNING_MAP.keys()), index=1)
    tuning = TUNING_MAP[tuning_label]
    st.divider()
    score_title  = st.text_input("曲名（任意）", placeholder="さくらさくら")
    score_author = st.text_input("作者（任意）", placeholder="日本古謡")

# ===========================
# ファイルアップロード
# ===========================
uploaded = st.file_uploader("MusicXML ファイル (.xml / .mxl)", type=["xml", "mxl"])

if not uploaded:
    st.info(
        "👆 MusicXML ファイルをアップロードしてください。\n\n"
        "**PDF → MusicXML の変換方法:**\n"
        "- [MuseScore](https://musescore.org/) で楽譜を開き「ファイル → エクスポート → MusicXML」\n"
        "- Finale / Dorico / Sibelius のエクスポート機能を使用"
    )
    st.stop()

file_bytes = uploaded.read()

# ===========================
# Step 1: 解析（キャッシュ）
# ===========================
@st.cache_data(show_spinner="楽譜を解析中...")
def parse_notes(fb: bytes, fname: str, tuning: str):
    """MusicXML を変換して音符情報（辞書リスト）を返す"""
    suffix = Path(fname).suffix or ".xml"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(fb)
        tmp_path = tmp.name
    try:
        result = convert_musicxml(tmp_path, MAPPING_PATH, tuning)
    finally:
        os.unlink(tmp_path)
    notes = [
        dict(
            note_name=n.note_name,
            midi=n.midi,
            duration=n.duration,
            offset=n.offset,
            out_of_range=n.out_of_range,
        )
        for n in result.notes
    ]
    return notes, list(result.warnings)


note_list, init_warnings = parse_notes(file_bytes, uploaded.name, tuning)

real_notes = [n for n in note_list if n["note_name"] != "rest" and n["midi"] != -1]
oor_count  = sum(1 for n in real_notes if n["out_of_range"])

col1, col2 = st.columns(2)
col1.metric("音符数", len(real_notes))
col2.metric("音域外", oor_count, delta=f"-{oor_count}" if oor_count else None,
            delta_color="inverse")

# ===========================
# Step 2: 転調スライダー
# ===========================
mapping_  = load_mapping(MAPPING_PATH)
midi_map_ = build_midi_to_position(mapping_, tuning)

def count_oor(shift: int) -> int:
    return sum(1 for n in real_notes if (n["midi"] + shift) not in midi_map_)

shift = 0
if oor_count > 0:
    min_remain = min(count_oor(s) for s in CANDIDATES)
    best_shift = min(
        (s for s in CANDIDATES if count_oor(s) == min_remain), key=abs
    )
    st.warning(f"⚠️ {oor_count} 件が音域外です。転調で解決できる場合があります。")
    shift = st.select_slider(
        "全体転調（半音）",
        options=CANDIDATES,
        value=best_shift,
        format_func=lambda s: (
            f"{s:+d} 半音　→ 音域外残り {count_oor(s)} 件"
            + ("  ✅ 推奨" if s == best_shift else "")
        ),
    )

# ===========================
# Step 3: HTML 生成（キャッシュ）
# ===========================
@st.cache_data(show_spinner="楽譜を生成中...")
def make_html(fb: bytes, fname: str, tuning: str,
              shift: int, title: str, author: str) -> str:
    suffix = Path(fname).suffix or ".xml"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(fb)
        tmp_path = tmp.name
    try:
        result = convert_musicxml(tmp_path, MAPPING_PATH, tuning)
    finally:
        os.unlink(tmp_path)

    mapping__  = load_mapping(MAPPING_PATH)
    midi_map__ = build_midi_to_position(mapping__, tuning)

    all_n = [n for n in result.notes if n.note_name != "rest" and n.midi != -1]
    if shift != 0:
        for sn in all_n:
            new_midi = sn.midi + shift
            sn.midi      = new_midi
            sn.note_name = m21pitch.Pitch(midi=new_midi).nameWithOctave
            if new_midi in midi_map__:
                s, p = midi_map__[new_midi][0]
                sn.string, sn.position = s, p
                sn.out_of_range = False
                sn.warning = None
            else:
                sn.out_of_range = True
        result.warnings = [
            sn.warning for sn in result.notes if sn.out_of_range and sn.warning
        ]
    result.transpose = shift

    data = yaml.safe_load(to_intermediate_yaml(result))
    return render_html(data, title=title, attribution=author)


html = make_html(file_bytes, uploaded.name, tuning, shift, score_title, score_author)

# ===========================
# Step 4: プレビュー & ダウンロード
# ===========================
st.divider()
st.subheader("文化譜プレビュー")
components.html(html, height=700, scrolling=True)

dl_name = f"{score_title or 'shamisen_score'}.html"
st.download_button(
    "📥 HTML をダウンロード",
    data=html,
    file_name=dl_name,
    mime="text/html",
    type="primary",
)
