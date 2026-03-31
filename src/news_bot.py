from __future__ import annotations

import json
import html
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from config import DEFAULT_NEWS_BOT_CONFIG, DOCS_DIR, NEWS_STATE_JSON, OUTPUT_DIR, PROJECT_ROOT

IS_WINDOWS = os.name == "nt"
INVEST_ANALYSIS_CANDIDATES = (
    Path(r"C:\AI\Invest\output\analysis_payload.json"),
    PROJECT_ROOT / "data" / "invest_analysis_snapshot.json",
)
INVEST_HISTORY_CANDIDATES = (
    Path(r"C:\AI\Invest\output\portfolio_history_1y_daily.csv"),
    PROJECT_ROOT / "data" / "portfolio_history_1y_daily.csv",
)
TEFAS_HISTORY_URL = "https://www.tefas.gov.tr/api/DB/BindHistoryInfo"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
TEFAS_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.tefas.gov.tr",
    "Referer": "https://www.tefas.gov.tr/TarihselVeriler.aspx",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}
YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}


CATEGORY_LABELS = {
    "macro": "Makro",
    "technology": "Teknoloji",
    "robotics": "Robotik",
    "financial_system": "Finansal Sistem",
}

TOPIC_ROUTER = {
    "nvidia": {
        "label": "Nvidia",
        "best_source": "Bloomberg Technology",
        "best_url": "https://www.bloomberg.com/series/bloomberg-technology",
        "backup_source": "Stratechery",
        "backup_url": "https://stratechery.com/about/",
        "reason": "Nvidia, AI capex, çipler ve veri merkezi yarışı gibi konularda en hızlı ve en piyasa duyarlı akışlardan biri.",
        "mode": "Önce hızlı haber akışını oku, sonra stratejik anlamlandırma için ikinci kaynağa geç.",
        "keywords": ("nvidia", "gpu", "chip", "chips", "semiconductor", "data center"),
    },
    "ai_models": {
        "label": "YZ Modelleri",
        "best_source": "The Information",
        "best_url": "https://www.theinformation.com/about/",
        "backup_source": "Semafor Tech",
        "backup_url": "https://www.semafor.com/vertical/tech",
        "reason": "Model savaşı, şirket içi hamleler, ürün stratejisi ve yatırım akışlarını erken okumak için çok güçlü.",
        "mode": "İlk önce oyuncular ne yapıyor diye bak, sonra piyasa etkisini ikinci kaynakta teyit et.",
        "keywords": ("openai", "anthropic", "model", "llm", "chatgpt", "gemini", "meta ai", "ai"),
    },
    "robotics": {
        "label": "Robotik",
        "best_source": "The Robot Report",
        "best_url": "https://www.therobotreport.com/",
        "backup_source": "Bloomberg Technology",
        "backup_url": "https://www.bloomberg.com/series/bloomberg-technology",
        "reason": "Robotik şirketleri, depo otomasyonu, humanoid gelişmeler ve sanayi kullanımlarını daha odaklı verir.",
        "mode": "Niş bir alan olduğu için önce uzman yayına git, büyük piyasa etkisi varsa sonra geniş teknoloji kaynağına bak.",
        "keywords": ("robot", "robotics", "humanoid", "autonomous", "factory", "warehouse", "automation"),
    },
    "geopolitics": {
        "label": "Jeopolitik",
        "best_source": "Reuters World",
        "best_url": "https://www.reuters.com/world/",
        "backup_source": "Foreign Affairs",
        "backup_url": "https://www.foreignaffairs.com/",
        "reason": "Jeopolitik olaylar, devlet kararları, savunma ve ticaret gerilimlerinde temiz ve hızlı temel akış sunar.",
        "mode": "Önce olay akışını Reuters'tan al, daha sonra yapısal anlamlandırma için derin kaynağa geç.",
        "keywords": ("china", "trade", "tariff", "sanction", "defense", "war", "military", "treasury", "fed"),
    },
    "payments": {
        "label": "Ödemeler / Visa",
        "best_source": "Payments Dive",
        "best_url": "https://www.paymentsdive.com/",
        "backup_source": "Reuters Business",
        "backup_url": "https://www.reuters.com/business/",
        "reason": "Visa, Mastercard, fintek altyapısı, API ekonomisi ve ödeme ağları tarafında daha odaklı akış verir.",
        "mode": "Spesifik ödeme trendini odaklı yayında gör, daha sonra makro yansımayı business akışta kontrol et.",
        "keywords": ("visa", "mastercard", "payment", "payments", "api", "fintech", "wallet", "stablecoin"),
    },
    "markets": {
        "label": "Markets",
        "best_source": "Bloomberg",
        "best_url": "https://www.bloomberg.com/",
        "backup_source": "Financial Times",
        "backup_url": "https://www.ft.com/markets",
        "reason": "Piyasa fiyatlaması, faiz, tahvil, dolar ve risk iştahı gibi konularda hızlı ve profesyonel akış sunar.",
        "mode": "İlk reaksiyonu Bloomberg'de gör, daha sakin ve analitik bağlamı FT ile tamamla.",
        "keywords": ("market", "stocks", "bond", "bonds", "yield", "inflation", "dollar", "rates", "equity"),
    },
}

KEYWORD_WEIGHTS = {
    "macro": {
        "tariff": 5,
        "sanction": 5,
        "china": 4,
        "u.s.": 4,
        "united states": 4,
        "fed": 4,
        "treasury": 3,
        "oil": 3,
        "inflation": 4,
        "trade": 4,
        "defense": 3,
        "geopolitical": 3,
        "central bank": 4,
    },
    "technology": {
        "nvidia": 7,
        "openai": 5,
        "anthropic": 4,
        "google": 3,
        "microsoft": 3,
        "ai": 4,
        "artificial intelligence": 5,
        "chip": 4,
        "semiconductor": 4,
        "data center": 4,
        "gpu": 5,
        "model": 3,
    },
    "robotics": {
        "robot": 5,
        "robotics": 6,
        "humanoid": 6,
        "automation": 4,
        "factory": 3,
        "warehouse": 3,
        "autonomous": 4,
        "tesla bot": 5,
    },
    "financial_system": {
        "visa": 6,
        "mastercard": 5,
        "payment": 5,
        "api": 3,
        "fintech": 4,
        "swift": 5,
        "stablecoin": 4,
        "settlement": 4,
        "banking": 3,
        "digital wallet": 4,
    },
}

WHY_IT_MATTERS = {
    "macro": "Makro rejim degisimi kur, faiz, emtia ve risk istahini birlikte etkiler.",
    "technology": "YZ altyapi yarisi sermaye akislarini, cip talebini ve platform kazananlarini belirler.",
    "robotics": "Robotik gercek dunyaya indiginde verimlilik, uretim yapisi ve is gucu dengesi degisir.",
    "financial_system": "Odeme ve finans altyapisindaki degisim yeni kazananlari ve islem akisini yeniden kurar.",
}

SOURCE_QUALITY_BONUS = {
    "Reuters World": 5,
    "Reuters Business": 5,
    "Reuters Technology": 5,
    "AP World": 4,
    "BBC World": 4,
    "The Robot Report": 4,
    "Payments Dive": 3,
    "TechCrunch": -6,
}

LOW_SIGNAL_PATTERNS = (
    "fund launches",
    "launches $",
    "launches a $",
    "program to support",
    "change their gmail address",
    "startup program",
    "appeared first on",
    "lets users",
    "letting users",
    "gmail address",
    "early stage ai startups",
)


