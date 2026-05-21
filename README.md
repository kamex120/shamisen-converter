# 三味線譜変換ツール

五線譜（PDF）を三味線の勘所情報付き中間XMLに変換するツール。
Google Colab 上で全工程を実行できる。

---

## 処理の流れ

```
PDF → 画像（pdf2image）→ MusicXML（oemer）→ 三味線中間XML（shamisen_converter）
```

---

## 現在の状況

- [x] 勘所マッピングYAML作成（本調子・二上り・三下り）
- [x] 変換エンジン基本実装（`shamisen_converter.py`）
- [x] 中間XML出力
- [x] PDF→MusicXML変換（oemer）※精度は要改善
- [x] Colabノートブック（`shamisen_colab.ipynb`）で全工程を実行可能
- [ ] 中間XMLから楽譜表示
- [ ] 手動修正UI
- [ ] oemerの認識精度改善 or Audiverisへの切り替え

---

## ファイル構成

```
shamisen_mapping.yaml    # 勘所マッピング定義
shamisen_converter.py    # 変換エンジン本体
shamisen_colab.ipynb     # Google Colab ノートブック（全工程）
README.md                # このファイル
```

---

## Colabでの使い方

### 前提条件
- GitHubのPersonal Access Token（`repo` スコープ）
- Colab Secrets に `GITHUB_TOKEN` として登録済み

### 手順
1. [Google Colab](https://colab.research.google.com) を開く
2. ファイル → ノートブックを開く → GitHub → `kamex120/shamisen-converter` → `shamisen_colab.ipynb`
3. ランタイムのタイプを **T4 GPU** に変更（ランタイム → ランタイムのタイプを変更）
4. **セル0**（セットアップ）を実行
5. **セル1-a** でPDFをアップロード
6. **セル1-b** でMusicXMLに変換（数分〜）
7. **セル1-c** で再生して認識精度を確認
8. **セル2** で調弦を選択
9. **セル3** で三味線中間XMLに変換・ダウンロード

### セル0 で行うこと
- GitHubリポジトリのクローン（2回目以降は `git pull`）
- 依存ライブラリのインストール（oemer / music21 / pdf2image / onnxruntime-gpu）
- oemerのモデルウェイトのダウンロード（初回のみ、数分）

---

## 設計上の決定事項

### 対象
- 流派：文化譜（長唄系・最もメジャー）
- 将来的に他流派も選択できるようにする

### 調弦
- 本調子 / 二上り / 三下り の3種類に対応
- 実行時にユーザーが選択する

### 弦の優先順位
- 三の弦を最優先で使う
- 同じ音が複数の弦で出せる場合は三の弦を選択

### 音域外の音
- 警告を出してユーザーに処理を選ばせる
- 選択肢：オクターブ上げ／下げ／スキップ／未解決のまま

### 和音
- 三味線は単音楽器のため、和音は最高音のみ使用

---

## 中間XMLの構造

```xml
<ShamisenScore tuning="honchoshi" style="bunkafu">
  <Warnings>
    <Warning>音域外: C3（MIDI 48）は対応する勘所がありません</Warning>
  </Warnings>
  <Notes>
    <Note
      offset="0.0"
      duration="1.0"
      original_note="D4"
      original_midi="62"
      string="三"
      string_key="san_no_ito"
      position="0"
      status="ok"
    />
    <Rest offset="1.0" duration="1.0"/>
    <Note
      offset="2.0"
      duration="1.0"
      original_note="C3"
      original_midi="48"
      out_of_range="true"
      status="unresolved"
    />
  </Notes>
</ShamisenScore>
```

---

## 勘所マッピング（shamisen_mapping.yaml）

### 本調子
| 勘所 | 三の弦 | 二の弦 | 一の弦 |
|------|--------|--------|--------|
| 0（開放）| D4 | G4 | D5 |
| 1 | E4 | A4 | E5 |
| 2 | F#4 | B4 | F#5 |
| 3 | G4 | C5 | G5 |
| 4 | A4 | D5 | A5 |
| 5 | B4 | E5 | - |
| 6 | C#5 | F#5 | - |
| 7 | D5 | G5 | - |
| 8 | E5 | - | - |
| 9 | F#5 | - | - |
| 10 | G5 | - | - |

※ 本調子の二の弦3番はC（ナチュラル）

### 二上り：二の弦がG4→A4に上がる。他は本調子と同じ
### 三下り：三の弦がD4→C4に下がる。他は本調子と同じ

---

## 既知の課題・注意点

- **oemerの認識精度**：楽譜の品質・複雑さによって大きく変わる。再生確認（セル1-c）で必ずチェックすること
- **処理時間**：oemer の推論はGPU使用でも数十秒〜数分かかる
- **oemerのGPU対応**：`onnxruntime-gpu>=1.18.0` が必要（cuDNN 9 / CUDA 12 対応）
- **勘所マッピング**：仮定値が含まれる。三味線に詳しい人に確認・修正が必要
- **複数パート（合奏）**：非対応

---

## 今後やること

- [ ] oemerの認識精度改善（Audiverisへの切り替えも検討）
- [ ] 音域外の音の候補（オクターブ違い）を中間XMLに含める
- [ ] 同じ音の複数候補（弦の選択肢）を中間XMLに保持する
- [ ] 手動修正UIの検討
- [ ] 中間XMLから文化譜として表示・出力する
- [ ] 他流派対応（研精会譜・縦譜など）
