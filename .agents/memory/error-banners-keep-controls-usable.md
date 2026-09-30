# Error banners must leave Lab controls usable

The user needs to continue navigating when repeated JavaScript errors occur.
Keep the main UI notification compact, with bounded, scrollable details and
an always-visible dismiss button plus Escape dismissal. Ordinary notification
text must allow clicks to pass through. Dismissal lasts until page reload,
including repeated errors; keep logging and bounded `data-errors` diagnostics
available so dismissal does not hide failures from headless checks.
