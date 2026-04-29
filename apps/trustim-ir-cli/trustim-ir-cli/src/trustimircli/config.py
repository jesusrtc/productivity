import os
import toml

CONFIG_DIR = os.path.expanduser('~/.config/ir')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.toml')

ENVIRONMENTS = {
    'stg': {
        'name': 'Staging',
        'host': 'https://airp.stg.linkedin.com',
    },
    'prod': {
        'name': 'Production',
        'host': 'https://airp.prod.linkedin.com',
    },
}

# ei is an alias for stg
ENV_ALIASES = {'ei': 'stg'}

DEFAULT_ENV = 'stg'


def _ensure_config_dir():
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE) as f:
        return toml.load(f)


def save_config(config):
    _ensure_config_dir()
    fd = os.open(CONFIG_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        toml.dump(config, f)


def resolve_env(env_key):
    return ENV_ALIASES.get(env_key, env_key)


def get_env():
    config = load_config()
    return resolve_env(config.get('env', DEFAULT_ENV))


def set_env(env_key):
    config = load_config()
    config['env'] = resolve_env(env_key)
    save_config(config)


def get_host():
    env_key = get_env()
    env = ENVIRONMENTS.get(env_key, ENVIRONMENTS[DEFAULT_ENV])
    return env['host']


def get_auth():
    config = load_config()
    env_key = config.get('env', DEFAULT_ENV)
    auth_section = config.get('auth', {})
    return auth_section.get(env_key, {})


def save_auth(host, cookies, username):
    config = load_config()
    env_key = config.get('env', DEFAULT_ENV)
    if 'auth' not in config:
        config['auth'] = {}
    config['auth'][env_key] = {
        'host': host,
        'cookies': cookies,
        'username': username,
    }
    save_config(config)


def clear_auth():
    config = load_config()
    env_key = config.get('env', DEFAULT_ENV)
    if 'auth' in config:
        config['auth'].pop(env_key, None)
    save_config(config)


def get_cert_name():
    config = load_config()
    return config.get('cert', '')


def set_cert_name(name):
    config = load_config()
    config['cert'] = name
    save_config(config)
