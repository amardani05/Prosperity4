from datamodel import OrderDepth, TradingState, Order
import json

class Trader:

    def bid(self):
        return 1000

    def run(self, state: TradingState):
        data = {}
        if state.traderData:
            try:
                data = json.loads(state.traderData)
            except Exception:
                data = {}

        result = {}

        if "ASH_COATED_OSMIUM" in state.order_depths:
            osm_state = data.get("osm", {})
            osm = OsmiumTrader("ASH_COATED_OSMIUM", state, osm_state)
            result["ASH_COATED_OSMIUM"] = osm.get_orders()
            data["osm"] = osm.export_state()

        if "INTARIAN_PEPPER_ROOT" in state.order_depths:
            pep_state = data.get("pep", {})
            pep = PepperTrader("INTARIAN_PEPPER_ROOT", state, pep_state)
            result["INTARIAN_PEPPER_ROOT"] = pep.get_orders()
            data["pep"] = pep.export_state()

        return result, 0, json.dumps(data)


# ── Base class ────────────────────────────────────────────────────────────────

class ProductTrader:
    def __init__(self, name: str, state: TradingState, position_limit: int):
        self.name = name
        self.position_limit = position_limit
        self.position = state.position.get(name, 0)
        self.order_depth: OrderDepth = state.order_depths[name]
        self.orders = []
        self.buy_capacity = position_limit - self.position
        self.sell_capacity = position_limit + self.position

        bids = self.order_depth.buy_orders
        asks = self.order_depth.sell_orders
        self.best_bid = max(bids) if bids else None
        self.best_ask = min(asks) if asks else None
        if self.best_bid is not None and self.best_ask is not None:
            self.mid = (self.best_bid + self.best_ask) / 2
        elif self.best_bid is not None:
            self.mid = self.best_bid
        elif self.best_ask is not None:
            self.mid = self.best_ask
        else:
            self.mid = None

    def buy(self, price: int, volume: int):
        if self.buy_capacity <= 0 or volume <= 0:
            return
        vol = min(volume, self.buy_capacity)
        self.orders.append(Order(self.name, int(price), int(vol)))
        self.buy_capacity -= vol

    def sell(self, price: int, volume: int):
        if self.sell_capacity <= 0 or volume <= 0:
            return
        vol = min(volume, self.sell_capacity)
        self.orders.append(Order(self.name, int(price), -int(vol)))
        self.sell_capacity -= vol


# ── ASH_COATED_OSMIUM ─────────────────────────────────────────────────────────
#
# Stationary but with a slowly-drifting true fair value. Training data shows
# daily means varying by ~1.5 ticks (10000 / 10001 / 10002), and the live
# submission data showed the mid running 5–10 ticks above a static FV=10001,
# which caused two problems:
#
#   1. We missed take-opportunities at 10001–10004 that were positive-edge
#      relative to the true mid but looked zero-or-negative vs static FV.
#   2. Flatten-buys at FV=10001 when short never reached the market, because
#      best_bid was 9999 and our 10001 order still sat 7–10 ticks below mid.
#      Meanwhile, passive-ask fills at best_ask-1 kept filling on upticks,
#      so we drifted short and couldn't cover.
#
# Fix: EMA-based dynamic FV.
#   - Slow α (0.001, effective span ~1000 ticks) so the FV doesn't chase noise
#   - Bootstrap at first observed mid when no prior state exists
#   - Round to int for price decisions (orders must be integer prices)
#
# With dynamic FV:
#   - Take-side catches near-mid asks/bids that were previously ignored
#   - Flatten orders land inside the spread (at mid), become best bid/ask,
#     and actually fill when aggressors cross — no more stuck inventory

