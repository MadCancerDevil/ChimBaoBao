# -*- coding: utf-8 -*-
"""Mo hinh nen (candlestick) va mo hinh cum gia (chart patterns)."""

import numpy as np
import pandas as pd

from analysis import find_swings


# ---------------------------------------------------------------
# Tien ich doc nen
# ---------------------------------------------------------------

def _parts(row):
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    body = abs(c - o)
    rng = max(h - l, 1e-9)
    upper = h - max(o, c)
    lower = min(o, c) - l
    return o, h, l, c, body, rng, upper, lower


def _green(row):
    return row["close"] > row["open"]


def _red(row):
    return row["close"] < row["open"]


def _downtrend_before(df, i, n=5):
    seg = df["close"].iloc[max(0, i - n):i]
    return len(seg) >= 3 and seg.iloc[-1] < seg.iloc[0]


def _uptrend_before(df, i, n=5):
    seg = df["close"].iloc[max(0, i - n):i]
    return len(seg) >= 3 and seg.iloc[-1] > seg.iloc[0]


# ---------------------------------------------------------------
# ~10 mo hinh nen kinh dien (muc 1)
# ---------------------------------------------------------------

def detect_candles(df):
    """Nhan dien mo hinh nen tai nen cuoi cung.
    Tra ve list (ten, huong) voi huong: 'bull' / 'bear' / 'neutral'."""
    if len(df) < 6:
        return []
    out = []
    i = len(df) - 1
    cur = df.iloc[i]
    prev = df.iloc[i - 1]
    p2 = df.iloc[i - 2]
    o, h, l, c, body, rng, upper, lower = _parts(cur)
    po, ph, pl, pc, pbody, prng, pupper, plower = _parts(prev)

    # Doji
    if body <= 0.1 * rng:
        out.append(("Doji", "neutral"))

    # Hammer / Bua (sau chuoi giam)
    if lower >= 2 * body and upper <= max(0.15 * rng, 0.6 * body) \
            and body > 0.05 * rng and _downtrend_before(df, i):
        out.append(("Hammer (Búa)", "bull"))

    # Shooting Star / Sao Bang (sau chuoi tang)
    if upper >= 2 * body and lower <= max(0.15 * rng, 0.6 * body) \
            and body > 0.05 * rng and _uptrend_before(df, i):
        out.append(("Shooting Star (Sao Băng)", "bear"))

    # Bullish / Bearish Engulfing
    if _red(prev) and _green(cur) and c >= max(po, pc) and o <= min(po, pc) \
            and body > pbody:
        out.append(("Bullish Engulfing (Nhấn chìm tăng)", "bull"))
    if _green(prev) and _red(cur) and o >= max(po, pc) and c <= min(po, pc) \
            and body > pbody:
        out.append(("Bearish Engulfing (Nhấn chìm giảm)", "bear"))

    # Piercing Line / Dark Cloud Cover
    if _red(prev) and _green(cur) and o < pc \
            and c > (po + pc) / 2 and c < po:
        out.append(("Piercing Line (Đường nhọn)", "bull"))
    if _green(prev) and _red(cur) and o > pc \
            and c < (po + pc) / 2 and c > po:
        out.append(("Dark Cloud Cover (Mây đen)", "bear"))

    # Morning Star / Evening Star (cum 3 nen)
    o2, h2, l2, c2, b2, r2, u2, lo2 = _parts(p2)
    if _red(p2) and b2 > 0.5 * r2 and pbody <= 0.3 * prng \
            and _green(cur) and c > (o2 + c2) / 2:
        out.append(("Morning Star (Sao Mai)", "bull"))
    if _green(p2) and b2 > 0.5 * r2 and pbody <= 0.3 * prng \
            and _red(cur) and c < (o2 + c2) / 2:
        out.append(("Evening Star (Sao Hôm)", "bear"))

    # Marubozu
    if body >= 0.9 * rng and rng > 0:
        out.append(("Marubozu tăng" if _green(cur) else "Marubozu giảm",
                    "bull" if _green(cur) else "bear"))

    # Three White Soldiers / Three Black Crows
    last3 = [df.iloc[i - 2], df.iloc[i - 1], cur]
    if all(_green(x) for x in last3) \
            and last3[0]["close"] < last3[1]["close"] < last3[2]["close"] \
            and all(_parts(x)[4] > 0.5 * _parts(x)[5] for x in last3):
        out.append(("Three White Soldiers (3 chàng lính)", "bull"))
    if all(_red(x) for x in last3) \
            and last3[0]["close"] > last3[1]["close"] > last3[2]["close"] \
            and all(_parts(x)[4] > 0.5 * _parts(x)[5] for x in last3):
        out.append(("Three Black Crows (3 con quạ)", "bear"))

    return out


