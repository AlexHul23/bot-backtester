"""
optimizer.py
Búsqueda automática de parámetros ("no sé qué estrategia usar, dime tú").

En vez de que el usuario elija parámetros a ciegas, probamos muchas
combinaciones razonables por regla y las rankeamos con los mismos
criterios que usarías para validar un bot para prop firm:
Profit Factor, Sharpe aproximado y control de Drawdown.

Esto NO reemplaza al motor genético completo (fase 2 del roadmap),
pero da un punto de partida basado en datos reales en vez de intuición.
"""
import itertools
import pandas as pd

from engine import StrategyConfig, run_backtest
from metrics import compute_metrics

# Rangos de parámetros por regla. Deliberadamente acotados para que
# la búsqueda corra en segundos en el hosting gratuito.
PARAM_GRIDS = {
    "ema_cross": {
        "fast_period": [8, 12, 20],
        "slow_period": [50, 100, 200],
    },
    "rsi_reversion": {
        "rsi_period": [7, 14, 21],
        "rsi_oversold": [20, 30],
        "rsi_overbought": [70, 80],
    },
    "donchian_breakout": {
        "donchian_period": [10, 20, 55],
    },
    "smc_confluence": {
        "smc_require_choch": [False, True],
        "smc_require_ob_or_fvg": [True, False],
        "smc_require_confirmation": [True, False],
        "smc_require_killzone": [False, True],
    },
}

RISK_GRID = {
    "sl_atr_mult": [1.0, 1.5, 2.5],
    "tp_atr_mult": [2.0, 3.0, 5.0],
}


def _combinations(grid: dict):
    keys = list(grid.keys())
    for combo in itertools.product(*grid.values()):
        yield dict(zip(keys, combo))


def run_grid_search(df: pd.DataFrame, entry_rule: str, base_cfg_kwargs: dict, max_combos: int = 60) -> pd.DataFrame:
    """
    Prueba combinaciones de parámetros para `entry_rule` sobre `df`.
    Devuelve un DataFrame ordenado por score de robustez (mejor primero).
    """
    rule_grid = PARAM_GRIDS.get(entry_rule, {})
    results = []
    count = 0

    for rule_params in _combinations(rule_grid):
        if entry_rule == "ema_cross" and rule_params["fast_period"] >= rule_params["slow_period"]:
            continue  # combinación inválida

        for risk_params in _combinations(RISK_GRID):
            if count >= max_combos:
                break
            count += 1

            cfg_kwargs = dict(base_cfg_kwargs)
            cfg_kwargs.update(rule_params)
            cfg_kwargs.update(risk_params)
            cfg_kwargs["entry_rule"] = entry_rule

            cfg = StrategyConfig(**cfg_kwargs)
            trades, equity, final_balance = run_backtest(df, cfg)
            stats = compute_metrics(trades, equity, cfg.initial_balance)

            if stats["Total Trades"] < 10:
                continue  # muy pocos trades para confiar en el resultado

            pf = stats["Profit Factor"]
            pf_value = pf if isinstance(pf, (int, float)) else 999.0
            sharpe = stats["Sharpe (aprox)"]
            max_dd = abs(stats["Max Drawdown %"])

            # score simple: premia PF y Sharpe altos, castiga drawdown alto.
            # Referencia (igual a tus criterios de prop firm): PF>1.6, Sharpe>1.5, DD<20%
            score = (pf_value * 1.0) + (sharpe * 0.5) - (max_dd * 0.05)

            row = {**rule_params, **risk_params, "score": round(score, 2)}
            row.update(stats)
            results.append(row)

    if not results:
        return pd.DataFrame()

    result_df = pd.DataFrame(results).sort_values("score", ascending=False).reset_index(drop=True)
    return result_df
