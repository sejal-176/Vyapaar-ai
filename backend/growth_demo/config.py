"""Configuration constants and measurement explanations for Growth Insights preview.
Follows all project rules:
- No banned words (revenue, sales, profit, income, eligible, score, will return, bring back, guaranteed, because)
- Money in integer paise
"""

COMPARE_WINDOW_DAYS = 14
MIN_PAST_VISITS = 4
LAPSE_MULTIPLIER = 2.0
MIN_LAPSE_DAYS = 3
VELOCITY_WINDOW_DAYS = 28
DAYS_LEFT_WARN = 3
SLOW_MOVER_DROP_PCT = 30
SLOW_MOVER_MIN_PREV_UNITS = 10
SHRINK_PCT = 25
MAX_OFFER_PCT = 10
MIN_MARGIN_LEFT_POINTS = 5

HOW_WE_MEASURE = {
    "lapsing": (
        f"A customer is flagged when days since their last visit exceeds "
        f"{LAPSE_MULTIPLIER}x their median gap between visit days (and at least {MIN_LAPSE_DAYS} days), "
        f"with at least {MIN_PAST_VISITS} visits recorded."
    ),
    "customer_change": (
        f"Compares visits and spend across the last {COMPARE_WINDOW_DAYS} days against the previous "
        f"{COMPARE_WINDOW_DAYS} days. Spend change is split exactly into visits effect and basket effect."
    ),
    "shrinking": (
        f"Customers with at least 2 visits in the last {COMPARE_WINDOW_DAYS} days whose spend per visit "
        f"decreased by at least {SHRINK_PCT}% compared to the prior {COMPARE_WINDOW_DAYS} days."
    ),
    "inventory": (
        f"Usual pace is the median units billed per active day over the last {VELOCITY_WINDOW_DAYS} days. "
        f"Days left is stock on hand divided by usual pace. Low stock applies when days left is under {DAYS_LEFT_WARN} days."
    ),
    "slow_movers": (
        f"Products where units billed in the last {COMPARE_WINDOW_DAYS} days fell by at least {SLOW_MOVER_DROP_PCT}% "
        f"compared to the prior {COMPARE_WINDOW_DAYS} days (minimum {SLOW_MOVER_MIN_PREV_UNITS} units previously)."
    ),
    "guardrails": (
        f"Offers are capped at {MAX_OFFER_PCT}%. All items in the customer's last 5 baskets must have a "
        f"recorded cost price. The remaining margin after the offer must be at least {MIN_MARGIN_LEFT_POINTS} points."
    ),
}

