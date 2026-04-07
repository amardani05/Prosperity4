from datamodel import OrderDepth, TradingState, Order

class Trader:
    def __init__(self):
        pass
        
    def run(self, state):
        result = {}

        emerald_trader = EmeraldTrader('EMERALDS', state)
        #tomato_trader = TomatoesTrader('TOMATOES', state)

        result["EMERALDS"] = emerald_trader.get_orders()
        #result["TOMATOES"] = tomato_trader.get_orders()

        conversions = 0
        traderData = ""
        return result, conversions, traderData

class ProductTrader:
    def __init__(self, name, state):
        self.name = name
        self.state = state

        # Pull the position and depth from state
        self.position = self.state.position.get(self.name, 0)
        try: self.order_depth: OrderDepth = self.state.order_depths[self.name]
        except: pass
        self.orders = []

        self.best_bid = max(self.order_depth.buy_orders.keys())
        self.best_ask = min(self.order_depth.sell_orders.keys())

        self.position_limit = 50
        self.buy_limit = self.position_limit - self.position
        self.sell_limit = self.position_limit + self.position

     # if Bid < Fair value 
        # Buy if pos limit < 50
    # if Ask > Fair value
        # Offload all inventory available, go short if ask volume is high enough
    def buy(self, price, volume):
        if (self.buy_limit <= 0):
            return
        actual_volume = min(volume, self.buy_limit)
        self.orders.append(Order(self.name, price, actual_volume))
        self.buy_limit -= actual_volume

    def sell(self, price, volume):
        if (self.sell_limit <= 0):
            return
        actual_volume = min(volume, self.sell_limit)
        self.orders.append(Order(self.name, price, -actual_volume))
        self.sell_limit -= actual_volume

    def get_total_volumes(self):
        market_bid_volume = market_ask_volume = 0
        try:
            market_bid_volume = sum([v for p, v in self.order_depth.buy_orders.items()])
            market_ask_volume = sum([v for p, v in self.order_depth.sell_orders.items()])
        except: pass
        return market_bid_volume, market_ask_volume

class EmeraldTrader(ProductTrader):
    def __init__(self, name, state):
        super().__init__(name, state)
        self.fair_value = 10000
    
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
        
        half_spread = int((self.best_ask - self.best_bid) / 2)
        self.buy(9996, self.buy_limit)
        self.sell(10004, self.sell_limit)

        return self.orders

# class TomatoesTrader(ProductTrader):