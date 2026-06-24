# Auditoría crítica del bot — hallazgos

> Revisión completa solicitada: "revisa todo el bot que esté correcto y sea
> lo más óptimo posible". Este documento separa **bugs corregidos**,
> **debilidades de diseño pendientes de decisión** y **límites estructurales**.

---

## 1. Bugs de correctness YA CORREGIDOS

| # | Archivo | Bug | Impacto | Estado |
|---|---------|-----|---------|--------|
| 1 | mt5_connector.py | `ORDER_FILLING_IOC` hardcodeado | Toda orden falla (retcode 10030) en brokers FOK-only | ✅ autodetecta `filling_mode` |
| 2 | mt5_connector.py | `round(price, 5)` fijo | Precios off-tick rechazados en NAS100/XAUUSD | ✅ usa `symbol.digits` |
| 3 | mt5_connector.py | `result` sin guardia None | Crash si `order_send` devuelve None | ✅ guardia añadida |
| 4 | backtest.py | Sin costes de trading | Resultados inflados (~13% de edge) | ✅ spread+comisión+slippage |
| 5 | backtest.py | Entrada en close de la vela señal | Precio no ejecutable (look-ahead suave) | ✅ entra en open de la vela siguiente |

(Bugs 1-8 de sesiones previas: OrderBlock duplicado, sizing por pips, repainting,
over-trading, mitigación OB/FVG, stops microscópicos — ver CLAUDE.md §4.)

---

## 2. Debilidades de DISEÑO (requieren tu decisión, no reescritas aún)

### 2A. Wyckoff: rango definido con el tercio central del lookback
`indicators/wyckoff.py` define el trading range con las velas `[n/3 : 2n/3]`,
que pueden estar 30-60 velas en el pasado. Luego busca Spring/Upthrust en las
últimas 10 velas. **Si el precio se ha alejado de ese rango antiguo, los
springs/upthrusts comparan el precio actual contra un nivel desconectado** →
señales Wyckoff potencialmente espurias.

- **Fix propuesto:** definir el rango con consolidación reciente (p.ej. las
  20-30 velas previas a la posible penetración), no un slice fijo.
- **No aplicado** porque cambia las señales y el backtest; decisión tuya.

### 2B. Volume: divergencia solo detecta caídas de volumen
`indicators/volume.py` marca divergencia únicamente cuando el volumen BAJA
(precio↑/vol↓ = bearish; precio↓/vol↓ = bullish). No contempla precio↓/vol↑
(distribución genuina) ni precio↑/vol↑ (fuerza genuina). Implementación parcial,
no incorrecta — solo deja señales sobre la mesa.

### 2C. Peso de confluencia sin validación
Los pesos en `strategy.py` (0.20 OB, 0.25 CHoCH, 0.15 FVG…) están elegidos a
mano, no optimizados. Con datos reales conviene un grid search.

---

## 3. Límites ESTRUCTURALES (no se arreglan con código)

### 3A. Frecuencia tope ≈ 0.1-0.15 trades/día por par
Demostrado con `analyze_frequency.py` (barrido MIN_SCORE 0.45→0.70):
la frecuencia **no sube** al aflojar el filtro porque está limitada por el
**tiempo de retención** (~2.5 días/trade con target 4.5 ATR del R:R 1:3).
→ **1-2 trades/día con R:R 1:3 en M30 es imposible.** Tope real ≈ 3/mes/par.

### 3B. Rentabilidad realista
Expectativa neta de costes ≈ +0.22R, ~5 trades/mes:
- 0.5% riesgo → ~+0.6%/mes
- Para 3-5%/mes haría falta ~3% riesgo/trade → ruina probable en $1,000.

### 3C. Todo medido sobre datos SINTÉTICOS
El edge (+0.22R) NO está validado. Requiere histórico real del broker.

---

## 4. Caminos posibles (elegir uno)

| Camino | R:R | Timeframe | Trades/día | %/mes realista | Trade-off |
|--------|-----|-----------|-----------|----------------|-----------|
| **A. Frecuencia** | 1:1.5 | M5/M15 | ~1-2 | depende | más costes spread, menor calidad |
| **B. Calidad** (actual) | 1:3 | M30 | ~0.1 | ~1% | pocas señales, alta selectividad |

**Pendiente de tu decisión antes de optimizar más.**

---

## 5. Antes de la demo — checklist obligatorio

- [ ] Exportar histórico real de XAUUSD y NAS100 desde MT5
- [ ] Correr `run_backtest.py` con CSV real (no sintético)
- [ ] Verificar nombre real de NAS100 en tu broker (US100/USTEC/NDX100…)
- [ ] Confirmar que `symbol_info.filling_mode` y `digits` se leen bien
- [ ] DRY_RUN=true durante al menos 1-2 semanas observando señales
