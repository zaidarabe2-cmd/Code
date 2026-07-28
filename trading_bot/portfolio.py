"""
Portfolio-level risk controls that span all open positions.

Currently: the correlation filter, adapted from the Alpaca playbook. Its job is
to stop the bot from unknowingly doubling a single macro bet across correlated
instruments (XAUUSD vs NAS100 are a risk-on/risk-off pair).
"""
import logging

from config import RISK_ON_BETA, MAX_NET_MACRO_EXPOSURE, CORRELATION_FILTER

logger = logging.getLogger(__name__)


def _position_beta(symbol: str, is_long: bool) -> float:
    """Risk-on exposure contributed by one open position (0 if unknown symbol)."""
    beta = RISK_ON_BETA.get(symbol.upper(), 0.0)
    return beta if is_long else -beta


def net_macro_exposure(open_positions) -> float:
    """Sum the risk-on beta across all currently open MT5 positions.

    `open_positions` is a list of MT5 position objects (with .symbol and .type,
    where type 0 = BUY/long, 1 = SELL/short).
    """
    total = 0.0
    for p in open_positions:
        is_long = (p.type == 0)
        total += _position_beta(p.symbol, is_long)
    return total


def allows_new_trade(symbol: str, direction: str, open_positions) -> tuple[bool, str]:
    """
    Returns (allowed, reason). Blocks a candidate trade whose macro exposure
    would ADD to an already-maxed net risk-on/off bet in the same direction.
    """
    if not CORRELATION_FILTER:
        return True, ""

    candidate = _position_beta(symbol, direction == "BUY")
    if candidate == 0.0:
        return True, ""                      # symbol not in the correlation map

    current = net_macro_exposure(open_positions)
    projected = current + candidate

    # Block only if the new trade PUSHES net exposure further past the cap
    # (i.e., same sign as current net and already at/over the limit).
    if abs(projected) > MAX_NET_MACRO_EXPOSURE + 1e-9 and abs(projected) > abs(current):
        macro = "risk-ON" if candidate > 0 else "risk-OFF"
        return False, (f"correlation filter: {direction} {symbol} adds {macro} exposure "
                       f"(net {current:+.1f} → {projected:+.1f}, cap ±{MAX_NET_MACRO_EXPOSURE})")
    return True, ""
