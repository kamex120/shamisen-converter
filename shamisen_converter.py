"""
shamisen_converter.py
五線譜（MusicXML）→ 三味線中間YAML変換エンジン
対象: 文化譜（長唄系）
"""

import yaml
from music21 import converter, note, chord
from dataclasses import dataclass, field
from typing import Optional


# ===========================
# データクラス
# ===========================

@dataclass
class ShamisenNote:
    """三味線の1音を表す中間表現"""
    string: Optional[str]       # "san_no_ito" / "ni_no_ito" / "ichi_no_ito" / None
    position: Optional[str]     # 勘所ラベル（"0"=開放, "#", "b", "1#" など）/ None
    midi: int                   # 元の音高（MIDIノート番号）
    note_name: str              # 元の音名（例: "D4"）
    duration: float             # 音の長さ（四分音符=1.0）
    offset: float               # 曲頭からの位置（四分音符単位）
    out_of_range: bool = False  # 音域外フラグ
    warning: Optional[str] = None  # 警告メッセージ


@dataclass
class ConversionResult:
    """変換結果全体"""
    tuning: str                          # 調弦名
    notes: list[ShamisenNote] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ===========================
# マッピングの読み込み
# ===========================

def load_mapping(yaml_path: str) -> dict:
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_midi_to_position(mapping: dict, tuning: str) -> dict:
    """
    MIDIノート番号 → [(弦名, 勘所ラベル), ...] の辞書を作る
    優先順位: 勘所番号（開放弦からの半音数）が小さい順、同点なら string_priority 順
    """
    tuning_data = mapping["tunings"][tuning]
    priority = mapping["meta"]["string_priority"]
    string_index = {s: i for i, s in enumerate(priority)}

    # (semi_offset, string_index, string_name, pos) のリストを構築
    entries: dict[int, list] = {}
    for string_name in priority:
        string_data = tuning_data[string_name]
        open_midi = string_data["open_midi"]
        for pos, info in string_data["positions"].items():
            midi = info["midi"]
            semi_offset = midi - open_midi
            entries.setdefault(midi, []).append(
                (semi_offset, string_index[string_name], string_name, pos)
            )

    # ソートして (string_name, pos) だけ残す
    return {
        midi: [(s, p) for _, _, s, p in sorted(opts)]
        for midi, opts in entries.items()
    }


# ===========================
# 変換エンジン
# ===========================

def convert_note(
    midi_num: int,
    note_name: str,
    duration: float,
    offset: float,
    midi_map: dict
) -> ShamisenNote:
    """1音を三味線の勘所に変換する"""

    if midi_num in midi_map:
        # 三の弦優先で最初の候補を使う
        string_name, position = midi_map[midi_num][0]
        return ShamisenNote(
            string=string_name,
            position=position,
            midi=midi_num,
            note_name=note_name,
            duration=duration,
            offset=offset,
        )
    else:
        # 音域外
        warning = f"音域外: {note_name}（MIDI {midi_num}）は対応する勘所がありません"
        return ShamisenNote(
            string=None,
            position=None,
            midi=midi_num,
            note_name=note_name,
            duration=duration,
            offset=offset,
            out_of_range=True,
            warning=warning,
        )


def convert_musicxml(
    musicxml_path: str,
    mapping_path: str,
    tuning: str = "honchoshi"
) -> ConversionResult:
    """
    MusicXMLファイルを読み込んで三味線中間表現に変換する

    Parameters:
        musicxml_path: MusicXMLファイルのパス
        mapping_path:  shamisen_mapping.yaml のパス
        tuning:        "honchoshi" / "niagari" / "sansagari"
    """

    mapping = load_mapping(mapping_path)
    midi_map = build_midi_to_position(mapping, tuning)

    score = converter.parse(musicxml_path)
    result = ConversionResult(tuning=tuning)

    # 音符を順番に処理
    for element in score.flat.notesAndRests:
        duration = element.duration.quarterLength
        offset = float(element.offset)

        if isinstance(element, note.Rest):
            # 休符
            result.notes.append(ShamisenNote(
                string=None,
                position=None,
                midi=-1,
                note_name="rest",
                duration=duration,
                offset=offset,
            ))

        elif isinstance(element, note.Note):
            midi_num = element.pitch.midi
            note_name = element.pitch.nameWithOctave
            sn = convert_note(midi_num, note_name, duration, offset, midi_map)
            result.notes.append(sn)
            if sn.warning:
                result.warnings.append(sn.warning)

        elif isinstance(element, chord.Chord):
            # 和音→最高音だけ使う（三味線は単音楽器）
            highest = max(element.pitches, key=lambda p: p.midi)
            midi_num = highest.midi
            note_name = highest.nameWithOctave
            sn = convert_note(midi_num, note_name, duration, offset, midi_map)
            sn.warning = (sn.warning or "") + "（和音→最高音を使用）"
            result.notes.append(sn)
            if sn.warning:
                result.warnings.append(sn.warning)

    return result


