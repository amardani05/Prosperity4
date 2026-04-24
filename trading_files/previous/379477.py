"""
IMC Prosperity Round 3 — IV Scalping + VFE Mean Reversion
==========================================================
Strategy from top-team write-up (Volcanic Rock / Vouchers):

IV SCALPING  (primary alpha ~100-150k/round)
  1. Compute implied vol for VEV_5000..VEV_5500 each tick.
  2. Fit quadratic parabola to IV vs log-moneyness → smile-fitted sigma per strike.
  3. Compute smile-fair BSM price per strike.
  4. Track a SLOW EWM of (market_price − smile_fair) per strike.
     This absorbs systematic parabola-fit biases so the signal is zero-mean.
  5. Signal = current_deviation − slow_EWM_baseline.
     Signal > +THRESH → option temporarily rich → SELL
     Signal < −THRESH → option temporarily cheap → BUY
  6. Passive quotes at floor/ceil of smile_fair to capture spread.

VFE MEAN REVERSION  (secondary, volatile)
  Fast EMA on VFE mid; lag-1 return autocorr = -0.17.
  Passive limit orders at EMA ± 3 ticks; aggressive take at ± 6.

VEV_4000 AS VFE PROXY
  Delta ≈ 1.0, same MR signal as VFE but with higher position limit (300 vs 200).
  Gives more capacity for the mean-reversion component.

HP  mean-reversion MM around 10 000 (unchanged).

NO DELTA HEDGING  (reference team: "prohibitively expensive bid-ask spreads").
"""

from datamodel import OrderDepth, TradingState, Order
import json
import math

# ─── Products ────────────────────────────────────────────────────────────────
VOUCHER_STRIKES: dict[str, int] = {
    "VEV_4000": 4000, "VEV_4500": 4500,
    "VEV_5000": 5000, "VEV_5100": 5100,
    "VEV_5200": 5200, "VEV_5300": 5300,
    "VEV_5400": 5400, "VEV_5500": 5500,
}
# Only these have reliable IV for smile fitting (near-ATM)
SMILE_STRIKES: dict[str, int] = {k: v for k, v in VOUCHER_STRIKES.items() if v >= 5000}

LIMITS: dict[str, int] = {
    "HYDROGEL_PACK": 200,
    "VELVETFRUIT_EXTRACT": 200,
    **{k: 300 for k in VOUCHER_STRIKES},
}

# ─── Calibrated initial sigma per strike (from historical data) ───────────────
SIGMA_INIT: dict[int, float] = {
    4000: 0.0436,  4500: 0.0246,
    5000: 0.01261, 5100: 0.01259, 5200: 0.01265,
    5300: 0.01275, 5400: 0.01203, 5500: 0.01297,
}

# ─── Tuning ───────────────────────────────────────────────────────────────────
TTE_START      = 5.0        # days to expiry at Round 3 ts=0
TICKS_PER_DAY  = 1_000_000  # ts range: 0..999900 step 100

SIGMA_LO, SIGMA_HI = 0.005, 0.08

# IV scalping
DEV_SLOW_ALPHA = 0.002   # slow EWM for per-strike deviation baseline (~350-tick half-life)
DEV_FAST_ALPHA = 0.15    # fast EWM of current deviation (smooths noise)
SCALP_THRESH   = 0.75    # signal ticks to take aggressively
SCALP_SIZE     = 20      # units per quote
MAX_LEAN       = 2       # max inventory lean in ticks
LEAN_PER_UNIT  = 150     # 1 tick lean per N units of position

# VFE mean reversion
VFE_EMA_ALPHA  = 0.1     # half-life ~7 ticks
VFE_MR_THRESH  = 3.0     # passive quote distance from EMA (ticks)
VFE_MR_AGGR    = 6.0     # aggressively take beyond this
VFE_MR_SIZE    = 15
VFE_MR_CAP     = 80      # max |pos| from MR

# VEV_4000 mean-reversion proxy
V4K_MR_SIZE    = 10
V4K_TAKE_EDGE  = 3       # ticks of clear edge to take