@dataclass
class FeedItem:
    source: str
    title: str
    link: str
    published_at: str | None
    summary: str
    summary_tr: str
    categories: list[str]
    score: int
    why_it_matters: str
    matched_keywords: list[str]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    value = raw_value.strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\bThe post\b.*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bappeared first on\b.*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text.replace("\n", " ").replace("\r", " "))
    return text.strip()


def _fix_mojibake(value: str | None) -> str:
    if not value:
        return ""
    text = str(value)
    for _ in range(2):
        if not any(token in text for token in ("Ã", "Ä", "Å", "â", "�")):
            break
        try:
            repaired = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
        except UnicodeError:
            break
        if not repaired or repaired == text:
            break
        text = repaired
    return text.replace("\x00", "").strip()


def _html_text(value: str | None) -> str:
    fixed = _fix_mojibake(value)
    escaped = html.escape(fixed)
    return escaped.encode("ascii", "xmlcharrefreplace").decode("ascii")


def _first_text(element: ElementTree.Element, paths: Iterable[str]) -> str:
    for path in paths:
        node = element.find(path)
        if node is not None and node.text:
            return _clean_text(node.text)
    return ""


def _fetch_feed_xml(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; InvestNewsBot/1.0; +https://local.bot)",
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return response.read()
    except URLError as exc:
        if "unknown url type: https" not in str(exc).lower():
            raise
    if not IS_WINDOWS:
        raise URLError("PowerShell fallback is only available on Windows.")
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "(Invoke-WebRequest -UseBasicParsing -Uri '{}' -Headers @{{'User-Agent'='Mozilla/5.0 (compatible; InvestNewsBot/1.0)'; 'Accept'='application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8'}}).Content".format(url),
    ]
    result = subprocess.run(command, capture_output=True, check=True)
    return result.stdout


def _extract_items(feed_name: str, xml_payload: bytes) -> list[dict]:
    root = ElementTree.fromstring(xml_payload)
    items = []
    for item in root.findall(".//item"):
        title = _first_text(item, ("title",))
        link = _first_text(item, ("link",))
        summary = _first_text(item, ("description", "{http://purl.org/rss/1.0/modules/content/}encoded"))
        published_at = _first_text(item, ("pubDate", "{http://www.w3.org/2005/Atom}updated", "published"))
        if title and link:
            items.append(
                {
                    "source": feed_name,
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published_at": published_at or None,
                }
            )
    if items:
        return items

    for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        title = _first_text(entry, ("{http://www.w3.org/2005/Atom}title",))
        summary = _first_text(
            entry,
            ("{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content"),
        )
        published_at = _first_text(
            entry,
            ("{http://www.w3.org/2005/Atom}updated", "{http://www.w3.org/2005/Atom}published"),
        )
        link = ""
        for link_node in entry.findall("{http://www.w3.org/2005/Atom}link"):
            href = link_node.attrib.get("href", "").strip()
            if href:
                link = href
                break
        if title and link:
            items.append(
                {
                    "source": feed_name,
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published_at": published_at or None,
                }
            )
    return items


def _score_item(title: str, summary: str, categories: Iterable[str], published_at: str | None) -> tuple[int, list[str]]:
    text = f"{title} {summary}".lower()
    matched_keywords: list[str] = []
    score = 0
    for category in categories:
        for keyword, weight in KEYWORD_WEIGHTS.get(category, {}).items():
            if keyword in text:
                score += weight
                matched_keywords.append(keyword)
    published_dt = _parse_datetime(published_at)
    if published_dt is not None:
        age_hours = (_utc_now() - published_dt).total_seconds() / 3600
        if age_hours <= 12:
            score += 4
        elif age_hours <= 24:
            score += 3
        elif age_hours <= 48:
            score += 2
        elif age_hours <= 72:
            score += 1
    if any(token in text for token in ("surge", "record", "ban", "approve", "launch", "deal", "funding")):
        score += 2
    return score, sorted(set(matched_keywords))


def _passes_quality_filter(item: dict, score: int, matched_keywords: list[str]) -> bool:
    title = item["title"].lower()
    summary = item["summary"].lower()
    combined = f"{title} {summary}"
    source = item["source"]
    if any(pattern in combined for pattern in LOW_SIGNAL_PATTERNS):
        return False
    if source == "TechCrunch" and "nvidia" not in combined and "openai" not in combined and "anthropic" not in combined:
        return False
    if len(matched_keywords) < 2 and score < 15:
        return False
    if score < 16 and source not in {"Reuters World", "Reuters Business", "Reuters Technology", "The Robot Report", "Payments Dive"}:
        return False
    if "exclusive" not in combined and "nvidia" not in combined and "openai" not in combined and "visa" not in combined and "robot" not in combined and score < 18:
        return False
    return True


def _normalize_summary(summary: str) -> str:
    cleaned = _fix_mojibake(_clean_text(summary))
    if len(cleaned) > 280:
        cleaned = cleaned[:277].rstrip() + "..."
    return cleaned


def _build_turkish_summary(title: str, summary: str, primary_category: str, matched_keywords: list[str], source: str) -> str:
    keyword_set = set(matched_keywords)
    if {"humanoid", "warehouse"} & keyword_set:
        return "Bu haber, insansi robotlarin depo ve lojistik tarafinda gercek saha kullanimina gectigini gosteriyor."
    if {"visa", "mastercard", "stablecoin"} & keyword_set:
        return "Bu haber, odeme aglari ve stablecoin tarafinda rekabetin sertlestigini ve finans altyapisinda yeni guc dengeleri olustugunu gosteriyor."
    if "nvidia" in keyword_set or "gpu" in keyword_set or "semiconductor" in keyword_set:
        return "Bu haber, Nvidia ve yapay zeka cipleri tarafinda altyapi yarisinin hiz kesmeden devam ettigini gosteriyor."
    if "openai" in keyword_set or "anthropic" in keyword_set or "model" in keyword_set or primary_category == "technology":
        return "Bu haber, yapay zeka modeli ve altyapi yarisinda yeni urun, yatirim veya platform hamlelerinin surdugunu gosteriyor."
    if "robot" in keyword_set or "robotics" in keyword_set or primary_category == "robotics":
        return "Bu haber, robotik uygulamalarin laboratuvar asamasindan cikip gercek operasyonlara daha fazla girdigini gosteriyor."
    if "china" in keyword_set or "tariff" in keyword_set or "sanction" in keyword_set or primary_category == "macro":
        return "Bu haber, makro ve jeopolitik tarafta piyasalari etkileyebilecek yeni bir kirilmaya isaret ediyor."
    if primary_category == "financial_system":
        return "Bu haber, odeme ve finans altyapisinda oyuncular arasindaki rekabetin yeniden sekillendigini gosteriyor."
    cleaned = _normalize_summary(summary)
    if cleaned:
        return f"{source} haberine gore: {cleaned}"
    return "Bu haber, gunun stratejik akisinda izlenmeye deger bir gelismeye isaret ediyor."


def _pick_primary_category(categories: Iterable[str], matched_keywords: Iterable[str]) -> str:
    category_scores = {}
    keyword_set = set(matched_keywords)
    for category in categories:
        category_scores[category] = sum(
            weight for keyword, weight in KEYWORD_WEIGHTS.get(category, {}).items() if keyword in keyword_set
        )
    if category_scores:
        return max(category_scores, key=category_scores.get)
    return next(iter(categories), "technology")


