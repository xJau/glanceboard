"""Glanceboard for Kindle — deterministic daily board for a jailbroken Paperwhite."""

#: Bump this whenever the board's *appearance* changes.
#:
#: The change-detection hash includes it, so a device that has already drawn
#: today's board still fetches the redesigned one. Without it a layout change
#: reaches the Kindle only when the calendar or the weather happens to move.
__version__ = "0.3.0"
