"""
IMC Prosperity Trade Visualizer
--------------------------------
Reads prices_round_X_day_Y.csv and trades_round_X_day_Y.csv,
then plots bid/ask price levels and trade markers per product.

Own-bot trades (buyer or seller == "SUBMISSION") are plotted as
large crosses (x) — green for buys, red for sells.
Market trades are plotted as small dots.
"""

import os
import sys
import zipfile
import glob
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D

# ── colour palette ────────────────────────────────────────────────────────────
BID_COLOR      = "#2196F3"   # blue
ASK_COLOR      = "#F44336"   # red
MID_COLOR      = "#9E9E9E"   # grey
OWN_BUY_COLOR  = "#00C853"   # bright green  (our bot buys)
OWN_SELL_COLOR = "#FF1744"   # bright red    (our bot sells)
MKT_COLOR      = "#FF9800"   # orange        (market trades)


# ── data loading ──────────────────────────────────────────────────────────────

def _read_csv_from_source(source: str, name_pattern: str) -> pd.DataFrame | None:
    """Read a CSV that may be inside a zip or a plain file on disk."""
    # Direct file match
    if os.path.isfile(source) and source.endswith(".csv"):
        return pd.read_csv(source, sep=";")

    # Zip file – find all entries matching pattern and concatenate
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as z:
            matches = sorted(n for n in z.namelist() if name_pattern in n and n.endswith(".csv"))
            if not matches:
                return None
            frames = []
            for name in matches:
                with z.open(name) as f:
                    frames.append(pd.read_csv(f, sep=";"))
            return pd.concat(frames, ignore_index=True)

    return None


def load_prices(source: str) -> pd.DataFrame:
    df = _read_csv_from_source(source, "prices")
    if df is None:
        raise FileNotFoundError(f"No prices CSV found in: {source}")
    df.columns = df.columns.str.strip()
    return df


def load_trades(source: str) -> pd.DataFrame:
    df = _read_csv_from_source(source, "trades")
    if df is None:
        print(f"[warn] No trades CSV found in: {source}. Skipping trade markers.")
        return pd.DataFrame()
    df.columns = df.columns.str.strip()
    # Normalise column names across formats
    df.columns = [c.lower() for c in df.columns]
    for col in ("buyer", "seller"):
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].fillna("")
    return df


# ── plotting ──────────────────────────────────────────────────────────────────

