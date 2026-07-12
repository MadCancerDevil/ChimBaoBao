# -*- coding: utf-8 -*-
"""Module phan tich ky thuat: chi bao, da khung, swing, phan ky, Fibonacci."""

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


# ---------------------------------------------------------------
# Chi bao co ban
# ---------------------------------------------------------------

def rsi_series(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)


def compute_indicators(df, cfg):
    s = cfg["signals"]
    close = df["close"]

    df["ma_short"] = close.rolling(s["ma_short"]).mean()
    df["ma_long"] = close.rolling(s["ma_long"]).mean()
    df["rsi"] = rsi_series(close, s["rsi_period"])

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

    # Volume TB khong tinh phien hien tai
    df["vol_avg"] = (
        df["volume"].shift(1).rolling(s["volume_avg_period"]).mean()
    )
    return df


def session_elapsed_fraction(now=None):
    """Ty le thoi gian phien (9:00-11:30, 13:00-14:45 = 255 phut) da qua."""
    now = now or datetime.now(VN_TZ)
    t = now.hour * 60 + now.minute
    minutes = max(0, min(t, 690) - 540) + max(0, min(t, 885) - 780)
    frac = minutes / 255
    if frac <= 0:
        return 1.0
    return max(0.2, min(1.0, frac))


def volume_ratio(last, candle_is_today=True):
    vol_avg = last["vol_avg"]
    if not pd.notna(vol_avg) or vol_avg <= 0:
        return 0.0
    vol = last["volume"]
    if candle_is_today:
        vol = vol / session_elapsed_fraction()
    return float(vol / vol_avg)


def is_today_candle(df):
    try:
        last_date = pd.to_datetime(df.iloc[-1]["time"]).date()
        return last_date == datetime.now(VN_TZ).date()
    except Exception:
        return False


# ---------------------------------------------------------------
# Da khung thoi gian (muc 2)
# ---------------------------------------------------------------

TREND_WINDOWS = [("1 tuần", 5, 2.0), ("1 tháng", 21, 4.0),
                 ("3 tháng", 63, 8.0), ("9 tháng", 189, 15.0)]


def resample_ohlc(df, rule):
    """Gop nen ngay thanh nen tuan ('W') hoac thang ('ME')."""
    d = df.copy()
    d["time"] = pd.to_datetime(d["time"])
    d = d.set_index("time")
    out = d.resample(rule).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna().reset_index()
    return out


def multi_timeframe_trends(df):
    """Xu huong theo tung khung dua tren % thay doi gia va vi tri so voi MA."""
    close = df["close"]
    trends = {}
    for label, days, thr in TREND_WINDOWS:
        if len(close) <= days:
            trends[label] = "n/a"
            continue
        chg = (close.iloc[-1] / close.iloc[-1 - days] - 1) * 100
        if chg >= thr:
            trends[label] = f"TĂNG ↑ ({chg:+.1f}%)"
        elif chg <= -thr:
            trends[label] = f"GIẢM ↓ ({chg:+.1f}%)"
        else:
            trends[label] = f"ĐI NGANG → ({chg:+.1f}%)"
    return trends


# ---------------------------------------------------------------
# Swing dinh/day (muc 3)
# ---------------------------------------------------------------

def find_swings(df, wing=2):
    """Tim swing high/low theo mau hinh fractal (2 nen moi ben).
    Tra ve (highs, lows) - list cac tuple (index, gia)."""
    highs, lows = [], []
    h, l = df["high"].values, df["low"].values
    for i in range(wing, len(df) - wing):
        if h[i] == max(h[i - wing:i + wing + 1]):
            if not highs or highs[-1][0] < i - wing:
                highs.append((i, float(h[i])))
        if l[i] == min(l[i - wing:i + wing + 1]):
            if not lows or lows[-1][0] < i - wing:
                lows.append((i, float(l[i])))
    return highs, lows


def latest_swing_summary(df):
    """Dinh/day gan nhat da xac nhan (kem ngay)."""
    highs, lows = find_swings(df)
    out = {}
    if highs:
        i, p = highs[-1]
        out["swing_high"] = {"price": p,
                             "date": str(pd.to_datetime(df.iloc[i]["time"]).date())}
    if lows:
        i, p = lows[-1]
        out["swing_low"] = {"price": p,
                            "date": str(pd.to_datetime(df.iloc[i]["time"]).date())}
    return out


