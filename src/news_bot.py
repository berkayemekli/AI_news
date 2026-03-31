from __future__ import annotations

import json
import html
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

from config import DEFAULT_NEWS_BOT_CONFIG, NEWS_STATE_JSON, OUTPUT_DIR

INVEST_ANALYSIS_JSON = Path(r"C:\AI\Invest\output\analysis_payload.json")
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
    "macro": "Makro rejim değişimleri kur, faiz, emtia ve risk iştahını birlikte etkiler.",
    "technology": "YZ altyapı yarışı sermaye akışını, çip talebini ve platform kazananlarını belirler.",
    "robotics": "Robotik gerçek dünyaya indiğinde verimlilik, üretim yapısı ve iş gücü dengesi değişir.",
    "financial_system": "Ödeme ve finans altyapısındaki değişim yeni kazananları ve işlem akışını yeniden kurar.",
}

SOURCE_QUALITY_BONUS = {
    "Reuters World": 5,
    "Reuters Business": 5,
    "Reuters Technology": 5,
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
        return "Bu haber, insans? robotlar?n depo ve lojistik taraf?nda ger?ek saha kullan?m?na ge?ti?ini g?steriyor."
    if {"visa", "mastercard", "stablecoin"} & keyword_set:
        return "Bu haber, ?deme a?lar? ve stablecoin taraf?nda rekabetin sertle?ti?ini ve finans altyap?s?nda yeni g?? dengeleri olu?tu?unu g?steriyor."
    if "nvidia" in keyword_set or "gpu" in keyword_set or "semiconductor" in keyword_set:
        return "Bu haber, Nvidia ve yapay zeka ?ipleri taraf?nda altyap? yar???n?n h?z kesmeden devam etti?ini g?steriyor."
    if "openai" in keyword_set or "anthropic" in keyword_set or "model" in keyword_set or primary_category == "technology":
        return "Bu haber, yapay zeka modeli ve altyap? yar???nda yeni ?r?n, yat?r?m veya platform hamlelerinin s?rd???n? g?steriyor."
    if "robot" in keyword_set or "robotics" in keyword_set or primary_category == "robotics":
        return "Bu haber, robotik uygulamalar?n laboratuvar a?amas?ndan ??k?p ger?ek operasyonlara daha fazla girdi?ini g?steriyor."
    if "china" in keyword_set or "tariff" in keyword_set or "sanction" in keyword_set or primary_category == "macro":
        return "Bu haber, makro ve jeopolitik tarafta piyasalar? etkileyebilecek yeni bir k?r?lmaya i?aret ediyor."
    if primary_category == "financial_system":
        return "Bu haber, ?deme ve finans altyap?s?nda oyuncular aras?ndaki rekabetin yeniden ?ekillendi?ini g?steriyor."
    cleaned = _normalize_summary(summary)
    if cleaned:
        return f"{source} haberine g?re: {cleaned}"
    return "Bu haber, g?n?n stratejik ak???nda izlenmeye de?er bir geli?meye i?aret ediyor."


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
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_invest_analysis() -> dict:
    if not INVEST_ANALYSIS_JSON.exists():
        return {}
    try:
        return json.loads(INVEST_ANALYSIS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _post_form(url: str, data: dict[str, str], headers: dict[str, str]) -> dict:
    encoded = urlencode(data).encode("utf-8")
    request = Request(url, data=encoded, headers=headers, method="POST")
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str, headers: dict[str, str]) -> dict:
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


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


def _build_market_sidebar() -> list[dict]:
    analysis = _load_invest_analysis()
    if not analysis:
        return []

    items: list[dict] = []
    market = analysis.get("market_snapshot", {})
    usd_try = market.get("usd_try")
    if usd_try is not None:
        items.append(
            {
                "label": "USD/TRY",
                "value": f"{usd_try:.2f}",
                "change": _fix_mojibake(market.get("usd_try_trend", "bilgi yok")),
                "note": "Güncel kur yönü",
            }
        )

    try:
        gta_price, gta_change = _fetch_tefas_daily_change("GTA")
    except Exception:
        gta_price, gta_change = None, None
    if gta_price is not None:
        items.append(
            {
                "label": "Altın Fonu",
                "value": f"{gta_price:.4f}",
                "change": f"%{gta_change:.2f}" if gta_change is not None else "günlük yok",
                "note": "TEFAS günlük değişim",
            }
        )

    try:
        gtz_price, gtz_change = _fetch_tefas_daily_change("GTZ")
    except Exception:
        gtz_price, gtz_change = None, None
    if gtz_price is not None:
        items.append(
            {
                "label": "Gümüş Fonu",
                "value": f"{gtz_price:.4f}",
                "change": f"%{gtz_change:.2f}" if gtz_change is not None else "günlük yok",
                "note": "TEFAS günlük değişim",
            }
        )

    try:
        gtl_price, gtl_change = _fetch_tefas_daily_change("GTL")
    except Exception:
        gtl_price, gtl_change = None, None
    if gtl_price is not None:
        items.append(
            {
                "label": "GTL Para Piyasası",
                "value": f"{gtl_price:.6f}",
                "change": f"%{gtl_change:.2f}" if gtl_change is not None else "günlük yok",
                "note": "TEFAS günlük değişim",
            }
        )

    try:
        gvi_price, gvi_change = _fetch_tefas_daily_change("GVI")
    except Exception:
        gvi_price, gvi_change = None, None
    if gvi_price is not None:
        items.append(
            {
                "label": "GVI Fon Sepeti",
                "value": f"{gvi_price:.4f}",
                "change": f"%{gvi_change:.2f}" if gvi_change is not None else "günlük yok",
                "note": "TEFAS günlük değişim",
            }
        )

    try:
        gtm_price, gtm_change = _fetch_tefas_daily_change("GTM")
    except Exception:
        gtm_price, gtm_change = None, None
    if gtm_price is not None:
        items.append(
            {
                "label": "GTM Temettü",
                "value": f"{gtm_price:.4f}",
                "change": f"%{gtm_change:.2f}" if gtm_change is not None else "günlük yok",
                "note": "TEFAS günlük değişim",
            }
        )

    try:
        garan_price, garan_change = _fetch_yahoo_daily_change("GARAN.IS")
    except Exception:
        garan_price, garan_change = None, None
    if garan_price is not None:
        items.append(
            {
                "label": "GARAN",
                "value": f"{garan_price:.2f}",
                "change": f"%{garan_change:.2f}" if garan_change is not None else "günlük yok",
                "note": "Yahoo günlük değişim",
            }
        )

    return items[:7]


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
            score, matched_keywords = _score_item(
                raw_item["title"],
                raw_item["summary"],
                feed.categories,
                raw_item["published_at"],
            )
            score += SOURCE_QUALITY_BONUS.get(feed.name, 0)
            if score <= 0:
                continue
            raw_item["summary"] = _normalize_summary(raw_item["summary"])
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
    previous_state = _load_previous_state(NEWS_STATE_JSON)
    trend_snapshot = _build_trend_snapshot(ranked)
    topic_router = _build_topic_router(ranked)
    today_stack = _build_today_stack(topic_router)

    return {
        "generated_at": _utc_now().isoformat(),
        "headlines": [asdict(item) for item in selected],
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
            lines.append(f"T?rk?e ?zet: {item['summary_tr']}")
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
    for item in report.get("headlines", []):
        labels = ", ".join(CATEGORY_LABELS.get(category, category) for category in item["categories"])
        cards.append(
            """
            <article class="headline-card">
              <div class="headline-top">
                <span class="pill">{labels}</span>
                <span class="score">Puan {score}</span>
              </div>
              <h3>{title}</h3>
              <p>{summary_tr}</p>
              <div class="meta"><strong>Kaynak:</strong> {source}</div>
              <div class="meta"><strong>Neden önemli:</strong> {why}</div>
              <a class="btn primary" href="{link}" target="_blank" rel="noreferrer">Habere Git</a>
            </article>
            """.format(
                labels=html.escape(_fix_mojibake(labels)),
                score=item["score"],
                title=html.escape(_fix_mojibake(item["title"])),
                summary_tr=html.escape(_fix_mojibake(item.get("summary_tr") or item["summary"] or "Özet bulunamadı.")),
                source=html.escape(_fix_mojibake(item["source"])),
                why=html.escape(_fix_mojibake(item["why_it_matters"])),
                link=html.escape(item["link"]),
            ).strip()
        )
    if cards:
        return "\n".join(cards)
    return """
    <article class="headline-card empty">
      <div class="headline-top">
        <span class="pill">Feed Durumu</span>
      </div>
      <h3>Bugün anlamlı başlık seçilemedi</h3>
      <p>Muhtemel nedenler: kaynak erişim hatası, DNS/TLS sorunu veya seçici filtrelerden geçen haber olmaması.</p>
    </article>
    """.strip()


def _render_router_cards(report: dict) -> str:
    cards = []
    for route in report.get("topic_router", []):
        cards.append(
            """
            <article class="route-card">
              <div class="route-top">
                <span class="pill">{label}</span>
                <span class="route-score">Trend {score}</span>
              </div>
              <h3>{source}</h3>
              <p>{reason}</p>
              <div class="meta"><strong>Yedek kaynak:</strong> {backup}</div>
              <div class="meta"><strong>Kullanım:</strong> {mode}</div>
              <div class="actions">
                <a class="btn primary" href="{url}" target="_blank" rel="noreferrer">En İyi Kaynak</a>
                <a class="btn secondary" href="{backup_url}" target="_blank" rel="noreferrer">Yedek Kaynak</a>
              </div>
            </article>
            """.format(
                label=html.escape(_fix_mojibake(route["label"])),
                score=route["score"],
                source=html.escape(_fix_mojibake(route["best_source"])),
                reason=html.escape(_fix_mojibake(route["reason"])),
                backup=html.escape(_fix_mojibake(route["backup_source"])),
                mode=html.escape(_fix_mojibake(route["mode"])),
                url=html.escape(route["best_url"]),
                backup_url=html.escape(route["backup_url"]),
            ).strip()
        )
    return "\n".join(cards)


def _render_today_stack(report: dict) -> str:
    items = []
    for index, route in enumerate(report.get("today_stack", []), start=1):
        items.append(
            "<li><strong>{index}. {source}:</strong> {label} konusu için bugünün en iyi ilk durağı.</li>".format(
                index=index,
                source=html.escape(_fix_mojibake(route["best_source"])),
                label=html.escape(_fix_mojibake(route["label"])),
            )
        )
    return "\n".join(items)


def _render_error_list(report: dict) -> str:
    if not report.get("errors"):
        return "<li>Kaynak hatası görünmüyor.</li>"
    return "\n".join("<li>{}</li>".format(html.escape(_fix_mojibake(error))) for error in report["errors"])


def _render_market_sidebar() -> str:
    items = _build_market_sidebar()
    if not items:
        return '<div class="market-empty">Invest verisi bulunamadı.</div>'
    blocks = []
    for item in items:
        blocks.append(
            """
            <div class="market-item">
              <div class="market-head">
                <strong>{label}</strong>
                <span>{change}</span>
              </div>
              <div class="market-value">{value}</div>
              <div class="market-note">{note}</div>
            </div>
            """.format(
                label=html.escape(_fix_mojibake(item["label"])),
                change=html.escape(_fix_mojibake(item["change"])),
                value=html.escape(_fix_mojibake(item["value"])),
                note=html.escape(_fix_mojibake(item["note"])),
            ).strip()
        )
    return "\n".join(blocks)


def _render_html(report: dict) -> str:
    generated_at = html.escape(report["generated_at"])
    trend_signals = " ".join(html.escape(_fix_mojibake(signal)) for signal in report.get("trend_signals", []))
    headline_count = len(report.get("headlines", []))
    router_count = len(report.get("topic_router", []))
    lead = report["headlines"][0] if report.get("headlines") else None
    lead_title = html.escape(_fix_mojibake(lead["title"])) if lead else "Bugünün güçlü sinyalleri burada toplanıyor."
    lead_summary = html.escape(_fix_mojibake(lead.get("summary_tr") or lead.get("summary") or "")) if lead else "Filtrelenmiş küresel gelişmeler, daha editoryal bir akış içinde sunulur."
    lead_source = html.escape(_fix_mojibake(lead["source"])) if lead else "AI News"
    lead_link = html.escape(lead["link"]) if lead else "#"
    market_sidebar = _render_market_sidebar()
    return """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dünya Gelişmeleri Paneli</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&family=Source+Serif+4:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #f4eee4;
      --panel: #fffdfa;
      --panel-strong: #fbf6ef;
      --line: #d9cdbc;
      --ink: #1d2022;
      --muted: #6f685f;
      --gold: #a13c2b;
      --cyan: #235f5b;
      --mint: #235f5b;
      --shadow: 0 18px 36px rgba(74, 50, 28, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Manrope", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 12% 12%, rgba(161, 60, 43, 0.08), transparent 18%),
        linear-gradient(180deg, #f8f3eb 0%, #f1e9dd 100%);
      min-height: 100vh;
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      background-image:
        linear-gradient(rgba(31,32,34,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(31,32,34,0.03) 1px, transparent 1px);
      background-size: 28px 28px;
      mask-image: linear-gradient(180deg, rgba(0,0,0,0.32), transparent 88%);
      pointer-events: none;
    }}
    .wrap {{
      width: min(1240px, calc(100% - 32px));
      margin: 0 auto;
      padding: 22px 0 56px;
      position: relative;
      z-index: 1;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 18px;
      padding: 0 0 18px;
      margin-bottom: 18px;
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .topbar strong {{
      color: var(--ink);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      font-size: 0.78rem;
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.25fr 0.75fr;
      gap: 24px;
      min-height: 52vh;
    }}
    .hero-main, .hero-side, .section-card, .headline-card, .route-card, .mini-panel {{
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow);
    }}
    .hero-main {{
      border-radius: 32px;
      min-height: 520px;
      padding: 34px;
      display: flex;
      align-items: stretch;
      background:
        linear-gradient(180deg, rgba(255, 252, 248, 0.2), rgba(255, 252, 248, 0.94)),
        url("https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?auto=format&fit=crop&w=1400&q=80") center/cover;
    }}
    .hero-side {{
      border-radius: 28px;
      display: grid;
      gap: 1px;
      overflow: hidden;
      background: var(--line);
    }}
    .hero-panel {{
      min-height: 220px;
      padding: 24px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      background: var(--panel-strong);
    }}
    .hero-panel.top {{
      background:
        linear-gradient(180deg, rgba(255, 250, 244, 0.55), rgba(255, 250, 244, 0.96)),
        url("https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=1000&q=80") center/cover;
    }}
    .hero-panel.bottom {{
      background:
        linear-gradient(180deg, rgba(251, 246, 239, 0.68), rgba(251, 246, 239, 0.98)),
        url("https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=1000&q=80") center/cover;
    }}
    .eyebrow {{
      display: inline-flex;
      padding: 8px 14px;
      border-radius: 999px;
      border: 1px solid rgba(161,60,43,0.16);
      background: rgba(255,252,248,0.86);
      color: var(--gold);
      font-size: 0.76rem;
      font-weight: 800;
      letter-spacing: 0.18em;
      text-transform: uppercase;
    }}
    h1, h2, h3 {{
      margin: 0;
      font-family: "Source Serif 4", serif;
      letter-spacing: -0.03em;
      line-height: 1;
    }}
    h1 {{
      margin-top: 18px;
      font-size: clamp(3rem, 7vw, 5.8rem);
      max-width: 11ch;
    }}
    h2 {{
      font-size: clamp(2rem, 3vw, 3rem);
    }}
    h3 {{
      font-size: 1.7rem;
      margin-top: 16px;
    }}
    .lede {{
      margin-top: 18px;
      max-width: 58ch;
      color: #403a34;
      font-size: 1.08rem;
    }}
    .hero-copy {{
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 22px;
      width: 100%;
      align-self: end;
    }}
    .hero-rail {{
      align-self: end;
      padding: 18px;
      border-radius: 22px;
      border: 1px solid var(--line);
      background: rgba(255,253,250,0.92);
    }}
    .hero-rail p {{
      margin: 10px 0 0;
      color: var(--muted);
    }}
    .hero-stats, .mini-grid, .headline-grid, .router-grid {{
      display: grid;
      gap: 16px;
    }}
    .hero-stats {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
      margin-top: 28px;
    }}
    .stat, .mini-panel {{
      border-radius: 18px;
      padding: 10px 12px;
      background: var(--panel-strong);
    }}
    .stat strong {{
      display: block;
      font-size: 1rem;
    }}
    .stat span {{
      font-size: 0.82rem;
    }}
    .stat span, .muted, .meta, .footer-note {{
      color: var(--muted);
    }}
    .section {{
      margin-top: 28px;
    }}
    .section-card {{
      border-radius: 28px;
      padding: 28px;
    }}
    .section-top {{
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 18px;
      margin-bottom: 22px;
    }}
    .section-top p {{
      max-width: 58ch;
      margin: 0;
      color: var(--muted);
    }}
    .headline-grid {{
      grid-template-columns: repeat(12, 1fr);
    }}
    .headline-card, .route-card {{
      border-radius: 24px;
      padding: 22px;
      background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(251,246,239,0.96)), var(--panel-strong);
      position: relative;
      overflow: hidden;
    }}
    .headline-card::before, .route-card::before {{
      content: "";
      position: absolute;
      inset: 0 auto auto 0;
      width: 100%;
      height: 4px;
      background: linear-gradient(90deg, var(--gold), transparent 72%);
    }}
    .headline-card {{
      grid-column: span 6;
    }}
    .headline-card.empty {{
      grid-column: span 12;
    }}
    .route-card {{
      grid-column: span 6;
    }}
    .headline-top, .route-top {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
    }}
    .pill, .score, .route-score {{
      display: inline-flex;
      border-radius: 999px;
      padding: 8px 12px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.76);
      font-size: 0.78rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .pill {{ color: var(--mint); }}
    .score, .route-score {{ color: var(--gold); }}
    .headline-card h3 {{
      font-size: 2rem;
      line-height: 1.02;
    }}
    p {{
      line-height: 1.6;
    }}
    .meta {{
      margin-top: 12px;
      font-size: 0.95rem;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 20px;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 12px 16px;
      border-radius: 999px;
      text-decoration: none;
      font-weight: 800;
      border: 1px solid var(--line);
      transition: transform 180ms ease, border-color 180ms ease, background 180ms ease;
    }}
    .btn:hover {{
      transform: translateY(-1px);
    }}
    .btn.primary {{
      background: linear-gradient(135deg, #b54632, #8a2a1f);
      color: #fff9f5;
      border-color: transparent;
    }}
    .btn.secondary {{
      color: var(--ink);
      background: rgba(255,255,255,0.75);
    }}
    .mini-grid {{
      grid-template-columns: 1.1fr 0.9fr;
      margin-top: 22px;
    }}
    .today-list ol {{
      margin: 14px 0 0;
      padding-left: 20px;
    }}
    .today-list li {{
      margin-top: 10px;
      color: #dce7ed;
    }}
    .clock {{
      margin-top: 10px;
      font-size: clamp(2rem, 5vw, 3.5rem);
      font-weight: 800;
      letter-spacing: -0.05em;
    }}
    .errors ul {{
      margin: 14px 0 0;
      padding-left: 18px;
    }}
    .errors li {{
      margin-top: 8px;
      color: #dce7ed;
    }}
    .market-stack {{
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }}
    .market-item {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      background: rgba(255,255,255,0.72);
    }}
    .market-head {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: var(--muted);
      font-size: 0.84rem;
    }}
    .market-head strong {{
      color: var(--ink);
    }}
    .market-value {{
      margin-top: 6px;
      font-size: 1.35rem;
      font-weight: 800;
      color: var(--ink);
    }}
    .market-note {{
      margin-top: 4px;
      font-size: 0.82rem;
      color: var(--muted);
    }}
    .market-empty {{
      margin-top: 12px;
      color: var(--muted);
    }}
    .footer-note {{
      margin-top: 28px;
      padding: 0 6px;
      font-size: 0.92rem;
    }}
    @media (max-width: 960px) {{
      .hero, .mini-grid {{
        grid-template-columns: 1fr;
      }}
      .hero-copy {{
        grid-template-columns: 1fr;
      }}
      .headline-card, .route-card {{
        grid-column: span 12;
      }}
    }}
    @media (max-width: 640px) {{
      .wrap {{
        width: min(100% - 20px, 1180px);
      }}
      .hero-main {{
        min-height: 520px;
        padding: 24px;
      }}
      .hero-stats {{
        grid-template-columns: 1fr;
      }}
      .section-card {{
        padding: 20px;
      }}
      .section-top {{
        display: block;
      }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <div class="topbar">
      <strong>AI News Briefing</strong>
      <span>Günlük küresel sinyal akışı, seçilmiş kaynaklar, Türkçe özetler</span>
    </div>
    <section class="hero">
      <article class="hero-main">
        <div class="hero-copy">
          <div>
            <div class="eyebrow">Günün Çerçevesi</div>
            <h1>Gerçekten önemli ne oluyor?</h1>
            <p class="lede">Bu sayfa, dashboard görünümünden çok editoryal briefing mantığıyla hazırlandı: daha temiz görsel dil, daha güçlü başlıklar ve her haber için kısa Türkçe anlatım.</p>
            <div class="hero-stats">
              <div class="stat">
                <strong>{headline_count}</strong>
                <span>Seçilen başlık</span>
              </div>
              <div class="stat">
                <strong>{router_count}</strong>
                <span>Aktif konu yönlendirici</span>
              </div>
              <div class="stat">
                <strong>3</strong>
                <span>Bugünün ilk durakları</span>
              </div>
            </div>
          </div>
          <div class="hero-rail">
            <div class="eyebrow">Lead Story</div>
            <h3>{lead_title}</h3>
            <p>{lead_summary}</p>
            <div class="meta"><strong>Kaynak:</strong> {lead_source}</div>
            <div class="actions">
              <a class="btn primary" href="{lead_link}" target="_blank" rel="noreferrer">Lead Haberi Aç</a>
            </div>
          </div>
        </div>
      </article>
      <aside class="hero-side">
        <section class="hero-panel top">
          <div class="eyebrow">Editör Notu</div>
          <h3>{top_source}</h3>
          <p>{top_reason}</p>
        </section>
        <section class="hero-panel bottom">
          <div class="eyebrow">Bugünkü Ritim</div>
          <h3 id="clock">--:--:--</h3>
          <p id="clock-date">{generated_at}</p>
          <p class="muted">{trend_signals}</p>
        </section>
      </aside>
    </section>

    <section class="section">
      <div class="section-card">
        <div class="section-top">
          <div>
            <div class="eyebrow">Seçilmiş Haberler</div>
            <h2>Bugünün briefing sayfası</h2>
          </div>
          <p>Her haber skor, kategori ve stratejik ilgi açısından filtrelendi; ham akış yerine daha kısa ve daha editoryal bir özet dili kullanıldı.</p>
        </div>
        <div class="headline-grid">
          {headline_cards}
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-card">
        <div class="section-top">
          <div>
            <div class="eyebrow">Yönlendirme Masası</div>
            <h2>Konuya Göre En İyi Site</h2>
          </div>
          <p>Bugün hangi konu baskınsa, sizi o alanı daha iyi kapsayan kaynağa yönlendirir.</p>
        </div>
        <div class="headline-grid">
          {router_cards}
        </div>

        <div class="mini-grid">
          <div class="mini-panel today-list">
            <div class="eyebrow">Hızlı Liste</div>
            <h3>Bugün Hangi 3 Siteye Bakayım?</h3>
            <ol>
              {today_stack}
            </ol>
          </div>
          <div class="mini-panel errors">
            <div class="eyebrow">Sistem Notları</div>
            <h3>Veri Kaynağı Durumu</h3>
            <ul>
              {error_list}
            </ul>
          </div>
        </div>
      </div>
    </section>

    <p class="footer-note">Son güncelleme: {generated_at}. Sayfa Python tarafında `news_bot` ile üretildi.</p>
  </main>
  <script>
    const clockEl = document.getElementById("clock");
    const dateEl = document.getElementById("clock-date");
    function updateClock() {{
      const now = new Date();
      const time = new Intl.DateTimeFormat("tr-TR", {{
        timeZone: "Europe/Istanbul",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
      }}).format(now);
      const date = new Intl.DateTimeFormat("tr-TR", {{
        timeZone: "Europe/Istanbul",
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric"
      }}).format(now);
      clockEl.textContent = time;
      dateEl.textContent = date;
    }}
    updateClock();
    setInterval(updateClock, 1000);
  </script>
</body>
</html>
""".format(
        headline_count=headline_count,
        router_count=router_count,
        generated_at=generated_at,
        trend_signals=trend_signals or "Belirgin kategori ivmesi yok; haber akışı dengeli.",
        headline_cards=_render_headline_cards(report),
        router_cards=_render_router_cards(report),
        today_stack=_render_today_stack(report),
        error_list=_render_error_list(report),
        market_sidebar=market_sidebar,
        lead_title=lead_title,
        lead_summary=lead_summary,
        lead_source=lead_source,
        lead_link=lead_link,
        top_source=html.escape(_fix_mojibake(report["topic_router"][0]["best_source"] if report.get("topic_router") else "Semafor")),
        top_reason=html.escape(_fix_mojibake(report["topic_router"][0]["reason"] if report.get("topic_router") else "Günün baskın konusu için seçilmiş başlangıç kaynağı.")),
    )


def write_news_outputs(report: dict, output_dir: Path = OUTPUT_DIR) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    NEWS_STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "world_developments_report.md"
    json_path = output_dir / "world_developments_payload.json"
    html_path = output_dir / "world_developments_dashboard.html"
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_render_html(report), encoding="utf-8")
    NEWS_STATE_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"markdown": markdown_path, "json": json_path, "html": html_path, "state": NEWS_STATE_JSON}


def run() -> dict:
    report = collect_news()
    output_paths = write_news_outputs(report)
    return {"report": report, "output_paths": output_paths}


if __name__ == "__main__":
    result = run()
    print(f"Markdown report: {result['output_paths']['markdown']}")
    print(f"JSON payload: {result['output_paths']['json']}")
    print(f"HTML dashboard: {result['output_paths']['html']}")