def _build_why_it_matters(primary_category: str, matched_keywords: list[str]) -> str:
    base = WHY_IT_MATTERS.get(primary_category, "Bu gelişme stratejik yönü değiştirebilir.")
    if not matched_keywords:
        return base
    top_keywords = ", ".join(matched_keywords[:2])
    return f"{base} Bu sinyal özellikle {top_keywords} ekseninde öne çıkıyor."


def _deduplicate(items: Iterable[FeedItem]) -> list[FeedItem]:
    deduped: list[FeedItem] = []
    seen_titles: set[str] = set()
    for item in items:
        normalized_title = item.title.lower().strip()
        if normalized_title in seen_titles:
            continue
        seen_titles.add(normalized_title)
        deduped.append(item)
    return deduped


def _load_previous_state(path: Path) -> dict:
    candidate_paths = [path, DOCS_DIR / "world_developments_payload.json", OUTPUT_DIR / "world_developments_payload.json"]
    for candidate in candidate_paths:
        if not candidate.exists():
            continue
        try:
            state = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(state, dict):
            if candidate == path and not state.get("market_items") and (DOCS_DIR / "world_developments_payload.json").exists():
                continue
            return state
    return {}


def _market_state_lookup(previous_state: dict | None) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    if not isinstance(previous_state, dict):
        return lookup
    for item in previous_state.get("market_items", []) or []:
        label = str(item.get("label") or "").strip()
        if label:
            lookup[label] = item
    return lookup


def _history_daily_change_by_code(instrument_code: str) -> float | None:
    for history_path in INVEST_HISTORY_CANDIDATES:
        if not history_path.exists():
            continue
        rows: list[float] = []
        try:
            import csv

            with history_path.open("r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    code = str(row.get("instrument_code") or "").upper()
                    close = row.get("close")
                    if code != instrument_code.upper() or not close:
                        continue
                    rows.append(float(close))
        except Exception:
            continue
        if len(rows) < 2 or not rows[-2]:
            continue
        return ((rows[-1] / rows[-2]) - 1.0) * 100
    return None


def _load_invest_analysis() -> dict:
    for path in INVEST_ANALYSIS_CANDIDATES:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _post_form(url: str, data: dict[str, str], headers: dict[str, str]) -> dict:
    encoded = urlencode(data).encode("utf-8")
    request = Request(url, data=encoded, headers=headers, method="POST")
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str, headers: dict[str, str]) -> dict:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        if not IS_WINDOWS:
            raise
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            f"(Invoke-RestMethod -Uri '{url}' -Headers @{{'User-Agent'='Mozilla/5.0'}} | ConvertTo-Json -Depth 8)",
        ]
        result = subprocess.run(command, capture_output=True, check=True)
        return json.loads(result.stdout.decode("utf-8"))


def _fetch_tefas_daily_change(fund_code: str) -> tuple[float | None, float | None]:
    today = datetime.now().date()
    start = (today - timedelta(days=7)).strftime("%d.%m.%Y")
    end = today.strftime("%d.%m.%Y")
    payload = {
        "fontip": "YAT",
        "sfontur": "",
        "fonkod": fund_code,
        "fongrup": "",
        "bastarih": start,
        "bittarih": end,
        "fonturkod": "",
    }
    raw = _post_form(TEFAS_HISTORY_URL, payload, TEFAS_HEADERS)
    rows = []
    for item in raw.get("data", []):
        price_raw = item.get("FIYAT") or item.get("Fiyat")
        date_raw = item.get("TARIH") or item.get("Tarih")
        if price_raw in (None, "") or not date_raw:
            continue
        rows.append(
            {
                "date": str(date_raw)[:10],
                "close": float(str(price_raw).replace(",", ".")),
            }
        )
    rows.sort(key=lambda row: row["date"])
    if len(rows) < 2:
        return (rows[-1]["close"], None) if rows else (None, None)
    latest = float(rows[-1]["close"])
    previous = float(rows[-2]["close"])
    change_pct = ((latest / previous) - 1.0) * 100 if previous else None
    return latest, change_pct


def _fetch_yahoo_daily_change(symbol: str) -> tuple[float | None, float | None]:
    end = datetime.now().date()
    start = end - timedelta(days=10)
    period1 = int(datetime.combine(start, datetime.min.time()).timestamp())
    period2 = int(datetime.combine(end + timedelta(days=1), datetime.min.time()).timestamp())
    url = YAHOO_CHART_URL.format(symbol=symbol) + f"?period1={period1}&period2={period2}&interval=1d&includeAdjustedClose=true"
    raw = _get_json(url, YAHOO_HEADERS)
    result = raw.get("chart", {}).get("result", [])
    if not result:
        return None, None
    closes = [close for close in result[0].get("indicators", {}).get("quote", [{}])[0].get("close", []) if close is not None]
    if not closes:
        return None, None
    latest = float(closes[-1])
    if len(closes) < 2:
        return latest, None
    previous = float(closes[-2])
    change_pct = ((latest / previous) - 1.0) * 100 if previous else None
    return latest, change_pct


def _fetch_yahoo_change_set(symbol: str) -> tuple[float | None, float | None, float | None]:
    end = datetime.now().date()
    start = end - timedelta(days=380)
    period1 = int(datetime.combine(start, datetime.min.time()).timestamp())
    period2 = int(datetime.combine(end + timedelta(days=1), datetime.min.time()).timestamp())
    url = YAHOO_CHART_URL.format(symbol=symbol) + f"?period1={period1}&period2={period2}&interval=1d&includeAdjustedClose=true"
    raw = _get_json(url, YAHOO_HEADERS)
    result = raw.get("chart", {}).get("result", [])
    if not result:
        return None, None, None
    closes = [close for close in result[0].get("indicators", {}).get("quote", [{}])[0].get("close", []) if close is not None]
    if not closes:
        return None, None, None
    latest = float(closes[-1])
    daily = ((latest / closes[-2]) - 1.0) * 100 if len(closes) >= 2 and closes[-2] else None
    yearly = ((latest / closes[0]) - 1.0) * 100 if closes[0] else None
    return latest, daily, yearly


def _build_trend_snapshot(items: list[FeedItem]) -> dict[str, dict]:
    counts = {category: 0 for category in CATEGORY_LABELS}
    avg_scores = {category: [] for category in CATEGORY_LABELS}
    for item in items:
        for category in item.categories:
            if category in counts:
                counts[category] += 1
                avg_scores[category].append(item.score)
    snapshot = {}
    for category, count in counts.items():
        score_values = avg_scores[category]
        snapshot[category] = {
            "count": count,
            "avg_score": round(sum(score_values) / len(score_values), 1) if score_values else 0.0,
        }
    return snapshot


def _compare_trends(previous: dict, current: dict) -> list[str]:
    trend_lines: list[str] = []
    for category, current_stats in current.items():
        previous_stats = previous.get("trend_snapshot", {}).get(category, {})
        previous_count = int(previous_stats.get("count", 0))
        current_count = int(current_stats.get("count", 0))
        delta = current_count - previous_count
        if delta >= 2:
            trend_lines.append(f"{CATEGORY_LABELS[category]} ivmesi artıyor ({previous_count} -> {current_count}).")
        elif delta <= -2:
            trend_lines.append(f"{CATEGORY_LABELS[category]} akışı yavaşladı ({previous_count} -> {current_count}).")
    if not trend_lines:
        trend_lines.append("Belirgin kategori ivmesi yok; haber akışı dengeli.")
    return trend_lines


