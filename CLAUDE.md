# CLAUDE.md — Contexto del proyecto para continuar en Claude Code

> **Para el próximo agente Claude:** Lee este archivo completo antes de tocar
> cualquier código. Contiene todas las decisiones de diseño, bugs ya corregidos,
> resultados de backtest y los próximos pasos acordados con el usuario.

---

## 1. Resumen del proyecto

Bot de trading algorítmico para **MetaTrader 5** basado en:
- **SMC** (Smart Money Concepts): Order Blocks, FVG, BOS/CHoCH, Liquidity pools
- **Wyckoff**: detección de fases Acumulación/Distribución, Spring, Upthrust
- **VSA** (Volume Spread Analysis): no_supply, no_demand, climax, esfuerzo/resultado
- **Price Action**: pin bars, engulfing, inside bars, tendencia EMA

**Instrumentos elegidos (basado en investigación):**
- `XAUUSD` — Oro: instrumento #1 por consenso de la comunidad SMC. ICT construyó
  SMC sobre oro. Sweeps de liquidez más limpios del mercado.
- `NAS100` — Nasdaq 100: tendencias fuertes, CHoCH muy claros, correlación negativa
  con oro (diversificación real risk-on/risk-off).

**Timeframe:** M30 (30 minutos) — balance óptimo frecuencia/ruido para estos activos.

**Cuenta demo objetivo:** $1,000 USD en MetaTrader 5.

**R:R mínimo:** 1:3 (break-even estadístico: >25% de aciertos).

---

## 2. Estructura del repositorio

```
Code/
├── CLAUDE.md                          ← este archivo
├── trading_bot/                       ← el bot (TODO el trabajo está aquí)
│   ├── bot.py                         ← loop principal (entry point)
│   ├── config.py                      ← TODOS los parámetros configurables
│   ├── strategy.py                    ← motor de confluencia SMC+Wyckoff+VSA+PA
│   ├── risk_manager.py                ← sizing correcto por tick_value/tick_size
│   ├── mt5_connector.py               ← conexión MT5, datos, órdenes
│   ├── backtest.py                    ← backtester walk-forward (sin MT5)
│   ├── run_backtest.py                ← análisis completo multi-semilla 2 pares
│   ├── generate_data.py               ← genera OHLCV realista para backtests
│   ├── projection.py                  ← calcula rentabilidad mensual/anual
│   ├── fetch_history.py               ← descarga histórico de Yahoo Finance (*)
│   ├── requirements.txt
│   ├── .env.example
│   ├── .gitignore
│   └── indicators/
│       ├── smc.py                     ← OBs, FVG, BOS/CHoCH, liquidity
│       ├── wyckoff.py                 ← fases Wyckoff
│       ├── volume.py                  ← VSA
│       ├── price_action.py            ← patrones de velas + EMA trend
│       └── atr.py                     ← ATR para el piso del SL
│
└── sports_betting_bot/                ← bot anterior (no tocar)
```

(*) `fetch_history.py` usa Yahoo Finance — bloqueado en el entorno de Claude Code
    en la nube. Funciona en la máquina local del usuario.

---

## 3. Rama de desarrollo

```
git checkout claude/trading-bot-qftk8s
```

Todos los commits están pusheados a `origin/claude/trading-bot-qftk8s`.

---

## 4. Bugs críticos ya corregidos (NO reintroducir)

| Bug | Archivo | Corrección |
|-----|---------|-----------|
| Clase `OrderBlock` duplicada | `indicators/smc.py` | Consolidada en una sola |
| Sizing de lote con `point × 10` | `risk_manager.py` | Reescrito con `tick_value/tick_size` (correcto para oro, índices, cualquier instrumento) |
| Repainting (vela viva analizada) | `bot.py` | `df.iloc[:-1]` — solo velas cerradas |
| Mismo setup disparado 60×/vela | `bot.py` | Guard `last_traded_bar` por símbolo |
| OB/FVG "violados" mal detectados | `indicators/smc.py` | Escanea todas las velas post-formación, no solo la última |
| Stops microscópicos → lote gigante | `strategy.py` | Piso ATR: `SL_ATR_MULT=1.5` |
| BOS/CHoCH: trending mal calculado | `indicators/smc.py` | Reescrito: walk incremental de swings |
| Liquidity pools con candles arbitrarios | `indicators/smc.py` | Solo compara swing points reales |

---

## 5. Parámetros clave (config.py)

```python
SYMBOLS    = ["XAUUSD", "NAS100"]   # los 2 pares elegidos
TIMEFRAME  = "M30"
MAGIC      = 20240001

# Riesgo
RISK_PER_TRADE_PCT  = 0.5    # 0.5% de balance por trade
MIN_RR_RATIO        = 3.0    # mínimo 1:3
MAX_OPEN_TRADES     = 2      # 1 por símbolo máximo

# Protección de capital
MAX_DAILY_LOSS_PCT     = 3.0    # pausa el día si pierde 3%
MAX_CONSECUTIVE_LOSSES = 4      # cool-down tras 4 pérdidas seguidas
MAX_TOTAL_DRAWDOWN_PCT = 15.0   # kill-switch permanente

# SMC (ajustado para M30)
SWING_WINDOW       = 3      # ventana rápida para M30
OB_LOOKBACK        = 100
FVG_MIN_GAP_PCT    = 0.0003
LIQUIDITY_LOOKBACK = 60
BOS_LOOKBACK       = 40
WYCKOFF_LOOKBACK   = 200
SL_ATR_MULT        = 1.5    # stops mínimo 1.5×ATR
SL_ATR_BUFFER      = 0.3

# Sesión (institucional: Londres + NY)
ALLOWED_SESSIONS_UTC = [(7, 17)]  # 07:00–17:00 UTC

# Confluencia mínima para abrir trade
MIN_CONFLUENCE_SCORE = 0.60
```

