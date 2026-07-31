"""
smc.py
Conceptos de Smart Money Concepts (SMC) calculados sobre velas OHLC.

PRINCIPIO DE DISEÑO MÁS IMPORTANTE: cero look-ahead bias.
Un swing high/low real solo se puede confirmar varias velas DESPUÉS de que
ocurrió (necesitas ver que el precio se movió en contra para saber que ahí
hubo un extremo). Todo en este módulo respeta eso: cualquier información
sobre "lo que pasó en la vela i" solo se vuelve disponible/usable en filas
posteriores a i, nunca antes. Esto es lo que el reproductor de velas en la
app te deja verificar visualmente.

Cobertura de este v1 (lo que pediste, priorizado por impacto):
  Estructura:  swings, BOS, CHoCH, tendencia/rango
  Liquidez:    equal highs/lows, liquidity sweep
  Oferta/demanda: order blocks (alcista/bajista)
  Ineficiencias: Fair Value Gap (FVG)
  Contexto:    premium/discount/equilibrium, kill zones (Londres/NY)
  Confirmación: vela envolvente, pin bar, momentum, expansión de volatilidad

Pendiente para v2 (más nicho / requieren más definición operativa antes de
poder detectarse de forma no ambigua): breaker block, mitigation block,
rejection block, liquidez interna vs externa, inverse FVG, volume imbalance.
"""
import numpy as np
import pandas as pd

import indicators as ind


# ---------------------------------------------------------------------------
# ESTRUCTURA: swings, BOS, CHoCH, tendencia
# ---------------------------------------------------------------------------

def swing_points(df: pd.DataFrame, left: int = 2, right: int = 2):
    """
    Detecta swing highs/lows con un fractal simétrico (left velas antes,
    right velas después). Devuelve las señales YA DESPLAZADAS `right` velas
    hacia adelante, para que representen el momento en que la información
    está realmente disponible (no antes) — así se evita look-ahead.
    """
    window = left + right + 1
    is_high = df["High"] == df["High"].rolling(window, center=True).max()
    is_low = df["Low"] == df["Low"].rolling(window, center=True).min()

    confirmed_high = is_high.shift(right).fillna(False).astype(bool)
    confirmed_low = is_low.shift(right).fillna(False).astype(bool)
    swing_high_price = df["High"].shift(right).where(confirmed_high)
    swing_low_price = df["Low"].shift(right).where(confirmed_low)

    return confirmed_high, confirmed_low, swing_high_price, swing_low_price


def market_structure(df: pd.DataFrame, swing_left: int = 2, swing_right: int = 2) -> pd.DataFrame:
    """
    Calcula tendencia vigente, BOS y CHoCH vela por vela.
    - BOS (Break of Structure): rompimiento de estructura A FAVOR de la
      tendencia vigente (continuación).
    - CHoCH (Change of Character): rompimiento de estructura EN CONTRA de
      la tendencia vigente (primera señal de posible reversión). MSS (Market
      Structure Shift) se trata como sinónimo de CHoCH en este motor.
    Devuelve el df original + columnas nuevas: trend, bos_bull, bos_bear,
    choch_bull, choch_bear, structure_high, structure_low.
    """
    confirmed_high, confirmed_low, sh_price, sl_price = swing_points(df, swing_left, swing_right)

    n = len(df)
    close = df["Close"].values
    sh_vals = sh_price.values
    sl_vals = sl_price.values
    ch = confirmed_high.values
    cl = confirmed_low.values

    trend = np.full(n, None, dtype=object)
    bos_bull = np.zeros(n, dtype=bool)
    bos_bear = np.zeros(n, dtype=bool)
    choch_bull = np.zeros(n, dtype=bool)
    choch_bear = np.zeros(n, dtype=bool)
    structure_high = np.full(n, np.nan)
    structure_low = np.full(n, np.nan)

    cur_trend = None
    cur_sh = np.nan
    cur_sl = np.nan
    broken_sh = False
    broken_sl = False

    for i in range(n):
        if ch[i] and not np.isnan(sh_vals[i]):
            cur_sh = sh_vals[i]
            broken_sh = False
        if cl[i] and not np.isnan(sl_vals[i]):
            cur_sl = sl_vals[i]
            broken_sl = False

        if not np.isnan(cur_sh) and not broken_sh and close[i] > cur_sh:
            broken_sh = True
            if cur_trend in (None, "up"):
                bos_bull[i] = True
            else:
                choch_bull[i] = True
            cur_trend = "up"

        if not np.isnan(cur_sl) and not broken_sl and close[i] < cur_sl:
            broken_sl = True
            if cur_trend in (None, "down"):
                bos_bear[i] = True
            else:
                choch_bear[i] = True
            cur_trend = "down"

        trend[i] = cur_trend
        structure_high[i] = cur_sh
        structure_low[i] = cur_sl

    out = df.copy()
    out["trend"] = trend
    out["bos_bull"] = bos_bull
    out["bos_bear"] = bos_bear
    out["choch_bull"] = choch_bull
    out["choch_bear"] = choch_bear
    out["structure_high"] = structure_high
    out["structure_low"] = structure_low
    return out


