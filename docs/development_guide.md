---
title: 開発環境とプロジェクト実行ガイド
document_id: GUIDE-DEV-001
version: 0.1.0
status: Active
project: Project Atlas
author: Takatori Tatsuo
created: 2026-10-04
updated: 2026-10-04
---

# 開発環境とプロジェクト実行ガイド (macOS)

本ドキュメントでは、Project Atlas を macOS 環境においてセットアップし、仮想環境を有効化してプロジェクトを実行する手順をまとめる。

## 1. 前提条件
- macOS 環境
- Python 3.x がインストールされていること

## 2. 仮想環境の有効化 (Activate)
Project Atlas では、プロジェクトルート直下にPythonの仮想環境（例: `venv/`）が用意されている。ターミナルで以下のコマンドを実行し、仮想環境を有効化する。

```bash
source venv/bin/activate
```

### 正常に有効化されたことの確認
有効化されると、ターミナルのプロンプトの先頭に `(venv)` のような仮想環境名が表示される。また、以下のコマンドで参照しているPythonのパスが仮想環境内のものになっているか確認できる。

```bash
which python
```
*出力例*: `/Users/.../ProjectAtlas/venv/bin/python`

---

## 3. プロジェクトの実行方法
仮想環境を有効化した状態で、プロジェクトのエントリポイントやモジュールを実行する。

### 基本的な実行形式
- モジュールとして実行する場合（推奨）：
  ```bash
  python -m src.main
  ```
  *(※ `python src/main.py` ではなく、必ずルートディレクトリから `-m src.main` として実行してください。直接ファイルを実行すると `src` パッケージが認識されず `ModuleNotFoundError` になります)*

### Gemini 連携ブリーフ出力の実行例
- Gemini 専用プリセット（東証プライム・20日平均売買代金30億円以上・株価5,000円以下）＋既存監視銘柄同梱＋Google ドライブ同期フォルダへの自動コピー：
  ```bash
  python -m src.main \
    --config config/screening_gemini.yaml \
    --watch-symbols 7203.T 6758.T \
    --brief-copy-dir "~/Library/CloudStorage/GoogleDrive-xxx/マイドライブ/ProjectAtlas"
  ```
- 主な関連 CLI オプション：
  - `--gemini-brief`: `output.formats` に `"gemini"` が含まれていない設定でも `gemini_brief_YYYY-MM-DD.md` および `gemini_brief_latest.md` を追加出力する。
  - `--brief-copy-dir <PATH>`: `output.gemini_brief_copy_dir` を上書きし、同期フォルダへ自動コピーする（未マウント時は警告ログのみ出力しローカル出力は維持）。
  - `--watch-symbols <SYM...>`: スクリーニング上位外の既存監視銘柄について、同一フォーマットの最新判断材料を別セクションへ同梱する。

---

## 4. トラブルシューティング
- **コマンドが見つからない場合**:
  正しく `source venv/bin/activate` が実行されているか、カレントディレクトリがプロジェクトルート (`/Users/takatoritatsuo/program/ProjectAtlas`) であるかを確認する。
- **パッケージが不足している場合**:
  必要に応じて以下のコマンドで依存関係をインストールする。
  ```bash
  pip install -r requirements.txt
  ```
