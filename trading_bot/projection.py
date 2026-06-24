"""
Proyección de rentabilidad anual/mensual basada en los resultados del backtest.
Calcula múltiples escenarios de riesgo con precisión estadística.
"""
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import generate_data
from backtest import simulate


def run_projection():
    # ── 1. Corremos el backtest en un solo dataset continuo (5000 velas) ──────
    # 5,000 velas H1 = 5,000 horas
    # Forex abre 24h/día, 5 días/semana → 120h/semana
    # 5,000h / 120h = 41.7 semanas ≈ 10.4 meses de mercado real
    N_CANDLES = 5000
    H1_HOURS_PER_MONTH = 120 * 4.33  # 4.33 semanas/mes × 120h/semana
    MONTHS_IN_DATASET = N_CANDLES / H1_HOURS_PER_MONTH   # ≈ 9.6 meses

    seeds = list(range(12))
    all_freqs = []
    all_exp = []

    for seed in seeds:
        df = generate_data.generate_market(n_candles=N_CANDLES, seed=seed)
        trades = simulate(df, rr=3.0)
        if not trades:
            continue
        freq_per_month = len(trades) / MONTHS_IN_DATASET
        exp = np.mean([t.r_multiple for t in trades])
        all_freqs.append(freq_per_month)
        all_exp.append(exp)

    avg_trades_month = np.mean(all_freqs)
    avg_exp_r        = np.mean(all_exp)
    std_exp_r        = np.std(all_exp)

    print("\n" + "═"*62)
    print("      PROYECCIÓN DE RENTABILIDAD — TRADING BOT SMC+WYCKOFF")
    print("═"*62)
    print(f"\n  Datos base (12 simulaciones × {N_CANDLES:,} velas H1):")
    print(f"  Trades/mes           : {avg_trades_month:.1f}")
    print(f"  Expectancy media     : +{avg_exp_r:.3f} R/trade (±{std_exp_r:.3f})")

    # ── 2. Proyección por nivel de riesgo ─────────────────────────────────────
    BALANCE = 1000.0
    risk_levels = [
        ("Conservador",  0.5,  "Recomendado para demo $1k"),
        ("Moderado",     1.0,  "Tras 2 meses demo positivos"),
        ("Agresivo",     2.0,  "Solo tras 3+ meses de track record"),
    ]

    print(f"\n  {'─'*58}")
    print(f"  {'NIVEL':<14} {'RIESGO':>7} {'MENSUAL':>9} {'ANUAL':>9} {'3 AÑOS':>9}")
    print(f"  {'─'*58}")

    for label, risk_pct, nota in risk_levels:
        # Ganancia por trade = expectancy × riesgo_pct
        gain_per_trade_pct = avg_exp_r * risk_pct / 100.0   # fracción del balance

        # Crecimiento mensual compuesto (N trades por mes)
        monthly_factor = (1 + gain_per_trade_pct) ** avg_trades_month
        monthly_ret    = (monthly_factor - 1) * 100
        annual_ret     = (monthly_factor**12 - 1) * 100
        three_year     = (monthly_factor**36 - 1) * 100

        balance_1y  = BALANCE * monthly_factor**12
        balance_3y  = BALANCE * monthly_factor**36

        print(f"  {label:<14} {risk_pct:>5.1f}%  {monthly_ret:>+7.2f}%  {annual_ret:>+8.1f}%  {three_year:>+8.1f}%")

    print(f"  {'─'*58}")

    # ── 3. Escenario detallado conservador (0.5%) con compounding ─────────────
    print(f"\n  ESCENARIO CONSERVADOR ($1,000 | riesgo 0.5% | R:R 1:3)")
    print(f"  {'─'*44}")

    risk_pct = 0.5
    gain_per_trade_pct = avg_exp_r * risk_pct / 100.0
    monthly_factor = (1 + gain_per_trade_pct) ** avg_trades_month
    balance = BALANCE

    print(f"  {'Mes':<6} {'Balance':>10} {'Ganancia mes':>14} {'Retorno acum.':>14}")
    for m in range(1, 13):
        prev = balance
        balance *= monthly_factor
        ganancia = balance - prev
        ret_acum = (balance / BALANCE - 1) * 100
        print(f"  {m:<6} ${balance:>9,.2f}   ${ganancia:>+9.2f}   {ret_acum:>+11.1f}%")

    balance_1y = balance
    print(f"\n  Balance a 12 meses  : ${balance_1y:>9,.2f}  ({(balance_1y/BALANCE-1)*100:+.1f}%)")
    balance_3y = BALANCE * monthly_factor**36
    print(f"  Balance a 36 meses  : ${balance_3y:>9,.2f}  ({(balance_3y/BALANCE-1)*100:+.1f}%)")

    # ── 4. Peor escenario estadístico (expectancy - 1σ) ───────────────────────
    print(f"\n  PEOR CASO ESTADÍSTICO (-1σ expectancy)")
    exp_low = avg_exp_r - std_exp_r
    gptp_low = exp_low * 0.5 / 100.0
    mf_low = (1 + gptp_low) ** avg_trades_month
    mr_low = (mf_low - 1) * 100
    ar_low = (mf_low**12 - 1) * 100
    print(f"  Expectancy usada     : +{exp_low:.3f} R")
    if mr_low > 0:
        print(f"  Mensual              : {mr_low:+.2f}%  |  Anual: {ar_low:+.1f}%")
    else:
        print(f"  Mensual              : {mr_low:+.2f}%  ← temporada de pérdidas")
        print(f"  Balance tras 12 meses (riesgo 0.5%): ${BALANCE * mf_low**12:,.2f}")

    # ── 5. Regla de escalado progresivo ───────────────────────────────────────
    print(f"\n  REGLA DE ESCALADO PROGRESIVO (para llegar a capital serio)")
    print(f"  {'─'*44}")
    escalado = [
        (1, 3,   0.5, "Fase demo: validar edge"),
        (4, 6,   0.5, "Live conservador, mismo riesgo"),
        (7, 12,  1.0, "Subir riesgo solo si DD<5%"),
        (13, 24, 2.0, "Moderado si 6+ meses positivos"),
    ]
    for m_ini, m_fin, rp, desc in escalado:
        gpt = avg_exp_r * rp / 100.0
        mf = (1 + gpt) ** avg_trades_month
        mr = (mf - 1) * 100
        print(f"  Mes {m_ini:>2}–{m_fin:<2}  riesgo {rp}%  →  ~{mr:+.2f}%/mes  ({desc})")

    print("\n" + "═"*62)
    print("  ⚠  Proyección basada en datos sintéticos. Los mercados reales")
    print("     tienen slippage, correlaciones y eventos inesperados.")
    print("     Valida SIEMPRE con histórico real de tu broker antes de live.")
    print("═"*62 + "\n")


if __name__ == "__main__":
    run_projection()