# ---------------------------------------------------------------------------
# LIQUIDEZ: equal highs/lows, liquidity sweep
# ---------------------------------------------------------------------------

def equal_levels(df: pd.DataFrame, confirmed_high, confirmed_low, sh_price, sl_price,
                  lookback: int = 50, tolerance_pct: float = 0.05):
    """
    Marca swing highs/lows que están muy cerca de otro swing anterior
    (posible acumulación de liquidez - equal highs / equal lows).
    tolerance_pct: % de distancia máxima entre dos niveles para considerarlos "iguales".
    """
    n = len(df)
    equal_high = np.zeros(n, dtype=bool)
    equal_low = np.zeros(n, dtype=bool)

    sh_idx = np.where(confirmed_high.values)[0]
    sl_idx = np.where(confirmed_low.values)[0]
    sh_vals = sh_price.values
    sl_vals = sl_price.values

    for k, i in enumerate(sh_idx):
        recent = sh_idx[(sh_idx < i) & (sh_idx >= i - lookback)]
        for j in recent:
            if abs(sh_vals[i] - sh_vals[j]) / sh_vals[j] * 100 <= tolerance_pct:
                equal_high[i] = True
                break

    for k, i in enumerate(sl_idx):
        recent = sl_idx[(sl_idx < i) & (sl_idx >= i - lookback)]
        for j in recent:
            if abs(sl_vals[i] - sl_vals[j]) / sl_vals[j] * 100 <= tolerance_pct:
                equal_low[i] = True
                break

    return pd.Series(equal_high, index=df.index), pd.Series(equal_low, index=df.index)


def liquidity_sweep(df: pd.DataFrame, structure_high: pd.Series, structure_low: pd.Series):
    """
    Liquidity sweep (stop hunt): la mecha rompe un nivel de estructura vigente
    pero el CIERRE se queda del lado contrario -> "barrida" de liquidez,
    disparador clásico de entrada SMC.
    """
    sweep_high = (df["High"] > structure_high) & (df["Close"] < structure_high)
    sweep_low = (df["Low"] < structure_low) & (df["Close"] > structure_low)
    return sweep_high.fillna(False), sweep_low.fillna(False)


# ---------------------------------------------------------------------------
# OFERTA Y DEMANDA: Order Blocks
# ---------------------------------------------------------------------------

