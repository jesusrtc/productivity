"""Validate client-owned domain mappings and small, inert uploaded PNG icons."""
import base64
import binascii
import re
import struct
import zlib


PNG_PREFIX = 'data:image/png;base64,'


def validate_icon(value):
    if not isinstance(value, str) or not value.startswith(PNG_PREFIX) or len(value) > 90000:
        raise ValueError('Upload an icon as a PNG of at most 64 KB')
    try:
        image = base64.b64decode(value[len(PNG_PREFIX):], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('The uploaded icon is not a valid PNG') from exc
    if len(image) > 65536 or not image.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('The uploaded icon is not a valid PNG of at most 64 KB')
    offset, chunks, pixels = 8, [], []
    while offset + 12 <= len(image):
        length = struct.unpack('>I', image[offset:offset + 4])[0]
        end = offset + 12 + length
        if end > len(image):
            raise ValueError('The uploaded PNG is incomplete')
        kind = image[offset + 4:offset + 8]
        payload = image[offset + 8:end - 4]
        crc = struct.unpack('>I', image[end - 4:end])[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError('The uploaded PNG is damaged')
        if not chunks:
            if kind != b'IHDR' or length != 13:
                raise ValueError('The uploaded icon needs a PNG image header')
            width, height = struct.unpack('>II', payload[:8])
            if not 1 <= width <= 256 or not 1 <= height <= 256:
                raise ValueError('Uploaded icons must be at most 256 × 256 pixels')
            depth, color, compression, filtering, interlace = payload[8:]
            depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if depth not in depths.get(color, set()) or compression or filtering or interlace:
                raise ValueError('Upload a standard PNG or choose the image again to resize it')
            channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
            stride = (width * channels * depth + 7) // 8 + 1
        if kind == b'IDAT':
            pixels.append(payload)
        if kind == b'IEND' and length:
            raise ValueError('The uploaded PNG is damaged')
        chunks.append(kind)
        offset = end
        if kind == b'IEND':
            break
    if offset != len(image) or not chunks or chunks[-1] != b'IEND' or b'IDAT' not in chunks:
        raise ValueError('The uploaded PNG is incomplete')
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(b''.join(pixels), height * stride + 1)
        if len(raw) != height * stride or not decoder.eof or decoder.unused_data or any(raw[y * stride] > 4 for y in range(height)):
            raise ValueError('The uploaded PNG image data is invalid')
    except zlib.error as exc:
        raise ValueError('The uploaded PNG image data is invalid') from exc
    return PNG_PREFIX + base64.b64encode(image).decode('ascii')


def validate_mappings(value):
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError('Define at most 100 link domain mappings')
    rows, domains = [], set()
    for entry in value:
        if not isinstance(entry, dict) or set(entry) - {'domain', 'service', 'includeSubdomains', 'name', 'icon'}:
            raise ValueError('Each mapping needs a domain and a service icon or an uploaded icon')
        domain = entry.get('domain')
        if not isinstance(domain, str):
            raise ValueError('Enter a domain such as mygrafana.mycompany.com')
        try:
            domain = domain.strip().rstrip('.').encode('idna').decode('ascii').lower()
        except UnicodeError as exc:
            raise ValueError('Enter a valid domain') from exc
        if len(domain) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in domain.split('.')):
            raise ValueError('Enter a hostname without a scheme, port, path, or wildcard')
        if domain in domains:
            raise ValueError('Each domain can have only one icon mapping')
        domains.add(domain)
        service, name = entry.get('service'), entry.get('name', '')
        if not isinstance(service, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', service):
            raise ValueError('Choose a service icon or upload a custom icon')
        if not isinstance(name, str) or len(name.strip()) > 80:
            raise ValueError('Custom tool names must be at most 80 characters')
        include = entry.get('includeSubdomains', False)
        if not isinstance(include, bool):
            raise ValueError('Include subdomains must be true or false')
        row = {'domain': domain, 'service': service, 'includeSubdomains': include, 'name': name.strip()}
        if service == 'custom':
            row['icon'] = validate_icon(entry.get('icon'))
        elif entry.get('icon'):
            raise ValueError('Select Custom icon to use an uploaded image')
        rows.append(row)
    return rows