def confluence_score(direction, price, levels, last, vol_ratio, trends,
                     rsi_oversold=35, rsi_overbought=72):
    """Cham diem hop luu 0-5 cho mot mo hinh nen dao chieu."""
    score = 1  # ban than mo hinh
    detail = ["mô hình nến"]

    # Vi tri: gan ho tro (bull) / khang cu (bear) trong pham vi 2.5%
    if direction == "bull" and levels.get("buy_zone_high"):
        ref = levels["buy_zone_high"]
        if ref and abs(price - ref) / ref <= 0.025 or \
                (levels["buy_zone_low"] or 0) <= price <= ref:
            score += 1
            detail.append("tại vùng hỗ trợ")
    if direction == "bear" and levels.get("breakout_level"):
        ref = levels["breakout_level"]
        if ref and abs(price - ref) / ref <= 0.025:
            score += 1
            detail.append("tại vùng kháng cự")

    # RSI cuc doan
    rsi = last.get("rsi") if isinstance(last, dict) else last["rsi"]
    if pd.notna(rsi):
        if direction == "bull" and rsi <= rsi_oversold + 5:
            score += 1
            detail.append(f"RSI thấp ({rsi:.0f})")
        if direction == "bear" and rsi >= rsi_overbought - 5:
            score += 1
            detail.append(f"RSI cao ({rsi:.0f})")

    # Volume
    if vol_ratio >= 1.5:
        score += 1
        detail.append(f"volume {vol_ratio:.1f}x")

    # Xu huong tuan cung huong
    wk = trends.get("1 tuần", "")
    if (direction == "bull" and "TĂNG" in wk) or \
            (direction == "bear" and "GIẢM" in wk):
        score += 1
        detail.append("khung tuần cùng hướng")

    return score, detail


# ---------------------------------------------------------------
# Mo hinh cum gia (muc 5)
# ---------------------------------------------------------------

def detect_rectangle(df, min_bars=15, max_width_pct=10.0):
    """Hinh chu nhat tich luy tren cac nen DA DONG (bo nen hom nay).
    Tra ve dict mo ta hoac None."""
    closed = df.iloc[:-1]
    if len(closed) < min_bars + 5:
        return None
    best = None
    for n in range(min(60, len(closed)), min_bars - 1, -1):
        win = closed.tail(n)
        hi, lo = float(win["high"].max()), float(win["low"].min())
        mid = float(win["close"].mean())
        width = (hi - lo) / mid * 100
        if width <= max_width_pct:
            best = {"type": "rectangle", "bars": n, "high": hi, "low": lo,
                    "width_pct": round(width, 1)}
            break
    return best


