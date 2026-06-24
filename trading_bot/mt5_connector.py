"""
MetaTrader 5 connection and order execution layer.
"""
import time
import logging
from typing import Optional
import MetaTrader5 as mt5

from config import (
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH,
    SLIPPAGE, MAGIC, DRY_RUN, TIMEFRAME_MAP
)

logger = logging.getLogger(__name__)


def connect() -> bool:
    kwargs = {}
    if MT5_PATH:
        kwargs["path"] = MT5_PATH
    if MT5_SERVER:
        kwargs["server"] = MT5_SERVER
    if MT5_LOGIN:
        kwargs["login"] = MT5_LOGIN
        kwargs["password"] = MT5_PASSWORD

    if not mt5.initialize(**kwargs):
        logger.error("MT5 initialize failed: %s", mt5.last_error())
        return False

    info = mt5.account_info()
    logger.info("Connected: %s | Balance: %.2f %s | Leverage: 1:%s",
                info.name, info.balance, info.currency, info.leverage)
    return True


def disconnect():
    mt5.shutdown()


def get_balance() -> float:
    info = mt5.account_info()
    return info.balance if info else 0.0


def get_open_trades(symbol: str = "") -> list:
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    return list(positions) if positions else []


def _supported_filling(symbol: str):
    """Pick a filling mode the symbol actually supports.

    Hardcoding IOC makes EVERY order fail (retcode 10030) on brokers/symbols
    that only allow FOK or RETURN. We read the symbol's filling_mode bitmask
    and choose accordingly.
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_RETURN
    mode = info.filling_mode
    if mode & 1:                      # SYMBOL_FILLING_FOK
        return mt5.ORDER_FILLING_FOK
    if mode & 2:                      # SYMBOL_FILLING_IOC
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def _round_to_digits(symbol: str, price: float) -> float:
    """Round a price to the instrument's digit precision (not a fixed 5).

    NAS100 trades to 1-2 digits, gold to 2-3; rounding everything to 5 digits
    can produce prices the broker rejects as off-tick ('invalid price').
    """
    info = mt5.symbol_info(symbol)
    digits = info.digits if info else 5
    return round(price, digits)


def place_order(
    symbol: str,
    order_type: str,          # "BUY" or "SELL"
    lot: float,
    sl: float,
    tp: float,
    comment: str = "SMC-Bot",
) -> Optional[int]:
    """Places a market order. Returns ticket number or None on failure."""
    if DRY_RUN:
        logger.info("[DRY RUN] %s %s %.4f lot | SL=%.5f TP=%.5f", order_type, symbol, lot, sl, tp)
        return -1  # fake ticket

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logger.error("Cannot get tick for %s", symbol)
        return None

    price = tick.ask if order_type == "BUY" else tick.bid
    mt5_type = mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL

    request = {
        "action":   mt5.TRADE_ACTION_DEAL,
        "symbol":   symbol,
        "volume":   lot,
        "type":     mt5_type,
        "price":    price,
        "sl":       _round_to_digits(symbol, sl),
        "tp":       _round_to_digits(symbol, tp),
        "deviation": SLIPPAGE,
        "magic":    MAGIC,
        "comment":  comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _supported_filling(symbol),
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        err = result.comment if result else mt5.last_error()
        code = result.retcode if result else "n/a"
        logger.error("Order failed: %s (%s)", err, code)
        return None

    logger.info("Order placed: ticket=%s %s %s %.4f | SL=%.5f TP=%.5f",
                result.order, order_type, symbol, lot, sl, tp)
    return result.order


def close_position(ticket: int) -> bool:
    """Closes a specific position by ticket."""
    if DRY_RUN:
        logger.info("[DRY RUN] Close position ticket=%s", ticket)
        return True

    position = mt5.positions_get(ticket=ticket)
    if not position:
        logger.warning("Position %s not found", ticket)
        return False

    pos = position[0]
    order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(pos.symbol)
    price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

    request = {
        "action":    mt5.TRADE_ACTION_DEAL,
        "symbol":    pos.symbol,
        "volume":    pos.volume,
        "type":      order_type,
        "position":  ticket,
        "price":     price,
        "deviation": SLIPPAGE,
        "magic":     MAGIC,
        "comment":   "SMC-Bot Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": _supported_filling(pos.symbol),
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        err = result.comment if result else mt5.last_error()
        logger.error("Close failed: %s", err)
        return False

    logger.info("Position %s closed", ticket)
    return True


def get_symbol_info(symbol: str):
    info = mt5.symbol_info(symbol)
    if info is None:
        mt5.symbol_select(symbol, True)
        time.sleep(0.1)
        info = mt5.symbol_info(symbol)
    return info


def get_candles(symbol: str, timeframe: str, count: int = 500):
    tf = TIMEFRAME_MAP.get(timeframe.upper())
    if tf is None:
        raise ValueError(f"Unknown timeframe: {timeframe}")
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    return rates  # numpy structured array: time, open, high, low, close, tick_volume, spread, real_volume
