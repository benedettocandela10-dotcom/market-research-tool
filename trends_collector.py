"""Optional Trends MCP layer for demand / trend scores."""

import argparse
import os
from datetime import datetime
from typing import List, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

TRENDS_API_URL = "https://api.trendsmcp.ai/api"
DEFAULT_SOURCES = ["google shopping", "amazon", "reddit"]


def _api_key() -> Optional[str]:
    key = os.getenv("TRENDS_API_KEY", "").strip()
    if not key or "your_" in key.lower() or key.startswith("xxxx"):
        return None
    return key


def fetch_trend(keyword: str, source: str, api_key: str) -> dict:
    """Fetch latest trend point for a keyword on a source."""
    res = requests.post(
        TRENDS_API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"source": source, "keyword": keyword},
        timeout=30,
    )
    res.raise_for_status()
    return res.json()


def _extract_score(data: dict) -> Optional[float]:
    """Normalize API response to a single 0-100 score when possible."""
    if isinstance(data, (int, float)):
        return float(data)
    if isinstance(data, dict):
        for key in ("value", "score", "interest", "normalized_value"):
            if key in data and data[key] is not None:
                try:
                    return float(data[key])
                except (TypeError, ValueError):
                    pass
        series = data.get("data") or data.get("timeline") or data.get("values")
        if isinstance(series, list) and series:
            last = series[-1]
            if isinstance(last, dict):
                for key in ("value", "score", "v"):
                    if key in last:
                        try:
                            return float(last[key])
                        except (TypeError, ValueError):
                            pass
            elif isinstance(last, (int, float)):
                return float(last)
    return None


def fetch_trends_for_keywords(
    keywords: List[str],
    sources: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Return one row per keyword+source with trend_score.
    Used by market_collector when --trends is set (merged on keyword).
    """
    api_key = _api_key()
    if not api_key:
        print("Trends MCP skipped: set TRENDS_API_KEY in .env")
        return pd.DataFrame()

    if sources is None:
        sources = DEFAULT_SOURCES

    rows = []
    for kw in keywords:
        scores = {}
        for source in sources:
            try:
                data = fetch_trend(kw, source, api_key)
                score = _extract_score(data)
                if score is not None:
                    scores[source.replace(" ", "_")] = score
            except Exception as e:
                print(f"Trends error [{source}] {kw}: {e}")

        if scores:
            avg = sum(scores.values()) / len(scores)
            rows.append(
                {
                    "keyword": kw,
                    "trend_score": round(avg, 2),
                    "trend_sources": ", ".join(scores.keys()),
                    **{f"trend_{k}": v for k, v in scores.items()},
                }
            )

    return pd.DataFrame(rows)


def run_cli(keywords: List[str], sources: List[str]) -> pd.DataFrame:
    df = fetch_trends_for_keywords(keywords, sources)
    os.makedirs("output", exist_ok=True)
    path = f"output/trends_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved {len(df)} trend rows to {path}")
    return df


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch Trends MCP demand scores.")
    parser.add_argument("--keywords", nargs="+", required=True)
    parser.add_argument(
        "--sources",
        nargs="+",
        default=DEFAULT_SOURCES,
        help='Trend sources, e.g. "google shopping" amazon reddit',
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_cli(args.keywords, args.sources)