---

## 6. Resultados del backtest

### Configuración del test
- 12 simulaciones × 8,000 velas M30 por instrumento
- GARCH volatility clustering + regime switching (UP/DOWN/RANGE)
- Walk-forward real: cada trade se resuelve en barras posteriores
- Riesgo: 0.5% | R:R: 1:3 | Balance inicial: $1,000

### Resultados

| Instrumento | Trades | Win Rate | Profit Factor | Expectancy |
|------------|--------|----------|---------------|-----------|
| XAUUSD | 246 | 31.3% | **1.37** | **+0.252 R** ✅ |
| NAS100 | 222 | 31.5% | **1.38** | **+0.261 R** ✅ |
| **PORTFOLIO** | **468** | **31.4%** | **1.37** | **+0.256 R** ✅ |

- Max drawdown portfolio: **7.9%**
- Pérdidas consecutivas máx: 12
- Balance final (compuesto): **$1,785** (+78.5%)

### Proyección de rentabilidad

| Riesgo/trade | Mensual | Anual | Nota |
|-------------|---------|-------|------|
| 0.5% | +0.65% | **+8.1%** | Fase demo recomendada |
| 1.0% | +1.31% | **+16.9%** | Tras 2 meses demo positivos |
| 2.0% | +2.63% | **+36.9%** | Tras 6+ meses de track record |

**Frecuencia:** ~2.5 trades/mes por instrumento = ~5 trades/mes en total.

---

## 7. Cómo correr cada componente

```bash
cd trading_bot

# Generar datos sintéticos M30 para XAUUSD y NAS100
python generate_data.py --instrument XAUUSD --candles 8000
python generate_data.py --instrument NAS100 --candles 8000

# Backtest completo (ambos pares, 12 regímenes)
python run_backtest.py --candles 8000 --seeds 12 --risk 0.5 --rr 3 --balance 1000

# Proyección de rentabilidad
python projection.py

# Bot en modo DRY RUN (analiza pero no opera)
# Requiere MT5 en Windows + credenciales en .env
python bot.py
```

---

## 8. Próximos pasos acordados con el usuario

Estos son los temas que quedaron pendientes o como sugerencias al final de la conversación:

### Inmediatos (siguiente sesión)
1. **Conectar a MT5 real en demo** — el usuario tiene una cuenta demo de $1,000.
   - Configurar `.env` con sus credenciales
   - Correr `DRY_RUN=true` primero para ver señales sin operar
   - Verificar que los símbolos `XAUUSD` y `NAS100` estén disponibles en su broker
   - Algunos brokers usan nombres distintos: `GOLD`, `US100`, `NDX100`, `USTEC`

2. **Backtest con datos reales del broker** — exportar desde MT5 History Center:
   ```bash
   python run_backtest.py  # con CSV real en lugar de sintético
   ```

### Mejoras técnicas pendientes
3. **Script de exportación automática MT5→CSV** — para correr el backtest con datos
   reales sin configurar nada manualmente. Ya discutido con el usuario.

4. **Trailing Stop** — implementar TSL para dejar correr los ganadores más allá
   del TP fijo (especialmente útil en NAS100 que tiene tendencias largas).

5. **Dashboard / monitor** — el usuario mencionó querer ver el estado del bot.
   Opciones: Rich console en tiempo real, o un simple archivo HTML que se regenere.

6. **Multi-timeframe confirmation** — añadir confirmación en H4 antes de entrar
   en M30 (top-down analysis, muy recomendado en SMC).

### Optimización futura
7. **Optimizar parámetros con datos reales** — una vez que haya histórico real,
   hacer grid search sobre `MIN_CONFLUENCE_SCORE`, `SL_ATR_MULT`, `OB_LOOKBACK`.

8. **Añadir M15 como tercer timeframe** — si el usuario quiere más frecuencia
   manteniendo la calidad de señales.

---

## 9. Notas importantes para el próximo agente

- **NO cambiar** `risk_manager.py` sin entender el sizing por `tick_value/tick_size`.
  El cálculo anterior (basado en pips) estaba roto para oro e índices.
- **NO** operar la vela viva (`df.iloc[-1]`). Siempre usar `df.iloc[:-1]` (solo cerradas).
- El usuario entiende trading y SMC (menciona conocer a Francisco Frías / Solid Trading).
  Puede usar terminología técnica directamente.
- El backtest usa datos **sintéticos** (sin MT5). Para validar edge real hace falta
  CSV con histórico del broker del usuario.
- La varianza entre regímenes es alta (±0.234 R). Algunos meses serán negativos —
  es normal y esperado.
- En MetaTrader 5, NAS100 puede llamarse diferente según el broker:
  `NAS100`, `US100`, `USTEC`, `NDX100`, `NQ100`. El usuario debe verificar.

---

## 10. Estado actual del repositorio

- **Rama:** `claude/trading-bot-qftk8s`
- **Último commit:** `a954587` — "Switch to M30 + XAUUSD/NAS100"
- **Estado:** limpio, todo pusheado a origin
- **Tests de sintaxis:** todos pasan (`python -m py_compile`)
- **Backtest:** corre sin MT5 con `python run_backtest.py`
