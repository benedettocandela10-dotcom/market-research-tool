"""Streamlit dashboard for browsing and filtering market research CSV exports."""

from pathlib import Path

import pandas as pd
import streamlit as st

OUTPUT_DIR = Path("output")


def list_csv_files() -> list[Path]:
    if not OUTPUT_DIR.exists():
        return []
    return sorted(OUTPUT_DIR.glob("market_data_*.csv"), reverse=True)


def format_price(row: pd.Series) -> str:
    price = row.get("price")
    if pd.isna(price) or price is None or price == "":
        return "—"
    currency = row.get("currency") or "USD"
    try:
        return f"{currency} {float(price):,.2f}"
    except (TypeError, ValueError):
        return str(price)


@st.cache_data
def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    for col in ("price", "engagement_score", "comments", "trend_score"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def main():
    st.set_page_config(page_title="Market Research", layout="wide")
    st.title("Market Research Dashboard")

    files = list_csv_files()
    if not files:
        st.warning(
            "No CSV files in `output/`. Run the collector first:\n\n"
            "`python market_collector.py --keywords \"your niche\"`"
        )
        return

    file_labels = [f.name for f in files]
    selected = st.sidebar.selectbox("Dataset", file_labels, index=0)
    path = OUTPUT_DIR / selected
    df = load_csv(str(path))

    st.sidebar.markdown("---")
    st.sidebar.subheader("Filters")

    platforms = sorted(df["platform"].dropna().unique()) if "platform" in df.columns else []
    sel_platforms = st.sidebar.multiselect("Platform", platforms, default=platforms)

    keywords = sorted(df["keyword"].dropna().unique()) if "keyword" in df.columns else []
    sel_keywords = st.sidebar.multiselect("Keyword", keywords, default=keywords)

    has_price = "price" in df.columns and df["price"].notna().any()
    price_min, price_max = 0.0, 0.0
    if has_price:
        priced = df[df["price"].notna() & (df["price"] > 0)]["price"]
        if len(priced):
            price_min = float(priced.min())
            price_max = float(priced.max())
            lo, hi = st.sidebar.slider(
                "Price range",
                min_value=price_min,
                max_value=price_max,
                value=(price_min, price_max),
            )
        else:
            lo, hi = 0.0, 0.0
    else:
        lo, hi = 0.0, 0.0

    min_engagement = st.sidebar.number_input(
        "Min engagement score", min_value=0, value=0, step=1
    )

    st.sidebar.markdown("---")
    sort_col = st.sidebar.selectbox(
        "Sort by",
        [c for c in ["engagement_score", "price", "date", "title", "platform", "keyword"] if c in df.columns],
        index=0 if "engagement_score" in df.columns else 0,
    )
    sort_asc = st.sidebar.checkbox("Ascending", value=False)

    filtered = df.copy()
    if sel_platforms and "platform" in filtered.columns:
        filtered = filtered[filtered["platform"].isin(sel_platforms)]
    if sel_keywords and "keyword" in filtered.columns:
        filtered = filtered[filtered["keyword"].isin(sel_keywords)]
    if has_price and "price" in filtered.columns:
        mask = filtered["price"].isna() | (
            (filtered["price"] >= lo) & (filtered["price"] <= hi)
        )
        filtered = filtered[mask]
    if "engagement_score" in filtered.columns:
        filtered = filtered[filtered["engagement_score"].fillna(0) >= min_engagement]

    if sort_col in filtered.columns:
        filtered = filtered.sort_values(sort_col, ascending=sort_asc, na_position="last")

    # Summary metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total rows", len(filtered))
    if "platform" in filtered.columns:
        c2.metric("Platforms", filtered["platform"].nunique())
    if "keyword" in filtered.columns:
        c3.metric("Keywords", filtered["keyword"].nunique())
    if has_price and len(filtered[filtered["price"].notna() & (filtered["price"] > 0)]):
        median = filtered.loc[filtered["price"] > 0, "price"].median()
        c4.metric("Median price", f"{median:,.2f}")
    else:
        c4.metric("Median price", "—")

    if "platform" in filtered.columns and len(filtered):
        st.subheader("Listings by platform")
        counts = filtered["platform"].value_counts()
        st.bar_chart(counts)

    if "keyword" in filtered.columns and has_price and len(filtered):
        priced = filtered[filtered["price"].notna() & (filtered["price"] > 0)]
        if len(priced):
            st.subheader("Average price by keyword")
            avg = priced.groupby("keyword")["price"].mean().sort_values(ascending=False)
            st.bar_chart(avg)

    display = filtered.copy()
    if "price" in display.columns:
        display["price_display"] = display.apply(format_price, axis=1)
    if "snippet" in display.columns:
        display["snippet"] = display["snippet"].fillna("").astype(str).str[:200]

    show_cols = [
        c
        for c in [
            "platform",
            "keyword",
            "title",
            "price_display",
            "price",
            "currency",
            "engagement_score",
            "comments",
            "date",
            "trend_score",
            "snippet",
            "url",
        ]
        if c in display.columns
    ]

    st.subheader(f"Results ({len(display)} rows)")
    st.dataframe(
        display[show_cols],
        use_container_width=True,
        column_config={
            "url": st.column_config.LinkColumn("url"),
            "snippet": st.column_config.TextColumn("snippet", width="large"),
            "title": st.column_config.TextColumn("title", width="medium"),
        },
        hide_index=True,
    )

    st.download_button(
        "Download filtered CSV",
        data=filtered.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"filtered_{selected}",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