def order_blocks(df: pd.DataFrame, bos_bull: pd.Series, bos_bear: pd.Series, max_search: int = 20):
    """
    Order Block simplificado: la última vela de color opuesto antes del
    impulso que produjo el BOS. Se calcula EN el momento del BOS (no antes),
    así que no hay look-ahead: para cuando se marca el OB, el BOS ya ocurrió.
    Devuelve 4 series con el techo/piso del OB vigente, propagado hacia
    adelante hasta que aparece uno nuevo.
    """
    n = len(df)
    is_bear_candle = (df["Close"] < df["Open"]).values
    is_bull_candle = (df["Close"] > df["Open"]).values
    high = df["High"].values
    low = df["Low"].values

    bull_ob_high = np.full(n, np.nan)
    bull_ob_low = np.full(n, np.nan)
    bear_ob_high = np.full(n, np.nan)
    bear_ob_low = np.full(n, np.nan)

    cur_bull_high, cur_bull_low = np.nan, np.nan
    cur_bear_high, cur_bear_low = np.nan, np.nan

    bb = bos_bull.values
    be = bos_bear.values

    for i in range(n):
        if bb[i]:
            j = i - 1
            steps = 0
            while j >= 0 and not is_bear_candle[j] and steps < max_search:
                j -= 1
                steps += 1
            if j >= 0 and is_bear_candle[j]:
                cur_bull_high, cur_bull_low = high[j], low[j]
        if be[i]:
            j = i - 1
            steps = 0
            while j >= 0 and not is_bull_candle[j] and steps < max_search:
                j -= 1
                steps += 1
            if j >= 0 and is_bull_candle[j]:
                cur_bear_high, cur_bear_low = high[j], low[j]

        bull_ob_high[i], bull_ob_low[i] = cur_bull_high, cur_bull_low
        bear_ob_high[i], bear_ob_low[i] = cur_bear_high, cur_bear_low

    idx = df.index
    return (pd.Series(bull_ob_high, index=idx), pd.Series(bull_ob_low, index=idx),
            pd.Series(bear_ob_high, index=idx), pd.Series(bear_ob_low, index=idx))


# ---------------------------------------------------------------------------
# INEFICIENCIAS: Fair Value Gap
# ---------------------------------------------------------------------------

def fair_value_gaps(df: pd.DataFrame):
    """
    FVG de 3 velas, estándar SMC. Se confirma en la vela 3 (i), usando solo
    High/Low de las velas i-2 e i -> sin look-ahead.
    """
    bull_fvg = df["Low"] > df["High"].shift(2)
    bear_fvg = df["High"] < df["Low"].shift(2)

    bull_fvg_top = df["Low"].where(bull_fvg)
    bull_fvg_bottom = df["High"].shift(2).where(bull_fvg)
    bear_fvg_top = df["Low"].shift(2).where(bear_fvg)
    bear_fvg_bottom = df["High"].where(bear_fvg)

    return (bull_fvg.fillna(False), bull_fvg_top, bull_fvg_bottom,
            bear_fvg.fillna(False), bear_fvg_top, bear_fvg_bottom)


# ---------------------------------------------------------------------------
# CONTEXTO: premium / discount / equilibrium, kill zones
# ---------------------------------------------------------------------------

def premium_discount_zone(df: pd.DataFrame, structure_high: pd.Series, structure_low: pd.Series,
                           equilibrium_band_pct: float = 5.0) -> pd.Series:
    """
    Divide el rango de estructura vigente en premium (mitad superior, zona
    "cara" para vender) y discount (mitad inferior, zona "barata" para comprar).
    Devuelve strings: 'premium', 'discount', 'equilibrium', o None si no hay
    rango de estructura definido todavía.
    """
    rng = structure_high - structure_low
    eq = structure_low + rng * 0.5
    band = rng * (equilibrium_band_pct / 100.0)

    zone = pd.Series(None, index=df.index, dtype=object)
    valid = rng.notna() & (rng > 0)

    close = df["Close"]
    is_eq = valid & (close - eq).abs() <= band
    is_premium = valid & ~is_eq & (close > eq)
    is_discount = valid & ~is_eq & (close < eq)

    zone[is_eq] = "equilibrium"
    zone[is_premium] = "premium"
    zone[is_discount] = "discount"
    return zone


LONDON_KZ = (7, 10)     # hora UTC
NEWYORK_KZ = (12, 15)   # hora UTC


def kill_zone(index: pd.DatetimeIndex) -> pd.Series:
    """True si la vela cae dentro de la kill zone de Londres o Nueva York (hora UTC)."""
    hours = index.hour
    in_london = (hours >= LONDON_KZ[0]) & (hours < LONDON_KZ[1])
    in_ny = (hours >= NEWYORK_KZ[0]) & (hours < NEWYORK_KZ[1])
    return pd.Series(in_london | in_ny, index=index)


