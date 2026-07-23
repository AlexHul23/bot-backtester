"""
engine.py
Motor de backtesting orientado a trades (no solo vectorizado),
para poder simular SL/TP, position sizing y una posición a la vez,
igual que lo harías en MQL5.

Diseño pensado para que luego puedas añadir:
- generación genética de reglas
- walk-forward
- Monte Carlo
sin reescribir el core.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List

import indicators as ind


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    direction: str  # "long" or "short"
    sl: float
    tp: float
    size: float
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl: float = 0.0


@dataclass
class StrategyConfig:
    entry_rule: str          # "ema_cross", "rsi_reversion", "donchian_breakout"
    fast_period: int = 12
    slow_period: int = 26
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    donchian_period: int = 20
    atr_period: int = 14
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 3.0
    risk_per_trade_pct: float = 1.0   # % del balance arriesgado por trade
    allow_shorts: bool = True
    initial_balance: float = 10000.0
    point_value: float = 1.0          # valor monetario de 1.0 de precio por 1 unidad de tamaño (ajusta según instrumento)


def build_signals(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    """Calcula indicadores y columnas de señal long/short según la regla elegida."""
    df = df.copy()
    df["ATR"] = ind.atr(df, cfg.atr_period)

    if cfg.entry_rule == "ema_cross":
        df["fast"] = ind.ema(df["Close"], cfg.fast_period)
        df["slow"] = ind.ema(df["Close"], cfg.slow_period)
        cross_up = (df["fast"] > df["slow"]) & (df["fast"].shift(1) <= df["slow"].shift(1))
        cross_down = (df["fast"] < df["slow"]) & (df["fast"].shift(1) >= df["slow"].shift(1))
        df["long_signal"] = cross_up
        df["short_signal"] = cross_down

    elif cfg.entry_rule == "rsi_reversion":
        df["rsi"] = ind.rsi(df["Close"], cfg.rsi_period)
        df["long_signal"] = (df["rsi"] < cfg.rsi_oversold) & (df["rsi"].shift(1) >= cfg.rsi_oversold)
        df["short_signal"] = (df["rsi"] > cfg.rsi_overbought) & (df["rsi"].shift(1) <= cfg.rsi_overbought)

    elif cfg.entry_rule == "donchian_breakout":
        df["dc_high"] = ind.donchian_high(df, cfg.donchian_period).shift(1)
        df["dc_low"] = ind.donchian_low(df, cfg.donchian_period).shift(1)
        df["long_signal"] = df["Close"] > df["dc_high"]
        df["short_signal"] = df["Close"] < df["dc_low"]

    else:
        raise ValueError(f"Regla de entrada desconocida: {cfg.entry_rule}")

    df["long_signal"] = df["long_signal"].fillna(False)
    df["short_signal"] = df["short_signal"].fillna(False)
    return df


def run_backtest(df: pd.DataFrame, cfg: StrategyConfig):
    """
    Simula trade-by-trade, una posición abierta a la vez (como una EA simple).
    Devuelve: lista de Trade, curva de equity (pd.Series), balance final.
    """
    df = build_signals(df, cfg)

    balance = cfg.initial_balance
    equity_curve = []
    trades: List[Trade] = []
    open_trade: Optional[Trade] = None

    for i in range(len(df)):
        row = df.iloc[i]
        time = df.index[i]
        price = row["Close"]
        atr_val = row["ATR"]

        # --- gestionar posición abierta: revisar SL/TP con High/Low de la vela ---
        if open_trade is not None:
            hit_sl = hit_tp = False
            if open_trade.direction == "long":
                hit_sl = row["Low"] <= open_trade.sl
                hit_tp = row["High"] >= open_trade.tp
            else:
                hit_sl = row["High"] >= open_trade.sl
                hit_tp = row["Low"] <= open_trade.tp

            if hit_sl or hit_tp:
                exit_price = open_trade.sl if hit_sl else open_trade.tp
                reason = "SL" if hit_sl else "TP"
                pnl = _calc_pnl(open_trade, exit_price, cfg.point_value)
                open_trade.exit_time = time
                open_trade.exit_price = exit_price
                open_trade.exit_reason = reason
                open_trade.pnl = pnl
                balance += pnl
                trades.append(open_trade)
                open_trade = None

        # --- abrir nueva posición si no hay una abierta y hay señal ---
        if open_trade is None and not np.isnan(atr_val) and atr_val > 0:
            direction = None
            if row["long_signal"]:
                direction = "long"
            elif cfg.allow_shorts and row["short_signal"]:
                direction = "short"

            if direction is not None:
                sl_dist = atr_val * cfg.sl_atr_mult
                tp_dist = atr_val * cfg.tp_atr_mult
                if direction == "long":
                    sl = price - sl_dist
                    tp = price + tp_dist
                else:
                    sl = price + sl_dist
                    tp = price - tp_dist

                size = _position_size(balance, cfg.risk_per_trade_pct, sl_dist, cfg.point_value)
                if size > 0:
                    open_trade = Trade(
                        entry_time=time, entry_price=price, direction=direction,
                        sl=sl, tp=tp, size=size,
                    )

        # equity marcada a mercado (incluye posición abierta flotante)
        floating = 0.0
        if open_trade is not None:
            floating = _calc_pnl(open_trade, price, cfg.point_value)
        equity_curve.append(balance + floating)

    equity_series = pd.Series(equity_curve, index=df.index, name="equity")
    return trades, equity_series, balance


def _calc_pnl(trade: Trade, exit_price: float, point_value: float) -> float:
    diff = (exit_price - trade.entry_price) if trade.direction == "long" else (trade.entry_price - exit_price)
    return diff * trade.size * point_value


def _position_size(balance: float, risk_pct: float, sl_distance: float, point_value: float) -> float:
    if sl_distance <= 0:
        return 0.0
    risk_amount = balance * (risk_pct / 100.0)
    size = risk_amount / (sl_distance * point_value)
    return max(size, 0.0)
