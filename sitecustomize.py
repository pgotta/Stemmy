"""Automatically apply Stemmy's Windows performance policy to Python jobs."""

try:
    from stemmy_windows_performance import apply_windows_performance_policy

    apply_windows_performance_policy()
except Exception:
    # Performance tuning must never prevent Stemmy or a model subprocess starting.
    pass
