"""Shared URL rules for link service names and locally bundled brand icons."""
import json
from pathlib import Path
from urllib.parse import urlsplit


REGISTRY_PATH = Path(__file__).parent / 'static' / 'link-services.json'
SERVICES = json.loads(REGISTRY_PATH.read_text())
EXTERNAL_TYPES = [{'id': row['id'], 'name': row['name'], 'kind': 'external'} for row in SERVICES]
EXTERNAL_TYPES.append({'id': 'url', 'name': 'Link', 'kind': 'external'})


def infer(url, mappings=()):
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        return None
    host = parsed.hostname.lower().rstrip('.')
    path = parsed.path.lower()

    def domain_matches(domain):
        return host == domain or host.endswith('.' + domain)

    # A specific configured hostname wins over a parent-domain mapping and
    # all built-in heuristics, regardless of the order entered in Settings.
    for mapping in sorted(mappings, key=lambda row: len(row['domain']), reverse=True):
        if host != mapping['domain'] and not (mapping.get('includeSubdomains') and domain_matches(mapping['domain'])):
            continue
        if mapping['service'] == 'custom':
            return {'id': 'url', 'name': mapping.get('name') or mapping['domain'], 'iconData': mapping['icon'], 'mapped': True}
        service = next((row for row in SERVICES if row['id'] == mapping['service']), None)
        if service:
            return {**service, 'name': mapping.get('name') or service['name'], 'mapped': True}

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