# ===========================
# 中間XML出力
# ===========================

STRING_LABEL = {
    "san_no_ito": "三",
    "ni_no_ito":  "二",
    "ichi_no_ito": "一",
}

def to_intermediate_yaml(result: ConversionResult) -> str:
    """変換結果を中間YAMLとして出力する"""

    data: dict = {
        "tuning": result.tuning,
        "style": "bunkafu",
    }
    if result.warnings:
        data["warnings"] = result.warnings

    notes = []
    for sn in result.notes:
        if sn.note_name == "rest":
            notes.append({"type": "rest", "offset": sn.offset, "duration": sn.duration})
        else:
            entry: dict = {
                "type": "note",
                "offset": sn.offset,
                "duration": sn.duration,
                "note": sn.note_name,
                "midi": sn.midi,
            }
            if sn.out_of_range:
                entry["out_of_range"] = True
                entry["status"] = "unresolved"
            else:
                entry["string"] = STRING_LABEL.get(sn.string, sn.string)
                entry["string_key"] = sn.string
                entry["position"] = sn.position
                entry["status"] = "ok"
            if sn.warning:
                entry["warning"] = sn.warning
            notes.append(entry)

    data["notes"] = notes
    return yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


# ===========================
# 音域外の処理（ユーザー選択）
# ===========================

OUT_OF_RANGE_OPTIONS = {
    "1": "オクターブ上げて再変換",
    "2": "オクターブ下げて再変換",
    "3": "この音をスキップ（休符として扱う）",
    "4": "そのまま未解決として残す",
}

def resolve_out_of_range(
    result: ConversionResult,
    midi_map: dict,
    interactive: bool = True
) -> ConversionResult:
    """
    音域外の音をユーザーの選択に従って処理する
    interactive=False の場合はすべて「未解決のまま」にする
    """

    for sn in result.notes:
        if not sn.out_of_range:
            continue

        if not interactive:
            continue

        print(f"\n⚠️  音域外: {sn.note_name}（offset={sn.offset}）")
        for k, v in OUT_OF_RANGE_OPTIONS.items():
            print(f"  {k}: {v}")

        choice = input("選択してください [1-4]: ").strip()

        if choice == "1":
            new_midi = sn.midi + 12
            new_name = sn.note_name + "(+8va)"
            if new_midi in midi_map:
                string_name, position = midi_map[new_midi][0]
                sn.string = string_name
                sn.position = position
                sn.midi = new_midi
                sn.note_name = new_name
                sn.out_of_range = False
                sn.warning = f"オクターブ上げて解決: {new_name}"
            else:
                print("  → オクターブ上げても音域外のため未解決のままです")

        elif choice == "2":
            new_midi = sn.midi - 12
            new_name = sn.note_name + "(-8va)"
            if new_midi in midi_map:
                string_name, position = midi_map[new_midi][0]
                sn.string = string_name
                sn.position = position
                sn.midi = new_midi
                sn.note_name = new_name
                sn.out_of_range = False
                sn.warning = f"オクターブ下げて解決: {new_name}"
            else:
                print("  → オクターブ下げても音域外のため未解決のままです")

        elif choice == "3":
            sn.note_name = "rest"
            sn.out_of_range = False
            sn.warning = "音域外のためスキップ"

        else:
            # 4 or その他 → そのまま
            pass

    return result


# ===========================
# メイン（Colabでの使用例）
# ===========================

if __name__ == "__main__":
    import sys

    # パスは適宜変更
    MUSICXML_PATH = "input.xml"
    MAPPING_PATH  = "shamisen_mapping.yaml"
    OUTPUT_PATH   = "shamisen_output.yaml"

    # 調弦選択
    print("調弦を選んでください:")
    print("  1: 本調子")
    print("  2: 二上り")
    print("  3: 三下り")
    choice = input("選択 [1-3]: ").strip()
    tuning_map = {"1": "honchoshi", "2": "niagari", "3": "sansagari"}
    tuning = tuning_map.get(choice, "honchoshi")
    print(f"→ {tuning} で変換します\n")

    # 変換
    result = convert_musicxml(MUSICXML_PATH, MAPPING_PATH, tuning)

    # 警告表示
    if result.warnings:
        print(f"⚠️  {len(result.warnings)}件の警告があります")

    # 音域外の処理
    mapping = load_mapping(MAPPING_PATH)
    midi_map = build_midi_to_position(mapping, tuning)
    result = resolve_out_of_range(result, midi_map, interactive=True)

    # 中間YAML出力
    yaml_str = to_intermediate_yaml(result)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(yaml_str)

    print(f"\n✅ 変換完了 → {OUTPUT_PATH}")
