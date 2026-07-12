# -*- coding: utf-8 -*-
"""Danh muc ca nhan theo tung nguoi dung Telegram (muc 11)."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PORTFOLIO_FILE = "portfolio.json"


def load_portfolio():
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": {}}


def save_portfolio(data):
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def set_avg(pf, user_id, user_name, symbol, avg_price, qty=None):
    """Dat/ghi de gia von. Tra ve (thanh_cong, tin_nhan)."""
    u = pf["users"].setdefault(str(user_id), {"name": user_name,
                                              "positions": {}})
    u["name"] = user_name or u.get("name", "")
    old = u["positions"].get(symbol)
    u["positions"][symbol] = {
        "avg": float(avg_price),
        "qty": int(qty) if qty else None,
        "peak_gain_pct": 0.0,
        "worst_alerted_pct": 0.0,
        "updated": datetime.now(VN_TZ).isoformat(),
    }
    if old:
        return True, (f"✅ Đã cập nhật giá vốn <b>{symbol}</b>: "
                      f"{old['avg']:,.0f}đ → {float(avg_price):,.0f}đ"
                      + (f" (SL: {int(qty):,})" if qty else ""))
    return True, (f"✅ Đã ghi nhận vị thế <b>{symbol}</b> giá vốn "
                  f"{float(avg_price):,.0f}đ"
                  + (f", số lượng {int(qty):,}" if qty else ""))


def remove_avg(pf, user_id, symbol):
    u = pf["users"].get(str(user_id))
    if u and symbol in u.get("positions", {}):
        del u["positions"][symbol]
        return True, f"✅ Đã xóa <b>{symbol}</b> khỏi danh mục của bạn"
    return False, f"❌ Bạn chưa đặt giá vốn cho {symbol} (dùng /avg trước)"


def _position_advice(symbol, pos, price, levels, fib):
    """Goi y hanh dong dua tren gia von + cac moc ky thuat."""
    avg = pos["avg"]
    pnl = (price / avg - 1) * 100
    lines = []

    res = levels.get("breakout_level") or 0
    sup = levels.get("buy_zone_low") or 0
    sl = levels.get("stoploss_level") or 0

    if pnl > 1:  # dang loi
        if res and res > price:
            lines.append(f"Kháng cự gần nhất {res:,.0f}đ "
                         f"({(res/avg-1)*100:+.1f}% so vốn) — "
                         "cân nhắc chốt một phần tại đó")
        if fib and fib.get("nearest_above"):
            k, v = fib["nearest_above"]
            lines.append(f"Vùng cản Fib kế tiếp: {k} ~{v:,.0f}đ")
        guard = max(avg * 1.01, sl)
        lines.append(f"Đề xuất dời stoploss lên ~{guard:,.0f}đ "
                     "(trên hòa vốn) để bảo toàn lãi")
    elif pnl < -1:  # dang lo
        lines.append(f"Điểm hòa vốn: {avg:,.0f}đ "
                     f"(cần tăng {(avg/price-1)*100:.1f}%)")
        if res and abs(avg - res) / res <= 0.03:
            lines.append("⚠️ Hòa vốn trùng vùng kháng cự — sẽ khó vượt, "
                         "cân nhắc hạ tỷ trọng khi hồi gần mốc này")
        if sl:
            lines.append(f"Hỗ trợ/cắt lỗ theo kịch bản: {sl:,.0f}đ "
                         f"({(sl/avg-1)*100:+.1f}% so vốn) — "
                         "thủng là tín hiệu thoát")
    else:
        lines.append("Quanh hòa vốn — theo dõi phản ứng tại các mốc "
                     f"hỗ trợ {sup:,.0f}đ / kháng cự {res:,.0f}đ")
    return pnl, lines


def build_pl_block(user, snapshot, levels_map, fib_map, detail=True):
    """Khoi lai/lo cua 1 nguoi. snapshot: {sym: {price: ...}}."""
    lines = []
    for sym, pos in sorted(user.get("positions", {}).items()):
        snap = snapshot.get(sym)
        if not snap:
            lines.append(f"<b>{sym}</b>: chưa có dữ liệu giá "
                         "(mã có đang được theo dõi không? /list)")
            continue
        price = snap["price"]
        pnl, advice = _position_advice(
            sym, pos, price, levels_map.get(sym, {}), fib_map.get(sym))
        icon = "🟢" if pnl > 0.5 else "🔴" if pnl < -0.5 else "⚪"
        head = (f"{icon} <b>{sym}</b>: vốn {pos['avg']:,.0f} → "
                f"{price:,.0f}đ (<b>{pnl:+.1f}%</b>)")
        if pos.get("qty"):
            money = (price - pos["avg"]) * pos["qty"]
            head += f" | {money:+,.0f}đ ({pos['qty']:,} cp)"
        lines.append(head)
        if detail:
            lines.extend(f"   • {a}" for a in advice)
    if not lines:
        return None
    return "\n".join(lines)


def position_alerts(pf, cfg, snapshot, levels_map):
    """Canh bao vi the: tu loi thanh lo, cham nguong lo.
    Tra ve list (user_id, message) va co cap nhat trang thai peak."""
    p_cfg = cfg.get("portfolio", {})
    guard = p_cfg.get("profit_guard_pct", 5)
    loss_levels = sorted(p_cfg.get("loss_alert_pcts", [-5, -10]),
                         reverse=True)
    alerts = []
    changed = False

    for uid, u in pf.get("users", {}).items():
        name = u.get("name", "")
        for sym, pos in u.get("positions", {}).items():
            snap = snapshot.get(sym)
            if not snap:
                continue
            price = snap["price"]
            pnl = (price / pos["avg"] - 1) * 100

            # Cap nhat dinh lai cao nhat
            if pnl > pos.get("peak_gain_pct", 0):
                pos["peak_gain_pct"] = round(pnl, 2)
                changed = True

            # Tu loi thanh lo
            if pos.get("peak_gain_pct", 0) >= guard and pnl < 0 \
                    and not pos.get("p2l_alerted"):
                pos["p2l_alerted"] = True
                changed = True
                alerts.append((uid, (
                    f"⚠️ <b>[{sym}] {name}: vị thế từ lời thành lỗ</b>\n"
                    f"Từng đạt +{pos['peak_gain_pct']:.1f}%, hiện "
                    f"{pnl:+.1f}% (giá {price:,.0f}đ / vốn "
                    f"{pos['avg']:,.0f}đ)\nKiểm tra lại kế hoạch cắt lỗ.")))
            if pnl > 1 and pos.get("p2l_alerted"):
                pos["p2l_alerted"] = False  # hoi phuc -> cho phep bao lai
                changed = True

            # Cham cac nguong lo
            worst = pos.get("worst_alerted_pct", 0)
            for lv in loss_levels:
                if pnl <= lv < worst if worst else pnl <= lv:
                    if worst == 0 or lv < worst:
                        pos["worst_alerted_pct"] = lv
                        changed = True
                        sl = levels_map.get(sym, {}).get("stoploss_level")
                        extra = (f"\nMốc cắt lỗ kỹ thuật: {sl:,.0f}đ"
                                 if sl else "")
                        alerts.append((uid, (
                            f"🔴 <b>[{sym}] {name}: lỗ chạm {lv}%</b>\n"
                            f"Vốn {pos['avg']:,.0f} → {price:,.0f}đ "
                            f"({pnl:+.1f}%){extra}")))
                    break
            if pnl > loss_levels[0] and pos.get("worst_alerted_pct", 0) != 0:
                pos["worst_alerted_pct"] = 0  # hoi ve tren nguong dau
                changed = True

    return alerts, changed
