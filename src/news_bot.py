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

from config import DEFAULT_NEWS_BOT_CONFIG, DOCS_DIR, NEWS_STATE_JSON, OUTPUT_DIR

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
    "macro": "Makro rejim degisimi kur, faiz, emtia ve risk istahini birlikte etkiler.",
    "technology": "YZ altyapi yarisi sermaye akislarini, cip talebini ve platform kazananlarini belirler.",
    "robotics": "Robotik gercek dunyaya indiginde verimlilik, uretim yapisi ve is gucu dengesi degisir.",
    "financial_system": "Odeme ve finans altyapisindaki degisim yeni kazananlari ve islem akisini yeniden kurar.",
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
    for item in report.get("headlines", [])[1:7]:
        labels = " ? ".join(CATEGORY_LABELS.get(category, category) for category in item["categories"])
        cards.append(
            """
            <article class="story-card">
              <div class="story-meta-row">
                <span class="story-tag">{labels}</span>
                <span class="story-score">Skor {score}</span>
              </div>
              <h3>{title}</h3>
              <p>{summary}</p>
              <div class="story-footer">
                <span><strong>Kaynak:</strong> {source}</span>
                <a href="{link}" target="_blank" rel="noreferrer">Haberi a?</a>
              </div>
            </article>
            """.format(
                labels=_html_text(labels or "Genel"),
                score=item["score"],
                title=_html_text(item["title"]),
                summary=_html_text(item.get("summary_tr") or item["summary"] or "?zet bulunamad?."),
                source=_html_text(item["source"]),
                link=html.escape(item["link"]),
            ).strip()
        )
    if cards:
        return "\n".join(cards)
    return """
    <article class="story-card empty-state">
      <div class="story-meta-row"><span class="story-tag">Feed durumu</span></div>
      <h3>Bug?n yeterince g??l? haber se?ilemedi</h3>
      <p>Kaynak eri?imi d??t???nde ya da filtre ?ok sert kald???nda briefing bu alan? bo? ge?mek yerine bunu a??k?a s?yler.</p>
    </article>
    """.strip()


def _render_router_cards(report: dict) -> str:
    cards = []
    for route in report.get("topic_router", [])[:4]:
        cards.append(
            """
            <article class="route-card">
              <div class="route-topline">
                <span class="route-label">{label}</span>
                <span class="route-trend">Trend {score}</span>
              </div>
              <h3>{source}</h3>
              <p>{reason}</p>
              <div class="route-links">
                <a href="{url}" target="_blank" rel="noreferrer">Ana kaynak</a>
                <span>Yedek: {backup}</span>
              </div>
            </article>
            """.format(
                label=_html_text(route["label"]),
                score=route["score"],
                source=_html_text(route["best_source"]),
                reason=_html_text(route["reason"]),
                url=html.escape(route["best_url"]),
                backup=_html_text(route["backup_source"]),
            ).strip()
        )
    return "\n".join(cards)


def _render_today_stack(report: dict) -> str:
    items = []
    for index, route in enumerate(report.get("today_stack", [])[:5], start=1):
        items.append(
            "<li><strong>{index}.</strong> <span>{label}</span><small>{source}</small></li>".format(
                index=index,
                label=_html_text(route["label"]),
                source=_html_text(route["best_source"]),
            )
        )
    if items:
        return "\n".join(items)
    return "<li><strong>1.</strong> <span>Bug?n rota olu?mad?</span><small>Kaynak bekleniyor</small></li>"


def _render_error_list(report: dict) -> str:
    if not report.get("errors"):
        return "<li>Kaynak hatas? g?r?nm?yor.</li>"
    return "\n".join("<li>{}</li>".format(_html_text(error)) for error in report["errors"][:5])


def _render_market_sidebar() -> str:
    items = _build_market_sidebar()
    if not items:
        return '<div class="market-empty">Invest verisi bulunamad?.</div>'
    blocks = []
    for item in items[:8]:
        blocks.append(
            """
            <article class="market-card">
              <div class="market-top">
                <strong>{label}</strong>
                <span>{change}</span>
              </div>
              <div class="market-value">{value}</div>
              <div class="market-note">{note}</div>
            </article>
            """.format(
                label=_html_text(item["label"]),
                change=_html_text(item["change"]),
                value=_html_text(item["value"]),
                note=_html_text(item["note"]),
            ).strip()
        )
    return "\n".join(blocks)


