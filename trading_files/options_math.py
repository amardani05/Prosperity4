"""
options_math.py
---------------
Black-Scholes fair value, Greeks, and implied-volatility inversion.
Pure stdlib (math only) so it can be dropped into the Prosperity sandbox.

Sign conventions: European options, continuous compounding, no dividends.
If you need a dividend yield q, subtract it from r and scale S by e^(-q*T).
"""
from math import log, sqrt, exp, erf, pi

_SQRT_2PI = sqrt(2.0 * pi)
_SQRT_2 = sqrt(2.0)


def norm_pdf(x: float) -> float:
    return exp(-0.5 * x * x) / _SQRT_2PI


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / _SQRT_2))


def _d1_d2(S: float, K: float, T: float, sigma: float, r: float = 0.0):
    sqT = sigma * sqrt(T)
    d1 = (log(S / K) + (r + 0.5 * sigma * sigma) * T) / sqT
    return d1, d1 - sqT


# ── fair-value pricers ──────────────────────────────────────────────────────

def bs_call(S: float, K: float, T: float, sigma: float, r: float = 0.0) -> float:
    if T <= 0.0:
        return max(S - K, 0.0)
    if sigma <= 0.0:
        return max(S - K * exp(-r * T), 0.0)
    d1, d2 = _d1_d2(S, K, T, sigma, r)
    return S * norm_cdf(d1) - K * exp(-r * T) * norm_cdf(d2)


def bs_put(S: float, K: float, T: float, sigma: float, r: float = 0.0) -> float:
    if T <= 0.0:
        return max(K - S, 0.0)
    if sigma <= 0.0:
        return max(K * exp(-r * T) - S, 0.0)
    d1, d2 = _d1_d2(S, K, T, sigma, r)
    return K * exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def bs_price(S: float, K: float, T: float, sigma: float, r: float = 0.0,
             is_call: bool = True) -> float:
    return bs_call(S, K, T, sigma, r) if is_call else bs_put(S, K, T, sigma, r)


# ── Greeks ──────────────────────────────────────────────────────────────────

def bs_delta(S, K, T, sigma, r=0.0, is_call=True):
    if T <= 0.0 or sigma <= 0.0:
        if is_call:
            return 1.0 if S > K else (0.5 if S == K else 0.0)
        return -1.0 if S < K else (-0.5 if S == K else 0.0)
    d1, _ = _d1_d2(S, K, T, sigma, r)
    return norm_cdf(d1) if is_call else norm_cdf(d1) - 1.0


def bs_gamma(S, K, T, sigma, r=0.0):
    if T <= 0.0 or sigma <= 0.0:
        return 0.0
    d1, _ = _d1_d2(S, K, T, sigma, r)
    return norm_pdf(d1) / (S * sigma * sqrt(T))


def bs_vega(S, K, T, sigma, r=0.0):
    """Vega per unit of sigma (not per 1%). Multiply by 0.01 for 'per 1 vol point'."""
    if T <= 0.0 or sigma <= 0.0:
        return 0.0
    d1, _ = _d1_d2(S, K, T, sigma, r)
    return S * norm_pdf(d1) * sqrt(T)


def bs_theta(S, K, T, sigma, r=0.0, is_call=True):
    """Theta per unit of T (same units you passed, e.g. years)."""
    if T <= 0.0 or sigma <= 0.0:
        return 0.0
    d1, d2 = _d1_d2(S, K, T, sigma, r)
    first = -(S * norm_pdf(d1) * sigma) / (2.0 * sqrt(T))
    if is_call:
        return first - r * K * exp(-r * T) * norm_cdf(d2)
    return first + r * K * exp(-r * T) * norm_cdf(-d2)


def bs_rho(S, K, T, sigma, r=0.0, is_call=True):
    if T <= 0.0:
        return 0.0
    _, d2 = _d1_d2(S, K, T, sigma, r)
    sign = 1.0 if is_call else -1.0
    return sign * K * T * exp(-r * T) * norm_cdf(sign * d2)


def greeks(S, K, T, sigma, r=0.0, is_call=True) -> dict:
    """Convenience: all Greeks in one dict."""
    return {
        "price": bs_price(S, K, T, sigma, r, is_call),
        "delta": bs_delta(S, K, T, sigma, r, is_call),
        "gamma": bs_gamma(S, K, T, sigma, r),
        "vega":  bs_vega(S, K, T, sigma, r),
        "theta": bs_theta(S, K, T, sigma, r, is_call),
        "rho":   bs_rho(S, K, T, sigma, r, is_call),
    }


