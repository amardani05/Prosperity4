"""
Local backtester for IMC Prosperity
------------------------------------
Replays the order book tick by tick, runs your Trader, matches orders,
and outputs:
  - my_trades.csv   → bot's fills (feed to visualizer as the trades file)
  - my_prices.csv   → prices with your bot's P&L in the profit_and_loss column

Usage:
    python backtester.py                        # uses ROUND_1.zip
    python backtester.py path/to/round.zip

Then visualize:
    python visualizer.py my_prices.csv my_trades.csv
"""

import sys
import json
import zipfile
import pandas as pd
from datamodel import OrderDepth, TradingState, Order

POSITION_LIMIT = 50


def build_order_depth(row: pd.Series) -> OrderDepth:
    depth = OrderDepth()
    for i in range(1, 4):
        bp = row.get(f"bid_price_{i}")
        bv = row.get(f"bid_volume_{i}")
        ap = row.get(f"ask_price_{i}")
        av = row.get(f"ask_volume_{i}")
        if pd.notna(bp) and pd.notna(bv) and bp > 0:
            depth.buy_orders[int(bp)] = int(bv)
        if pd.notna(ap) and pd.notna(av) and ap > 0:
            depth.sell_orders[int(ap)] = -int(av)
    return depth


def match_orders(orders, depth: OrderDepth, position: int):
    """Match a list of Orders against the current order book snapshot.
    Returns list of (price, qty_signed) fills and updated position."""
    fills = []
    pos = position

    for order in orders:
        qty   = order.quantity   # positive = buy, negative = sell
        price = order.price

        if qty > 0:  # buy — match against sell orders at price <= order.price
            for ask in sorted(depth.sell_orders):
                if ask > price or qty == 0:
                    break
                available = abs(depth.sell_orders[ask])
                fill = min(qty, available, POSITION_LIMIT - pos)
                if fill <= 0:
                    continue
                fills.append((ask, fill))
                pos += fill
                qty -= fill

        elif qty < 0:  # sell — match against buy orders at price >= order.price
            to_sell = abs(qty)
            for bid in sorted(depth.buy_orders, reverse=True):
                if bid < price or to_sell == 0:
                    break
                available = depth.buy_orders[bid]
                fill = min(to_sell, available, POSITION_LIMIT + pos)
                if fill <= 0:
                    continue
                fills.append((bid, -fill))
                pos -= fill
                to_sell -= fill

    return fills, pos


def run(zip_path: str):
    # ── load all price data ───────────────────────────────────────────────────
    with zipfile.ZipFile(zip_path) as z:
        frames = []
        for name in sorted(n for n in z.namelist() if "prices" in n and n.endswith(".csv")):
            with z.open(name) as f:
                frames.append(pd.read_csv(f, sep=";"))

    prices = pd.concat(frames, ignore_index=True)
    prices.columns = [c.strip() for c in prices.columns]
    prices = prices.sort_values(["day", "timestamp"]).reset_index(drop=True)
    prices["profit_and_loss"] = 0.0   # will be filled in with bot P&L

    # ── import the trader ────────────────────────────────────────────────────
    from Round_1_Trader_demo import Trader
    trader = Trader()

    # ── state ────────────────────────────────────────────────────────────────
    trader_data = ""
    positions   = {}      # product → int
    realized    = {}      # product → float  (cash flow from trades)
    trade_rows  = []

    # ── main loop ────────────────────────────────────────────────────────────
    grouped = prices.groupby(["day", "timestamp"], sort=False)

    for (day, ts), group in grouped:

        # Build order depths for this tick
        order_depths = {row["product"]: build_order_depth(row)
                        for _, row in group.iterrows()}

        state = TradingState(
            traderData   = trader_data,
            timestamp    = int(ts),
            listings     = {},
            order_depths = order_depths,
            own_trades   = {},
            market_trades= {},
            position     = dict(positions),
            observations = None,
        )

        try:
            result, _, trader_data = trader.run(state)
        except Exception as e:
            print(f"[error] day={day} ts={ts}: {e}")
            continue

        # Match and record fills
        for product, orders in result.items():
            if product not in order_depths:
                continue

            pos    = positions.get(product, 0)
            fills, new_pos = match_orders(orders, order_depths[product], pos)

            for fill_price, fill_qty in fills:
                buyer  = "SUBMISSION" if fill_qty > 0 else ""
                seller = "SUBMISSION" if fill_qty < 0 else ""
                trade_rows.append({
                    "timestamp": ts,
                    "buyer":     buyer,
                    "seller":    seller,
                    "symbol":    product,
                    "currency":  "XIRECS",
                    "price":     fill_price,
                    "quantity":  abs(fill_qty),
                })
                realized[product] = realized.get(product, 0.0) - fill_qty * fill_price

            positions[product] = new_pos

        # Mark-to-market P&L per product, written back into prices DataFrame
        for _, row in group.iterrows():
            product = row["product"]
            mid     = row["mid_price"]
            if mid <= 0:
                continue
            pos   = positions.get(product, 0)
            real  = realized.get(product, 0.0)
            pnl   = real + pos * mid
            mask  = (prices["day"] == day) & (prices["timestamp"] == ts) & (prices["product"] == product)
            prices.loc[mask, "profit_and_loss"] = pnl

    # ── output ───────────────────────────────────────────────────────────────
    trades_df = pd.DataFrame(trade_rows)
    trades_df.to_csv("my_trades.csv", sep=";", index=False)
    prices.to_csv("my_prices.csv",   sep=";", index=False)

    # ── summary ──────────────────────────────────────────────────────────────
    print(f"\n{'─'*40}")
    print(f"Total fills: {len(trades_df)}")
    if not trades_df.empty:
        for sym, g in trades_df.groupby("symbol"):
            buys  = g[g["buyer"]  == "SUBMISSION"]["quantity"].sum()
            sells = g[g["seller"] == "SUBMISSION"]["quantity"].sum()
            print(f"  {sym}: bought {buys}  sold {sells}")
    print(f"\nFinal positions: {positions}")
    for p, r in realized.items():
        mid_row = prices[prices["product"] == p].sort_values("timestamp").iloc[-1]
        mid = mid_row["mid_price"] if mid_row["mid_price"] > 0 else 0
        pnl = r + positions.get(p, 0) * mid
        print(f"  {p} P&L: {pnl:,.0f}")
    print(f"\nSaved: my_trades.csv  my_prices.csv")
    print(f"Visualize with: python visualizer.py my_prices.csv my_trades.csv")


if __name__ == "__main__":
    zip_path = sys.argv[1] if len(sys.argv) > 1 else "ROUND_1.zip"
    run(zip_path)
