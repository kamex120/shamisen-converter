"""
app.py — 三味線文化譜変換 Web アプリ（Streamlit）
PDF / MusicXML → 三味線文化譜 HTML
"""

import streamlit as st
import streamlit.components.v1 as components
from streamlit_drawable_canvas import st_canvas
import yaml
import tempfile
import os
import glob
import subprocess
import io
from pathlib import Path
from PIL import Image
import fitz  # PyMuPDF
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
MAPPING_PATH     = "shamisen_mapping.yaml"
TUNING_MAP       = {"本調子": "honchoshi", "二上り": "niagari", "三下り": "sansagari"}
CANDIDATES       = list(range(-12, 13)) + [-24, 24]
AUDIVERIS_URL    = (
    "https://github.com/Audiveris/audiveris/releases/download/"
    "5.10.2/Audiveris-5.10.2-ubuntu22.04-x86_64.deb"
)
AUDIVERIS_EXTRACT = "/tmp/audiveris_app"
AUDIVERIS_BIN     = f"{AUDIVERIS_EXTRACT}/opt/audiveris/bin/Audiveris"
CANVAS_SCALE      = 1.5

# ===========================
# ページ設定
# ===========================
st.set_page_config(page_title="三味線文化譜変換", page_icon="🎵", layout="wide")
st.title("🎵 三味線文化譜変換")
st.caption("PDF / MusicXML → 三味線文化譜（横書き）")

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
uploaded = st.file_uploader("楽譜ファイル (.pdf / .xml / .mxl)", type=["pdf", "xml", "mxl"])

if not uploaded:
    st.info(
        "👆 楽譜ファイルをアップロードしてください。\n\n"
        "- **PDF**: 印刷用楽譜をそのままアップロード（Audiveris で自動認識）\n"
        "- **MusicXML**: MuseScore・Finale などで書き出したファイル"
    )
    st.stop()

file_bytes = uploaded.read()
is_pdf = uploaded.name.lower().endswith(".pdf")

# ファイルが変わったらセッションをリセット
file_id = f"{uploaded.name}_{len(file_bytes)}"
if st.session_state.get("_file_id") != file_id:
    st.session_state._file_id        = file_id
    st.session_state.audiveris_ready  = False
    st.session_state.pdf_for_audiveris = None


