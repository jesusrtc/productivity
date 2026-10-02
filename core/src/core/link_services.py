"""Shared URL rules for link service names and locally bundled brand icons."""
import json
from pathlib import Path
from urllib.parse import urlsplit


REGISTRY_PATH = Path(__file__).parent / 'static' / 'link-services.json'
SERVICES = json.loads(REGISTRY_PATH.read_text())
EXTERNAL_TYPES = [{'id': row['id'], 'name': row['name'], 'kind': 'external'} for row in SERVICES]
EXTERNAL_TYPES.append({'id': 'url', 'name': 'Link', 'kind': 'external'})


def infer(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        return None
    host = parsed.hostname.lower().rstrip('.')
    path = parsed.path.lower()

    def domain_matches(domain):
        return host == domain or host.endswith('.' + domain)

    for service in SERVICES:
        for rule in service['rules']:
            prefix = rule['path']
            if domain_matches(rule['domain']) and (path == prefix or path.startswith(prefix + '/')):
                return service
        if any(domain_matches(domain) for domain in service['domains']):
            return service
        if any(part == label or part.startswith(label + '-') or part.endswith('-' + label)
               for part in host.split('.') for label in service['host_labels']):
            return service
    return None
