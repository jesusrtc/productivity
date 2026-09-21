# Dashboard section controls expose JSON only

The user's follow-up to the dashboard requests **Show filter** as the only
section header control. It opens the full editable JSON object, with no separate
field form, filter-summary text, or reorder arrows. Add section also starts
from JSON. Every section setting, including its title and `position`, is in the
JSON; lower positions come first.

Persist one complete JSON file per section at `.assistant/dashboard/<id>.json`.
Keep defaults and the new-section template in packaged JSON resources, without
another frontend defaults map. Validate syntax, types, missing/unknown fields,
and expected revisions; preserve drafts and focus through polling and errors.
Preserve the user's existing custom filters and order on migration from the
older single dashboard.json file. That original file is retained as a backup;
individual files become authoritative. Do not reset a user's P0 or Starred
settings to the original shipped defaults.