def _topic_scores(items: list[FeedItem]) -> dict[str, int]:
    scores = {topic: 0 for topic in TOPIC_ROUTER}
    for item in items:
        text = f"{item.title} {item.summary}".lower()
        for topic, config in TOPIC_ROUTER.items():
            for keyword in config["keywords"]:
                if keyword in text:
                    scores[topic] += item.score + 1
    return scores


def _build_topic_router(items: list[FeedItem]) -> list[dict]:
    scores = _topic_scores(items)
    ranked_topics = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    chosen_topics = [topic for topic, score in ranked_topics if score > 0][:4]
    if not chosen_topics:
        chosen_topics = ["nvidia", "geopolitics", "markets"]

    router = []
    for topic in chosen_topics:
        config = TOPIC_ROUTER[topic]
        router.append(
            {
                "topic": topic,
                "label": config["label"],
                "score": scores.get(topic, 0),
                "best_source": config["best_source"],
                "best_url": config["best_url"],
                "backup_source": config["backup_source"],
                "backup_url": config["backup_url"],
                "reason": config["reason"],
                "mode": config["mode"],
            }
        )
    return router


def _build_today_stack(router: list[dict]) -> list[dict]:
    picks = router[:3]
    if len(picks) < 3:
        fallback_topics = ["nvidia", "geopolitics", "markets"]
        existing = {item["topic"] for item in picks}
        for topic in fallback_topics:
            if topic in existing:
                continue
            config = TOPIC_ROUTER[topic]
            picks.append(
                {
                    "topic": topic,
                    "label": config["label"],
                    "score": 0,
                    "best_source": config["best_source"],
                    "best_url": config["best_url"],
                    "backup_source": config["backup_source"],
                    "backup_url": config["backup_url"],
                    "reason": config["reason"],
                    "mode": config["mode"],
                }
            )
            if len(picks) == 3:
                break
    return picks


def collect_news() -> dict:
    cutoff = _utc_now() - timedelta(hours=DEFAULT_NEWS_BOT_CONFIG.lookback_hours)
    collected: list[FeedItem] = []
    political_candidates: list[dict] = []
    errors: list[str] = []

    for feed in DEFAULT_NEWS_BOT_CONFIG.feeds:
        try:
            xml_payload = _fetch_feed_xml(feed.url)
            raw_items = _extract_items(feed.name, xml_payload)[: DEFAULT_NEWS_BOT_CONFIG.max_items_per_feed]
        except (HTTPError, URLError, TimeoutError, ElementTree.ParseError) as exc:
            errors.append(f"{feed.name}: {exc}")
            continue
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or str(exc)).strip()
            errors.append(f"{feed.name}: {details or exc}")
            continue

        for raw_item in raw_items:
            published_dt = _parse_datetime(raw_item["published_at"])
            if published_dt is not None and published_dt < cutoff:
                continue
            political_text = " ".join([raw_item["title"], raw_item["summary"]]).lower()
            normalized_summary = _normalize_summary(raw_item["summary"])
            if "macro" in feed.categories and any(
                token in political_text
                for token in (
                    "trump",
                    "china",
                    "tariff",
                    "white house",
                    "beijing",
                    "europe",
                    "nato",
                    "ukraine",
                    "iran",
                    "trade",
                    "sanction",
                    "congress",
                    "government",
                    "election",
                    "military",
                    "minister",
                    "president",
                )
            ):
                political_candidates.append(
                    {
                        "source": raw_item["source"],
                        "title": raw_item["title"],
                        "link": raw_item["link"],
                        "summary": normalized_summary,
                        "summary_tr": _build_turkish_summary(
                            raw_item["title"],
                            normalized_summary,
                            "macro",
                            [],
                            raw_item["source"],
                        ),
                        "published_at": raw_item["published_at"],
                    }
                )
            score, matched_keywords = _score_item(
                raw_item["title"],
                raw_item["summary"],
                feed.categories,
                raw_item["published_at"],
            )
            score += SOURCE_QUALITY_BONUS.get(feed.name, 0)
            if score <= 0:
                continue
            raw_item["summary"] = normalized_summary
            if not _passes_quality_filter(raw_item, score, matched_keywords):
                continue
            primary_category = _pick_primary_category(feed.categories, matched_keywords)
            category_set = sorted(set(feed.categories + (primary_category,)))
            collected.append(
                FeedItem(
                    source=raw_item["source"],
                    title=raw_item["title"],
                    link=raw_item["link"],
                    published_at=raw_item["published_at"],
                    summary=raw_item["summary"],
                    summary_tr=_build_turkish_summary(
                        raw_item["title"],
                        raw_item["summary"],
                        primary_category,
                        matched_keywords,
                        raw_item["source"],
                    ),
                    categories=category_set,
                    score=score,
                    why_it_matters=_build_why_it_matters(primary_category, matched_keywords),
                    matched_keywords=matched_keywords,
                )
            )

    ranked = sorted(_deduplicate(collected), key=lambda item: (-item.score, item.title))
    selected = ranked[: DEFAULT_NEWS_BOT_CONFIG.max_headlines]
    political_items = []
    seen_links: set[str] = set()
    for row in political_candidates:
        link = row.get("link") or ""
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        political_items.append(row)
    if not political_items:
        for item in ranked:
            text = " ".join([item.title, item.summary, item.summary_tr]).lower()
            if "macro" in item.categories or any(
                token in text
                for token in (
                    "trump",
                    "china",
                    "tariff",
                    "white house",
                    "beijing",
                    "europe",
                    "nato",
                    "ukraine",
                    "iran",
                    "trade",
                    "sanction",
                    "congress",
                    "government",
                    "election",
                    "military",
                    "minister",
                    "president",
                )
            ):
                political_items.append(asdict(item))
    previous_state = _load_previous_state(NEWS_STATE_JSON)
    if not political_items:
        political_items = previous_state.get("political_items", []) or []
    normalized_political_items = []
    for item in political_items[:4]:
        summary = _normalize_summary(item.get("summary", ""))
        normalized_political_items.append(
            {
                **item,
                "summary": summary,
                "summary_tr": item.get("summary_tr")
                or _build_turkish_summary(
                    item.get("title", ""),
                    summary,
                    "macro",
                    [],
                    item.get("source", ""),
                ),
            }
        )
    political_items = normalized_political_items
    trend_snapshot = _build_trend_snapshot(ranked)
    topic_router = _build_topic_router(ranked)
    today_stack = _build_today_stack(topic_router)
    market_items = _build_market_sidebar(previous_state)

    return {
        "generated_at": _utc_now().isoformat(),
        "headlines": [asdict(item) for item in selected],
        "political_items": political_items,
        "market_items": market_items,
        "trend_snapshot": trend_snapshot,
        "trend_signals": _compare_trends(previous_state, trend_snapshot),
        "topic_router": topic_router,
        "today_stack": today_stack,
        "errors": errors,
        "coverage_notes": {
            "objective": "Gerçekten önemli olanları seçmek ve günlük stratejik farkındalık yaratmak.",
            "categories": CATEGORY_LABELS,
        },
    }


