# Shell templates stay paired with the running backend

Jinja auto-reloading index.html after a pull can combine a new template with an
older Python process. New tojson variables (LINK_SERVICES and
NATIVE_BROWSER_REUSE were observed) become Undefined and make GET / return 500.
Load the index Template when create_app runs and retain that object for the
process lifetime. Asset cache invalidation still works; template contract changes
take effect with the backend restart. Cache native-browser capability separately
from the plain external-opener capability.
