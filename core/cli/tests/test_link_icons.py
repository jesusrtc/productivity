"""Domain normalization and uploaded icon validation remain CLI-owned."""
import base64
import struct
import zlib

import pytest
from lab import settings
from lab.link_icons import validate_icon


def png(width=1,height=1):
    def chunk(kind,payload):
        return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)
    image=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))
    image+=chunk(b'IDAT',zlib.compress((b'\x00'+b'\xff\x00\x00\xff'*width)*height))+chunk(b'IEND',b'')
    return 'data:image/png;base64,'+base64.b64encode(image).decode()


def test_domain_rules_normalize_and_persist_client_wide(monorepo,tmp_path):
    icon=png()
    result=settings.update_global(monorepo,{'linkDomainMappings':[
        {'domain':'MYGRAFANA.MyCompany.com.','service':'grafana'},
        {'domain':'büro.example','service':'custom','name':' Console ','icon':icon,'includeSubdomains':True},
    ]})
    rules=result['linkDomainMappings']
    assert rules[0]=={'domain':'mygrafana.mycompany.com','service':'grafana','name':'','includeSubdomains':False}
    assert rules[1]['domain']=='xn--bro-hoa.example' and rules[1]['name']=='Console' and rules[1]['icon']==icon
    other=tmp_path/'other';other.mkdir()
    assert settings.load(other)['linkDomainMappings']==rules
    assert settings.update_global(monorepo,{'linkDomainMappings':[]})['linkDomainMappings']==[]


def test_uploaded_icons_validate_dimensions_crc_and_pixels():
    assert validate_icon(png())==png()
    for value in [png(257),png(1,257),png()[:-4],png()+ 'AA==',
                  'data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\n').decode(),
                  'data:image/svg+xml;base64,'+base64.b64encode(b'<svg/>').decode()]:
        with pytest.raises(ValueError):validate_icon(value)
    encoded=base64.b64decode(png().split(',')[1]);damaged=encoded[:-6]+b'\x00'+encoded[-5:]
    with pytest.raises(ValueError):validate_icon('data:image/png;base64,'+base64.b64encode(damaged).decode())
