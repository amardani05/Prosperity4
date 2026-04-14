from datamodel import OrderDepth, TradingState, Order
import json
 
POS_LIMITS = {
    'ASH_COATED_OSMIUM': 50,
    'INTARIAN_PEPPER_ROOT': 50,
}
 
class Trader:
    def __init__(self):
        pass
 
    def run(self, state):
        print(list(state.order_depths.keys()))
        result = {}
        trader_data = {}
        if state.traderData:
            try: trader_data = json.loads(state.traderData)
            except: pass
        
        try:
            osmium_trader = OsmiumTrader('ASH_COATED_OSMIUM', state)
            result['ASH_COATED_OSMIUM'] = osmium_trader.get_orders()
        except Exception as e:
            print(f"OSMIUM ERROR: {e}")
            result['ASH_COATED_OSMIUM'] = []

        try:
            pepper_root_trader = PepperRootTrader('INTARIAN_PEPPER_ROOT', state, trader_data)
            result['INTARIAN_PEPPER_ROOT'] = pepper_root_trader.get_orders()
        except Exception as e:
            print(f"PEPPER ERROR: {e}")
            result['INTARIAN_PEPPER_ROOT'] = []
 
        conversions = 0
        traderData = json.dumps(trader_data)
        return result, conversions, traderData
 
class ProductTrader:
    def __init__(self, name, state):
        self.name = name
        self.state = state
 
        self.position = self.state.position.get(self.name, 0)
        if self.name in self.state.order_depths:
            self.order_depth = self.state.order_depths[self.name]
        else:
            self.order_depth = OrderDepth()
        self.orders = []
 
        if self.order_depth.buy_orders and self.order_depth.sell_orders:
            self.best_bid = max(self.order_depth.buy_orders.keys())
            self.best_ask = min(self.order_depth.sell_orders.keys())
        else:
            self.best_bid = None
            self.best_ask = None
 
        self.position_limit = POS_LIMITS.get(name, 80)
        self.buy_limit = self.position_limit - self.position
        self.sell_limit = self.position_limit + self.position
 
    def buy(self, price, volume):
        if self.buy_limit <= 0 or volume <= 0:
            return
        actual_volume = min(volume, self.buy_limit)
        self.orders.append(Order(self.name, int(price), actual_volume))
        self.buy_limit -= actual_volume
 
    def sell(self, price, volume):
        if self.sell_limit <= 0 or volume <= 0:
            return
        actual_volume = min(volume, self.sell_limit)
        self.orders.append(Order(self.name, int(price), -actual_volume))
        self.sell_limit -= actual_volume
 
    def get_total_volumes(self):
        market_bid_volume = market_ask_volume = 0
        if self.order_depth.buy_orders:
            market_bid_volume = sum(v for p, v in self.order_depth.buy_orders.items())
        if self.order_depth.sell_orders:
            market_ask_volume = sum(abs(v) for p, v in self.order_depth.sell_orders.items())
        return market_bid_volume, market_ask_volume
 
 
class OsmiumTrader(ProductTrader):
    """
    Static asset ~10,000. Spread 16. Same as EMERALDS.
    Take anything mispriced, penny the book, skew by position.
    """
    def __init__(self, name, state):
        super().__init__(name, state)
        self.fair_value = int((self.best_bid + self.best_ask) / 2)
        self.skew_factor = 10
 
    def get_orders(self):
        if self.best_bid is None or self.best_ask is None:
            return self.orders
        
        print(f"best_bid={self.best_bid}, best_ask={self.best_ask}, fair={self.fair_value}, pos={self.position}")
        print(f"sell_orders={self.order_depth.sell_orders}")
        print(f"buy_orders={self.order_depth.buy_orders}")
 
        # Take mispriced orders — sweep all levels
        for price, qty in sorted(self.order_depth.sell_orders.items()):
            if price < self.fair_value:
                self.buy(price, abs(qty))
            elif price == self.fair_value and self.position < 0:
                self.buy(price, min(abs(qty), abs(self.position)))
 
        for price, qty in sorted(self.order_depth.buy_orders.items(), reverse=True):
            if price > self.fair_value:
                self.sell(price, qty)
            elif price == self.fair_value and self.position > 0:
                self.sell(price, min(qty, self.position))
 
        skew = self.position // self.skew_factor
 
        passive_bid = min(self.fair_value - 1, self.best_bid + 1) - skew
        passive_ask = max(self.fair_value + 1, self.best_ask - 1) - skew
 
        passive_bid = min(passive_bid, self.fair_value - 1)
        passive_ask = max(passive_ask, self.fair_value + 1)
 
        self.buy(passive_bid, self.buy_limit)
        self.sell(passive_ask, self.sell_limit)

        print(f"ORDERS: {[(o.price, o.quantity) for o in self.orders]}")

        return self.orders
 
 
class PepperRootTrader(ProductTrader):
    """
    Drifting asset, ~1000/day upward trend. Spread 11-14.
    Dynamic fair value from book mid. Imbalance skew. Aggressive spreads.
    """
    def __init__(self, name, state, trader_data):
        super().__init__(name, state)
        self.trader_data = trader_data
        self.scaling_factor = 10
        if self.best_bid is not None and self.best_ask is not None:
            self.fair_value = int((self.best_bid + self.best_ask) / 2)
        else:
            self.fair_value = None
 
    def get_orders(self):
        if self.best_bid is None or self.best_ask is None or self.fair_value is None:
            return self.orders
 
        for price, qty in sorted(self.order_depth.sell_orders.items()):
            if price < self.fair_value:
                self.buy(price, abs(qty))
            elif price == self.fair_value and self.position < 0:
                self.buy(price, min(abs(qty), abs(self.position)))
 
        for price, qty in sorted(self.order_depth.buy_orders.items(), reverse=True):
            if price > self.fair_value:
                self.sell(price, qty)
            elif price == self.fair_value and self.position > 0:
                self.sell(price, min(qty, self.position))
 
        half_spread = max(int((self.best_ask - self.best_bid) / 2) - 1, 2)
 
        bid_vol, ask_vol = self.get_total_volumes()
        if (bid_vol + ask_vol) == 0:
            imbalance = 0
        else:
            imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol)
 
        adjusted_fair = int(self.fair_value - (imbalance * self.scaling_factor))
 
        self.buy(adjusted_fair - half_spread, self.buy_limit)
        self.sell(adjusted_fair + half_spread, self.sell_limit)
 
        return self.orders