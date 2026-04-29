import json
import os

from trustimircli.config import CONFIG_DIR

UNDO_FILE = os.path.join(CONFIG_DIR, 'last_undo.json')


def save_undo(action, fields, env=None):
    if env is None:
        from trustimircli.config import get_env
        env = get_env()
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(UNDO_FILE, 'w') as f:
        json.dump({'action': action, 'fields': fields, 'env': env}, f)


def load_undo():
    if not os.path.exists(UNDO_FILE):
        return None
    try:
        with open(UNDO_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        return None


def clear_undo():
    if os.path.exists(UNDO_FILE):
        os.remove(UNDO_FILE)