def detect_double_triple(df, tol=0.025):
    """2-3 dinh hoac 2-3 day gan bang nhau. Tra ve dict hoac None."""
    highs, lows = find_swings(df.iloc[:-1])
    out = None
    # Dinh
    if len(highs) >= 2:
        pts = highs[-3:]
        prices = [p for _, p in pts]
        ref = prices[-1]
        near = [p for p in prices if abs(p - ref) / ref <= tol]
        if len(near) >= 2:
            i_from = pts[0][0] if len(near) == len(pts) else pts[-2][0]
            neckline = float(df["low"].iloc[i_from:].min())
            out = {"type": f"{len(near)} đỉnh", "level": ref,
                   "neckline": neckline, "direction": "bear"}
    # Day (uu tien neu moi hon)
    if len(lows) >= 2:
        pts = lows[-3:]
        prices = [p for _, p in pts]
        ref = prices[-1]
        near = [p for p in prices if abs(p - ref) / ref <= tol]
        if len(near) >= 2:
            i_from = pts[0][0] if len(near) == len(pts) else pts[-2][0]
            neckline = float(df["high"].iloc[i_from:-1].max())
            cand = {"type": f"{len(near)} đáy", "level": ref,
                    "neckline": neckline, "direction": "bull"}
            if out is None or lows[-1][0] > highs[-1][0]:
                out = cand
    return out


def detect_head_shoulders(df, tol=0.035):
    """Vai dau vai: 3 swing dinh, dinh giua cao nhat, 2 vai xap xi."""
    highs, lows = find_swings(df.iloc[:-1])
    if len(highs) < 3:
        return None
    (i1, p1), (i2, p2), (i3, p3) = highs[-3:]
    if p2 > p1 and p2 > p3 and abs(p1 - p3) / p3 <= tol \
            and p2 / max(p1, p3) >= 1.02:
        between = df["low"].iloc[i1:i3 + 1]
        neckline = float(between.min())
        return {"type": "Vai-Đầu-Vai", "head": p2, "neckline": neckline,
                "direction": "bear"}
    return None


def detect_converging(df):
    """Mau hinh hoi tu (tam giac/nem): dinh thap dan + day cao dan
    (hoac mot ben phang), bien do thu hep >= 30%."""
    closed = df.iloc[:-1].tail(60).reset_index(drop=True)
    highs, lows = find_swings(closed)
    if len(highs) < 3 or len(lows) < 3:
        return None
    hx = np.array([i for i, _ in highs[-4:]])
    hy = np.array([p for _, p in highs[-4:]])
    lx = np.array([i for i, _ in lows[-4:]])
    ly = np.array([p for _, p in lows[-4:]])
    sh = np.polyfit(hx, hy, 1)[0]
    sl = np.polyfit(lx, ly, 1)[0]
    mean_p = float(closed["close"].mean())
    sh_pct, sl_pct = sh / mean_p * 100, sl / mean_p * 100
    # Hoi tu: canh tren khong tang, canh duoi khong giam, va co thu hep
    if sh_pct <= 0.05 and sl_pct >= -0.05 and (sl_pct - sh_pct) > 0.08:
        start_rng = hy[0] - ly[0]
        end_rng = hy[-1] - ly[-1]
        if start_rng > 0 and end_rng / start_rng <= 0.7:
            shape = ("nêm/tam giác dốc lên" if sl_pct > 0.1 and sh_pct > -0.05
                     else "nêm/tam giác dốc xuống" if sh_pct < -0.1
                     else "tam giác cân")
            upper_now = float(np.polyval(np.polyfit(hx, hy, 1),
                                         len(closed) - 1))
            lower_now = float(np.polyval(np.polyfit(lx, ly, 1),
                                         len(closed) - 1))
            return {"type": f"hội tụ ({shape})", "upper": upper_now,
                    "lower": lower_now}
    return None


def track_chart_patterns(df):
    """Tong hop cac mau hinh cum dang hinh thanh (theo doi ngam)."""
    tracked = []
    r = detect_rectangle(df)
    if r:
        tracked.append(r)
    d = detect_double_triple(df)
    if d:
        tracked.append(d)
    hs = detect_head_shoulders(df)
    if hs:
        tracked.append(hs)
    cv = detect_converging(df)
    if cv:
        tracked.append(cv)
    return tracked


