"""The CLI uses shared API validation and targets one authenticated UI view."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from core import auth
from lab import paths


def test_owner_cli_scope_covers_ui_api_without_weakening_notebook_token(monorepo):
    from core.main import create_app
    app=create_app()
    with TestClient(app,client=('127.0.0.1',50000)) as local:
        token=paths.read_local_cli_token()
        headers={'Authorization':f'Bearer {token}','X-Lab-CLI-Scope':'owner'}
        assert local.get('/api/commands',headers={'Authorization':f'Bearer {token}'}).status_code==401
        response=local.get('/api/commands',headers=headers)
        assert response.status_code==200,response.text
        catalogue=response.json()
        def api_routes(routes):
            for route in routes:
                if isinstance(route,APIRoute) and route.include_in_schema and route.path.startswith('/api/'):
                    yield route
                elif hasattr(route,'original_router'):
                    yield from api_routes(route.original_router.routes)
        actual={(method.lower(),route.path_format) for route in api_routes(app.routes) for method in route.methods}
        exposed={(method,path) for path,operations in catalogue['paths'].items() for method in operations}
        assert actual==exposed
        assert 'label' in catalogue['components']['schemas']['SessionMetadata']['properties']
        assert local.get('/api/commands',headers={**headers,'Origin':'https://other.example'}).status_code==401
        assert local.get('/api/commands',headers={**headers,'Authorization':'Bearer wrong'}).status_code==401
    with TestClient(app,client=('10.0.0.8',50000)) as remote:
        assert remote.get('/api/commands',headers=headers).status_code==401


def test_ui_commands_select_one_view_and_return_its_result(client):
    with client.websocket_connect('/ws/ui-control') as first:
        client_id=first.receive_json()['id']
        first.send_json({'type':'state','info':{'title':'First','workspace':'demo'}})
        assert client.get('/api/ui/clients').json()[0]['id']==client_id
        with ThreadPoolExecutor(max_workers=1) as pool:
            response=pool.submit(lambda:client.post('/api/ui/command',json={'action':'inspect'}))
            command=first.receive_json()
            assert command['action']=='inspect'
            first.send_json({'type':'result','id':command['id'],'result':{'controls':[{'label':'Save'}]}})
            assert response.result(timeout=5).json()=={'controls':[{'label':'Save'}]}
        with client.websocket_connect('/ws/ui-control') as second:
            second_id=second.receive_json()['id']
            assert client.post('/api/ui/command',json={'action':'inspect'}).status_code==409
            with ThreadPoolExecutor(max_workers=1) as pool:
                response=pool.submit(lambda:client.post('/api/ui/command',json={'action':'fill','client_id':second_id,'params':{'selector':'#title','value':'New title'}}))
                command=second.receive_json()
                assert command['params']['value']=='New title'
                # An unrelated view cannot acknowledge another view's action.
                first.send_json({'type':'result','id':command['id'],'result':'wrong view'})
                second.send_json({'type':'result','id':command['id'],'error':'Control is disabled.'})
                result=response.result(timeout=5)
                assert result.status_code==422 and result.json()['detail']=='Control is disabled.'
        assert client.post('/api/ui/command',json={'action':'eval','params':{'code':'alert(1)'}}).status_code==400
    assert client.post('/api/ui/command',json={'action':'inspect'}).status_code==503


def test_ui_control_does_not_connect_unauthenticated_or_cross_origin(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws/ui-control',headers={'Origin':'https://elsewhere.example'}): pass
    client.post('/api/auth/logout')
    assert client.get('/api/ui/clients').status_code==401
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws/ui-control'): pass
