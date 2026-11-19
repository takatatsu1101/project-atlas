---
title: テクニカル指標仕様書
document_id: SPEC-INDICATOR-001
version: 0.2.0
status: Implemented
project: Project Atlas
author: Takatori Tatsuo
updated: 2026-11-19
---

# テクニカル指標仕様

`IndicatorCalculator`（`src/indicator_calculator/calculator.py`）は OHLCV 系列から以下 15 種類のテクニカル指標を一括ベクトル計算する。

| 指標キー | 算出内容 | 備考 |
|---|---|---|
| `SMA5` | 終値の 5 営業日単純移動平均 | データ長 5 日未満は未格納 |
| `SMA25` | 終値の 25 営業日単純移動平均 | データ長 25 日未満は未格納 |
| `SMA75` | 終値の 75 営業日単純移動平均 | データ長 75 日未満は未格納 |
| `SMA200` | 終値の 200 営業日単純移動平均 | 長期トレンド基準。データ長 200 日未満は未格納 |
| `RSI5` | 終値の 5 営業日 RSI（Cutler 型） | 短期反転トリガー用（`min_periods=1`） |
| `RSI14` | 終値の 14 営業日 RSI（Cutler 型） | モメンタム評価用（`min_periods=1`） |
| `MACD` | EMA(12, 26, 9) の `macd` / `signal` / `histogram` | 辞書形式で格納 |
| `HIGHEST_HIGH_20` | 当日含む直近 20 営業日の高値最大値 | `min_periods=1` |
| `HIGHEST_HIGH_60` | 当日含む直近 60 営業日の高値最大値 | `min_periods=1` |
| `HIGHEST_HIGH_250` | 当日含む直近 250 営業日の高値最大値（52週高値相当） | `min_periods=1` |
| `LOWEST_LOW_20` | 当日含む直近 20 営業日の安値最小値 | `min_periods=1` |
| `ATR5` | 5 営業日 True Range 平均 | 短期ボラティリティ（VCP 収縮率分子） |
| `ATR14` | 14 営業日 True Range 平均 | 定常リスク・損切り幅基準 |
| `ATR20` | 20 営業日 True Range 平均 | 中期ボラティリティ（VCP 収縮率分母） |
| `VOLUME_RATIO` | 当日出来高 ÷ 当日含む直近 20 営業日平均出来高 | 出来高急増倍率 |

## キャッシュ整合性

- JSON キャッシュ（`cache/indicators_{symbol}[_{suffix}].json`）の読込時は、系列長一致・全日付列完全一致に加え、最新要素の `indicators` に `LOWEST_LOW_20`, `RSI5`, `ATR5`, `ATR20`, `HIGHEST_HIGH_60`, `HIGHEST_HIGH_250` がすべて含まれることを検証し、旧形式キャッシュの混入を防ぐ。