def chart_breakout_signals(symbol, df, tracked, vol_ratio, spike_ratio):
    """Tin hieu pha vo mau hinh cum + volume (chi luc nay moi ban canh bao).
    Tra ve list (key, message)."""
    if len(df) < 3:
        return []
    price = float(df.iloc[-1]["close"])
    prev = float(df.iloc[-2]["close"])
    vol_ok = vol_ratio >= spike_ratio
    sigs = []

    for p in tracked:
        t = p["type"]
        if t == "rectangle":
            hi, lo = p["high"], p["low"]
            target_up = round(hi + (hi - lo))
            target_dn = round(lo - (hi - lo))
            if prev <= hi < price and vol_ok:
                sigs.append((f"CHART_RECT_UP", (
                    f"🔺 <b>[{symbol}] Phá vỡ hình chữ nhật {p['bars']} phiên"
                    f"</b>\nVượt cạnh trên {hi:,.0f}đ, volume {vol_ratio:.1f}x"
                    f"\n🎯 Mục tiêu đo mẫu hình: ~{target_up:,}đ")))
            if prev >= lo > price and vol_ok:
                sigs.append((f"CHART_RECT_DN", (
                    f"🔻 <b>[{symbol}] Thủng hình chữ nhật {p['bars']} phiên"
                    f"</b>\nGãy cạnh dưới {lo:,.0f}đ, volume {vol_ratio:.1f}x"
                    f"\n⚠️ Mục tiêu đo mẫu hình: ~{target_dn:,}đ")))
        elif "đỉnh" in t or t == "Vai-Đầu-Vai":
            neck = p["neckline"]
            if prev >= neck > price and vol_ok:
                sigs.append((f"CHART_TOP_BREAK", (
                    f"🔻 <b>[{symbol}] Gãy viền cổ mẫu hình {t}</b>\n"
                    f"Thủng {neck:,.0f}đ kèm volume {vol_ratio:.1f}x — "
                    "tín hiệu phân phối đỉnh, cân nhắc giảm tỷ trọng.")))
        elif "đáy" in t:
            neck = p["neckline"]
            if prev <= neck < price and vol_ok:
                height = neck - p["level"]
                sigs.append((f"CHART_BOTTOM_BREAK", (
                    f"🔺 <b>[{symbol}] Xác nhận mẫu hình {t}</b>\n"
                    f"Vượt viền cổ {neck:,.0f}đ kèm volume {vol_ratio:.1f}x"
                    f"\n🎯 Mục tiêu đo mẫu hình: ~{round(neck + height):,}đ")))
        elif "hội tụ" in t:
            if p["upper"] <= p["lower"]:
                continue  # hai canh da cat nhau - mau hinh het hieu luc
            if prev <= p["upper"] < price and vol_ok:
                sigs.append((f"CHART_CONV_UP", (
                    f"🔺 <b>[{symbol}] Phá vỡ mẫu hình {t}</b>\n"
                    f"Vượt cạnh trên ~{p['upper']:,.0f}đ, volume "
                    f"{vol_ratio:.1f}x")))
            if prev >= p["lower"] > price and vol_ok:
                sigs.append((f"CHART_CONV_DN", (
                    f"🔻 <b>[{symbol}] Gãy mẫu hình {t}</b>\n"
                    f"Thủng cạnh dưới ~{p['lower']:,.0f}đ, volume "
                    f"{vol_ratio:.1f}x")))
    return sigs


def describe_tracked(tracked):
    """Mo ta ngan gon cac mau hinh dang theo doi (cho /status, bao cao)."""
    if not tracked:
        return None
    parts = []
    for p in tracked:
        t = p["type"]
        if t == "rectangle":
            parts.append(f"chữ nhật {p['bars']} phiên "
                         f"{p['low']:,.0f}-{p['high']:,.0f}đ "
                         f"(nén {p['width_pct']}%)")
        elif "hội tụ" in t:
            parts.append(f"{t} {p['lower']:,.0f}-{p['upper']:,.0f}đ")
        elif t == "Vai-Đầu-Vai":
            parts.append(f"{t}, viền cổ {p['neckline']:,.0f}đ")
        else:
            parts.append(f"{t} quanh {p['level']:,.0f}đ, "
                         f"viền cổ {p['neckline']:,.0f}đ")
    return "; ".join(parts)
