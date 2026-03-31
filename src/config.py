from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
DOCS_DIR = PROJECT_ROOT / "docs"
NEWS_STATE_JSON = DATA_DIR / "news_state.json"


@dataclass(frozen=True)
class NewsFeed:
    name: str
    url: str
    categories: tuple[str, ...]


@dataclass(frozen=True)
class NewsBotConfig:
    max_headlines: int = 4
    max_items_per_feed: int = 12
    lookback_hours: int = 72
    feeds: tuple[NewsFeed, ...] = (
        NewsFeed(
            name="Reuters World",
            url="https://feeds.reuters.com/Reuters/worldNews",
            categories=("macro",),
        ),
        NewsFeed(
            name="Reuters Business",
            url="https://feeds.reuters.com/reuters/businessNews",
            categories=("macro", "financial_system"),
        ),
        NewsFeed(
            name="Reuters Technology",
            url="https://feeds.reuters.com/reuters/technologyNews",
            categories=("technology", "ai", "robotics"),
        ),
        NewsFeed(
            name="TechCrunch",
            url="https://techcrunch.com/feed/",
            categories=("technology", "ai"),
        ),
        NewsFeed(
            name="Quartz",
            url="https://qz.com/feed",
            categories=("macro", "technology", "financial_system"),
        ),
        NewsFeed(
            name="The Robot Report",
            url="https://www.therobotreport.com/feed/",
            categories=("robotics",),
        ),
        NewsFeed(
            name="Payments Dive",
            url="https://www.paymentsdive.com/feeds/news/",
            categories=("financial_system",),
        ),
    )


DEFAULT_NEWS_BOT_CONFIG = NewsBotConfig()