# ===========================
# Audiveris ユーティリティ
# ===========================
@st.cache_resource(show_spinner=False)
def setup_audiveris() -> tuple:
    """Audiveris を /tmp に展開。(bin_path, error_msg) を返す"""
    if os.path.isfile(AUDIVERIS_BIN):
        return AUDIVERIS_BIN, None

    os.makedirs(AUDIVERIS_EXTRACT, exist_ok=True)
    deb_path = "/tmp/audiveris.deb"

    try:
        import urllib.request
        urllib.request.urlretrieve(AUDIVERIS_URL, deb_path)
    except Exception as e:
        return None, f"ダウンロード失敗: {e}"

    try:
        r = subprocess.run(
            ["dpkg-deb", "--extract", deb_path, AUDIVERIS_EXTRACT],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            return None, f"展開失敗 (dpkg-deb): {r.stderr}"
    except Exception as e:
        return None, f"展開エラー: {e}"
    finally:
        if os.path.exists(deb_path):
            os.remove(deb_path)

    if not os.path.isfile(AUDIVERIS_BIN):
        found = glob.glob(f"{AUDIVERIS_EXTRACT}/**/Audiveris", recursive=True)
        return None, f"バイナリが見つかりません: {found or AUDIVERIS_EXTRACT}"

    os.chmod(AUDIVERIS_BIN, 0o755)
    return AUDIVERIS_BIN, None


@st.cache_data(show_spinner="Audiveris で楽譜認識中（1〜2分）...")
def run_audiveris(pdf_bytes: bytes, fname: str, bin_path: str) -> tuple:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        pdf_path = tmp.name
    omr_dir = tempfile.mkdtemp()
    try:
        proc = subprocess.run(
            ["xvfb-run", bin_path, "-batch", "-export", "-output", omr_dir, "--", pdf_path],
            capture_output=True, text=True, timeout=180,
        )
        found = (
            glob.glob(f"{omr_dir}/**/*.mxl", recursive=True)
            + glob.glob(f"{omr_dir}/**/*.xml", recursive=True)
        )
        if not found:
            return None, proc.stderr[-500:] or "MusicXML が生成されませんでした"
        with open(found[0], "rb") as f:
            return f.read(), None
    except subprocess.TimeoutExpired:
        return None, "タイムアウト（180秒）"
    except Exception as e:
        return None, str(e)
    finally:
        os.unlink(pdf_path)


# ===========================
# PDF 処理（白塗り → Audiveris）
# ===========================
if is_pdf:

    @st.cache_data
    def pdf_to_png(pdf_bytes: bytes, scale: float = CANVAS_SCALE) -> bytes:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(scale, scale))
        return pix.tobytes("png")

    def apply_whitout(pdf_bytes: bytes, rects: list) -> bytes:
        if not rects:
            return pdf_bytes
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            for r in rects:
                page.add_redact_annot(fitz.Rect(*r), fill=(1, 1, 1))
            page.apply_redactions()
        return doc.tobytes()

    # ── 白塗りキャンバス ──
    st.subheader("✏️ 白塗り（任意）")
    st.caption("コード名・歌詞など Audiveris が誤認識しそうな箇所をドラッグで選択")

    img_png  = pdf_to_png(file_bytes)
    canvas_bg = Image.open(io.BytesIO(img_png))

    canvas_result = st_canvas(
        background_image=canvas_bg,
        drawing_mode="rect",
        fill_color="rgba(255, 255, 255, 0.65)",
        stroke_color="#FF4444",
        stroke_width=2,
        height=canvas_bg.height,
        width=canvas_bg.width,
        key="whitout_canvas",
    )

    # キャンバスから矩形を取得
    current_rects = []
    if canvas_result.json_data:
        for obj in canvas_result.json_data.get("objects", []):
            if obj.get("type") == "rect":
                sx = obj.get("scaleX", 1)
                sy = obj.get("scaleY", 1)
                x0 = obj["left"] / CANVAS_SCALE
                y0 = obj["top"]  / CANVAS_SCALE
                x1 = (obj["left"] + obj["width"]  * sx) / CANVAS_SCALE
                y1 = (obj["top"]  + obj["height"] * sy) / CANVAS_SCALE
                if (x1 - x0) > 3 and (y1 - y0) > 3:
                    current_rects.append((x0, y0, x1, y1))

    col_info, col_btn = st.columns([3, 1])
    with col_info:
        if current_rects:
            st.caption(f"✅ {len(current_rects)} 箇所を白塗り予定")
        else:
            st.caption("白塗りなし（そのまま変換）")
    with col_btn:
        if st.button("▶ 変換開始", type="primary", use_container_width=True):
            processed = apply_whitout(file_bytes, current_rects)
            st.session_state.pdf_for_audiveris = processed
            st.session_state.audiveris_ready   = True
            st.rerun()

    if not st.session_state.get("audiveris_ready"):
        st.stop()

    # ── Audiveris 実行 ──
    st.divider()
    with st.status("Audiveris をセットアップ中...", expanded=True) as status:
        st.write("初回起動時のみ Audiveris をダウンロードします（約 2 分）")
        bin_path, setup_err = setup_audiveris()
        if not bin_path:
            status.update(label="セットアップ失敗", state="error")
            st.error(f"Audiveris のセットアップに失敗しました\n\n詳細: {setup_err}")
            st.stop()
        status.update(label="楽譜を認識中...", state="running")
        xml_bytes, err = run_audiveris(
            st.session_state.pdf_for_audiveris, uploaded.name, bin_path
        )
        if err:
            status.update(label="認識失敗", state="error")
            st.error(f"Audiveris エラー: {err}")
            st.stop()
        status.update(label="認識完了 ✅", state="complete")

    xml_source_bytes = xml_bytes
    xml_source_name  = uploaded.name.replace(".pdf", ".mxl")

else:
    xml_source_bytes = file_bytes
    xml_source_name  = uploaded.name


# ===========================
# Step 1: 解析
# ===========================
@st.cache_data(show_spinner="楽譜を解析中...")
def parse_notes(fb: bytes, fname: str, tuning: str) -> tuple:
    suffix = Path(fname).suffix or ".xml"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(fb)
        tmp_path = tmp.name
    try:
        result = convert_musicxml(tmp_path, MAPPING_PATH, tuning)
    finally:
        os.unlink(tmp_path)
    return (
        [dict(note_name=n.note_name, midi=n.midi, duration=n.duration,
              offset=n.offset, out_of_range=n.out_of_range) for n in result.notes],
        list(result.warnings),
    )


note_list, _ = parse_notes(xml_source_bytes, xml_source_name, tuning)
real_notes    = [n for n in note_list if n["note_name"] != "rest" and n["midi"] != -1]
oor_count     = sum(1 for n in real_notes if n["out_of_range"])

col1, col2 = st.columns(2)
col1.metric("音符数", len(real_notes))
col2.metric("音域外", oor_count,
            delta=f"-{oor_count}" if oor_count else None, delta_color="inverse")


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
# Step 3: HTML 生成
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


html = make_html(
    xml_source_bytes, xml_source_name,
    tuning, shift, score_title, score_author,
)


# ===========================
# Step 4: プレビュー & ダウンロード
# ===========================
st.divider()
st.subheader("文化譜プレビュー")
components.html(html, height=700, scrolling=True)

st.download_button(
    "📥 HTML をダウンロード",
    data=html,
    file_name=f"{score_title or 'shamisen_score'}.html",
    mime="text/html",
    type="primary",
)
