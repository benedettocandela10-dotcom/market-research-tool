import argparse
import base64
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

PLACEHOLDER_MARKERS = ("xxxx", "your_", "TUO_USERNAME", "YOUR_")


def _env(key: str) -> Optional[str]:
    val = os.getenv(key, "").strip()
    if not val:
        return None
    lower = val.lower()
    if any(m.lower() in lower for m in PLACEHOLDER_MARKERS):
        return None
    return val


def _parse_etsy_price(price: Any) -> float:
    if price is None:
        return 0.0
    if isinstance(price, dict):
        amount = price.get("amount", 0)
        divisor = price.get("divisor", 1) or 1
        return float(amount) / float(divisor)
    try:
        return float(price)
    except (TypeError, ValueError):
        return 0.0


def _etsy_listing_url(item: dict) -> str:
    if item.get("url"):
        return item["url"]
    listing_id = item.get("listing_id")
    if listing_id:
        return f"https://www.etsy.com/listing/{listing_id}"
    return ""


def _utc_date(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")


class MarketCollector:
    def __init__(self):
        self.results: List[Dict] = []
        self.reddit = None
        self.etsy_key = _env("ETSY_API_KEY")
        self.ebay_client_id = _env("EBAY_CLIENT_ID")
        self.ebay_client_secret = _env("EBAY_CLIENT_SECRET")
        self.ebay_sandbox = os.getenv("EBAY_SANDBOX", "false").lower() in ("1", "true", "yes")
        self._ebay_token: Optional[str] = None
        self._ebay_token_expires: float = 0

        if self._reddit_configured():
            self._init_reddit()

    def _reddit_configured(self) -> bool:
        return bool(
            _env("REDDIT_CLIENT_ID")
            and _env("REDDIT_CLIENT_SECRET")
            and _env("REDDIT_USERNAME")
            and _env("REDDIT_PASSWORD")
        )

    def _init_reddit(self):
        import praw

        self.reddit = praw.Reddit(
            client_id=_env("REDDIT_CLIENT_ID"),
            client_secret=_env("REDDIT_CLIENT_SECRET"),
            username=_env("REDDIT_USERNAME"),
            password=_env("REDDIT_PASSWORD"),
            user_agent=_env("REDDIT_USER_AGENT") or "market_research/1.0",
        )

    def configured_sources(self) -> Dict[str, bool]:
        return {
            "reddit": self.reddit is not None,
            "etsy": self.etsy_key is not None,
            "ebay": self.ebay_client_id is not None and self.ebay_client_secret is not None,
        }

    def print_config_status(self):
        src = self.configured_sources()
        print("Source configuration:")
        for name, ok in src.items():
            print(f"  {name}: {'ready' if ok else 'skipped (missing credentials)'}")
        if not any(src.values()):
            print("\nNo API credentials found. Copy config.example.env to .env and fill in your keys.")

    def _get_ebay_application_token(self) -> Optional[str]:
        if not self.ebay_client_id or not self.ebay_client_secret:
            return None
        if self._ebay_token and time.time() < self._ebay_token_expires - 60:
            return self._ebay_token

        host = "api.sandbox.ebay.com" if self.ebay_sandbox else "api.ebay.com"
        url = f"https://{host}/identity/v1/oauth2/token"
        creds = base64.b64encode(
            f"{self.ebay_client_id}:{self.ebay_client_secret}".encode()
        ).decode()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {creds}",
        }
        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        }
        res = requests.post(url, headers=headers, data=data, timeout=30)
        res.raise_for_status()
        body = res.json()
        self._ebay_token = body["access_token"]
        self._ebay_token_expires = time.time() + int(body.get("expires_in", 7200))
        return self._ebay_token

    def collect_reddit(
        self,
        keywords: List[str],
        subreddits: List[str],
        limit_per_kw: int = 20,
    ):
        if not self.reddit:
            print("Skipping Reddit (credentials not configured).")
            return

        print("Fetching Reddit data...")
        for kw in keywords:
            for sub in subreddits:
                try:
                    for post in self.reddit.subreddit(sub).search(
                        kw, limit=limit_per_kw, sort="new"
                    ):
                        if post.score < 3:
                            continue
                        snippet = (post.selftext or "")[:300].replace("\n", " ")
                        permalink = (
                            f"https://www.reddit.com{post.permalink}"
                            if post.permalink
                            else post.url
                        )
                        self.results.append(
                            {
                                "platform": "reddit",
                                "keyword": kw,
                                "title": post.title,
                                "snippet": snippet,
                                "price": None,
                                "currency": None,
                                "url": permalink,
                                "engagement_score": post.score,
                                "comments": post.num_comments,
                                "date": _utc_date(post.created_utc),
                            }
                        )
                        time.sleep(0.5)
                except Exception as e:
                    print(f"Reddit error {sub}/{kw}: {e}")

    def collect_etsy(self, keywords: List[str], limit: int = 20):
        if not self.etsy_key:
            print("Skipping Etsy (ETSY_API_KEY not configured).")
            return

        print("Fetching Etsy data...")
        headers = {"x-api-key": self.etsy_key}
        base_url = "https://openapi.etsy.com/v3/application/listings/search"

        for kw in keywords:
            params = {"query": kw, "limit": limit}
            try:
                res = requests.get(base_url, headers=headers, params=params, timeout=30)
                res.raise_for_status()
                data = res.json()
                for item in data.get("results", []):
                    self.results.append(
                        {
                            "platform": "etsy",
                            "keyword": kw,
                            "title": item.get("title", ""),
                            "snippet": "",
                            "price": _parse_etsy_price(item.get("price")),
                            "currency": item.get("currency_code", "USD"),
                            "url": _etsy_listing_url(item),
                            "engagement_score": item.get("views", 0)
                            + item.get("num_favorers", 0),
                            "comments": 0,
                            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        }
                    )
                time.sleep(1)
            except Exception as e:
                print(f"Etsy error {kw}: {e}")

    def collect_ebay(self, keywords: List[str], limit: int = 20):
        token = self._get_ebay_application_token()
        if not token:
            print("Skipping eBay (EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not configured).")
            return

        print("Fetching eBay data...")
        host = "api.sandbox.ebay.com" if self.ebay_sandbox else "api.ebay.com"
        base_url = f"https://{host}/buy/browse/v1/item_summary/search"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        for kw in keywords:
            params = {"q": kw, "limit": str(limit)}
            try:
                res = requests.get(
                    base_url, headers=headers, params=params, timeout=30
                )
                res.raise_for_status()
                data = res.json()
                for item in data.get("itemSummaries", []):
                    price_info = item.get("price") or {}
                    price = price_info.get("value", 0)
                    currency = price_info.get("currency", "USD")
                    item_id = item.get("itemId", "")
                    web_url = item.get("webUrl") or (
                        f"https://www.ebay.com/itm/{item_id}" if item_id else ""
                    )

                    self.results.append(
                        {
                            "platform": "ebay",
                            "keyword": kw,
                            "title": item.get("title", ""),
                            "snippet": item.get("condition", "") or "",
                            "price": float(price) if price else 0.0,
                            "currency": currency,
                            "url": web_url,
                            "engagement_score": 0,
                            "comments": 0,
                            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        }
                    )
                time.sleep(1.2)
            except Exception as e:
                print(f"eBay error {kw}: {e}")

    def run(
        self,
        keywords: List[str],
        reddit_subs: Optional[List[str]] = None,
        limit: int = 20,
        use_reddit: bool = True,
        use_etsy: bool = True,
        use_ebay: bool = True,
        include_trends: bool = False,
    ) -> pd.DataFrame:
        if reddit_subs is None:
            reddit_subs = [
                "ScaleModeling",
                "MechanicalKeyboards",
                "fountainpens",
                "watchrepair",
            ]

        self.print_config_status()

        if use_reddit:
            self.collect_reddit(keywords, reddit_subs, limit_per_kw=limit)
        if use_etsy:
            self.collect_etsy(keywords, limit=limit)
        if use_ebay:
            self.collect_ebay(keywords, limit=limit)

        df = pd.DataFrame(self.results)

        if include_trends:
            try:
                from trends_collector import fetch_trends_for_keywords

                trends_df = fetch_trends_for_keywords(keywords)
                if not trends_df.empty and not df.empty:
                    df = df.merge(
                        trends_df,
                        on="keyword",
                        how="left",
                        suffixes=("", "_trend"),
                    )
                elif trends_df.empty and df.empty:
                    df = trends_df
            except ImportError:
                print("Trends module not available.")
            except Exception as e:
                print(f"Trends collection skipped: {e}")

        os.makedirs("output", exist_ok=True)
        filename = f"output/market_data_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        print(f"Saved {len(df)} records to {filename}")
        return df


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collect market data from Reddit, Etsy, and eBay."
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        required=True,
        help="Search keywords (one or more)",
    )
    parser.add_argument(
        "--subs",
        nargs="+",
        default=[
            "ScaleModeling",
            "MechanicalKeyboards",
            "fountainpens",
            "watchrepair",
        ],
        help="Reddit subreddits to search",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max results per keyword per source",
    )
    parser.add_argument("--no-reddit", action="store_true", help="Skip Reddit")
    parser.add_argument("--no-etsy", action="store_true", help="Skip Etsy")
    parser.add_argument("--no-ebay", action="store_true", help="Skip eBay")
    parser.add_argument(
        "--trends",
        action="store_true",
        help="Include Trends MCP demand scores (requires TRENDS_API_KEY)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    collector = MarketCollector()
    collector.run(
        keywords=args.keywords,
        reddit_subs=args.subs,
        limit=args.limit,
        use_reddit=not args.no_reddit,
        use_etsy=not args.no_etsy,
        use_ebay=not args.no_ebay,
        include_trends=args.trends,
    )