class OsmiumTrader(ProductTrader):
    PRIOR_FV       = 10001     # bootstrap fallback if no mid available
    POSITION_LIMIT = 80
    FLATTEN_THRESH = 48
    EMA_ALPHA      = 0.005     # half-life ~138 ticks — adapts within a run

    def __init__(self, name, state, persisted: dict):
        super().__init__(name, state, position_limit=self.POSITION_LIMIT)

        prev_fv = persisted.get("ema_fv")
        if prev_fv is None:
            # First tick — anchor to current mid if we have one
            self.ema_fv = self.mid if self.mid is not None else self.PRIOR_FV
        elif self.mid is not None:
            self.ema_fv = self.EMA_ALPHA * self.mid + (1 - self.EMA_ALPHA) * prev_fv
        else:
            self.ema_fv = prev_fv

    def export_state(self) -> dict:
        return {"ema_fv": self.ema_fv}

    def get_orders(self):
        fv = round(self.ema_fv)

        # 1. Take positive-edge orders — but don't cross the flatten threshold.
        #    Greedy takes without this cap push inventory past ±FLATTEN_THRESH,
        #    which then fights the flatten logic below (flatten tries to unwind
        #    while takes keep adding). Cap take volume at the threshold so the
        #    two rules cooperate instead of compete.
        take_buy_budget = max(0, self.FLATTEN_THRESH - self.position)
        for price in sorted(self.order_depth.sell_orders):
            if price >= fv or take_buy_budget <= 0:
                break
            available = abs(self.order_depth.sell_orders[price])
            qty = min(available, take_buy_budget)
            self.buy(price, qty)
            take_buy_budget -= qty

        take_sell_budget = max(0, self.FLATTEN_THRESH + self.position)
        for price in sorted(self.order_depth.buy_orders, reverse=True):
            if price <= fv or take_sell_budget <= 0:
                break
            available = self.order_depth.buy_orders[price]
            qty = min(available, take_sell_budget)
            self.sell(price, qty)
            take_sell_budget -= qty

        # 2. Flatten if skewed, else passive-quote with positive edge
        if self.position > self.FLATTEN_THRESH:
            self.sell(fv, self.sell_capacity)
        elif self.position < -self.FLATTEN_THRESH:
            self.buy(fv, self.buy_capacity)
        else:
            if self.best_bid is not None and self.buy_capacity > 0:
                self.buy(min(self.best_bid + 1, fv - 1), self.buy_capacity)
            if self.best_ask is not None and self.sell_capacity > 0:
                self.sell(max(self.best_ask - 1, fv + 1), self.sell_capacity)

        return self.orders


# ── INTARIAN_PEPPER_ROOT ──────────────────────────────────────────────────────
#
# Unchanged from previous version: two-state machine (LONG +80 / SHORT −40),
# short-entry requires slope < −0.05 AND drawdown > 15, exit requires
# slope ≥ +0.05. Mode cooldown prevents whipsaw. Insurance against regime
# break; does not trigger on training data or on normal drift conditions.

class PepperTrader(ProductTrader):
    POSITION_LIMIT = 80
    SHORT_LIMIT    = 40

    HISTORY_LEN    = 500
    WINDOW         = 300

    SHORT_SLOPE      = -0.05
    REASSURE_SLOPE   =  0.05
    DRAWDOWN_CONFIRM = 15

    MODE_COOLDOWN    = 100

    def __init__(self, name, state, persisted: dict):
        super().__init__(name, state, position_limit=self.POSITION_LIMIT)
        self.mid_history   = list(persisted.get("mid_history", []))
        self.mode          = persisted.get("mode", "LONG")
        self.ticks_in_mode = persisted.get("ticks_in_mode", 0) + 1

        if self.mid is not None:
            self.mid_history.append(self.mid)
        if len(self.mid_history) > self.HISTORY_LEN:
            self.mid_history = self.mid_history[-self.HISTORY_LEN:]

    def export_state(self) -> dict:
        return {
            "mid_history":   self.mid_history,
            "mode":          self.mode,
            "ticks_in_mode": self.ticks_in_mode,
        }

    def _slope(self):
        if len(self.mid_history) < self.WINDOW:
            return None
        return (self.mid_history[-1] - self.mid_history[-self.WINDOW]) / self.WINDOW

    def _drawdown(self) -> float:
        if not self.mid_history:
            return 0.0
        return max(self.mid_history) - self.mid_history[-1]

    def _can_flip(self) -> bool:
        return self.ticks_in_mode >= self.MODE_COOLDOWN

    def _target_position(self) -> int:
        slope = self._slope()
        if slope is None:
            return self.POSITION_LIMIT

        if self.mode == "LONG":
            if (self._can_flip()
                and slope < self.SHORT_SLOPE
                and self._drawdown() > self.DRAWDOWN_CONFIRM):
                self.mode = "SHORT"
                self.ticks_in_mode = 0
                return -self.SHORT_LIMIT
            return self.POSITION_LIMIT

        # mode == SHORT
        if self._can_flip() and slope >= self.REASSURE_SLOPE:
            self.mode = "LONG"
            self.ticks_in_mode = 0
            return self.POSITION_LIMIT
        return -self.SHORT_LIMIT

    def get_orders(self):
        target = self._target_position()

        if self.position < target:
            remaining = target - self.position
            for price in sorted(self.order_depth.sell_orders):
                if remaining <= 0:
                    break
                take = min(remaining, abs(self.order_depth.sell_orders[price]))
                self.buy(price, take)
                remaining -= take

            if remaining > 0 and self.best_bid is not None:
                self.buy(self.best_bid + 1, remaining)

        elif self.position > target:
            remaining = self.position - target
            for price in sorted(self.order_depth.buy_orders, reverse=True):
                if remaining <= 0:
                    break
                hit = min(remaining, self.order_depth.buy_orders[price])
                self.sell(price, hit)
                remaining -= hit

            if remaining > 0 and self.best_ask is not None:
                self.sell(self.best_ask - 1, remaining)

        return self.orders