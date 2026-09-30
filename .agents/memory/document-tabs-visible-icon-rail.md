# Document tabs stay visible as icons

The user wants the collapsed document tabs navigation to show its contents,
rather than only a narrow rotated Tabs label. Desktop inline and modal views
use a 52px rail with clickable numbered document/nested-tab icons, an active
accent, blue Updated and green New dots, and an unsaved-change marker. Titles
and activity timestamps remain available in tooltips and accessible labels.

Keep the full resizable navigation drawer on hover/focus and the existing
activity dismissal, expiry, and cross-window behavior. Rail buttons mirror
the existing navigation and retain their identity across selection/refresh.
Leave 64px of content exposed when bounding the drawer; account for both the
icon rail and its resize handle. Mobile retains horizontal navigation.