def _render_signal_strip(report: dict) -> str:
    bits = [
        ("Ba?l?k", str(len(report.get("headlines", [])))),
        ("Router", str(len(report.get("topic_router", [])))),
        ("Sinyal", _html_text(" ? ".join(report.get("trend_signals", [])[:2]) or "Sinyal ak??? haz?rlan?yor")),
    ]
    return "\n".join(
        '<div class="signal-chip"><span>{}</span><strong>{}</strong></div>'.format(_html_text(label), value)
        for label, value in bits
    )


def _render_political_brief(report: dict) -> str:
    items = []
    for item in report.get("headlines", []):
        source = item.get("source", "")
        cats = item.get("categories", [])
        title = item.get("title", "")
        text = " ".join([title, item.get("summary", ""), item.get("summary_tr", "")]).lower()
        if "macro" not in cats and not any(token in text for token in ("trump", "china", "tariff", "white house", "beijing", "europe", "nato", "ukraine", "iran", "trade", "sanction", "congress")):
            continue
        items.append(
            """
            <li>
              <a href="{link}" target="_blank" rel="noreferrer">{title}</a>
              <span>{source}</span>
            </li>
            """.format(
                link=html.escape(item["link"]),
                title=_html_text(title),
                source=_html_text(source),
            ).strip()
        )
        if len(items) == 4:
            break
    if items:
        return "\n".join(items)
    return '<li><a href="https://www.reuters.com/world/" target="_blank" rel="noreferrer">Reuters World ak???n? a?</a><span>Tarafs?z siyasi tarama</span></li>'


def _build_market_sidebar() -> list[dict]:
    analysis = _load_invest_analysis()
    if not analysis:
        return []

    items: list[dict] = []
    market = analysis.get("market_snapshot", {})
    holdings = analysis.get("portfolio_mix", {}).get("holdings", [])
    holdings_by_code = {
        str(row.get("instrument_code") or "").upper(): row
        for row in holdings
        if row.get("instrument_code")
    }
    holdings_by_name = {
        str(row.get("instrument_name") or "").upper(): row
        for row in holdings
    }

    usd_try = market.get("usd_try")
    if usd_try is not None:
        trend_map = {
            "up": "Yukar?",
            "down": "A?a??",
            "flat": "Yatay",
            "unknown": "Belirsiz",
            "data_unavailable": "Veri yok",
        }
        items.append(
            {
                "label": "USD/TRY",
                "value": f"{usd_try:.2f}",
                "change": trend_map.get(str(market.get("usd_try_trend", "unknown")), "Bilgi yok"),
                "note": "Kur y?n?",
            }
        )

    fund_specs = [
        ("GTA", "Alt?n Fonu", 4),
        ("GTZ", "G?m?? Fonu", 4),
        ("GTL", "Para Piyasas?", 6),
        ("GVI", "Fon Sepeti", 4),
        ("GTM", "Temett?", 4),
    ]
    for code, label, precision in fund_specs:
        holding = holdings_by_code.get(code)
        price = change = None
        try:
            price, change = _fetch_tefas_daily_change(code)
        except Exception:
            price, change = None, None
        if price is not None:
            value = f"{price:.{precision}f}"
            note = "TEFAS g?nl?k"
        elif holding:
            amount = holding.get("amount")
            annual = holding.get("one_year_return_pct")
            value = f"{amount:,.0f} TL".replace(",", ".") if isinstance(amount, (int, float)) else "Portf?yde"
            note = f"Portf?y tutar? ? 1Y %{annual:.1f}" if isinstance(annual, (int, float)) else "Portf?yde mevcut"
        else:
            continue
        items.append(
            {
                "label": label,
                "value": value,
                "change": f"%{change:.2f}" if change is not None else "Portf?y ba??",
                "note": note,
            }
        )

    garan_holding = holdings_by_name.get("GARAN")
    try:
        garan_price, garan_change = _fetch_yahoo_daily_change("GARAN.IS")
    except Exception:
        garan_price, garan_change = None, None
    if garan_price is not None:
        items.append(
            {
                "label": "GARAN",
                "value": f"{garan_price:.2f}",
                "change": f"%{garan_change:.2f}" if garan_change is not None else "G?nl?k yok",
                "note": "Yahoo g?nl?k",
            }
        )
    elif garan_holding:
        items.append(
            {
                "label": "GARAN",
                "value": f"{garan_holding.get('amount', 0):,.0f} TL".replace(",", "."),
                "change": "Portf?y ba??",
                "note": "Invest holding de?eri",
            }
        )

    return items[:8]


