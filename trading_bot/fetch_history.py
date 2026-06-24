"""
Descarga histórico de Yahoo Finance y lo guarda como CSV listo para backtest.
Uso: python fetch_history.py [--symbol EURUSD=X] [--interval 1h] [--period 2y]
"""
import argparse
import os
import sys

import yfinance as yf
import pandas as pd


SYMBOL_MAP = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "XAUUSD": "GC=F",     # Gold futures
    "US500":  "^GSPC",    # S&P 500
    "BTCUSD": "BTC-USD",
}


def fetch(symbol: str, interval: str, period: str, out_dir: str = "data") -> str:
    yf_sym = SYMBOL_MAP.get(symbol.upper(), symbol)
    print(f"Descargando {yf_sym} | intervalo={interval} | periodo={period} …")

    ticker = yf.Ticker(yf_sym)
    df = ticker.history(period=period, interval=interval, auto_adjust=True)

    if df.empty:
        print(f"ERROR: sin datos para {yf_sym}. Verifica el símbolo y el intervalo.")
        sys.exit(1)

    # Renombrar columnas al formato que usa backtest.py
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "tick_volume"]
    df.index.name = "time"

    os.makedirs(out_dir, exist_ok=True)
    sym_clean = symbol.upper().replace("=X", "").replace("^", "").replace("-", "")
    filename = f"{out_dir}/{sym_clean}_{interval.upper()}.csv"
    df.to_csv(filename)
    print(f"Guardado: {filename}  ({len(df)} velas)")
    return filename


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol",   default="EURUSD", help="Símbolo (EURUSD, GBPUSD, XAUUSD, BTCUSD …)")
    ap.add_argument("--interval", default="1h",     help="Intervalo: 1h, 4h, 1d …")
    ap.add_argument("--period",   default="2y",     help="Periodo: 1y, 2y, 5y …")
    args = ap.parse_args()
    fetch(args.symbol, args.interval, args.period)


if __name__ == "__main__":
    main()
