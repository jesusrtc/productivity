# Normalize workspace history before tearing down the outgoing view

Moving goToWorkspace's pushState before teardown was insufficient for edited
notebooks: selectRepo still called replaceState after the old body classes
were cleared. Move that same URL/state normalization before _swapViewState
when the destination is already in the catalog, and pass historySettled only
for that exact workspace object. Initial/direct selection and a deferred
catalog lookup still normalize through selectRepo. Preserve null replacement
state, URL/query/hash, entry count, popstate behavior and terminal ownership.

_swapViewState also clears notebook navigation before changing the shell, so
the final reading-position measurement sees the outgoing layout. Position
capture alone did not improve repeated restoration (250.1 vs 247.1 ms median).
Together with earlier history normalization, two 20-visit runs reached
162.7/163.1 ms restoration medians: all 244 clicks and 982 native key checks
met 200 ms with 200 cells, a 500-line source extension and the full file/Git load.

Keep real Back/Forward verification of exact files and history IDs/URLs. The
verbose notebook trace overflowed; its late event order is not evidence.
Record untraced comparisons separately from diagnostic profiles.
