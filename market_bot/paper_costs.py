from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any


DEFAULT_CHARGE_MODEL = {
    "brokerage_mode": "flat",
    "brokerage_flat_inr": 20.0,
    "brokerage_percentage_rate": 0.0003,
    "stt_sell_rate": 0.0015,
    "exchange_rate": 0.0003553,
    "sebi_rate": 0.000001,
    "stamp_buy_rate": 0.00003,
    "gst_rate": 0.18,
}


def resolve_charge_model(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    model = dict(DEFAULT_CHARGE_MODEL)
    if config is not None:
        configured = config.get("paper_charge_model", config)
        if not isinstance(configured, Mapping):
            raise ValueError("paper_charge_model must be a JSON object")
        for key in model:
            if key in configured:
                model[key] = configured[key]

    mode = str(model["brokerage_mode"]).strip().lower()
    if mode not in {"flat", "min_flat_percentage"}:
        raise ValueError(
            "paper_charge_model.brokerage_mode must be "
            "'flat' or 'min_flat_percentage'"
        )
    model["brokerage_mode"] = mode
    for key in model:
        if key == "brokerage_mode":
            continue
        try:
            value = float(model[key])
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Invalid paper charge model value: {key}") from exc
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"paper charge model value {key} must be finite and non-negative")
        model[key] = value
    return model


def _positive_number(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite positive number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return number


def calculate_order_fees(
    orders: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not orders:
        raise ValueError("At least one executed order is required to calculate fees")
    model = resolve_charge_model(config)
    brokerage = sell_turnover = buy_turnover = total_turnover = 0.0
    for index, order in enumerate(orders, 1):
        side = str(order.get("side", "")).strip().upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError(f"Order {index} side must be BUY or SELL")
        price = _positive_number(order.get("price"), f"Order {index} price")
        quantity = _positive_number(order.get("quantity"), f"Order {index} quantity")
        turnover = price * quantity
        total_turnover += turnover
        if side == "BUY":
            buy_turnover += turnover
        else:
            sell_turnover += turnover
        if model["brokerage_mode"] == "flat":
            brokerage += model["brokerage_flat_inr"]
        else:
            brokerage += min(
                model["brokerage_flat_inr"],
                turnover * model["brokerage_percentage_rate"],
            )

    exchange = total_turnover * model["exchange_rate"]
    sebi = total_turnover * model["sebi_rate"]
    stt = sell_turnover * model["stt_sell_rate"]
    stamp = buy_turnover * model["stamp_buy_rate"]
    gst = (brokerage + exchange + sebi) * model["gst_rate"]
    fees = brokerage + stt + exchange + sebi + stamp + gst
    return {
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "exchange": round(exchange, 2),
        "sebi": round(sebi, 2),
        "stamp": round(stamp, 2),
        "gst": round(gst, 2),
        "total_fees": round(fees, 2),
        "order_count": len(orders),
        "brokerage_mode": model["brokerage_mode"],
        "fee_model_status": "modeled",
    }


def calculate_trade_fees(
    trade: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    action = str(trade.get("action", "")).strip().upper()
    if action not in {"BUY", "SELL"}:
        raise ValueError("Trade action must be BUY or SELL")
    entry_price_value = trade.get("entry")
    if entry_price_value in (None, ""):
        entry_price_value = trade.get("fill_premium")
    entry_quantity_value = trade.get("entry_quantity")
    if entry_quantity_value in (None, ""):
        entry_quantity_value = trade.get("quantity")
    entry_price = _positive_number(
        entry_price_value, "Entry price"
    )
    entry_quantity = _positive_number(
        entry_quantity_value, "Entry quantity"
    )
    exit_side = "SELL" if action == "BUY" else "BUY"
    orders = [{"side": action, "price": entry_price, "quantity": entry_quantity}]
    legs = trade.get("exit_legs", [])
    if isinstance(legs, str):
        try:
            legs = json.loads(legs)
        except json.JSONDecodeError as exc:
            raise ValueError("Trade exit_legs is not valid JSON") from exc
    if legs is None:
        legs = []
    if not isinstance(legs, list):
        raise ValueError("Trade exit_legs must be a list")
    if legs:
        for index, leg in enumerate(legs, 1):
            if not isinstance(leg, Mapping):
                raise ValueError(f"Exit leg {index} must be an object")
            orders.append(
                {
                    "side": exit_side,
                    "price": (
                        leg.get("fill")
                        if leg.get("fill") not in (None, "")
                        else leg.get("price")
                    ),
                    "quantity": leg.get("quantity"),
                }
            )
    else:
        orders.append(
            {
                "side": exit_side,
                "price": trade.get("exit_price"),
                "quantity": trade.get("exit_quantity") or entry_quantity,
            }
        )
    return calculate_order_fees(orders, config)
