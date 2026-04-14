from datamodel import OrderDepth, TradingState, Order
import json


class Trader:
    def run(self, state: TradingState):
        data = {}
        if state.traderData:
            try:
                data = json.loads(state.traderData)
            except Exception:
                data = {}

        result = {}

        if "ASH_COATED_OSMIUM" in state.order_depths:
            result["ASH_COATED_OSMIUM"] = OsmiumTrader("ASH_COATED_OSMIUM", state).get_orders()

        if "INTARIAN_PEPPER_ROOT" in state.order_depths:
            result["INTARIAN_PEPPER_ROOT"] = PepperTrader("INTARIAN_PEPPER_ROOT", state).get_orders()

        return result, 0, json.dumps(data)


# ── Base class ────────────────────────────────────────────────────────────────

class ProductTrader:
    def __init__(self, name: str, state: TradingState, position_limit: int = 50):
        self.name = name
        self.position_limit = position_limit
        self.position = state.position.get(name, 0)
        self.order_depth: OrderDepth = state.order_depths[name]
        self.orders = []
        self.buy_capacity  = position_limit - self.position
        self.sell_capacity = position_limit + self.position

        bids = self.order_depth.buy_orders
        asks = self.order_depth.sell_orders
        self.best_bid = max(bids) if bids else None
        self.best_ask = min(asks) if asks else None
        self.mid = (
            (self.best_bid + self.best_ask) / 2 if self.best_bid and self.best_ask
            else self.best_bid or self.best_ask
        )

    def buy(self, price: int, volume: int):
        if self.buy_capacity <= 0 or volume <= 0:
            return
        vol = min(volume, self.buy_capacity)
        self.orders.append(Order(self.name, price, vol))
        self.buy_capacity -= vol

    def sell(self, price: int, volume: int):
        if self.sell_capacity <= 0 or volume <= 0:
            return
        vol = min(volume, self.sell_capacity)
        self.orders.append(Order(self.name, price, -vol))
        self.sell_capacity -= vol


# ── ASH_COATED_OSMIUM ─────────────────────────────────────────────────────────
#
# Mean-reverting tightly around 10000 (confirmed from data).
# Spread is wide (~16 ticks: bid ~9992, ask ~10008).
#
# Strategy:
#   1. Take any order that crosses 10000 immediately.
#   2. Post passive quotes pennying best bid/ask to earn the spread.
#   3. Skew quotes toward zero inventory when position builds.
#      — bid shifts down when long (discourage buying more)
#      — ask shifts down when long (encourage selling)
#      BUT: cap ask at fv-3 minimum so we never sell deep below fair value.

class OsmiumTrader(ProductTrader):
    FAIR_VALUE  = 10000
    SKEW_FACTOR = 8   # position / skew_factor = tick offset per quote

    def __init__(self, name, state):
        super().__init__(name, state, position_limit=50)

    def get_orders(self):
        fv = self.FAIR_VALUE

        # 1. Take orders that cross fair value
        for price in sorted(self.order_depth.sell_orders):
            if price < fv:
                self.buy(price, abs(self.order_depth.sell_orders[price]))
            elif price == fv and self.position < 0:
                self.buy(price, min(abs(self.order_depth.sell_orders[price]), abs(self.position)))

        for price in sorted(self.order_depth.buy_orders, reverse=True):
            if price > fv:
                self.sell(price, self.order_depth.buy_orders[price])
            elif price == fv and self.position > 0:
                self.sell(price, min(self.order_depth.buy_orders[price], self.position))

        # 2. Passive quotes with inventory skew
        skew = self.position // self.SKEW_FACTOR  # positive when long → shifts both quotes down

        if self.best_bid is not None and self.buy_capacity > 0:
            bid = min(self.best_bid + 1, fv - 1) - skew
            self.buy(bid, self.buy_capacity)

        if self.best_ask is not None and self.sell_capacity > 0:
            ask = max(self.best_ask - 1, fv + 1) - skew
            # Never let ask drop below fv-3; don't give away product for nothing
            ask = max(ask, fv - 3)
            self.sell(ask, self.sell_capacity)

        return self.orders


# ── INTARIAN_PEPPER_ROOT ──────────────────────────────────────────────────────
#
# Confirmed from data: price rises at EXACTLY +0.1/tick (+1000 per 10k-tick day).
# Day -2: 9998 → 11002   Day -1: 10995 → 11998   Day 0: 11994 → 13007
#
# The original EMA approach (alpha=0.02) was completely inactive:
#   - EMA lags ~2-10 ticks behind mid at steady state
#   - passive bid ended up 3 ticks BELOW best bid → never filled
#   - passive ask ended up 11 ticks ABOVE best ask → never filled
#   - take condition (ask <= ema) never triggered since asks are above ema
#
# Correct strategy: DON'T market make. The trend is too strong.
# Just STAY MAXIMUM LONG at all times:
#   - Each tick the position is worth +0.1 more seashells per unit
#   - 50 units × +1000/day = +50,000 P&L per day from holding alone
#   - Spread cost to enter (~7 ticks × 50 units = 350) is negligible
#
# Implementation:
#   - Take all available asks to fill to position limit immediately
#   - Post a passive bid at best_bid+1 so we refill if ever reduced
#   - Never post asks (we always want to hold)

class PepperTrader(ProductTrader):

    def __init__(self, name, state):
        super().__init__(name, state, position_limit=50)

    def get_orders(self):
        # Take every available ask until we hit the position limit
        for price in sorted(self.order_depth.sell_orders):
            if self.buy_capacity <= 0:
                break
            self.buy(price, abs(self.order_depth.sell_orders[price]))

        # Passive bid just above best bid to stay filled between ticks
        if self.buy_capacity > 0 and self.best_bid is not None:
            self.buy(self.best_bid + 1, self.buy_capacity)

        # No asks — we never want to sell into a rising trend

        return self.orders
