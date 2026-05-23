"""
shamisen_renderer.py
三味線中間YAML → 文化譜HTML レンダラー

文化譜の仕様:
  - 3本の横線（下から 一の糸 / 二の糸 / 三の糸）
  - 数字は対応する弦の線の上に配置
  - 音価: 下線なし=4分、下線1本=8分、下線2本=16分
  - 休符: ● (下線で音価を表す)
  - 弦記号: | / || / ||| を数字の上に表示（弦が変わるとき）
  - 横書き（左→右）、1行 MEASURES_PER_ROW 小節
"""

import yaml

BEATS_PER_MEASURE = 4
MEASURES_PER_ROW  = 4

# スタッフ高さに対する各弦の線の縦位置（%）
# 下から 一の糸(bottom) / 二の糸(middle) / 三の糸(top)
LINE_TOP = {
    1: 20,   # ichi_no_ito → 三の糸（上の線）
    2: 50,   # ni_no_ito   → 二の糸（中の線）
    3: 80,   # san_no_ito  → 一の糸（下の線）
}

# 指記号（|=人差し指, ||=中指, |||=薬指）は指情報がないため非表示

TUNING_LABEL = {
    "honchoshi": "本調子",
    "niagari":   "二上り",
    "sansagari": "三下り",
}


# ===========================
# ユーティリティ
# ===========================

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def duration_class(dur: float) -> str:
    """音価 → CSSクラス"""
    if dur <= 0.25:
        return "dur-16"
    if dur <= 0.5:
        return "dur-8"
    return ""


# ===========================
# 小節グループ化
# ===========================

def group_into_measures(notes: list, beats: int = BEATS_PER_MEASURE) -> list:
    all_notes = [n for n in notes if "offset" in n]
    if not all_notes:
        return []
    max_end = max(n["offset"] + n.get("duration", 1) for n in all_notes)
    num_measures = int(max_end / beats) + 1
    result = []
    for i in range(num_measures):
        start = float(i * beats)
        result.append({
            "index": i + 1,
            "start": start,
            "notes": [n for n in all_notes if start <= n["offset"] < start + beats],
        })
    return result


# ===========================
# HTML パーツ生成
# ===========================

def render_note(note: dict, measure_start: float) -> str:
    """1音のHTMLを返す"""
    offset_in = note["offset"] - measure_start
    left_pct  = 5 + (offset_in / BEATS_PER_MEASURE) * 90
    dur       = note.get("duration", 1.0)
    dur_cls   = duration_class(dur)

    if note.get("type") == "rest":
        # 休符: 二の糸線上に ●
        underlines = ""
        if dur <= 0.25:
            underlines = '<span class="underline"></span><span class="underline"></span>'
        elif dur <= 0.5:
            underlines = '<span class="underline"></span>'
        html = (
            f'<div class="rest" style="left:{left_pct:.1f}%">'
            f'●{underlines}</div>'
        )
        return html

    string   = note.get("string", 2)
    position = str(note.get("position", "0"))
    top_pct  = LINE_TOP.get(string, 50)
    is_oor   = note.get("status") == "unresolved"

    # 下線（音価：8分・16分）
    underlines = ""
    if dur_cls == "dur-8":
        underlines = '<span class="underline"></span>'
    elif dur_cls == "dur-16":
        underlines = '<span class="underline"></span><span class="underline"></span>'

    # 延ばし線（二分音符以上: ー の数 = 拍数 - 1）
    num_ext = max(0, round(dur) - 1)
    ext_html = f'<span class="ext">{"ー" * num_ext}</span>' if num_ext > 0 else ""

    cls = f"note s{string}" + (" oor" if is_oor else "")

    return (
        f'<div class="{cls}" style="left:{left_pct:.1f}%;top:{top_pct}%">'
        f'<span class="pos">{position}</span>'
        f'{ext_html}'
        f'{underlines}'
        f'</div>'
    )


def render_measure(measure: dict) -> str:
    notes_html_parts = []
    for n in sorted(measure["notes"], key=lambda x: x["offset"]):
        notes_html_parts.append(render_note(n, measure["start"]))

    notes_html = "".join(notes_html_parts)
    # 3本目の弦線（一の糸）は疑似要素で描けないためdivで追加
    return (
        f'<div class="measure">'
        f'<div class="staff">'
        f'<div class="line-bottom"></div>'
        f'{notes_html}'
        f'</div></div>'
    )


def render_row(measures: list) -> str:
    first_mn  = measures[0]["index"]
    meas_html = "".join(render_measure(m) for m in measures)
    return (
        f'<div class="system">'
        f'<div class="measure-number">{first_mn}</div>'
        f'<div class="measures-row">{meas_html}</div>'
        f'</div>'
    )


# ===========================
# CSS
# ===========================

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "MS Mincho", serif;
  background: #fff; color: #000;
  padding: 20px;
}

