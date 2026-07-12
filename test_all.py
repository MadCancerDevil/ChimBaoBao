# -*- coding: utf-8 -*-
"""Bo kiem thu tong hop cho Stock Tracker v3."""
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from analysis import (compute_indicators, multi_timeframe_trends,
                      latest_swing_summary, all_divergences,
                      fibonacci_zones, resample_ohlc)
from patterns import (detect_candles, confluence_score, detect_rectangle,
                      detect_double_triple, detect_head_shoulders,
                      detect_converging, chart_breakout_signals,
                      track_chart_patterns)
import portfolio as pfm

PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name} {extra}")
    else:
        FAIL += 1
        print(f"  ✗ FAIL: {name} {extra}")


def mk(closes, opens=None, highs=None, lows=None, vols=None, start="2025-10-01"):
    n = len(closes)
    closes = np.array(closes, dtype=float)
    opens = np.array(opens, dtype=float) if opens is not None \
        else np.roll(closes, 1)
    if opens is None or len(opens) != n:
        opens = np.roll(closes, 1); opens[0] = closes[0]
    highs = np.array(highs, dtype=float) if highs is not None \
        else np.maximum(opens, closes) * 1.005
    lows = np.array(lows, dtype=float) if lows is not None \
        else np.minimum(opens, closes) * 0.995
    vols = np.array(vols, dtype=float) if vols is not None \
        else np.full(n, 700_000.0)
    return pd.DataFrame({
        "time": pd.bdate_range(start, periods=n),
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": vols})


cfg = json.load(open("config.json"))

# ================= 1. MO HINH NEN =================
print("\n[1] Mo hinh nen")
base = list(np.linspace(5000, 4600, 20))  # chuoi giam

# Hammer: than nho phia tren, bong duoi dai
df = mk(base + [4540],
        opens=base[:1] + base[:-1] + [4580],
        highs=[x * 1.005 for x in base] + [4585],
        lows=[x * 0.995 for x in base] + [4380])
found = [n for n, d in detect_candles(df)]
check("Hammer", any("Hammer" in x for x in found), str(found))

# Bullish Engulfing
closes = base + [4550, 4720]
opens = base[:1] + base[:-1] + [4650, 4520]
df = mk(closes, opens=opens)
found = [n for n, d in detect_candles(df)]
check("Bullish Engulfing", any("Nhấn chìm tăng" in x for x in found),
      str(found))

# Bearish Engulfing sau chuoi tang
up = list(np.linspace(4600, 5200, 20))
closes = up + [5250, 5080]
opens = up[:1] + up[:-1] + [5150, 5290]
df = mk(closes, opens=opens)
found = [n for n, d in detect_candles(df)]
check("Bearish Engulfing", any("Nhấn chìm giảm" in x for x in found),
      str(found))

# Shooting Star sau chuoi tang: bong tren dai
df = mk(up + [5210], opens=up[:1] + up[:-1] + [5190],
        highs=[x * 1.005 for x in up] + [5400],
        lows=[x * 0.995 for x in up] + [5185])
found = [n for n, d in detect_candles(df)]
check("Shooting Star", any("Sao Băng" in x for x in found), str(found))

# Morning Star: do lon -> doji nho -> xanh lon
closes = base + [4400, 4390, 4600]
opens = base[:1] + base[:-1] + [4600, 4395, 4420]
df = mk(closes, opens=opens)
found = [n for n, d in detect_candles(df)]
check("Morning Star", any("Sao Mai" in x for x in found), str(found))

# Marubozu
closes = base + [4800]
opens = base[:1] + base[:-1] + [4600]
df = mk(closes, opens=opens,
        highs=[x * 1.005 for x in base] + [4802],
        lows=[x * 0.995 for x in base] + [4599])
found = [n for n, d in detect_candles(df)]
check("Marubozu", any("Marubozu" in x for x in found), str(found))

# Three White Soldiers
closes = base + [4700, 4820, 4950]
opens = base[:1] + base[:-1] + [4600, 4710, 4830]
df = mk(closes, opens=opens)
found = [n for n, d in detect_candles(df)]
check("Three White Soldiers",
      any("3 chàng lính" in x for x in found), str(found))

# Doji
closes = base + [4600]
opens = base[:1] + base[:-1] + [4602]
df = mk(closes, opens=opens,
        highs=[x*1.005 for x in base] + [4650],
        lows=[x*0.995 for x in base] + [4550])
found = [n for n, d in detect_candles(df)]
check("Doji", any("Doji" in x for x in found), str(found))

# ================= 2. CHAM DIEM HOP LUU =================
print("\n[2] Cham diem hop luu")
levels = {"buy_zone_low": 4500, "buy_zone_high": 4650,
          "breakout_level": 5500, "stoploss_level": 4300}
last = {"rsi": 32}
trends = {"1 tuần": "TĂNG ↑ (+3%)"}
score, detail = confluence_score("bull", 4600, levels, last, 2.0, trends)
check("Diem hop luu bull day du = 5", score == 5, f"score={score} {detail}")
score2, _ = confluence_score("bull", 5200, levels, {"rsi": 55}, 0.8,
                             {"1 tuần": "GIẢM ↓"})
check("Diem hop luu bull yeu = 1", score2 == 1, f"score={score2}")

# ================= 3. MO HINH CUM =================
print("\n[3] Mo hinh cum gia")
np.random.seed(7)

# Hinh chu nhat: 30 phien di ngang 5000-5300 + nen pha vo
flat = 5150 + np.random.uniform(-140, 140, 35)
closes = list(np.linspace(4500, 5100, 30)) + list(flat) + [5450]
vols = [700_000] * (len(closes) - 1) + [2_200_000]
df = mk(closes, vols=vols)
tracked = track_chart_patterns(df)
types = [p["type"] for p in tracked]
check("Nhan dien hinh chu nhat", "rectangle" in types, str(types))
rect = [p for p in tracked if p["type"] == "rectangle"]
if rect:
    df2 = compute_indicators(df.copy(), cfg)
    from analysis import volume_ratio
    vr = volume_ratio(df2.iloc[-1], candle_is_today=False)
    sigs = chart_breakout_signals("TEST", df2, rect, vr, 2.5)
    check("Bao pha vo chu nhat kem volume",
          any("RECT_UP" in k for k, _ in sigs),
          str([k for k, _ in sigs]) + f" vr={vr:.1f}")

# 2 day: xuong 4500, len 5000, xuong 4520, vuot vien co 5050
closes = (list(np.linspace(5400, 4500, 25)) + list(np.linspace(4500, 5000, 15))
          + list(np.linspace(5000, 4520, 15)) + list(np.linspace(4520, 4900, 10))
          + [5080])
vols = [700_000] * (len(closes) - 1) + [2_300_000]
df = mk(closes, vols=vols)
dt = detect_double_triple(df)
check("Nhan dien 2 day", dt is not None and "đáy" in dt["type"],
      str(dt))
if dt:
    df2 = compute_indicators(df.copy(), cfg)
    from analysis import volume_ratio
    vr = volume_ratio(df2.iloc[-1], candle_is_today=False)
    sigs = chart_breakout_signals("TEST", df2, [dt], vr, 2.5)
    check("Bao xac nhan 2 day khi vuot vien co",
          any("BOTTOM" in k for k, _ in sigs), str([k for k, _ in sigs]))

# 2 dinh
closes = (list(np.linspace(4500, 5400, 25)) + list(np.linspace(5400, 4900, 15))
          + list(np.linspace(4900, 5380, 15)) + list(np.linspace(5380, 5000, 10))
          + [4830])
vols = [700_000] * (len(closes) - 1) + [2_300_000]
df = mk(closes, vols=vols)
dt = detect_double_triple(df)
check("Nhan dien 2 dinh", dt is not None and "đỉnh" in dt["type"], str(dt))

# Vai dau vai
closes = (list(np.linspace(4400, 5000, 15)) + list(np.linspace(5000, 4700, 8))
          + list(np.linspace(4700, 5400, 12)) + list(np.linspace(5400, 4720, 12))
          + list(np.linspace(4720, 5020, 10)) + list(np.linspace(5020, 4600, 8))
          + [4550])
df = mk(closes)
hs = detect_head_shoulders(df)
check("Nhan dien Vai-Dau-Vai", hs is not None, str(hs))

# Tam giac hoi tu: dinh thap dan, day cao dan
n_sw = 50
xs = np.arange(n_sw)
upper = 5400 - xs * 8
lower = 4800 + xs * 8
closes = [(u + l) / 2 + ((u - l) / 2) * np.sin(i / 2.0)
          for i, (u, l) in enumerate(zip(upper, lower))]
df = mk(list(np.linspace(4500, 5100, 20)) + closes + [closes[-1]])
cv = detect_converging(df)
check("Nhan dien mau hinh hoi tu", cv is not None, str(cv))

# ================= 4. DA KHUNG + SWING + PHAN KY + FIB =================
print("\n[4] Da khung, swing, phan ky, Fibonacci")
n = 200
closes = list(np.linspace(6000, 4000, 100)) + list(np.linspace(4000, 5500, 100))
df = compute_indicators(mk(closes), cfg)
tr = multi_timeframe_trends(df)
check("Xu huong 1 thang = TANG", "TĂNG" in tr["1 tháng"], tr["1 tháng"])
check("Xu huong 3 thang = TANG", "TĂNG" in tr["3 tháng"], tr["3 tháng"])
check("Xu huong 9 thang = DI NGANG (duoi nguong 15%)",
      "NGANG" in tr["9 tháng"], tr["9 tháng"])

sw = latest_swing_summary(df)
check("Co swing low ~4000", "swing_low" in sw
      and abs(sw["swing_low"]["price"] - 4000) < 200, str(sw.get("swing_low")))

# Phan ky tang: gia day thap hon, RSI day cao hon
seg1 = list(np.linspace(5500, 4500, 30))   # roi manh -> RSI rat thap
seg2 = list(np.linspace(4500, 4900, 15))
seg3 = list(np.linspace(4900, 4450, 25))   # roi tu tu -> day thap hon, RSI cao hon
seg4 = list(np.linspace(4450, 4600, 8))
df = compute_indicators(mk(seg1 + seg2 + seg3 + seg4), cfg)
divs = all_divergences(df, cfg)
check("Phat hien phan ky (co it nhat 1)", len(divs) >= 1, str(divs))

fib = fibonacci_zones(df)
check("Fibonacci tra ve vung can/do", fib is not None
      and (fib["nearest_above"] or fib["nearest_below"]), str(fib))

wk = resample_ohlc(df, "W")
check("Gop nen tuan dung ty le", 12 <= len(wk) <= 20, f"{len(wk)} tuan")

# ================= 5. DANH MUC =================
print("\n[5] Danh muc ca nhan")
pf = {"users": {}}
ok, msg = pfm.set_avg(pf, 111, "An", "NRC", 5400, 2000)
check("Dat gia von lan dau", ok and "ghi nhận" in msg, "")
ok, msg = pfm.set_avg(pf, 111, "An", "NRC", 5150)
check("Ghi de gia von", ok and "cập nhật" in msg and "5,400" in msg, "")
ok, msg = pfm.set_avg(pf, 222, "Binh", "NRC", 6000, 1000)
check("Nguoi thu 2 co ngan rieng",
      len(pf["users"]) == 2 and pf["users"]["111"]["positions"]["NRC"]["avg"] == 5150, "")

snapshot = {"NRC": {"price": 6100}}
levels_map = {"NRC": {"breakout_level": 6500, "buy_zone_low": 5300,
                      "stoploss_level": 4800}}
block = pfm.build_pl_block(pf["users"]["111"], snapshot, levels_map, {})
check("Khoi P/L nguoi loi co goi y chot loi",
      "+18.4%" in block and "chốt" in block, "")
block2 = pfm.build_pl_block(pf["users"]["222"], snapshot, levels_map, {})
check("Nguoi loi nhe (+1.7%) co goi y stoploss", "+1.7%" in block2, "")

# Canh bao tu loi thanh lo
pf["users"]["111"]["positions"]["NRC"]["peak_gain_pct"] = 8.0
snapshot_loss = {"NRC": {"price": 5050}}
alerts, dirty = pfm.position_alerts(pf, cfg, snapshot_loss, levels_map)
check("Canh bao tu loi thanh lo",
      any("từ lời thành lỗ" in m for _, m in alerts), str(len(alerts)))
alerts2, _ = pfm.position_alerts(pf, cfg, snapshot_loss, levels_map)
check("Khong bao lai lien tuc (p2l_alerted)",
      not any("từ lời thành lỗ" in m for _, m in alerts2), "")

# Cham nguong lo -5%
pf2 = {"users": {}}
pfm.set_avg(pf2, 333, "Chi", "NRC", 6000)
alerts3, _ = pfm.position_alerts(pf2, cfg, {"NRC": {"price": 5650}},
                                 levels_map)
check("Canh bao cham nguong lo -5%",
      any("chạm -5%" in m for _, m in alerts3), str(len(alerts3)))
alerts4, _ = pfm.position_alerts(pf2, cfg, {"NRC": {"price": 5350}},
                                 levels_map)
check("Canh bao xuong tiep nguong -10%",
      any("chạm -10%" in m for _, m in alerts4), str(len(alerts4)))

print(f"\n===== KET QUA: {PASS} dat / {FAIL} loi =====")
sys.exit(1 if FAIL else 0)
