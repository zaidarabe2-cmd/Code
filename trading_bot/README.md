# SMC + Wyckoff Trading Bot (MetaTrader 5)

Bot algorítmico que combina **Smart Money Concepts**, **Wyckoff**, **análisis de
volumen (VSA)** y **price action** con un sistema de confluencia y gestión de
riesgo estricta. Pensado para validar primero en backtest y luego operar en una
cuenta **demo** antes de cualquier capital real.

## Estructura

```
trading_bot/
├── bot.py            # Loop principal (live / dry-run) con reglas de capital
├── backtest.py       # Backtester: mide si la estrategia tiene EDGE real
├── strategy.py       # Motor de confluencia (combina los 4 módulos)
├── risk_manager.py   # Sizing por tick_value/tick_size + SL mínimo del broker
├── mt5_connector.py  # Conexión MT5, órdenes, datos
├── config.py         # Todos los parámetros
└── indicators/
    ├── smc.py            # Order Blocks, FVG, BOS/CHoCH, Liquidity
    ├── wyckoff.py        # Acumulación/Distribución, Spring, Upthrust
    ├── volume.py         # VSA: no_supply/no_demand, climax, esfuerzo/resultado
    ├── price_action.py   # Pin bars, engulfing, inside bars, EMA trend
    ├── atr.py            # ATR para el piso del Stop Loss
    └── kronos_signal.py  # Capa IA opcional (Kronos foundation model)
```

## Capa de IA opcional — Kronos

[Kronos](https://github.com/shiyu-coder/Kronos) (Tsinghua, AAAI 2026) es un
foundation model que predice velas futuras (OHLCV). Se integra como **una señal
más de confluencia** (peso `KRONOS_WEIGHT=0.20`), NUNCA como disparador único.

- **Desactivado por defecto** (`KRONOS_ENABLED=false`). El bot funciona igual sin él.
- Si falta `torch` o los pesos, devuelve señal neutra y avisa una vez — sin crashear.
- Es un **forecast probabilístico, no un edge garantizado**. Valídalo antes de confiar.

**Activarlo en tu máquina:**
```bash
git clone https://github.com/shiyu-coder/Kronos    # hazlo importable (PYTHONPATH)
pip install -r requirements-kronos.txt
# en .env:  KRONOS_ENABLED=true
```
Cómo funciona: forecast de `KRONOS_PRED_LEN` velas → si el retorno esperado supera
`KRONOS_MIN_MOVE`, suma al score en la dirección prevista, ponderado por la
concordancia entre las `KRONOS_SAMPLES` trayectorias Monte-Carlo (confianza real).

## Reglas de rentabilidad / supervivencia (incorporadas)

Estas son las que convierten una estrategia con expectativa positiva en una
**survivable** sobre los $1000 de la demo:

| Regla | Dónde | Valor por defecto |
|-------|-------|-------------------|
| R:R mínimo | `MIN_RR` | **1:3** |
| Riesgo por trade | `RISK_PCT` | 0.5 % del balance |
| Pérdida diaria máx. | `MAX_DAILY_LOSS_PCT` | 3 % → para hasta el día siguiente |
| Pérdidas seguidas máx. | `MAX_CONSEC_LOSSES` | 4 → cool-down |
| Drawdown total (kill-switch) | `MAX_DD_PCT` | 15 % → detiene el bot |
| Solo velas cerradas | siempre | sí (evita repintado) |
| 1 trade por vela | `ONE_TRADE_PER_BAR` | sí |
| Piso de SL por ATR | `SL_ATR_MULT` | 1.0 × ATR |

Con R:R 1:3 el **break-even está en ~25% de aciertos**. Si la estrategia logra
>30-35% de forma consistente en backtest, tiene expectativa positiva.

## Cómo validar ANTES de la demo

1. Exporta datos históricos de tu broker a CSV
   (`time,open,high,low,close,tick_volume`). En MT5: *History Center* o un
   script `copy_rates_range`.
2. Corre el backtest:
   ```bash
   python backtest.py data/EURUSD_H1.csv --risk 0.5 --rr 3 --balance 1000
   ```
3. Mira el veredicto. Necesitas: **Profit factor > 1.3** y **Expectancy > 0 R**
   sobre una muestra grande (idealmente 100+ trades y varios años / regímenes).

> El backtest con datos sintéticos (`python backtest.py` sin argumentos) es solo
> un smoke-test del pipeline: son datos aleatorios sin edge, así que **debe**
> dar resultado negativo. Eso confirma que la estrategia no inventa señales.

## Operar en demo

```bash
pip install -r requirements.txt          # en Windows con MT5 instalado
cp .env.example .env                      # rellena credenciales MT5
# DRY_RUN=true → analiza pero NO envía órdenes
python bot.py
```

Cuando el backtest confirme edge y el dry-run se vea correcto, pon
`DRY_RUN=false` en `.env` para operar en la demo.

## Aviso

El trading conlleva riesgo de pérdida. Ninguna estrategia garantiza beneficios.
Valida exhaustivamente en demo antes de arriesgar capital real.