/* ヘッダー */
.score-header { text-align: center; margin-bottom: 20px; position: relative; }
.score-header h1 { font-size: 26px; letter-spacing: 0.1em; }
.attribution { position: absolute; right: 0; top: 4px; font-size: 14px; }
.meta { font-size: 12px; text-align: left; margin-top: 6px; color: #444; }

/* 行（システム） */
.system {
  display: flex;
  align-items: stretch;
  margin-bottom: 40px;
}
.measure-number {
  width: 24px;
  font-size: 11px;
  padding-top: 24px;
  flex-shrink: 0;
  color: #555;
}
.measures-row {
  display: flex;
  flex: 1;
  border-left: 3px solid #000;
}

/* 小節 */
.measure {
  position: relative;
  flex: 1;
  border-right: 1px solid #000;
}

/* スタッフ（3本線） */
.staff {
  position: relative;
  height: 100px;
  margin: 12px 4px 8px;
}

/* 3本の弦線を疑似要素 + 追加divで描画 */
.staff::before,
.staff::after {
  content: '';
  position: absolute;
  left: 0; right: 0;
  height: 1px;
  background: #000;
}
.staff::before { top: 20%; }  /* 三の糸（上） */
.staff::after  { top: 50%; }  /* 二の糸（中） */
.staff .line-bottom {
  position: absolute;
  left: 0; right: 0;
  top: 80%;
  height: 1px;
  background: #000;
}

/* 音符 */
.note {
  position: absolute;
  transform: translate(-50%, -50%);
  text-align: center;
  line-height: 1;
}
.note .pos {
  display: block;
  font-size: 18px;
  font-weight: bold;
  line-height: 1;
}
.note .underline {
  display: block;
  height: 1px;
  background: #000;
  margin-top: 2px;
  width: 100%;
}
.note.oor .pos { color: #c00; }
.note .ext {
  display: inline;
  font-size: 16px;
  font-weight: normal;
  letter-spacing: -4px;
  margin-left: 1px;
}

/* 休符 */
.rest {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  font-size: 16px;
  font-weight: bold;
  text-align: center;
}
.rest .underline {
  display: block;
  height: 1px;
  background: #000;
  margin-top: 2px;
}

/* 警告 */
.warnings {
  font-size: 11px; color: #c00;
  margin-bottom: 12px;
  border: 1px solid #c00;
  padding: 6px 10px;
  border-radius: 4px;
}

/* 印刷設定 */
@media print {
  body { padding: 0; }
  .no-print { display: none !important; }
  .system { page-break-inside: avoid; }
  @page { size: A4 portrait; margin: 15mm 12mm; }
}
"""

PRINT_BTN = """
<div class="no-print" style="text-align:right; margin-bottom:12px;">
  <button onclick="window.print()"
    style="padding:6px 16px; font-size:13px; cursor:pointer;">
    🖨️ 印刷 / PDF保存
  </button>
</div>
"""


# ===========================
# メインHTML生成
# ===========================

def render_html(data: dict, title: str = "", attribution: str = "") -> str:
    tuning    = data.get("tuning", "")
    transpose = data.get("transpose", 0)
    notes     = data.get("notes", [])
    warnings  = data.get("warnings", [])

    measures = group_into_measures(notes)
    rows     = [measures[i:i + MEASURES_PER_ROW]
                for i in range(0, len(measures), MEASURES_PER_ROW)]

    tuning_str    = TUNING_LABEL.get(tuning, tuning)
    transpose_str = f"　転調: {transpose:+d}半音" if transpose != 0 else ""
    meta_str      = f"{tuning_str}{transpose_str}"

    warnings_html = ""
    if warnings:
        wlist = "".join(f"<li>{w}</li>" for w in warnings)
        warnings_html = f'<div class="warnings"><ul>{wlist}</ul></div>'

    rows_html = "\n".join(render_row(row) for row in rows)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>{title or "三味線文化譜"}</title>
<style>{CSS}</style>
</head>
<body>
{PRINT_BTN}
<div class="score-header">
  <h1>{title or "　"}</h1>
  <span class="attribution">{attribution}</span>
  <div class="meta">{meta_str}</div>
</div>
{warnings_html}
<div class="score">
{rows_html}
</div>
</body>
</html>"""


def save_html(data: dict, output_path: str,
              title: str = "", attribution: str = "") -> str:
    html = render_html(data, title=title, attribution=attribution)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


# ===========================
# CLI
# ===========================

if __name__ == "__main__":
    import sys
    yaml_path = sys.argv[1] if len(sys.argv) > 1 else "shamisen_output.yaml"
    out_path  = yaml_path.replace(".yaml", ".html")
    data = load_yaml(yaml_path)
    save_html(data, out_path)
    print(f"✅ HTML出力: {out_path}")