def _render_markdown(report: dict) -> str:
    lines = [
        "# Dunya Gelismeleri Botu",
        "",
        f"Uretim zamani: {report['generated_at']}",
        "",
        "## Bugunun 5 Onemli Basligi",
        "",
    ]
    headlines = report.get("headlines", [])
    if not headlines:
        lines.extend(
            [
                "Bu calistirmada anlamli haber secilemedi.",
                "",
                "Muhtemel nedenler: feed erisim hatasi, eski haberler veya anahtar kelime filtresi.",
                "",
            ]
        )
    for index, item in enumerate(headlines, start=1):
        labels = ", ".join(CATEGORY_LABELS.get(category, category) for category in item["categories"])
        lines.extend(
            [
                f"### {index}. {item['title']}",
                f"- Kaynak: {item['source']}",
                f"- Kategoriler: {labels}",
                f"- Onem skoru: {item['score']}",
                f"- Link: {item['link']}",
                f"- Bu seni neden ilgilendiriyor: {item['why_it_matters']}",
                "",
            ]
        )
        if item.get("summary_tr"):
            lines.append(f"Turkce ozet: {item['summary_tr']}")
            lines.append("")
    lines.extend(["## Trend Sinyali", ""])
    for signal in report.get("trend_signals", []):
        lines.append(f"- {signal}")
    lines.extend(["", "## Topic Router", ""])
    for route in report.get("topic_router", []):
        lines.append(f"- {route['label']}: {route['best_source']} (yedek: {route['backup_source']})")
    if report.get("errors"):
        lines.extend(["", "## Feed Notlari", ""])
        for error in report["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def _render_headline_cards(report: dict) -> str:
    cards = []
    for index, item in enumerate(report.get("headlines", [])[1:7], start=1):
        labels = " | ".join(CATEGORY_LABELS.get(category, category) for category in item["categories"])
        image_url = [
            "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1526379095098-d400fd0bf935?auto=format&fit=crop&w=1200&q=80",
            "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&q=80",
        ][(index - 1) % 4]
        cards.append(
            """
            <article class="story-card">
              <div class="story-image" style="background-image:url('{image_url}');"></div>
              <div class="story-body">
                <div class="story-meta-row">
                  <span class="story-tag">{labels}</span>
                  <span class="story-score">Skor {score}</span>
                </div>
                <h3>{title}</h3>
                <p>{summary}</p>
                <div class="story-footer">
                  <span><strong>Kaynak:</strong> {source}</span>
                  <a href="{link}" target="_blank" rel="noreferrer">Haberi ac</a>
                </div>
              </div>
            </article>
            """.format(
                image_url=image_url,
                labels=_html_text(labels or "Genel"),
                score=item["score"],
                title=_html_text(item["title"]),
                summary=_html_text(item.get("summary_tr") or item["summary"] or "Ozet bulunamadi."),
                source=_html_text(item["source"]),
                link=html.escape(item["link"]),
            ).strip()
        )
    if cards:
        return "\n".join(cards)
    return """
    <article class="story-card empty-state">
      <div class="story-body">
        <div class="story-meta-row"><span class="story-tag">Feed durumu</span></div>
        <h3>Bugun yeterince guclu haber secilemedi</h3>
        <p>Kaynak erisimi dustugunde ya da filtre cok sert kaldiginda briefing bu alani bos gecmek yerine bunu acikca soyler.</p>
      </div>
    </article>
    """.strip()


def _render_today_stack(report: dict) -> str:
    items = []
    for index, route in enumerate(report.get("today_stack", [])[:4], start=1):
        items.append(
            "<li><strong>{index}.</strong> <span>{label}</span><small>{source}</small></li>".format(
                index=index,
                label=_html_text(route["label"]),
                source=_html_text(route["best_source"]),
            )
        )
    if items:
        return "\n".join(items)
    return "<li><strong>1.</strong> <span>Bugun rota olusmadi</span><small>Kaynak bekleniyor</small></li>"


def _render_more_reads(report: dict) -> str:
    cards = []
    for route in report.get("today_stack", [])[:4]:
        cards.append(
            """
            <article class="more-card">
              <small>{label}</small>
              <h3>{source}</h3>
              <p>{reason}</p>
              <a href="{url}" target="_blank" rel="noreferrer">Kaynaga git</a>
            </article>
            """.format(
                label=_html_text(route["label"]),
                source=_html_text(route["best_source"]),
                reason=_html_text(route["reason"]),
                url=html.escape(route["best_url"]),
            ).strip()
        )
    return "\n".join(cards)


def _render_error_list(report: dict) -> str:
    if not report.get("errors"):
        return "<li>Kaynak hatasi gorunmuyor.</li>"
    return "\n".join("<li>{}</li>".format(_html_text(error)) for error in report["errors"][:4])


def _build_portfolio_performance() -> dict:
    analysis = _load_invest_analysis()
    if not analysis:
        return {"tracked_return_value": None, "tracked_return_pct": None, "daily_return_pct": None, "daily_return_label": "Gunluk veri yok"}

    instruments = analysis.get("transaction_analysis", {}).get("instruments", [])
    buy_amount = 0.0
    current_value = 0.0
    for item in instruments:
        buy_amount += float(item.get("buy_amount") or 0.0)
        current_value += float(item.get("current_value") or 0.0)
    tracked_return_value = current_value - buy_amount if buy_amount or current_value else None
    tracked_return_pct = ((current_value / buy_amount) - 1.0) * 100 if buy_amount else None

    daily_return_pct = None
    for history_path in INVEST_HISTORY_CANDIDATES:
        if not history_path.exists():
            continue
        try:
            import csv
            from collections import defaultdict
            rows_by_date = defaultdict(float)
            with history_path.open("r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    date = row.get("date")
                    close = row.get("close")
                    if not date or not close:
                        continue
                    rows_by_date[date] += float(close)
            dates = sorted(rows_by_date)
            if len(dates) >= 2:
                latest = rows_by_date[dates[-1]]
                previous = rows_by_date[dates[-2]]
                if previous:
                    daily_return_pct = ((latest / previous) - 1.0) * 100
                    break
        except Exception:
            daily_return_pct = None

    return {
        "tracked_return_value": tracked_return_value,
        "tracked_return_pct": tracked_return_pct,
        "daily_return_pct": daily_return_pct,
        "daily_return_label": "Portfoy bazinda" if daily_return_pct is not None else "Gunluk veri yok",
    }


def _render_performance_summary() -> str:
    perf = _build_portfolio_performance()

    def fmt_pct(value: float | None) -> str:
        return f"%{value:.2f}" if value is not None else "-"

    def fmt_tl(value: float | None) -> str:
        if value is None:
            return "-"
        return f"{value:,.0f} TL".replace(",", ".")

    cards = [
        {"label": "Maliyeti bilinen fonlar", "value": fmt_pct(perf["tracked_return_pct"]), "note": fmt_tl(perf["tracked_return_value"])} ,
        {"label": "Gunluk getiri", "value": fmt_pct(perf["daily_return_pct"]), "note": perf["daily_return_label"]},
    ]
    return "\n".join(
        """
        <div class="perf-card">
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{note}</small>
        </div>
        """.format(label=_html_text(card["label"]), value=_html_text(card["value"]), note=_html_text(card["note"])).strip()
        for card in cards
    )


def _render_market_sidebar(report: dict) -> str:
    items = report.get("market_items") or _build_market_sidebar(_load_previous_state(NEWS_STATE_JSON))
    if not items:
        return '<div class="market-empty">Invest verisi bulunamadi.</div>'
    blocks = []
    for item in items[:7]:
        blocks.append(
            """
            <article class="market-card">
              <div class="market-top">
                <strong>{label}</strong>
                <span>{value}</span>
              </div>
              <div class="market-metrics">
                <span><small>Gunluk</small><strong>{daily}</strong></span>
                <span><small>Maliyet</small><strong>{cost}</strong></span>
                <span><small>1Y</small><strong>{year}</strong></span>
              </div>
              <div class="market-note">{note}</div>
            </article>
            """.format(
                label=_html_text(item["label"]),
                value=_html_text(item["value"]),
                daily=_html_text(item["daily_change"]),
                cost=_html_text(item["cost_change"]),
                year=_html_text(item["year_change"]),
                note=_html_text(item["note"]),
            ).strip()
        )
    return "\n".join(blocks)


def _render_political_brief(report: dict) -> str:
    items = []
    for item in report.get("political_items", []):
        source = item.get("source", "")
        title = item.get("title", "")
        summary = item.get("summary_tr") or item.get("summary") or "Kisa ozet bulunamadi."
        published_at = item.get("published_at") or ""
        items.append(
            """
            <li>
              <div class="politics-copy">
                <strong>{title}</strong>
                <p>{summary}</p>
              </div>
              <span>{source} {published_at}</span>
            </li>
            """.format(
                title=_html_text(title),
                summary=_html_text(summary),
                source=_html_text(source),
                published_at=_html_text(published_at),
            ).strip()
        )
        if len(items) == 3:
            break
    if items:
        return "\n".join(items)
    return """
    <li>
      <div class="politics-copy">
        <strong>Bugun guclu siyasi baslik cikmadi</strong>
        <p>Feed akisi zayif kaldiginda bu alan link listesine dusmek yerine bos oldugunu acikca soyler.</p>
      </div>
      <span>Radar beklemede</span>
    </li>
    """.strip()


def _build_market_sidebar(previous_state: dict | None = None) -> list[dict]:
    analysis = _load_invest_analysis()
    if not analysis:
        return []

    items: list[dict] = []
    previous_market = _market_state_lookup(previous_state)
    market = analysis.get("market_snapshot", {})
    holdings = analysis.get("portfolio_mix", {}).get("holdings", [])
    pnl_items = analysis.get("transaction_analysis", {}).get("instruments", [])
    holdings_by_code = {str(row.get("instrument_code") or "").upper(): row for row in holdings if row.get("instrument_code")}
    holdings_by_name = {str(row.get("instrument_name") or "").upper(): row for row in holdings}
    pnl_by_code = {}
    for row in pnl_items:
        name = str(row.get("instrument_name") or "").upper()
        if name.startswith("GTA"):
            pnl_by_code["GTA"] = row
        elif name.startswith("GTL"):
            pnl_by_code["GTL"] = row
        elif name.startswith("GTM"):
            pnl_by_code["GTM"] = row
        elif name.startswith("GTZ"):
            pnl_by_code["GTZ"] = row
        elif name.startswith("GVI"):
            pnl_by_code["GVI"] = row
        elif name.startswith("GARAN"):
            pnl_by_code["GARAN"] = row

    def _fmt_pct(value: float | None) -> str:
        return f"%{value:.2f}" if value is not None else "-"

    usd_try = market.get("usd_try")
    if usd_try is not None:
        trend_map = {"up": "Yukari", "down": "Asagi", "flat": "Yatay", "unknown": "Belirsiz", "data_unavailable": "Veri yok"}
        usd_daily = None
        usd_yearly = None
        try:
            _, usd_daily, usd_yearly = _fetch_yahoo_change_set("TRY=X")
        except Exception:
            usd_daily, usd_yearly = None, None
        items.append({
            "label": "USD/TRY",
            "value": f"{usd_try:.2f}",
            "daily_change": _fmt_pct(usd_daily) if usd_daily is not None else trend_map.get(str(market.get("usd_try_trend", "unknown")), "Bilgi yok"),
            "cost_change": "-",
            "year_change": _fmt_pct(usd_yearly),
            "note": "Kur yonu",
            "raw_value": float(usd_try),
        })

    fund_specs = [("GTA", "Altin Fonu", 4), ("GTZ", "Gumus Fonu", 4), ("GTL", "Para Piyasasi", 6), ("GVI", "Fon Sepeti", 4), ("GTM", "Temettu", 4)]
    for code, label, precision in fund_specs:
        holding = holdings_by_code.get(code)
        pnl_row = pnl_by_code.get(code)
        previous_item = previous_market.get(label, {})
        price = change = None
        try:
            price, change = _fetch_tefas_daily_change(code)
        except Exception:
            price, change = None, None
        if price is not None:
            value = f"{price:.{precision}f}"
            note = "TEFAS gunluk"
            daily_change = _fmt_pct(change)
            raw_value = float(price)
        elif holding:
            current_price = float(pnl_row.get("current_price")) if pnl_row and pnl_row.get("current_price") not in (None, "") else None
            amount = holding.get("amount")
            if current_price is not None:
                value = f"{current_price:.{precision}f}"
                note = "Invest guncel fiyat"
                raw_value = current_price
            else:
                value = f"{amount:,.0f} TL".replace(",", ".") if isinstance(amount, (int, float)) else "Portfoyde"
                note = "Invest portfoy degeri"
                raw_value = float(amount) if isinstance(amount, (int, float)) else None
            daily_from_history = _history_daily_change_by_code(code)
            previous_value = previous_item.get("raw_value")
            previous_value = float(previous_value) if isinstance(previous_value, (int, float)) else None
            if daily_from_history is not None:
                daily_change = _fmt_pct(daily_from_history)
            elif current_price is not None and previous_value:
                daily_change = _fmt_pct(((current_price / previous_value) - 1.0) * 100)
            else:
                daily_change = "-"
        else:
            continue
        annual = holding.get("one_year_return_pct") if holding else None
        profit_loss = float(pnl_row.get("profit_loss") or 0.0) if pnl_row else None
        buy_amount = float(pnl_row.get("buy_amount") or 0.0) if pnl_row else None
        cost_change = ((profit_loss / buy_amount) * 100) if pnl_row and buy_amount else None
        items.append({
            "label": label,
            "value": value,
            "daily_change": daily_change,
            "cost_change": _fmt_pct(cost_change),
            "year_change": _fmt_pct(float(annual)) if isinstance(annual, (int, float)) else "-",
            "note": note,
            "raw_value": raw_value,
        })

    garan_holding = holdings_by_name.get("GARAN")
    try:
        garan_price, garan_change, garan_yearly = _fetch_yahoo_change_set("GARAN.IS")
    except Exception:
        garan_price, garan_change, garan_yearly = None, None, None
    if garan_price is not None:
        pnl_row = pnl_by_code.get("GARAN")
        profit_loss = float(pnl_row.get("profit_loss") or 0.0) if pnl_row else None
        buy_amount = float(pnl_row.get("buy_amount") or 0.0) if pnl_row else None
        cost_change = ((profit_loss / buy_amount) * 100) if pnl_row and buy_amount else None
        items.append({
            "label": "GARAN",
            "value": f"{garan_price:.2f}",
            "daily_change": _fmt_pct(garan_change),
            "cost_change": _fmt_pct(cost_change),
            "year_change": _fmt_pct(garan_yearly),
            "note": "Yahoo gunluk",
            "raw_value": float(garan_price),
        })
    elif garan_holding:
        previous_item = previous_market.get("GARAN", {})
        previous_value = previous_item.get("raw_value")
        previous_value = float(previous_value) if isinstance(previous_value, (int, float)) else None
        raw_value = float(garan_holding.get("amount", 0)) if isinstance(garan_holding.get("amount", 0), (int, float)) else None
        items.append({
            "label": "GARAN",
            "value": f"{garan_holding.get('amount', 0):,.0f} TL".replace(",", "."),
            "daily_change": _fmt_pct(((raw_value / previous_value) - 1.0) * 100) if raw_value and previous_value else "-",
            "cost_change": "-",
            "year_change": "-",
            "note": "Invest holding degeri",
            "raw_value": raw_value,
        })

    return items[:7]


def _render_html(report: dict) -> str:
    generated_at = _html_text(report["generated_at"])
    lead = report["headlines"][0] if report.get("headlines") else None
    lead_title = _html_text(lead["title"]) if lead else "Bugunun guclu sinyalleri burada toplaniyor."
    lead_summary = _html_text(lead.get("summary_tr") or lead.get("summary") or "Filtrelenmis kuresel gelismeler daha editoriyal bir akis icinde sunulur.") if lead else "Filtrelenmis kuresel gelismeler daha editoriyal bir akis icinde sunulur."
    lead_source = _html_text(lead["source"]) if lead else "AI News"
    lead_link = html.escape(lead["link"]) if lead else "#"
    lead_reason = _html_text(lead.get("why_it_matters") or "Sermaye, teknoloji ve devlet hamlelerinin nereye kaydigini daha hizli gormek icin.") if lead else "Sermaye, teknoloji ve devlet hamlelerinin nereye kaydigini daha hizli gormek icin."
    lead_image = "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1600&q=80"
    return """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI News Briefing</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{ --paper:#faf8f3; --panel:#ffffff; --ink:#161616; --muted:#726c64; --line:#e8e0d5; --accent:#c65435; --soft:#f6eee7; --shadow:0 14px 30px rgba(0,0,0,.05); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#ffffff; color:var(--ink); font-family:"Inter",sans-serif; }}
    a {{ color:inherit; text-decoration:none; }}
    .page {{ width:min(1380px, calc(100vw - 36px)); margin:0 auto; padding:18px 0 56px; }}
    .masthead {{ display:flex; justify-content:space-between; align-items:end; gap:16px; border-bottom:1px solid var(--line); padding-bottom:16px; }}
    .brand {{ font-family:"Instrument Serif",serif; font-size:clamp(2.6rem,5vw,4.6rem); letter-spacing:-.05em; }}
    .mast-copy {{ color:var(--muted); max-width:44ch; text-align:right; line-height:1.55; }}
    .editorial-grid {{ display:grid; grid-template-columns:minmax(0,1.68fr) minmax(290px,.72fr); gap:22px; padding-top:22px; align-items:start; }}
    .lead-shell {{ display:grid; gap:22px; }}
    .lead-story {{ display:grid; grid-template-columns:minmax(0,1.1fr) minmax(260px,.9fr); background:var(--panel); border:1px solid var(--line); border-radius:26px; overflow:hidden; box-shadow:var(--shadow); }}
    .lead-copy {{ padding:30px; }}
    .lead-photo {{ min-height:440px; background:linear-gradient(180deg,rgba(15,15,15,.08),rgba(15,15,15,.22)), url('{lead_image}') center/cover; }}
    .kicker {{ display:inline-flex; padding:8px 12px; border-radius:999px; background:var(--soft); color:var(--accent); font-size:.78rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; }}
    .lead-story h1 {{ margin:16px 0 16px; font-family:"Instrument Serif",serif; font-size:clamp(3rem,5vw,5.4rem); line-height:.95; letter-spacing:-.06em; max-width:10ch; }}
    .lead-summary {{ color:#302c28; font-size:1.08rem; line-height:1.8; max-width:56ch; }}
    .lead-meta {{ display:grid; gap:14px; margin-top:18px; padding-top:18px; border-top:1px solid var(--line); color:var(--muted); }}
    .lead-meta strong {{ color:var(--ink); }}
    .actions {{ margin-top:18px; display:flex; gap:12px; flex-wrap:wrap; }}
    .btn {{ display:inline-flex; align-items:center; justify-content:center; padding:12px 16px; border-radius:999px; font-weight:700; border:1px solid var(--line); }}
    .btn.primary {{ background:var(--ink); color:#fff; border-color:var(--ink); }}
    .btn.secondary {{ background:var(--soft); color:var(--accent); border-color:#edd9ce; }}
    .subgrid {{ display:grid; grid-template-columns:1fr; gap:18px; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:22px; padding:22px; box-shadow:var(--shadow); }}
    .panel h2 {{ margin:0 0 10px; font-family:"Instrument Serif",serif; font-size:2rem; letter-spacing:-.04em; }}
    .panel p.intro {{ margin:0 0 16px; color:var(--muted); line-height:1.65; }}
    .today-list, .politics-list, .error-list {{ list-style:none; padding:0; margin:0; display:grid; gap:12px; }}
    .today-list li, .politics-list li, .error-list li {{ padding-bottom:12px; border-bottom:1px solid #f1ebe3; }}
    .today-list li:last-child, .politics-list li:last-child, .error-list li:last-child {{ border-bottom:0; padding-bottom:0; }}
    .today-list li {{ display:grid; grid-template-columns:auto 1fr; gap:8px 12px; }}
    .today-list span {{ font-weight:700; }}
    .today-list small, .politics-list span {{ color:var(--muted); }}
    .politics-copy {{ display:grid; gap:6px; }}
    .politics-copy strong {{ font-family:"Instrument Serif",serif; font-size:1.1rem; line-height:1.15; letter-spacing:-.02em; }}
    .politics-copy p {{ margin:0; color:#39342f; line-height:1.65; }}
    .section-head {{ display:flex; justify-content:space-between; align-items:end; gap:12px; margin:4px 0 14px; }}
    .section-head h2 {{ margin:0; font-family:"Instrument Serif",serif; font-size:2.1rem; letter-spacing:-.04em; }}
    .section-head p {{ margin:0; color:var(--muted); max-width:38ch; }}
    .story-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }}
    .more-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin-top:18px; }}
    .more-card {{ background:#fff; border:1px solid var(--line); border-radius:18px; padding:16px; display:grid; gap:10px; }}
    .more-card small {{ color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-weight:800; }}
    .more-card h3 {{ margin:0; font-family:"Instrument Serif",serif; font-size:1.3rem; letter-spacing:-.03em; }}
    .more-card p {{ margin:0; color:#5e5850; line-height:1.55; font-size:.95rem; }}
    .more-card a {{ color:var(--accent); font-weight:700; }}
    .story-card {{ background:var(--panel); border:1px solid var(--line); border-radius:22px; overflow:hidden; box-shadow:var(--shadow); }}
    .story-image {{ height:170px; background-size:cover; background-position:center; }}
    .story-body {{ padding:18px; display:grid; gap:12px; }}
    .story-meta-row, .story-footer, .rail-head {{ display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; }}
    .story-tag, .story-score, .rail-tag {{ font-size:.74rem; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); font-weight:800; }}
    .story-card h3 {{ margin:0; font-family:"Instrument Serif",serif; font-size:1.65rem; line-height:1.04; letter-spacing:-.04em; }}
    .story-card p {{ margin:0; color:#39342f; line-height:1.72; }}
    .story-footer {{ padding-top:10px; border-top:1px solid #f1ebe3; color:var(--muted); font-size:.92rem; }}
    .story-footer a {{ color:var(--accent); font-weight:700; }}
    .right-rail {{ display:grid; gap:16px; }}
    .perf-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }}
    .perf-card {{ background:#fffaf6; border:1px solid #efe4d8; border-radius:18px; padding:14px; display:grid; gap:6px; }}
    .perf-card span {{ font-size:.76rem; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); font-weight:800; }}
    .perf-card strong {{ font-size:1.55rem; letter-spacing:-.04em; }}
    .perf-card small {{ color:var(--muted); }}
    .market-stack {{ display:grid; gap:8px; }}
    .market-card {{ padding:12px 0; border-top:1px solid #f1ebe3; }}
    .market-card:first-child {{ border-top:0; padding-top:0; }}
    .market-top {{ display:flex; justify-content:space-between; gap:10px; color:var(--muted); font-size:.88rem; }}
    .market-value {{ margin-top:5px; font-size:1.25rem; font-weight:800; letter-spacing:-.03em; }}
    .market-metrics {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; margin-top:10px; }}
    .market-metrics span {{ display:grid; gap:2px; padding:8px 10px; border-radius:12px; background:#fbf7f2; }}
    .market-metrics small {{ color:var(--muted); font-size:.68rem; text-transform:uppercase; letter-spacing:.08em; }}
    .market-metrics strong {{ font-size:.92rem; letter-spacing:-.02em; }}
    .market-note {{ margin-top:8px; font-size:.9rem; color:var(--muted); }}
    .rail-photo {{ height:160px; border-radius:18px; background:linear-gradient(180deg,rgba(16,16,16,.1),rgba(16,16,16,.25)), url('https://images.unsplash.com/photo-1496096265110-f83ad7f96608?auto=format&fit=crop&w=1000&q=80') center/cover; margin-top:12px; }}
    .footer-note {{ margin-top:26px; color:var(--muted); font-size:.92rem; border-top:1px solid var(--line); padding-top:16px; }}
    @media (max-width:1100px) {{ .editorial-grid,.lead-story,.subgrid,.story-grid,.perf-grid,.more-grid {{ grid-template-columns:1fr; }} .lead-photo {{ min-height:300px; order:-1; }} }}
  </style>
</head>
<body>
  <div class="page">
    <header class="masthead">
      <div class="brand">AI News Briefing</div>
      <div class="mast-copy">Dunyada gercekten onemli olani gurultuden ayiran daha editoriyal bir sabah sayfasi. Nvidia, robotik, odeme raylari ve jeopolitik ayni duzlemde.</div>
    </header>
    <main class="editorial-grid">
      <section class="lead-shell">
        <article class="lead-story">
          <div class="lead-copy">
            <div class="kicker">Generation AI</div>
            <h1>{lead_title}</h1>
            <p class="lead-summary">{lead_summary}</p>
            <div class="actions">
              <a class="btn primary" href="{lead_link}" target="_blank" rel="noreferrer">Lead haberi ac</a>
              <a class="btn secondary" href="https://www.reuters.com/world/" target="_blank" rel="noreferrer">Reuters World</a>
            </div>
            <div class="lead-meta">
              <div><strong>Kaynak:</strong> {lead_source}</div>
              <div><strong>Neden onemli:</strong> {lead_reason}</div>
              <div><strong>Guncellendi:</strong> {generated_at}</div>
            </div>
          </div>
          <div class="lead-photo"></div>
        </article>
        <section class="subgrid">
          <article class="panel">
            <h2>Siyasi radar</h2>
            <p class="intro">Dunya siyaseti ve jeopolitik tarafta bugunun one cikan basliklari.</p>
            <ul class="politics-list">{political_brief}</ul>
          </article>
        </section>
        <section>
          <div class="section-head">
            <h2>Secilmis haberler</h2>
            <p>Quartz hissine daha yakin, daha gorsel ve paylasilabilir kartlar.</p>
          </div>
          <div class="story-grid">{headline_cards}</div>
          <div class="more-grid">{more_reads}</div>
        </section>
      </section>
      <aside class="right-rail">
        <article class="panel">
          <div class="rail-head"><span class="rail-tag">Invest ozeti</span></div>
          <h2>Portfoy gorunumu</h2>
          <div class="perf-grid">{performance_summary}</div>
          <div class="rail-photo"></div>
        </article>
        <article class="panel">
          <div class="rail-head"><span class="rail-tag">Piyasa panosu</span></div>
          <h2>Fonlar ve ana izleme listesi</h2>
          <div class="market-stack">{market_sidebar}</div>
        </article>
      </aside>
    </main>
    <footer class="footer-note">Bu sayfa AI News motoru tarafindan otomatik uretilir. Politik tarama mumkun oldugunca Reuters merkezli kalir.</footer>
  </div>
</body>
</html>
""".format(
        lead_image=lead_image,
        lead_title=lead_title,
        lead_summary=lead_summary,
        lead_link=lead_link,
        lead_source=lead_source,
        lead_reason=lead_reason,
        generated_at=generated_at,
        today_stack=_render_today_stack(report),
        political_brief=_render_political_brief(report),
        headline_cards=_render_headline_cards(report),
        more_reads=_render_more_reads(report),
        performance_summary=_render_performance_summary(),
        market_sidebar=_render_market_sidebar(report),
        error_list=_render_error_list(report),
    )


def write_news_outputs(report: dict, output_dir: Path = OUTPUT_DIR) -> dict[str, Path]:
    def _safe_write(path: Path, content: str) -> None:
        try:
            path.write_text(content, encoding="utf-8")
        except PermissionError:
            return

    output_dir.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "world_developments_report.md"
    json_path = output_dir / "world_developments_payload.json"
    html_path = output_dir / "world_developments_dashboard.html"
    docs_html_path = DOCS_DIR / "index.html"
    docs_json_path = DOCS_DIR / "world_developments_payload.json"
    docs_markdown_path = DOCS_DIR / "world_developments_report.md"
    html_content = _render_html(report)
    json_content = json.dumps(report, ensure_ascii=False, indent=2)
    markdown_content = _render_markdown(report)
    _safe_write(markdown_path, markdown_content)
    _safe_write(json_path, json_content)
    _safe_write(html_path, html_content)
    _safe_write(docs_html_path, html_content)
    _safe_write(docs_json_path, json_content)
    _safe_write(docs_markdown_path, markdown_content)
    _safe_write(NEWS_STATE_JSON, json_content)
    return {
        "markdown": markdown_path,
        "json": json_path,
        "html": html_path,
        "docs_html": docs_html_path,
        "state": NEWS_STATE_JSON,
    }


def run() -> dict:
    report = collect_news()
    output_paths = write_news_outputs(report)
    return {"report": report, "output_paths": output_paths}


if __name__ == "__main__":
    result = run()
    print(f"Markdown report: {result['output_paths']['markdown']}")
    print(f"JSON payload: {result['output_paths']['json']}")
    print(f"HTML dashboard: {result['output_paths']['html']}")
    print(f"Docs dashboard: {result['output_paths']['docs_html']}")






