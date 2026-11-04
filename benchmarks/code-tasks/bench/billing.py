"""Real spend from the ShopAIKey account counter.

`/v1/dashboard/billing/usage` returns `total_usage` in cents (the account shows 8338 against a 100 USD limit,
so it cannot be dollars). The counter lags and is coarse for tiny calls, so cost is measured over a whole
system run (before/after, with a settle delay), not per task.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request


def total_usage_cents() -> float:
    base = os.environ["BENCH_OPENAI_BASE_URL"].removesuffix("/v1")
    request = urllib.request.Request(
        f"{base}/v1/dashboard/billing/usage", headers={"Authorization": f"Bearer {os.environ['BENCH_API_KEY']}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return float(json.load(response)["total_usage"])


def settled_usage_cents(wait_seconds: int = 20) -> float:
    time.sleep(wait_seconds)
    return total_usage_cents()
