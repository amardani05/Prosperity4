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


class ProductTrader:
    def __init__(self, name: str, state: TradingState, position_limit: int = 50):
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
        self.mid = (
            (self.best_bid + self.best_ask) / 2
            if self.best_bid is not None and self.best_ask is not None
            else None
        )

    def buy(self, price: int, volume: int):
        if self.buy_capacity <= 0 or volume <= 0:
            return
        vol = min(volume, self.buy_capacity)
        self.orders.append(Order(self.name, int(price), vol))
        self.buy_capacity -= vol

    def sell(self, price: int, volume: int):
        if self.sell_capacity <= 0 or volume <= 0:
            return
        vol = min(volume, self.sell_capacity)
        self.orders.append(Order(self.name, int(price), -vol))
        self.sell_capacity -= vol


class OsmiumTrader(ProductTrader):
    FAIR_VALUE = 10000
    SKEW_FACTOR = 6  # more aggressive than 8

    def __init__(self, name, state):
        super().__init__(name, state, position_limit=50)

    def get_orders(self):
        if self.best_bid is None or self.best_ask is None:
            return self.orders

        fv = self.FAIR_VALUE

        # Take ALL mispriced orders across all levels
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

        # Passive quotes with tighter skew
        skew = self.position // self.SKEW_FACTOR

        if self.buy_capacity > 0:
            bid = min(self.best_bid + 1, fv - 1) - skew
            bid = min(bid, fv - 1)
            self.buy(bid, self.buy_capacity)

        if self.sell_capacity > 0:
            ask = max(self.best_ask - 1, fv + 1) - skew
            ask = max(ask, fv)  # floor at fair value, not fv-3
            self.sell(ask, self.sell_capacity)

        return self.orders


class PepperTrader(ProductTrader):
    """
    Core: stay max long to capture +1000/day drift.
    Extra: when at max position, sell small amounts at the ask
    to capture spread, then rebuy at the bid next tick.
    Drift cost of not holding 10 units for 1 tick = 10 * 0.1 = 1
    Spread earned from selling 10 units = 10 * ~6 = 60
    Net gain per scalp cycle: ~59
    """
    SCALP_SIZE = 10  # units to sell for spread capture
    
    def __init__(self, name, state):
        super().__init__(name, state, position_limit=50)

    def get_orders(self):
        if self.best_bid is None or self.best_ask is None:
            return self.orders

        at_max = self.position >= self.position_limit
        near_max = self.position >= self.position_limit - self.SCALP_SIZE

        if at_max:
            # Already max long — scalp the spread
            # Sell SCALP_SIZE at best ask to capture spread
            if self.best_ask is not None and self.sell_capacity > 0:
                scalp_vol = min(self.SCALP_SIZE, self.sell_capacity)
                self.sell(self.best_ask, scalp_vol)

            # Post bid to rebuy what we sold
            if self.buy_capacity > 0 and self.best_bid is not None:
                self.buy(self.best_bid + 1, self.buy_capacity)

        elif near_max:
            # Close to max — buy remaining, start scalping
            # Take asks to fill up
            for price in sorted(self.order_depth.sell_orders):
                if self.buy_capacity <= 0:
                    break
                self.buy(price, abs(self.order_depth.sell_orders[price]))

            # If we have sell capacity from scalp, sell at ask
            if self.position >= self.position_limit and self.sell_capacity > 0:
                scalp_vol = min(self.SCALP_SIZE, self.sell_capacity)
                self.sell(self.best_ask, scalp_vol)

            # Passive bid for remaining
            if self.buy_capacity > 0 and self.best_bid is not None:
                self.buy(self.best_bid + 1, self.buy_capacity)

        else:
            # Not yet max — get there as fast as possible
            # Take all asks
            for price in sorted(self.order_depth.sell_orders):
                if self.buy_capacity <= 0:
                    break
                self.buy(price, abs(self.order_depth.sell_orders[price]))

            # Passive bid for the rest
            if self.buy_capacity > 0 and self.best_bid is not None:
                self.buy(self.best_bid + 1, self.buy_capacity)

        return self.orders