# HP – pure market-making, no fixed fair value
HP_QUOTE_SIZE = 15    # units per passive quote leg
HP_FLATTEN    = 100   # flatten all capacity beyond this


# ─── Black-Scholes ─────────────────────────────────────────────────────────────
def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def bs_call(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 1e-9:
        return max(S - K, 0.0)
    sqT = math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * sqT)
    return S * _ncdf(d1) - K * _ncdf(d1 - sigma * sqT)

def implied_vol(C: float, S: float, K: float, T: float) -> float | None:
    if T <= 0 or C <= max(S - K, 0.0) + 0.15:
        return None
    lo, hi = SIGMA_LO, SIGMA_HI
    if bs_call(S, K, T, hi) < C:
        return None
    for _ in range(50):
        mid = (lo + hi) / 2
        if bs_call(S, K, T, mid) < C:
            lo = mid
        else:
            hi = mid
    r = (lo + hi) / 2
    return r if SIGMA_LO < r < SIGMA_HI else None


# ─── Parabola fit (no numpy) ──────────────────────────────────────────────────
def fit_parabola(xs: list[float], ys: list[float]) -> list[float] | None:
    """Least-squares fit of y = a + b*x + c*x^2 via 3×3 normal equations."""
    n = len(xs)
    if n < 3:
        return None
    s0 = float(n)
    s1  = sum(xs);            s2 = sum(x*x for x in xs)
    s3  = sum(x**3 for x in xs); s4 = sum(x**4 for x in xs)
    sy  = sum(ys)
    sxy = sum(x*y for x, y in zip(xs, ys))
    sx2y= sum(x*x*y for x, y in zip(xs, ys))
    A = [[s0, s1, s2, sy], [s1, s2, s3, sxy], [s2, s3, s4, sx2y]]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(A[r][col]))
        A[col], A[piv] = A[piv], A[col]
        if abs(A[col][col]) < 1e-14:
            return None
        for row in range(col + 1, 3):
            f = A[row][col] / A[col][col]
            for j in range(col, 4):
                A[row][j] -= f * A[col][j]
    p = [0.0, 0.0, 0.0]
    for row in range(2, -1, -1):
        p[row] = A[row][3]
        for col in range(row + 1, 3):
            p[row] -= A[row][col] * p[col]
        p[row] /= A[row][row]
    return p


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _mid(od: OrderDepth) -> float | None:
    bb = max(od.buy_orders)  if od.buy_orders  else None
    ba = min(od.sell_orders) if od.sell_orders else None
    if bb and ba:
        return (bb + ba) / 2.0
    return float(bb) if bb else (float(ba) if ba else None)

def _ewm(old: float, new: float, alpha: float) -> float:
    return (1 - alpha) * old + alpha * new