# ── implied volatility (reverse BS) ─────────────────────────────────────────

def implied_vol(price: float, S: float, K: float, T: float,
                r: float = 0.0, is_call: bool = True,
                tol: float = 1e-6, max_iter: int = 100,
                initial: float = 0.3):
    """
    Invert Black-Scholes for sigma given a market price.
    Newton-Raphson on vega, with bisection fallback.

    Returns None if:
      - inputs invalid (T<=0, S<=0, K<=0)
      - price violates arbitrage bounds [intrinsic, upper]
      - solver fails to converge within tolerance
    """
    if T <= 0.0 or S <= 0.0 or K <= 0.0:
        return None

    disc_K = K * exp(-r * T)
    if is_call:
        intrinsic, upper = max(S - disc_K, 0.0), S
    else:
        intrinsic, upper = max(disc_K - S, 0.0), disc_K

    if price < intrinsic - 1e-8 or price > upper + 1e-8:
        return None
    if price <= intrinsic + 1e-10:
        return 1e-6   # degenerate: price is pure intrinsic, any tiny sigma works

    pricer = bs_call if is_call else bs_put

    # Newton-Raphson
    sigma = initial
    for _ in range(max_iter):
        diff = pricer(S, K, T, sigma, r) - price
        if abs(diff) < tol:
            return sigma
        v = bs_vega(S, K, T, sigma, r)
        if v < 1e-12:
            break
        new_sigma = sigma - diff / v
        if new_sigma <= 1e-6:
            new_sigma = 1e-6
        elif new_sigma >= 5.0:
            new_sigma = 5.0
        if abs(new_sigma - sigma) < 1e-12:
            return new_sigma
        sigma = new_sigma

    # Bisection fallback on [1e-6, 5.0]
    lo, hi = 1e-6, 5.0
    f_lo = pricer(S, K, T, lo, r) - price
    f_hi = pricer(S, K, T, hi, r) - price
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        diff = pricer(S, K, T, mid, r) - price
        if abs(diff) < tol or (hi - lo) < 1e-10:
            return mid
        if diff * f_lo < 0:
            hi, f_hi = mid, diff
        else:
            lo, f_lo = mid, diff
    return 0.5 * (lo + hi)


# ── moneyness helpers ───────────────────────────────────────────────────────

def log_moneyness(S: float, K: float) -> float:
    """ln(K/S). Negative = ITM call, positive = OTM call."""
    return log(K / S)


def standardized_moneyness(S: float, K: float, T: float) -> float:
    """m_t = ln(K/S) / sqrt(T). The x-axis of a normalized vol smile."""
    return log(K / S) / sqrt(T) if T > 0 else float("nan")


# ── self-test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 1) Round-trip: price → IV → price
    S, K, T, sig, r = 100.0, 100.0, 0.25, 0.20, 0.0
    c = bs_call(S, K, T, sig, r)
    p = bs_put(S, K, T, sig, r)
    print(f"ATM  call={c:.4f}  put={p:.4f}  (parity ok: r=0 ⇒ c==p)")

    iv = implied_vol(c, S, K, T, r, is_call=True)
    print(f"recovered IV from call price: {iv:.6f}   target {sig}")

    g = greeks(S, K, T, sig, r, is_call=True)
    print("Greeks:", {k: round(v, 5) for k, v in g.items()})

    # 2) Round-3-style: VEV_5400 at t=0 with S≈5250.5, mid=23, TTE=7/365
    S2, K2, T2, mid = 5250.5, 5400.0, 7.0 / 365.0, 23.0
    iv2 = implied_vol(mid, S2, K2, T2, is_call=True)
    if iv2 is not None:
        fv = bs_call(S2, K2, T2, iv2)
        print(f"\nVEV_5400 @ t=0  mid={mid}  TTE=7d")
        print(f"  implied vol = {iv2:.4f}")
        print(f"  reprice     = {fv:.4f}  (should match mid)")
        print(f"  m_t         = {standardized_moneyness(S2, K2, T2):.4f}")

    # 3) Deep OTM, tiny price: VEV_6500 mid=0.5
    iv3 = implied_vol(0.5, S2, 6500.0, T2, is_call=True)
    print(f"\nVEV_6500 @ t=0  mid=0.5 -> IV = {iv3}")

    # 4) Arbitrage-violating price should return None
    below_intrinsic = implied_vol(0.0, S2, 4000.0, T2, is_call=True)
    print(f"VEV_4000 mid=0 (below intrinsic 1250.5) -> {below_intrinsic}")
