# Workspace working priority and green-dot review

On 2026-10-01, the user requested workspace tabs to aggregate terminal activity:
any working terminal makes the workspace dot steady yellow, taking precedence
over unread green results. When no terminal is working, pending completed results
show blinking green. Include shared document terminals and retained verified
working state through uncertain reads; hiding workspace green must not acknowledge it.

The user also requested direct green-dot clicks to clear the indicator. Terminal
green dots acknowledge that terminal's completed response; workspace green dots
acknowledge its pending terminal results across shared views, without tab
activation. Keep yellow work independent, preserve normal tab-click behavior,
and allow keyboard activation of the green dot.
