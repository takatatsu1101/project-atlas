---
title: パターン仕様書一覧
document_id: SPEC-PATTERN-LIST
version: 0.1.0
status: Draft
project: Project Atlas
author:
created:
updated:
related:
  - specifications/feature_list.md
  - design/pattern_detector.md
---

# パターン仕様書一覧

## 1. 目的

本書は、Project Atlasで利用するチャートパターンを定義する。

各パターンは Pattern Detector により判定され、Score Engine が売買判断を行うための評価材料として利用する。

本仕様書では「どのようなチャートパターンを判定するか」を定義する。詳細な判定アルゴリズムや実装方法は設計書で管理する。

---

## 2. パターンカテゴリ

パターンは責務ごとにカテゴリへ分類する。

| カテゴリID | カテゴリ名 | 説明 |
|------------|------------|------|
| R | Reversal | トレンド転換を示すパターン |
| C | Continuation | トレンド継続を示すパターン |
| S | Support / Resistance | サポート・レジスタンスに関するパターン |
| K | Candlestick | ローソク足パターン |

---

## 3. パターン一覧

| ID | カテゴリ | パターン名 | 説明 | 優先度 | ステータス |
|----|----------|------------|------|---------|------------|
| R001 | Reversal | DoubleBottom | ダブルボトム | P1 | Draft |
| R002 | Reversal | DoubleTop | ダブルトップ | P1 | Draft |

---

## 4. パターン仕様テンプレート

今後、各パターンは個別仕様書として作成し、以下のテンプレートに従って定義する。

````yaml
---
title: <Pattern名>
document_id: SPEC-PATTERN-<Pattern ID>
version: 0.1.0
status: Draft
project: Project Atlas
pattern_id: <Pattern ID>
category: <カテゴリ>
author:
created:
updated:
related:
  - specifications/pattern_list.md
  - specifications/feature_list.md
  - design/pattern_detector.md
---
````
````md
# <Pattern名>

## 1. 概要
- Pattern ID：
- パターン名：
- 日本語名：
- カテゴリ：
- ステータス：
- 優先度：

## 2. 目的
- 判定する目的
- 採用理由・期待する効果

## 3. 前提条件
- 判定に必要な条件
- 必要なFeature

## 4. 入力
- 利用するFeature
- 利用するパラメータ

## 5. 出力
- 判定結果
- 判定レベル
- 判定理由

## 6. 判定概要
- 判定の考え方
- 判定手順（自然言語）
- 使用するパラメータ
- 備考

## 7. 判定基準
- 成立条件
- 不成立条件
- 判定レベル

## 8. 利用箇所
- 利用モジュール
- 利用目的

## 9. 例外処理
- データ不足時
- 判定不能時

## 10. テスト観点
- 正常系
- 境界値
- 異常系
- 代表例

## 11. 今後の拡張
- 改善案
- 将来追加予定
````

---

## 5. 命名規則

* Pattern ID はカテゴリごとに採番する（例：R001、C003）。
* パターン名は英語（PascalCase）とする。
* 仕様書内では日本語名を併記する。

---

## 6. Pattern追加ルール

新しいPatternを追加する場合は以下を満たすこと。

* 一意なPattern IDを採番する。
* カテゴリを決定する。
* 判定基準を定義する。
* 個別仕様書を作成する。

---

## 7. 更新履歴

| バージョン | 内容 |
|------------|------|
| 0.1.0 | 初版作成 |