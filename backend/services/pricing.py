"""
services/pricing.py — Pricing engine.

Fetches green coffee market price from an external commodity API,
applies per-grade multipliers from the database, and returns a
suggested transaction price.

The external API call is isolated in _fetch_market_rate() so it can
be swapped for a BAFS endpoint without touching the rest of the logic.
"""

from __future__ import annotations
import time
from typing import Dict, Optional

import httpx
from sqlalchemy.orm import Session

from config import get_settings
from models.inspection import Inspection
from models.pricing_config import PricingConfig

settings = get_settings()

# ── In-memory price cache ────────────────────────────────────────────────────
_cache: Dict = {"rate": None, "fetched_at": 0.0, "source": "none"}


async def _fetch_market_rate() -> tuple[float, str]:
    """
    Fetch current green coffee price (PHP/kg) from the configured commodity API.

    Returns (price_php_per_kg, source_label)
    source_label: "api" | "cache" | "fallback"
    """
    now = time.monotonic()

    # Return cached value if still fresh
    if _cache["rate"] is not None and (now - _cache["fetched_at"]) < settings.PRICE_CACHE_TTL_SECONDS:
        return _cache["rate"], "cache"

    if not settings.PRICE_API_URL or not settings.PRICE_API_KEY:
        return settings.PRICE_FALLBACK_PHP_PER_KG, "fallback"

    try:
        # Commodities-API structure:
        # GET /api/latest?access_key=KEY&base=USD&symbols=COFFEE
        # Response: { "data": { "rates": { "COFFEE": <price per troy oz or lb> } } }
        # We convert to PHP/kg using PHP exchange rate from the same call.
        params = {
            "access_key": settings.PRICE_API_KEY,
            "base":       "USD",
            "symbols":    f"{settings.PRICE_API_SYMBOL},PHP",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(settings.PRICE_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        rates = data.get("data", {}).get("rates", {})
        coffee_usd = rates.get(settings.PRICE_API_SYMBOL)
        php_per_usd = rates.get("PHP")

        if not coffee_usd or not php_per_usd:
            raise ValueError("Missing rate fields in API response.")

        # Commodities-API returns coffee price per lb in USD
        # Convert: USD/lb → USD/kg → PHP/kg
        usd_per_kg    = float(coffee_usd) / 0.453592
        php_per_kg    = usd_per_kg * float(php_per_usd)

        _cache["rate"]       = round(php_per_kg, 4)
        _cache["fetched_at"] = now
        _cache["source"]     = "api"

        return _cache["rate"], "api"

    except Exception:
        # Use last cached value if available, otherwise fallback
        if _cache["rate"] is not None:
            return _cache["rate"], "cache"
        return settings.PRICE_FALLBACK_PHP_PER_KG, "fallback"


async def suggest_price(inspection: Inspection, db: Session) -> Dict:
    """
    Return a suggested price dict for a given inspection.
    """
    market_rate, source = await _fetch_market_rate()

    cfg: Optional[PricingConfig] = (
        db.query(PricingConfig)
        .filter(PricingConfig.grade == inspection.grade.value)
        .first()
    )
    multiplier = float(cfg.multiplier) if cfg else 1.0

    weight_kg    = float(inspection.sample_weight_g) / 1000.0
    price_per_kg = round(market_rate * multiplier, 4)
    total_price  = round(price_per_kg * weight_kg, 4)

    return {
        "inspection_id":       inspection.id,
        "grade":               inspection.grade.value,
        "weight_kg":           weight_kg,
        "market_rate_per_kg":  market_rate,
        "multiplier":          multiplier,
        "price_per_kg":        price_per_kg,
        "total_price":         total_price,
        "currency":            settings.PRICE_BASE_CURRENCY,
        "source":              source,
    }
