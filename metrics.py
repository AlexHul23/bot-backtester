"""
metrics.py
Métricas estándar para evaluar si un bot es "bueno" de verdad,
no solo que tenga una curva bonita.
"""
import pandas as pd
import numpy as np


def compute_metrics(trades, equity: pd.Series, initial_balance: float) -> dict:
    if len(trades) == 0:
        return {
            "Total Trades": 0,
            "Win Rate %": 0.0,
            "Profit Factor": 0.0,
            "Net Profit": 0.0,
            "Net Profit %": 0.0,
            "Max Drawdown %": 0.0,
            "Sharpe (aprox)": 0.0,
            "Avg Trade": 0.0,
        }

    pnls = np.array([t.pnl for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    win_rate = len(wins) / len(pnls) * 100 if len(pnls) else 0
    gross_profit = wins.sum() if len(wins) else 0
    gross_loss = abs(losses.sum()) if len(losses) else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else np.inf

    net_profit = pnls.sum()
    net_profit_pct = net_profit / initial_balance * 100

    # Max drawdown sobre la curva de equity
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max * 100
    max_dd = drawdown.min()

    # Sharpe aproximado usando retornos diarios de la curva de equity
    daily_equity = equity.resample("D").last().dropna()
    daily_returns = daily_equity.pct_change().dropna()
    if len(daily_returns) > 1 and daily_returns.std() != 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    else:
        sharpe = 0.0

    return {
        "Total Trades": len(trades),
        "Win Rate %": round(win_rate, 2),
        "Profit Factor": round(profit_factor, 2) if profit_factor != np.inf else "inf",
        "Net Profit": round(net_profit, 2),
        "Net Profit %": round(net_profit_pct, 2),
        "Max Drawdown %": round(max_dd, 2),
        "Sharpe (aprox)": round(sharpe, 2),
        "Avg Trade": round(pnls.mean(), 2),
    }


def trades_to_dataframe(trades) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=[
            "entry_time", "exit_time", "direction", "entry_price",
            "exit_price", "sl", "tp", "exit_reason", "pnl"
        ])
    return pd.DataFrame([{
        "entry_time": t.entry_time,
        "exit_time": t.exit_time,
        "direction": t.direction,
        "entry_price": round(t.entry_price, 5),
        "exit_price": round(t.exit_price, 5) if t.exit_price else None,
        "sl": round(t.sl, 5),
        "tp": round(t.tp, 5),
        "exit_reason": t.exit_reason,
        "pnl": round(t.pnl, 2),
    } for t in trades])
