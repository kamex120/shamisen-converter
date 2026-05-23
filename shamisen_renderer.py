"""
shamisen_renderer.py
三味線中間YAML → 文化譜HTML レンダラー
横書き / A4印刷対応
"""

import yaml

BEATS_PER_MEASURE = 4   # 4/4拍子
MEASURES_PER_ROW  = 4   # 1行あたりの小節数

# スタッフ内の縦位置（top %）
STRING_TOP = {
    3: 5,   # 三の糸: 上の線より上
    2: 38,  # 二の糸: 2線の間
    1: 70,  # 一の糸: 下の線より下
}

# 弦の記号（縦棒を重ねて表現）
STRING_MARK = {
    3: "|||",
    2: "||",
    1: "|",
}

TUNING_LABEL = {
    "honchoshi": "本調子",
    "niagari":   "二上り",
    "sansagari": "三下り",
}


# ===========================
# データ読み込み
# ===========================

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ===========================
# 小節グループ化
# ===========================

def group_into_measures(notes: list, beats: int = BEATS_PER_MEASURE) -> list:
    """offset をもとに小節単位にグループ化"""
    all_notes = [n for n in notes if "offset" in n]
    if not all_notes:
        return []

    max_end = max(n["offset"] + n.get("duration", 1) for n in all_notes)
    num_measures = int(max_end / beats) + 1

    result = []
    for i in range(num_measures):
        start = i * beats
        end   = start + beats
        result.append({
            "index": i + 1,
            "start": float(start),
            "notes": [n for n in all_notes if start <= n["offset"] < end],
        })
    return result


# ===========================
# HTML パーツ生成
# ===========================

def render_note(note: dict, measure_start: float) -> str:
    """1音のHTML片"""
    offset_in = note["offset"] - measure_start
    left = offset_in / BEATS_PER_MEASURE * 100

    if note.get("type") == "rest":
        # 休符: 上の線上にドット
        return (
            f'<div class="beat-dot" style="left:{left:.1f}%">•</div>'
        )

    string   = note.get("string", 2)
    position = str(note.get("position", "0"))
    top      = STRING_TOP.get(string, 38)
    mark     = STRING_MARK.get(string, "")
    is_oor   = note.get("status") == "unresolved"

    cls = f"note s{string}" + (" oor" if is_oor else "")
    mark_html = f'<span class="string-mark">{mark}</span>'

    return (
        f'<div class="{cls}" style="left:{left:.1f}%;top:{top}%">'
        f'{mark_html}{position}</div>'
    )


def render_measure(measure: dict) -> str:
    notes_html = "".join(render_note(n, measure["start"]) for n in measure["notes"])
    return f'<div class="measure"><div class="staff">{notes_html}</div></div>'


def render_row(measures: list) -> str:
    first_mn   = measures[0]["index"]
    meas_html  = "".join(render_measure(m) for m in measures)
    return (
        f'<div class="system">'
        f'<div class="measure-number">{first_mn}</div>'
        f'<div class="measures-row">{meas_html}</div>'
        f'</div>'
    )


# ===========================
# メインHTML生成
# ===========================

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "MS Mincho", serif;
  background: #fff; color: #000;
  padding: 20px;
  font-size: 14px;
}

/* ヘッダー */
.score-header { text-align: center; margin-bottom: 20px; position: relative; }
.score-header h1 { font-size: 26px; letter-spacing: 0.1em; }
.attribution { position: absolute; right: 0; top: 0; font-size: 14px; }
.meta { font-size: 12px; text-align: left; margin-top: 6px; color: #444; }

/* 行（システム） */
.system {
  display: flex;
  align-items: flex-start;
  margin-bottom: 44px;
}
.measure-number {
  width: 24px;
  font-size: 11px;
  padding-top: 30px;
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

/* スタッフ（2本線） */
.staff {
  position: relative;
  height: 72px;
  margin: 20px 4px 4px;
}
.staff::before, .staff::after {
  content: '';
  position: absolute;
  left: 0; right: 0;
  height: 1px;
  background: #000;
}
.staff::before { top: 33%; }
.staff::after  { top: 66%; }

/* 音符 */
.note {
  position: absolute;
  transform: translateX(-50%);
  font-size: 17px;
  font-weight: bold;
  line-height: 1;
  text-align: center;
  white-space: nowrap;
}
.note .string-mark {
  display: block;
  font-size: 7px;
  font-weight: normal;
  letter-spacing: -1px;
  text-align: center;
  line-height: 1.2;
}
.note.oor { color: #c00; }

/* 休符ドット */
.beat-dot {
  position: absolute;
  transform: translateX(-50%);
  top: 33%;
  font-size: 14px;
  line-height: 1;
}

/* 警告 */
.warnings {
  font-size: 11px; color: #c00;
  margin-bottom: 12px;
  border: 1px solid #c00;
  padding: 6px 10px;
  border-radius: 4px;
}

/* 印刷 */
@media print {
  body { padding: 0; }
  .system { page-break-inside: avoid; }
  @page { size: A4 portrait; margin: 15mm 12mm; }
}
"""

PRINT_BTN = """
<div style="text-align:right; margin-bottom:12px; print-visibility:hidden">
  <button onclick="window.print()"
    style="padding:6px 16px; font-size:13px; cursor:pointer;">
    🖨️ 印刷 / PDF保存
  </button>
</div>
"""


def render_html(
    data: dict,
    title: str = "",
    attribution: str = "",
) -> str:
    tuning    = data.get("tuning", "")
    transpose = data.get("transpose", 0)
    notes     = data.get("notes", [])
    warnings  = data.get("warnings", [])

    measures = group_into_measures(notes)
    rows     = [measures[i:i+MEASURES_PER_ROW]
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


def save_html(
    data: dict,
    output_path: str,
    title: str = "",
    attribution: str = "",
) -> str:
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