def _render_html(report: dict) -> str:
    generated_at = _html_text(report["generated_at"])
    lead = report["headlines"][0] if report.get("headlines") else None
    lead_title = _html_text(lead["title"]) if lead else "Bug?n?n g??l? sinyalleri burada toplan?yor."
    lead_summary = _html_text(lead.get("summary_tr") or lead.get("summary") or "Filtrelenmi? k?resel geli?meler daha editoryal bir ak?? i?inde sunulur.") if lead else "Filtrelenmi? k?resel geli?meler daha editoryal bir ak?? i?inde sunulur."
    lead_source = _html_text(lead["source"]) if lead else "AI News"
    lead_link = html.escape(lead["link"]) if lead else "#"
    lead_reason = _html_text(lead.get("why_it_matters") or "Sermaye, teknoloji ve devlet hamlelerinin nereye kayd???n? daha h?zl? g?rmek i?in.") if lead else "Sermaye, teknoloji ve devlet hamlelerinin nereye kayd???n? daha h?zl? g?rmek i?in."
    trend_line = _html_text(" ? ".join(report.get("trend_signals", [])[:3]) or "Makro, yapay zeka, robotik ve finansal altyap? ayn? ekranda.")
    return """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI News Briefing</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Libre+Baskerville:wght@400;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --paper: #fbfaf7;
      --panel: #ffffff;
      --ink: #171717;
      --muted: #6f6a63;
      --line: #e6dfd4;
      --accent: #bb4d36;
      --accent-soft: #f7ece7;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--paper); color: var(--ink); font-family: "Inter", sans-serif; }}
    a {{ color: inherit; text-decoration: none; }}
    .page {{ width: min(1480px, calc(100vw - 40px)); margin: 0 auto; padding: 18px 0 56px; }}
    .masthead {{ display: flex; justify-content: space-between; gap: 16px; align-items: end; padding: 8px 0 18px; border-bottom: 1px solid var(--line); }}
    .brand {{ font-family: "Libre Baskerville", serif; font-size: clamp(2rem, 4vw, 3.4rem); letter-spacing: -0.04em; }}
    .mast-meta {{ color: var(--muted); font-size: 0.95rem; max-width: 46ch; text-align: right; }}
    .signal-row {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; padding: 14px 0 18px; border-bottom: 1px solid var(--line); }}
    .signal-chip {{ display: grid; gap: 4px; padding: 12px 14px; background: var(--panel); border: 1px solid var(--line); border-radius: 14px; min-height: 72px; }}
    .signal-chip span {{ font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }}
    .signal-chip strong {{ font-size: 0.98rem; line-height: 1.35; }}
    .editorial-grid {{ display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(320px, 0.92fr); gap: 26px; padding-top: 20px; align-items: start; }}
    .lead-column {{ display: grid; gap: 24px; }}
    .lead-story {{ background: var(--panel); border: 1px solid var(--line); border-radius: 22px; padding: 28px 30px 30px; }}
    .kicker {{ display: inline-flex; align-items: center; gap: 8px; font-size: 0.78rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--accent); font-weight: 800; }}
    .lead-story h1 {{ margin: 14px 0 14px; font-family: "Libre Baskerville", serif; font-size: clamp(2.5rem, 5vw, 4.6rem); line-height: 1.02; letter-spacing: -0.05em; max-width: 12ch; }}
    .lead-summary {{ font-size: 1.08rem; line-height: 1.75; max-width: 64ch; color: #2b2926; }}
    .lead-meta {{ display: grid; grid-template-columns: 180px 1fr; gap: 18px; margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--line); }}
    .lead-source strong, .rail-card h3, .section-title {{ font-family: "Libre Baskerville", serif; }}
    .lead-source {{ color: var(--muted); line-height: 1.6; }}
    .lead-why {{ line-height: 1.7; }}
    .lead-actions {{ margin-top: 18px; display: flex; gap: 12px; flex-wrap: wrap; }}
    .btn {{ display: inline-flex; align-items: center; justify-content: center; padding: 12px 16px; border-radius: 999px; border: 1px solid var(--line); font-weight: 700; }}
    .btn.primary {{ background: var(--ink); color: #fff; border-color: var(--ink); }}
    .btn.secondary {{ background: var(--accent-soft); color: var(--accent); border-color: #f0d8ce; }}
    .briefing-grid {{ display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(280px, 0.85fr); gap: 20px; }}
    .brief-card, .rail-card, .story-card, .route-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 20px; }}
    .brief-card, .rail-card {{ padding: 22px; }}
    .section-title {{ font-size: 1.6rem; margin: 0 0 10px; letter-spacing: -0.03em; }}
    .section-copy {{ color: var(--muted); line-height: 1.65; margin: 0 0 18px; }}
    .today-list, .politics-list, .error-list {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 12px; }}
    .today-list li {{ display: grid; grid-template-columns: auto 1fr; gap: 10px 12px; align-items: baseline; padding-bottom: 12px; border-bottom: 1px solid #f0ebe3; }}
    .today-list li:last-child, .politics-list li:last-child, .error-list li:last-child {{ border-bottom: 0; padding-bottom: 0; }}
    .today-list span {{ font-weight: 700; }}
    .today-list small {{ grid-column: 2; color: var(--muted); }}
    .story-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }}
    .story-card {{ padding: 20px; display: grid; gap: 14px; }}
    .story-card h3 {{ margin: 0; font-family: "Libre Baskerville", serif; font-size: 1.45rem; line-height: 1.18; letter-spacing: -0.03em; }}
    .story-card p {{ margin: 0; color: #34302b; line-height: 1.68; }}
    .story-meta-row, .story-footer, .route-topline, .route-links, .rail-top {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap; }}
    .story-tag, .story-score, .route-label, .route-trend, .rail-label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 800; color: var(--muted); }}
    .story-footer {{ color: var(--muted); font-size: 0.9rem; border-top: 1px solid #f0ebe3; padding-top: 12px; }}
    .story-footer a, .route-links a, .politics-list a {{ color: var(--accent); font-weight: 700; }}
    .right-rail {{ display: grid; gap: 18px; position: sticky; top: 16px; }}
    .rail-card h3 {{ margin: 0 0 10px; font-size: 1.35rem; letter-spacing: -0.03em; }}
    .market-stack {{ display: grid; gap: 12px; }}
    .market-card {{ padding: 14px 0; border-top: 1px solid #f0ebe3; }}
    .market-card:first-child {{ border-top: 0; padding-top: 0; }}
    .market-top {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; font-size: 0.88rem; color: var(--muted); }}
    .market-value {{ margin-top: 6px; font-size: 1.45rem; font-weight: 800; letter-spacing: -0.03em; }}
    .market-note {{ margin-top: 4px; color: var(--muted); font-size: 0.9rem; }}
    .route-stack {{ display: grid; gap: 12px; }}
    .route-card {{ padding: 18px; }}
    .route-card h3 {{ margin: 6px 0 8px; font-size: 1.15rem; }}
    .route-card p {{ margin: 0; color: #393530; line-height: 1.6; }}
    .route-links {{ margin-top: 12px; color: var(--muted); font-size: 0.9rem; }}
    .politics-list li {{ display: grid; gap: 6px; padding-bottom: 12px; border-bottom: 1px solid #f0ebe3; }}
    .politics-list span {{ color: var(--muted); font-size: 0.9rem; }}
    .error-list li {{ color: var(--muted); padding-bottom: 10px; border-bottom: 1px solid #f0ebe3; }}
    .footer-note {{ margin-top: 26px; color: var(--muted); font-size: 0.9rem; border-top: 1px solid var(--line); padding-top: 16px; }}
    .market-empty, .empty-state {{ color: var(--muted); }}
    @media (max-width: 1100px) {{ .editorial-grid, .briefing-grid, .lead-meta, .story-grid, .signal-row {{ grid-template-columns: 1fr; }} .right-rail {{ position: static; }} .page {{ width: min(100vw - 24px, 100%); }} }}
  </style>
</head>
<body>
  <div class="page">
    <header class="masthead">
      <div>
        <div class="brand">AI News Briefing</div>
        <div class="mast-meta">D?nyada ger?ekten ?nemli olan? g?r?lt?den ay?ran g?nl?k briefing. Nvidia, AI, robotik, finansal raylar ve jeopolitik ayn? sayfada.</div>
      </div>
      <div class="mast-meta">G?ncellendi: {generated_at}</div>
    </header>

    <section class="signal-row">
      {signal_strip}
    </section>

    <main class="editorial-grid">
      <section class="lead-column">
        <article class="lead-story">
          <div class="kicker">G?n?n ?er?evesi</div>
          <h1>{lead_title}</h1>
          <p class="lead-summary">{lead_summary}</p>
          <div class="lead-actions">
            <a class="btn primary" href="{lead_link}" target="_blank" rel="noreferrer">Lead haberi a?</a>
            <a class="btn secondary" href="https://www.reuters.com/world/" target="_blank" rel="noreferrer">Reuters World</a>
          </div>
          <div class="lead-meta">
            <div class="lead-source"><strong>{lead_source}</strong><br>{trend_line}</div>
            <div class="lead-why"><strong>Bu neden ?nemli?</strong><br>{lead_reason}</div>
          </div>
        </article>

        <section class="briefing-grid">
          <article class="brief-card">
            <h2 class="section-title">Bug?n?n briefing sayfas?</h2>
            <p class="section-copy">?nce hangi kap?ya bakman?z gerekti?ini burada s?k??t?rd?m. Ama? daha ?ok ba?l?k de?il, daha do?ru ilk okuma rotas?.</p>
            <ol class="today-list">
              {today_stack}
            </ol>
          </article>
          <article class="brief-card">
            <h2 class="section-title">Siyasi radar</h2>
            <p class="section-copy">Tarafs?z tarama i?in Reuters omurgas?n? koruyup bug?n?n ?ne ??kan siyasi ba?l?klar?n? ay?r?yorum.</p>
            <ul class="politics-list">
              {political_brief}
            </ul>
          </article>
        </section>

        <section>
          <div class="rail-top" style="margin-bottom: 12px;">
            <h2 class="section-title" style="margin:0;">Se?ilmi? haberler</h2>
            <div class="mast-meta" style="text-align:left;">Quartz benzeri daha editoryal, daha k?sa ve daha okunur ak??.</div>
          </div>
          <div class="story-grid">
            {headline_cards}
          </div>
        </section>
      </section>

      <aside class="right-rail">
        <article class="rail-card">
          <div class="rail-top">
            <span class="rail-label">Piyasa panosu</span>
            <span class="mast-meta">Invest ba?lant?s?</span>
          </div>
          <h3>Fonlar ve ana izleme listesi</h3>
          <div class="market-stack">
            {market_sidebar}
          </div>
        </article>

        <article class="rail-card">
          <div class="rail-top">
            <span class="rail-label">Topic router</span>
            <span class="mast-meta">En iyi ilk durak</span>
          </div>
          <h3>Konuya g?re do?ru kaynak</h3>
          <div class="route-stack">
            {router_cards}
          </div>
        </article>

        <article class="rail-card">
          <div class="rail-top">
            <span class="rail-label">Kaynak notlar?</span>
            <span class="mast-meta">Sistem sa?l???</span>
          </div>
          <h3>Feed durumu</h3>
          <ul class="error-list">
            {error_list}
          </ul>
        </article>
      </aside>
    </main>

    <footer class="footer-note">Bu sayfa AI News motoru taraf?ndan otomatik ?retilir. Politik tarama m?mk?n oldu?unca Reuters merkezli, teknoloji ve strateji taraf? ise konu router mant???yla y?nlendirilir.</footer>
  </div>
</body>
</html>
""".format(
        generated_at=generated_at,
        signal_strip=_render_signal_strip(report),
        lead_title=lead_title,
        lead_summary=lead_summary,
        lead_link=lead_link,
        lead_source=lead_source,
        trend_line=trend_line,
        lead_reason=lead_reason,
        today_stack=_render_today_stack(report),
        political_brief=_render_political_brief(report),
        headline_cards=_render_headline_cards(report),
        market_sidebar=_render_market_sidebar(),
        router_cards=_render_router_cards(report),
        error_list=_render_error_list(report),
    )


def write_news_outputs(report: dict, output_dir: Path = OUTPUT_DIR) -> dict[str, Path]:
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
    markdown_path.write_text(markdown_content, encoding="utf-8")
    json_path.write_text(json_content, encoding="utf-8")
    html_path.write_text(html_content, encoding="utf-8")
    docs_html_path.write_text(html_content, encoding="utf-8")
    docs_json_path.write_text(json_content, encoding="utf-8")
    docs_markdown_path.write_text(markdown_content, encoding="utf-8")
    NEWS_STATE_JSON.write_text(json_content, encoding="utf-8")
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






