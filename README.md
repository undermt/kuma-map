# クマ出没情報アプリ

滋賀・岐阜・愛知・静岡のクマ目撃情報をGoogleMap風に地図表示するAndroidアプリ(将来的に愛知も追加予定)。

公開URL: https://undermt.github.io/kuma-map/

## 現在のスコープ(MVP)

- 対象: **静岡県・岐阜県・滋賀県(大津市・高島市・栗東市)**
- 愛知県は緯度経度データが一切なく(PDFの住所文字列のみ)、二次利用規約も未確認のため今回は除外。将来追加する場合はジオコーディング実装+県への利用可否確認が必要。
- 滋賀県の米原市は地名のみ(座標なし)のため今回は見送り。甲賀市・東近江市・長浜市は目撃情報の一覧データ自体が存在しない(単発告知のみ)。
- 民間集約サイト(kumamap.com等)は、データ出典の検証可能性が低く利用規約も不明確なため不採用。県・市の公式データのみを一次情報源とする方針。
- 地図は **OpenStreetMap + Leaflet**(Google Maps不使用、課金設定不要)。

## 構成

```
クマ出没情報アプリ/
├── data-pipeline/          # 各県データの取得・正規化バッチ(Python)
│   ├── fetch_and_normalize.py
│   └── requirements.txt
├── docs/                   # GitHub Pagesで公開する静的サイト(地図本体)
│   ├── index.html          # Leaflet地図(Androidアプリはこれを表示する)
│   └── data.geojson        # 集約済みデータ(batchが生成)
└── android-app/            # Android Studioプロジェクト(WebViewラッパー)
    └── app/src/main/assets/ # オフライン用フォールバックのスナップショット(docsのコピー)
```

### データの流れ

1. `data-pipeline/fetch_and_normalize.py` が3県の一次情報源から取得・正規化し `docs/data.geojson` を生成
2. `docs/` を GitHub Pages で公開(未セットアップ、下記「残タスク」参照)
3. Androidアプリ(WebViewのみの薄いラッパー)がGitHub PagesのURLを表示。取得失敗時はアプリに同梱したオフラインスナップショット(`assets/`)にフォールバック

## 各県データソースの注意点

| 県 | ソース | 更新頻度 | 注意点 |
|---|---|---|---|
| 静岡県 | 県公式Googleマイマップ(KML) | 高頻度(随時) | 非公式のKMLエクスポートURLを使用。県がマップIDを変更すると壊れる |
| 岐阜県 | 県オープンデータ(Shapefile, CKAN API経由で最新年度を自動取得) | **年度単位**(年1回更新の過去データ) | 座標系はJGD2011第Ⅶ系(EPSG:6675)。ライセンスCC-BY 2.1 JP → **アプリ公開時は出典表示が必須** |
| 滋賀県(大津市) | 大津市公式Googleマイマップ(KML) | 中頻度 | 県全体はカバーしていない |
| 滋賀県(高島市) | 高島市公式Googleマイマップ(KML) | 中頻度 | 名前欄の日付表記が「R8.4.21」等の令和略記、大津市とは別実装 |
| 滋賀県(栗東市) | 栗東市公式サイト(HTML、目撃ごとに個別Googleマップリンク) | 随時 | 座標リンクが無い投稿(訂正情報・他市町経由の告知)は自動的に対象外。ページ構造変更に弱い(HTMLスクレイピングのため) |

**岐阜県は実質「1年以上前の年度データ」が最新表示になる点に注意。** 直近の出没情報が欲しい場合は「県域統合型GISぎふ」(非公式SPA、API仕様未解析)の追加調査が必要。

**愛知県以外についても、二次利用・商用利用の明確な規約が確認できたのは岐阜県のみ。** 個人利用の範囲を超えて公開・配布する場合は、各自治体の担当課(滋賀県: 自然環境保全課、静岡県: 自然保護課、大津市・高島市・栗東市: 各農林振興担当課)に利用可否を確認すること。

## 残タスク

1. データ更新の自動化(推奨: GitHub Actionsで`fetch_and_normalize.py`を日次実行し`docs/data.geojson`を自動コミット)
2. Android StudioでAPKをビルド(このPCにはAndroid SDK未インストール、`winget install Google.AndroidStudio`済み)

## ローカルでのデータ更新(手動)

```powershell
cd data-pipeline
pip install -r requirements.txt
python fetch_and_normalize.py
```

`docs/data.geojson` が更新されるので、`android-app/app/src/main/assets/data.geojson` にも必要に応じてコピーする。
