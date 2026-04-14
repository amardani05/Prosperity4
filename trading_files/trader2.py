from datamodel import OrderDepth, TradingState, Order

class Trader:
    def __init__(self):
        pass
        
    def run(self, state):
        result = {}

        emerald_trader = EmeraldTrader('EMERALDS', state)
        tomato_trader = TomatoesTrader('TOMATOES', state)

        result["EMERALDS"] = emerald_trader.get_orders()
        result["TOMATOES"] = tomato_trader.get_orders()

        conversions = 0
        traderData = ""
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

        self.position_limit = 50
        self.buy_limit = self.position_limit - self.position
        self.sell_limit = self.position_limit + self.position

    def buy(self, price, volume):
        if self.buy_limit <= 0:
            return
        actual_volume = min(volume, self.buy_limit)
        self.orders.append(Order(self.name, price, actual_volume))
        self.buy_limit -= actual_volume

    def sell(self, price, volume):
        if self.sell_limit <= 0:
            return
        actual_volume = min(volume, self.sell_limit)
        self.orders.append(Order(self.name, price, -actual_volume))
        self.sell_limit -= actual_volume

    def get_total_volumes(self):
        market_bid_volume = market_ask_volume = 0
        if self.order_depth.buy_orders:
            market_bid_volume = sum([v for p, v in self.order_depth.buy_orders.items()])
        if self.order_depth.sell_orders:
            market_ask_volume = sum([abs(v) for p, v in self.order_depth.sell_orders.items()])
        return market_bid_volume, market_ask_volume

class EmeraldTrader(ProductTrader):
    def __init__(self, name, state):
        super().__init__(name, state)
        self.fair_value = 10000
        self.skew_factor = 10

    def get_orders(self):
        if self.best_bid is None or self.best_ask is None:
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
                self.sell(price, min(abs(qty), self.position))

        # shift quotes to offload inventory
        skew = self.position // self.skew_factor

        # Penny the best bid/ask and away from 10K
        passive_bid = min(9999, self.best_bid + 1) - skew
        passive_ask = max(10001, self.best_ask - 1) - skew

        # never cross fair value
        passive_bid = min(passive_bid, self.fair_value - 1)
        passive_ask = max(passive_ask, self.fair_value + 1)

        self.buy(passive_bid, self.buy_limit)
        self.sell(passive_ask, self.sell_limit)

        return self.orders

class TomatoesTrader(ProductTrader):
    def __init__(self, name, state):
        super().__init__(name, state)
        self.fair_value = int((self.best_bid + self.best_ask) / 2)
        self.scaling_factor = 20
        self.position_skew_factor = 0.2
    
    def get_orders(self):
        for order in self.order_depth.sell_orders.items():
            if (order[0] < self.fair_value):
                self.buy(order[0], abs(order[1]))
            if (order[0] == self.fair_value and self.position < 0):
                self.buy(order[0], min(abs(order[1]), abs(self.position)))

        for order in self.order_depth.buy_orders.items():
            if (order[0] > self.fair_value):
                self.sell(order[0], order[1])
            if (order[0] == self.fair_value and self.position > 0):
                self.sell(order[0], min(abs(order[1]), abs(self.position)))
        
        half_spread = max(int((self.best_ask - self.best_bid) / 2) - 1, 3)
        current_spread = self.best_ask - self.best_bid
        if current_spread < 8:
            half_spread += 2

        bid_vol, ask_vol = self.get_total_volumes()
        if (bid_vol + ask_vol) == 0:
            imbalance = 0
        else:
            imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol)
        adjusted_fair = int(self.fair_value - (imbalance * self.scaling_factor) - (self.position * self.position_skew_factor))

        self.buy(adjusted_fair - half_spread, self.buy_limit)
        self.sell(adjusted_fair + half_spread, self.sell_limit)

        return self.orders