def _add_legend(ax):
    handles = [
        Line2D([0], [0], color=BID_COLOR,      lw=1.5, label="Bid"),
        Line2D([0], [0], color=ASK_COLOR,       lw=1.5, label="Ask"),
        Line2D([0], [0], color=MID_COLOR,       lw=1,   linestyle="--", label="Mid"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=MKT_COLOR,
               markersize=6, label="Market trade"),
        Line2D([0], [0], marker="x", color=OWN_BUY_COLOR,
               markersize=9, markeredgewidth=2, label="Our buy"),
        Line2D([0], [0], marker="x", color=OWN_SELL_COLOR,
               markersize=9, markeredgewidth=2, label="Our sell"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=8, framealpha=0.7)


def plot_product(prices_df: pd.DataFrame, trades_df: pd.DataFrame,
                 product: str, ax_price, ax_spread, ax_pnl):
    """Draw price chart + spread + P&L for a single product on the supplied axes."""
    p = prices_df[prices_df["product"].str.upper() == product.upper()].copy()
    if p.empty:
        ax_price.set_title(f"{product} – no data")
        return

    p = p.sort_values("timestamp").copy()
    # Replace mid_price=0 (both sides absent) with NaN so the line gaps instead of dipping to 0
    p.loc[p["mid_price"] == 0, "mid_price"] = float("nan")
    ts = p["timestamp"]

    # ── price levels ──
    ax_price.plot(ts, p["bid_price_1"], color=BID_COLOR, lw=1.2, label="Bid 1")
    ax_price.plot(ts, p["ask_price_1"], color=ASK_COLOR, lw=1.2, label="Ask 1")

    if "bid_price_2" in p.columns:
        ax_price.plot(ts, p["bid_price_2"], color=BID_COLOR, lw=0.6, alpha=0.45)
    if "ask_price_2" in p.columns:
        ax_price.plot(ts, p["ask_price_2"], color=ASK_COLOR, lw=0.6, alpha=0.45)
    if "bid_price_3" in p.columns:
        ax_price.plot(ts, p["bid_price_3"], color=BID_COLOR, lw=0.4, alpha=0.25)
    if "ask_price_3" in p.columns:
        ax_price.plot(ts, p["ask_price_3"], color=ASK_COLOR, lw=0.4, alpha=0.25)

    ax_price.plot(ts, p["mid_price"], color=MID_COLOR, lw=1, linestyle="--", alpha=0.7)

    # ── market trades ──
    if not trades_df.empty:
        sym_col = next((c for c in trades_df.columns if c in ("symbol", "product")), None)
        if sym_col:
            t = trades_df[trades_df[sym_col].str.upper() == product.upper()].copy()
        else:
            t = trades_df.copy()

        # Separate own vs market trades
        is_own = (t["buyer"].str.upper() == "SUBMISSION") | (t["seller"].str.upper() == "SUBMISSION")
        mkt = t[~is_own]
        own = t[is_own]

        # Market trades → small dots
    
        if not mkt.empty:
            ax_price.scatter(mkt["timestamp"], mkt["price"],
                             color=MKT_COLOR, s=15, zorder=3, alpha=0.6)

        # Own trades → crosses (green = we bought, red = we sold)
        if not own.empty:
            own_buys  = own[own["buyer"].str.upper()  == "SUBMISSION"]
            own_sells = own[own["seller"].str.upper() == "SUBMISSION"]

            if not own_buys.empty:
                ax_price.scatter(own_buys["timestamp"], own_buys["price"],
                                 marker="x", color=OWN_BUY_COLOR, s=120,
                                 linewidths=2.5, zorder=5, label="Our buy")

            if not own_sells.empty:
                ax_price.scatter(own_sells["timestamp"], own_sells["price"],
                                 marker="x", color=OWN_SELL_COLOR, s=120,
                                 linewidths=2.5, zorder=5, label="Our sell")

    ax_price.set_title(product, fontsize=11, fontweight="bold")
    ax_price.set_ylabel("Price")
    ax_price.yaxis.set_minor_locator(mticker.AutoMinorLocator())
    ax_price.grid(True, which="major", alpha=0.3)
    ax_price.grid(True, which="minor", alpha=0.1)
    _add_legend(ax_price)

    # ── auto-scale Y to actual price range with padding ──
    price_cols = [c for c in ("bid_price_1", "ask_price_1", "bid_price_2", "ask_price_2",
                               "bid_price_3", "ask_price_3", "mid_price") if c in p.columns]
    all_prices = p[price_cols].stack().dropna()
    all_prices = all_prices[all_prices > 0]   # exclude zero placeholders
    if not all_prices.empty:
        lo, hi = all_prices.min(), all_prices.max()
        pad = max((hi - lo) * 0.1, 1)
        ax_price.set_ylim(lo - pad, hi + pad)

    # ── spread ──
    if "bid_price_1" in p.columns and "ask_price_1" in p.columns:
        spread = p["ask_price_1"] - p["bid_price_1"]
        ax_spread.plot(ts, spread, color="#FFD600", lw=1.2)
        ax_spread.axhline(spread.mean(), color="#888", lw=0.8, linestyle="--")
        ax_spread.fill_between(ts, spread, spread.mean(),
                               where=spread >= spread.mean(),
                               interpolate=True, alpha=0.2, color="#FFD600")
        ax_spread.set_ylabel("Spread", fontsize=8)
        ax_spread.grid(True, alpha=0.25)

    # ── P&L ──
    if "profit_and_loss" in p.columns:
        ax_pnl.plot(ts, p["profit_and_loss"], color="#7B1FA2", lw=1.4)
        ax_pnl.axhline(0, color="#555", lw=0.8, linestyle="--")
        ax_pnl.fill_between(ts, p["profit_and_loss"], 0,
                             where=p["profit_and_loss"] >= 0,
                             interpolate=True, alpha=0.15, color="#4CAF50")
        ax_pnl.fill_between(ts, p["profit_and_loss"], 0,
                             where=p["profit_and_loss"] < 0,
                             interpolate=True, alpha=0.15, color="#F44336")
        ax_pnl.set_ylabel("P&L")
        ax_pnl.grid(True, alpha=0.25)


def visualize(prices_source: str, trades_source: str | None = None,
              products: list[str] | None = None):
    prices_df = load_prices(prices_source)
    trades_df = load_trades(trades_source or prices_source)

    all_products = sorted(prices_df["product"].str.upper().unique())
    if products:
        products = [p.upper() for p in products]
    else:
        products = all_products

    n = len(products)
    fig, axes = plt.subplots(
        nrows=n * 3, ncols=1,
        figsize=(14, 6 * n),
        gridspec_kw={"height_ratios": [4, 1, 1] * n},
        sharex=False,
    )
    if n == 1:
        axes = list(axes)

    fig.suptitle("IMC Prosperity – Price & Trade Visualizer", fontsize=13, fontweight="bold")
    fig.patch.set_facecolor("#1E1E2E")

    for ax in axes:
        ax.set_facecolor("#12121C")
        for spine in ax.spines.values():
            spine.set_edgecolor("#444")
        ax.tick_params(colors="#CCC")
        ax.yaxis.label.set_color("#CCC")
        ax.title.set_color("#EEE")

    for i, product in enumerate(products):
        ax_price  = axes[i * 3]
        ax_spread = axes[i * 3 + 1]
        ax_pnl    = axes[i * 3 + 2]
        plot_product(prices_df, trades_df, product, ax_price, ax_spread, ax_pnl)
        ax_pnl.set_xlabel("Timestamp", color="#CCC")

    plt.tight_layout()
    plt.show()


# ── CLI entry point ───────────────────────────────────────────────────────────

def _find_default_source() -> str | None:
    """Auto-detect a zip or CSV in the current working directory."""
    for pattern in ("*.zip", "prices_*.csv"):
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualize IMC Prosperity price & trade data.")
    parser.add_argument("prices",  nargs="?", help="Path to prices CSV or zip file (auto-detected if omitted)")
    parser.add_argument("trades",  nargs="?", help="Path to trades CSV (optional, can be same zip as prices)")
    parser.add_argument("-p", "--products", nargs="+", help="Products to display (default: all)")
    args = parser.parse_args()

    prices_src = args.prices or _find_default_source()
    if prices_src is None:
        print("Error: no prices CSV or zip found. Pass a path as the first argument.")
        sys.exit(1)

    visualize(prices_src, args.trades, args.products)