# ─── Trader ───────────────────────────────────────────────────────────────────
class Trader:
    def run(self, state: TradingState):
        data: dict = {}
        if state.traderData:
            try:
                data = json.loads(state.traderData)
            except Exception:
                pass

        tte   = max(TTE_START - state.timestamp / TICKS_PER_DAY, 1e-4)
        result: dict[str, list[Order]] = {}

        # Per-strike cached sigma & deviation EWMs
        sig  = {K: data.get(f"s{K}", SIGMA_INIT[K]) for K in SIGMA_INIT}
        slow = {K: data.get(f"sl{K}", 0.0) for K in SIGMA_INIT}  # slow dev baseline
        fast = {K: data.get(f"fa{K}", 0.0) for K in SIGMA_INIT}  # fast-smoothed dev

        vfe_ema: float | None = data.get("ema")

        # ── VFE mid ────────────────────────────────────────────────────────────
        vfe_od  = state.order_depths.get("VELVETFRUIT_EXTRACT")
        vfe_mid = _mid(vfe_od) if vfe_od else None

        if vfe_mid is not None:
            vfe_ema = vfe_mid if vfe_ema is None else _ewm(vfe_ema, vfe_mid, VFE_EMA_ALPHA)

            # ── Build IV smile ─────────────────────────────────────────────────
            smile_xs: list[float] = []
            smile_ys: list[float] = []
            opt_mid:  dict[int, float] = {}

            for sym, K in SMILE_STRIKES.items():
                if sym not in state.order_depths:
                    continue
                mid_c = _mid(state.order_depths[sym])
                if mid_c is None:
                    continue
                opt_mid[K] = mid_c
                iv = implied_vol(mid_c, vfe_mid, K, tte)
                if iv is not None:
                    sig[K] = _ewm(sig[K], iv, 0.03)
                    smile_xs.append(math.log(K / vfe_mid))
                    smile_ys.append(iv)

            para = fit_parabola(smile_xs, smile_ys) if len(smile_xs) >= 4 else None

            # ── IV scalping for each near-ATM strike ───────────────────────────
            for sym, K in SMILE_STRIKES.items():
                if sym not in state.order_depths:
                    continue

                # Smile-fair sigma
                if para is not None:
                    m = math.log(K / vfe_mid)
                    a, b, c = para
                    sig_smile = max(SIGMA_LO, min(SIGMA_HI, a + b*m + c*m*m))
                else:
                    sig_smile = sig[K]

                smile_fair = bs_call(vfe_mid, K, tte, sig_smile)

                # Update deviation EWMs
                if K in opt_mid:
                    raw_dev = opt_mid[K] - smile_fair
                    slow[K] = _ewm(slow[K], raw_dev, DEV_SLOW_ALPHA)
                    fast[K] = _ewm(fast[K], raw_dev, DEV_FAST_ALPHA)

                # Signal: fast deviation relative to slow baseline
                signal = fast[K] - slow[K]

                result[sym] = self._scalp(sym, smile_fair, signal, state)

            # ── VFE mean reversion ─────────────────────────────────────────────
            if vfe_od is not None:
                result["VELVETFRUIT_EXTRACT"] = self._vfe_mr(
                    state, vfe_od, vfe_mid, vfe_ema
                )

            # ── VEV_4000: VFE proxy + basic MM ────────────────────────────────
            if "VEV_4000" in state.order_depths:
                fair_4k = bs_call(vfe_mid, 4000, tte, sig[4000])
                mr_bias = vfe_mid - vfe_ema if vfe_ema else 0.0
                result["VEV_4000"] = self._vev4k(state, fair_4k, mr_bias)

            # ── VEV_4500: light MM only ────────────────────────────────────────
            if "VEV_4500" in state.order_depths:
                fair_45 = bs_call(vfe_mid, 4500, tte, sig[4500])
                result["VEV_4500"] = self._take_edge("VEV_4500", fair_45, V4K_TAKE_EDGE, state)

        # ── HYDROGEL_PACK ──────────────────────────────────────────────────────
        if "HYDROGEL_PACK" in state.order_depths:
            result["HYDROGEL_PACK"] = self._hp(state)

        # ── Persist ────────────────────────────────────────────────────────────
        if vfe_ema is not None:
            data["ema"] = vfe_ema
        for K in SIGMA_INIT:
            data[f"s{K}"]  = sig[K]
            data[f"sl{K}"] = slow[K]
            data[f"fa{K}"] = fast[K]

        return result, 0, json.dumps(data)

    # ─── IV scalping orders ───────────────────────────────────────────────────
    def _scalp(self, sym: str, fair: float, signal: float, state: TradingState) -> list[Order]:
        od  = state.order_depths[sym]
        pos = state.position.get(sym, 0)
        lim = LIMITS[sym]
        buy_cap  = lim - pos
        sell_cap = lim + pos
        orders: list[Order] = []

        def buy(p: int, q: int):
            nonlocal buy_cap
            q = min(q, buy_cap)
            if q > 0:
                orders.append(Order(sym, p, q)); buy_cap -= q

        def sell(p: int, q: int):
            nonlocal sell_cap
            q = min(q, sell_cap)
            if q > 0:
                orders.append(Order(sym, p, -q)); sell_cap -= q

        # Aggressive take when signal is clear
        if signal >= SCALP_THRESH:
            # Option fast-rich vs slow baseline → hit the bids
            for price in sorted(od.buy_orders, reverse=True):
                if price >= math.ceil(fair):
                    sell(price, od.buy_orders[price])

        elif signal <= -SCALP_THRESH:
            # Option fast-cheap vs slow baseline → lift the asks
            for price in sorted(od.sell_orders):
                if price <= math.floor(fair):
                    buy(price, abs(od.sell_orders[price]))

        # Passive quotes around smile fair (always post, lean for inventory)
        lean = min(MAX_LEAN, max(-MAX_LEAN, pos // LEAN_PER_UNIT))
        bid  = math.floor(fair) - lean
        ask  = math.ceil(fair)  - lean
        if bid >= ask:
            ask = bid + 1

        if bid < fair:
            buy(bid,  min(SCALP_SIZE, buy_cap))
        if ask > fair:
            sell(ask, min(SCALP_SIZE, sell_cap))

        return orders

    # ─── VFE mean reversion ───────────────────────────────────────────────────
    def _vfe_mr(self, state: TradingState, od: OrderDepth,
                mid: float, ema: float) -> list[Order]:
        sym = "VELVETFRUIT_EXTRACT"
        pos = state.position.get(sym, 0)
        lim = LIMITS[sym]
        buy_cap  = lim - pos
        sell_cap = lim + pos
        orders: list[Order] = []

        def buy(p: int, q: int):
            nonlocal buy_cap
            q = min(q, buy_cap)
            if q > 0:
                orders.append(Order(sym, p, q)); buy_cap -= q

        def sell(p: int, q: int):
            nonlocal sell_cap
            q = min(q, sell_cap)
            if q > 0:
                orders.append(Order(sym, p, -q)); sell_cap -= q

        dev = mid - ema
        mr_buy_cap  = max(0, VFE_MR_CAP + pos)
        mr_sell_cap = max(0, VFE_MR_CAP - pos)

        if dev >= VFE_MR_AGGR and mr_sell_cap > 0:
            for p in sorted(od.buy_orders, reverse=True):
                if sell_cap <= 0 or mr_sell_cap <= 0: break
                q = min(od.buy_orders[p], VFE_MR_SIZE, sell_cap, mr_sell_cap)
                sell(p, q); mr_sell_cap -= q

        elif dev <= -VFE_MR_AGGR and mr_buy_cap > 0:
            for p in sorted(od.sell_orders):
                if buy_cap <= 0 or mr_buy_cap <= 0: break
                q = min(abs(od.sell_orders[p]), VFE_MR_SIZE, buy_cap, mr_buy_cap)
                buy(p, q); mr_buy_cap -= q

        else:
            # Passive limit orders at EMA ± threshold
            if mr_buy_cap > 0 and buy_cap > 0:
                buy(round(ema - VFE_MR_THRESH), min(VFE_MR_SIZE, buy_cap, mr_buy_cap))
            if mr_sell_cap > 0 and sell_cap > 0:
                sell(round(ema + VFE_MR_THRESH), min(VFE_MR_SIZE, sell_cap, mr_sell_cap))

        return orders

    # ─── VEV_4000 MR proxy ────────────────────────────────────────────────────
    def _vev4k(self, state: TradingState, fair: float, mr_bias: float) -> list[Order]:
        sym = "VEV_4000"
        od  = state.order_depths[sym]
        pos = state.position.get(sym, 0)
        lim = LIMITS[sym]
        buy_cap  = lim - pos
        sell_cap = lim + pos
        orders: list[Order] = []

        def buy(p: int, q: int):
            nonlocal buy_cap
            q = min(q, buy_cap)
            if q > 0:
                orders.append(Order(sym, p, q)); buy_cap -= q

        def sell(p: int, q: int):
            nonlocal sell_cap
            q = min(q, sell_cap)
            if q > 0:
                orders.append(Order(sym, p, -q)); sell_cap -= q

        # Take obvious mispricing (> V4K_TAKE_EDGE ticks off fair)
        for p in sorted(od.sell_orders):
            if p < fair - V4K_TAKE_EDGE:
                buy(p, abs(od.sell_orders[p]))
        for p in sorted(od.buy_orders, reverse=True):
            if p > fair + V4K_TAKE_EDGE:
                sell(p, od.buy_orders[p])

        # MR skew: if VFE is above EMA (expect fall), lean short VEV_4000
        mr_lean = max(-2, min(2, round(mr_bias / VFE_MR_THRESH)))
        bid = math.floor(fair) - mr_lean
        ask = math.ceil(fair)  - mr_lean
        if bid >= ask: ask = bid + 1

        if bid < fair and buy_cap > 0:
            buy(bid,  min(V4K_MR_SIZE, buy_cap))
        if ask > fair and sell_cap > 0:
            sell(ask, min(V4K_MR_SIZE, sell_cap))

        return orders

    # ─── Generic take-edge-only (VEV_4500) ───────────────────────────────────
    def _take_edge(self, sym: str, fair: float, edge: float,
                   state: TradingState) -> list[Order]:
        od  = state.order_depths[sym]
        pos = state.position.get(sym, 0)
        lim = LIMITS[sym]
        buy_cap  = lim - pos
        sell_cap = lim + pos
        orders: list[Order] = []

        for p in sorted(od.sell_orders):
            if p < fair - edge:
                q = min(abs(od.sell_orders[p]), buy_cap)
                if q > 0:
                    orders.append(Order(sym, p, q)); buy_cap -= q
        for p in sorted(od.buy_orders, reverse=True):
            if p > fair + edge:
                q = min(od.buy_orders[p], sell_cap)
                if q > 0:
                    orders.append(Order(sym, p, -q)); sell_cap -= q
        return orders

    # ─── HYDROGEL_PACK ────────────────────────────────────────────────────────
    # Spread is ~16 ticks wide; return autocorr ≈ -0.13 (mild MR on returns).
    # Pure market-making: quote at bb+1 / ba-1, lean for inventory.
    # No fixed fair value — the old HP_FV=10000 caused permanent long buildup
    # because every ask below 10000 was taken aggressively and sells were
    # capped at max(ba-1, 10001), which is 3+ ticks above the market.
    def _hp(self, state: TradingState) -> list[Order]:
        sym = "HYDROGEL_PACK"
        od  = state.order_depths[sym]
        pos = state.position.get(sym, 0)
        lim = LIMITS[sym]
        buy_cap  = lim - pos
        sell_cap = lim + pos
        orders: list[Order] = []

        bb = max(od.buy_orders)  if od.buy_orders  else None
        ba = min(od.sell_orders) if od.sell_orders else None
        if bb is None and ba is None:
            return orders

        def buy(p: int, q: int):
            nonlocal buy_cap
            q = min(q, buy_cap)
            if q > 0:
                orders.append(Order(sym, p, q)); buy_cap -= q

        def sell(p: int, q: int):
            nonlocal sell_cap
            q = min(q, sell_cap)
            if q > 0:
                orders.append(Order(sym, p, -q)); sell_cap -= q

        # Inventory lean: shift quotes 1 tick per 50 units, cap at ±3
        lean = min(3, max(-3, pos // 50))

        if pos > HP_FLATTEN:
            # Long and skewed: undercut best ask with all remaining capacity
            if ba:
                sell(ba - 1, sell_cap)
        elif pos < -HP_FLATTEN:
            # Short and skewed: overbid best bid with all remaining capacity
            if bb:
                buy(bb + 1, buy_cap)
        else:
            # Normal: quote inside the spread, leaned toward flattening
            if bb and buy_cap > 0:
                buy(bb + 1 - lean, min(HP_QUOTE_SIZE, buy_cap))
            if ba and sell_cap > 0:
                sell(ba - 1 - lean, min(HP_QUOTE_SIZE, sell_cap))

        return orders