# ---------------------------------------------------------------
# Phan ky RSI/MACD (muc 3)
# ---------------------------------------------------------------

def detect_divergence(df, indicator="rsi"):
    """Phan ky giua gia va chi bao tren 2 swing gan nhat.
    Tra ve 'bullish' / 'bearish' / None."""
    if indicator not in df.columns or df[indicator].isna().all():
        return None
    highs, lows = find_swings(df)
    ind = df[indicator].values

    # Phan ky tang: gia tao day thap hon nhung chi bao tao day cao hon
    if len(lows) >= 2:
        (i1, p1), (i2, p2) = lows[-2], lows[-1]
        if not (np.isnan(ind[i1]) or np.isnan(ind[i2])):
            if p2 < p1 * 0.995 and ind[i2] > ind[i1] + 1:
                return "bullish"
    # Phan ky giam: gia tao dinh cao hon nhung chi bao tao dinh thap hon
    if len(highs) >= 2:
        (i1, p1), (i2, p2) = highs[-2], highs[-1]
        if not (np.isnan(ind[i1]) or np.isnan(ind[i2])):
            if p2 > p1 * 1.005 and ind[i2] < ind[i1] - 1:
                return "bearish"
    return None


def all_divergences(df_day, cfg):
    """Phan ky RSI/MACD tren ca khung ngay va tuan."""
    out = []
    for name, d in [("ngày", df_day)]:
        for ind, label in [("rsi", "RSI"), ("macd", "MACD")]:
            r = detect_divergence(d, ind)
            if r:
                out.append((f"{label} khung {name}",
                            "tăng 🟢" if r == "bullish" else "giảm 🔴"))
    # Khung tuan: gop nen roi tinh lai chi bao
    try:
        wk = resample_ohlc(df_day, "W")
        if len(wk) >= 20:
            wk["rsi"] = rsi_series(wk["close"])
            ema12 = wk["close"].ewm(span=12, adjust=False).mean()
            ema26 = wk["close"].ewm(span=26, adjust=False).mean()
            wk["macd"] = ema12 - ema26
            for ind, label in [("rsi", "RSI"), ("macd", "MACD")]:
                r = detect_divergence(wk, ind)
                if r:
                    out.append((f"{label} khung tuần",
                                "tăng 🟢" if r == "bullish" else "giảm 🔴"))
    except Exception:
        pass
    return out


# ---------------------------------------------------------------
# Fibonacci (muc 4)
# ---------------------------------------------------------------

def fibonacci_zones(df):
    """Xac dinh con song chinh gan nhat va cac vung Fib quan trong."""
    look = df.tail(180).reset_index(drop=True)
    i_lo = int(look["low"].idxmin())
    i_hi = int(look["high"].idxmax())
    lo = float(look["low"].min())
    hi = float(look["high"].max())
    if hi <= lo:
        return None
    rng = hi - lo
    price = float(df.iloc[-1]["close"])

    if i_lo < i_hi:  # song tang: day truoc, dinh sau
        levels = {
            "Fib 0.382 (hồi)": hi - rng * 0.382,
            "Fib 0.5 (hồi)": hi - rng * 0.5,
            "Fib 0.618 (hồi)": hi - rng * 0.618,
            "Fib 1.272 (mở rộng)": lo + rng * 1.272,
            "Fib 1.618 (mở rộng)": lo + rng * 1.618,
        }
        direction = "tăng"
    else:  # song giam
        levels = {
            "Fib 0.382 (hồi)": lo + rng * 0.382,
            "Fib 0.5 (hồi)": lo + rng * 0.5,
            "Fib 0.618 (hồi)": lo + rng * 0.618,
        }
        direction = "giảm"

    above = sorted([(k, v) for k, v in levels.items() if v > price],
                   key=lambda x: x[1])
    below = sorted([(k, v) for k, v in levels.items() if v <= price],
                   key=lambda x: -x[1])
    return {
        "direction": direction, "swing_low": lo, "swing_high": hi,
        "nearest_above": above[0] if above else None,
        "nearest_below": below[0] if below else None,
    }
