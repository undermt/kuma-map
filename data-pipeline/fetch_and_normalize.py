"""
クマ出没情報の収集・正規化パイプライン (MVP: 静岡県, 岐阜県, 滋賀県大津市)

各県のデータを取得し、共通スキーマのGeoJSON (docs/data.geojson) にまとめて出力する。
GitHub Pagesの /docs フォルダから配信し、Androidアプリ(WebView)はそのGeoJSONを読み込んで地図表示する想定。

実行方法:
    pip install -r requirements.txt
    python fetch_and_normalize.py
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

try:
    import shapefile
    from pyproj import Transformer
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "必要なライブラリが不足しています。`pip install -r requirements.txt` を実行してください。"
    ) from e

OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "data.geojson"
HEADERS = {
    # 愛知県サイト同様、素のUser-AgentだとブロックされるWAFがあるためブラウザ風に偽装
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
KML_NS = "{http://www.opengis.net/kml/2.2}"

SHIZUOKA_KML_URL = "https://www.google.com/maps/d/kml?mid=1o_iXJ5z-tA9bTd8k2DMFPLO9BS4LRDI&forcekml=1"
OTSU_KML_URL = "https://www.google.com/maps/d/kml?mid=1rE5HcSdJnm2gX3iT1FMt0aCVuQ9ArDs&forcekml=1"
GIFU_CKAN_API = "https://gifu-opendata.pref.gifu.lg.jp/api/3/action/package_show?id=c11265-010"

# 岐阜県オープンデータの平面直角座標系(第Ⅶ系, JGD2011)→ 緯度経度(JGD2011)変換
GIFU_CRS_TRANSFORMER = Transformer.from_crs("EPSG:6675", "EPSG:4326", always_xy=True)


@dataclass
class Sighting:
    prefecture: str
    city: str | None
    place: str | None
    date: str | None  # YYYY-MM-DD (不明な場合はNone)
    time: str | None
    count: int | None
    note: str | None
    source: str
    lon: float
    lat: float

    def to_feature(self) -> dict:
        props = asdict(self)
        lon = props.pop("lon")
        lat = props.pop("lat")
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        }


def _parse_int(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def _slash_date_to_iso(text: str | None) -> str | None:
    """'2026/4/2' -> '2026-04-02'"""
    if not text:
        return None
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", text.strip())
    if not m:
        return None
    y, mo, d = (int(g) for g in m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _fiscal_year_to_calendar_year(fiscal_year_reiwa: int, month: int) -> int:
    """令和N年度は N年4月始まり。西暦換算: 令和1年度=2019年度 (2018+N が起点年)"""
    base = 2018 + fiscal_year_reiwa
    return base if month >= 4 else base + 1


def fetch_shizuoka() -> list[Sighting]:
    resp = requests.get(SHIZUOKA_KML_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    results: list[Sighting] = []
    for placemark in root.iter(f"{KML_NS}Placemark"):
        data = {}
        for d in placemark.findall(f"{KML_NS}ExtendedData/{KML_NS}Data"):
            key = d.get("name")
            value = d.findtext(f"{KML_NS}value")
            data[key] = value
        if "経度" not in data or "緯度" not in data:
            continue
        try:
            lon = float(data["経度"])
            lat = float(data["緯度"])
        except (TypeError, ValueError):
            continue
        results.append(
            Sighting(
                prefecture="静岡県",
                city=data.get("市町"),
                place=data.get("地名"),
                date=_slash_date_to_iso(data.get("日付")),
                time=data.get("目撃時間"),
                count=_parse_int(data.get("目撃頭数")),
                note=data.get("備考") or None,
                source="静岡県 クマ出没マップ (https://www.pref.shizuoka.jp/kurashikankyo/shizenkankyo/wild/1017680.html)",
                lon=lon,
                lat=lat,
            )
        )
    return results


_OTSU_NAME_RE = re.compile(
    r"^(?P<month>\d{1,2})/(?P<day>\d{1,2})"
    r"[\s　]*"
    r"(?:(?P<hour>\d{1,2})[:：](?P<minute>\d{2})\s*頃?)?"
    r"[\s　]*"
    r"(?P<place>.*)$"
)


def fetch_otsu() -> list[Sighting]:
    resp = requests.get(OTSU_KML_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    results: list[Sighting] = []
    for folder in root.iter(f"{KML_NS}Folder"):
        folder_name = (folder.findtext(f"{KML_NS}name") or "").strip()
        m = re.search(r"令和(\d+)年度", folder_name)
        fiscal_year = int(m.group(1)) if m else None

        for placemark in folder.findall(f"{KML_NS}Placemark"):
            raw_name = (placemark.findtext(f"{KML_NS}name") or "").strip()
            raw_name = re.sub(r"[\s　]+", "　", raw_name)
            coords_text = placemark.findtext(f"{KML_NS}Point/{KML_NS}coordinates")
            if not coords_text:
                continue
            parts = coords_text.strip().split(",")
            if len(parts) < 2:
                continue
            lon, lat = float(parts[0]), float(parts[1])

            date_iso = None
            time_str = None
            place = raw_name
            nm = _OTSU_NAME_RE.match(raw_name)
            if nm:
                month, day = int(nm.group("month")), int(nm.group("day"))
                place = (nm.group("place") or "").strip("　 ") or None
                if nm.group("hour"):
                    time_str = f"{int(nm.group('hour')):02d}:{nm.group('minute')}"
                if fiscal_year is not None:
                    year = _fiscal_year_to_calendar_year(fiscal_year, month)
                    date_iso = f"{year:04d}-{month:02d}-{day:02d}"

            description = (placemark.findtext(f"{KML_NS}description") or "").strip() or None

            results.append(
                Sighting(
                    prefecture="滋賀県",
                    city="大津市",
                    place=place,
                    date=date_iso,
                    time=time_str,
                    count=None,
                    note=description,
                    source="大津市 ツキノワグマ出没マップ (https://www.city.otsu.lg.jp/soshiki/025/1605/g/t/74581.html)",
                    lon=lon,
                    lat=lat,
                )
            )
    return results


def _gifu_latest_zip_url() -> tuple[str, int]:
    """CKAN APIから最新年度のZIPリソースURLと令和年度番号を取得"""
    resp = requests.get(GIFU_CKAN_API, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resources = resp.json()["result"]["resources"]

    best = None  # (reiwa_year, url)
    for r in resources:
        if r.get("format", "").upper() != "ZIP":
            continue
        m = re.search(r"令和(\d+)年度", r.get("name", ""))
        if not m:
            continue
        year = int(m.group(1))
        if best is None or year > best[0]:
            best = (year, r["url"])
    if best is None:
        raise RuntimeError("岐阜県オープンデータからZIPリソースが見つかりませんでした")
    return best[1], best[0]


def fetch_gifu() -> list[Sighting]:
    zip_url, fiscal_year = _gifu_latest_zip_url()
    resp = requests.get(zip_url, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    shp_name = next(n for n in names if n.upper().endswith(".SHP"))
    dbf_name = next(n for n in names if n.upper().endswith(".DBF"))
    shx_name = next(n for n in names if n.upper().endswith(".SHX"))

    sf = shapefile.Reader(
        shp=io.BytesIO(zf.read(shp_name)),
        dbf=io.BytesIO(zf.read(dbf_name)),
        shx=io.BytesIO(zf.read(shx_name)),
        encoding="cp932",
    )

    source_label = (
        f"岐阜県オープンデータ「クママップ」令和{fiscal_year}年度分 "
        "(CC-BY 2.1 JP, https://gifu-opendata.pref.gifu.lg.jp/dataset/c11265-010)"
    )

    results: list[Sighting] = []
    for sr in sf.iterShapeRecords():
        if not sr.shape.points:
            continue
        x, y = sr.shape.points[0]
        lon, lat = GIFU_CRS_TRANSFORMER.transform(x, y)
        rec = sr.record.as_dict()

        month = _parse_int(rec.get("出没月"))
        day = _parse_int(rec.get("出没日"))
        date_iso = None
        if month and day:
            year = _fiscal_year_to_calendar_year(fiscal_year, month)
            date_iso = f"{year:04d}-{month:02d}-{day:02d}"

        note_parts = [p for p in (rec.get("出没場所"), rec.get("目撃者情報")) if p]

        results.append(
            Sighting(
                prefecture="岐阜県",
                city=rec.get("市町村名"),
                place=rec.get("旧市町村名") or rec.get("出没場所"),
                date=date_iso,
                time=rec.get("出没時間"),
                count=_parse_int(rec.get("頭数")),
                note="・".join(note_parts) or None,
                source=source_label,
                lon=lon,
                lat=lat,
            )
        )
    return results


def main() -> None:
    all_sightings: list[Sighting] = []
    fetchers = [
        ("静岡県", fetch_shizuoka),
        ("滋賀県(大津市)", fetch_otsu),
        ("岐阜県", fetch_gifu),
    ]
    for label, fn in fetchers:
        try:
            items = fn()
            print(f"[OK] {label}: {len(items)}件")
            all_sightings.extend(items)
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] {label}: 取得に失敗しました -> {e}")

    feature_collection = {
        "type": "FeatureCollection",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "features": [s.to_feature() for s in all_sightings],
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        __import__("json").dumps(feature_collection, ensure_ascii=False, indent=None),
        encoding="utf-8",
    )
    print(f"合計 {len(all_sightings)}件 -> {OUT_PATH}")


if __name__ == "__main__":
    main()