# ---------------------------------------------------------------------------
# CONFIRMACIÓN: velas de entrada
# ---------------------------------------------------------------------------

def confirmation_candles(df: pd.DataFrame, atr_period: int = 14):
    """
    Devuelve 4 series booleanas: bullish_engulfing, bearish_engulfing,
    bullish_pinbar, bearish_pinbar; y 2 series de momentum/expansión de
    volatilidad (booleanas).
    """
    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
    body = (c - o).abs()
    prev_o, prev_c = o.shift(1), c.shift(1)

    bullish_engulfing = (c > o) & (prev_c < prev_o) & (c > prev_o) & (o < prev_c)
    bearish_engulfing = (c < o) & (prev_c > prev_o) & (c < prev_o) & (o > prev_c)

    lower_wick = np.minimum(o, c) - l
    upper_wick = h - np.maximum(o, c)
    bullish_pinbar = (lower_wick >= 2 * body) & (upper_wick <= body)
    bearish_pinbar = (upper_wick >= 2 * body) & (lower_wick <= body)

    atr = ind.atr(df, atr_period)
    momentum_candle = body > (1.5 * atr)
    volatility_expansion = atr > (atr.rolling(20).mean() * 1.3)

    return (bullish_engulfing.fillna(False), bearish_engulfing.fillna(False),
            bullish_pinbar.fillna(False), bearish_pinbar.fillna(False),
            momentum_candle.fillna(False), volatility_expansion.fillna(False))


# ---------------------------------------------------------------------------
# Función de conveniencia: calcula TODO el set de columnas SMC de una vez.
# ---------------------------------------------------------------------------

def build_smc_dataframe(df: pd.DataFrame, swing_left: int = 2, swing_right: int = 2,
                         equal_lookback: int = 50, equal_tolerance_pct: float = 0.05,
                         atr_period: int = 14) -> pd.DataFrame:
    out = market_structure(df, swing_left, swing_right)

    confirmed_high, confirmed_low, sh_price, sl_price = swing_points(df, swing_left, swing_right)
    out["swing_high"] = confirmed_high
    out["swing_low"] = confirmed_low
    out["swing_high_price"] = sh_price
    out["swing_low_price"] = sl_price

    equal_high, equal_low = equal_levels(df, confirmed_high, confirmed_low, sh_price, sl_price,
                                          equal_lookback, equal_tolerance_pct)
    out["equal_high"] = equal_high
    out["equal_low"] = equal_low

    sweep_high, sweep_low = liquidity_sweep(df, out["structure_high"], out["structure_low"])
    out["liquidity_sweep_high"] = sweep_high
    out["liquidity_sweep_low"] = sweep_low

    bull_ob_h, bull_ob_l, bear_ob_h, bear_ob_l = order_blocks(df, out["bos_bull"], out["bos_bear"])
    out["bull_ob_high"] = bull_ob_h
    out["bull_ob_low"] = bull_ob_l
    out["bear_ob_high"] = bear_ob_h
    out["bear_ob_low"] = bear_ob_l

    bull_fvg, bull_top, bull_bot, bear_fvg, bear_top, bear_bot = fair_value_gaps(df)
    out["bull_fvg"] = bull_fvg
    out["bull_fvg_top"] = bull_top
    out["bull_fvg_bottom"] = bull_bot
    out["bear_fvg"] = bear_fvg
    out["bear_fvg_top"] = bear_top
    out["bear_fvg_bottom"] = bear_bot

    out["zone"] = premium_discount_zone(df, out["structure_high"], out["structure_low"])
    out["kill_zone"] = kill_zone(df.index)

    be, se, bp, sp, mom, volexp = confirmation_candles(df, atr_period)
    out["bullish_engulfing"] = be
    out["bearish_engulfing"] = se
    out["bullish_pinbar"] = bp
    out["bearish_pinbar"] = sp
    out["momentum_candle"] = mom
    out["volatility_expansion"] = volexp

    return out
