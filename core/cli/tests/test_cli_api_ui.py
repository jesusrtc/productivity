"""CLI serialization, discovery and local-owner credential boundaries."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from click.testing import CliRunner

from lab import paths
from lab.cli import main


def test_cli_uses_same_api_and_supports_ui_and_workspace_actions(monkeypatch,tmp_path):
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            calls.append((self.command,self.path,dict(self.headers),None))
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
            self.wfile.write(json.dumps({'paths':{'/api/term/sessions/metadata':{'patch':{'summary':'Rename terminal','parameters':[]}}},'components':{}}).encode())
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((self.command,self.path,dict(self.headers),body))
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(body).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setenv('LAB_HOME',str(tmp_path/'home'))
    token_file=paths.local_cli_token_file();token_file.parent.mkdir(parents=True);token_file.write_text('test-owner-token-with-at-least-32-characters')
    monkeypatch.setenv('LAB_URL',f'http://127.0.0.1:{server.server_port}')
    runner=CliRunner()
    try:
        result=runner.invoke(main,['api','routes','--search','Rename','--method','PATCH'])
        assert result.exit_code==0 and '/api/term/sessions/metadata' in result.output,result.output
        body_file=tmp_path/'action.json';body_file.write_text(json.dumps({'label':'Spaces, "quotes" and\nnewlines'}))
        result=runner.invoke(main,['api','call','POST','/api/example','--body-file',str(body_file),'--query','vault=one two'])
        assert result.exit_code==0,result.output
        assert calls[-1][1]=='/api/example?vault=one+two' and calls[-1][3]['label']=='Spaces, "quotes" and\nnewlines'
        assert calls[-1][2]['X-Lab-Cli-Scope']=='owner' and calls[-1][2]['Authorization'].startswith('Bearer ')
        result=runner.invoke(main,['ui','--client','view-1','rename-tab','terminal-1','Review'])
        assert result.exit_code==0,result.output
        assert calls[-1][3]['action']=='terminal-rename' and calls[-1][3]['client_id']=='view-1'
        result=runner.invoke(main,['workspace','open','demo','--vault','owning-vault','--client','view-2'])
        assert result.exit_code==0,result.output
        assert calls[-1][3]['params']=={'workspace':'demo','vault':'owning-vault'}
        assert calls[-1][3]['client_id']=='view-2'
        before=len(calls)
        for args in [['api','call','POST','https://elsewhere.example/api/example'],['api','call','POST','/api/example','--query','malformed'],['api','call','POST','/api/example','--json','invalid']]:
            assert runner.invoke(main,args).exit_code!=0
        monkeypatch.setenv('LAB_URL','https://remote.example')
        assert runner.invoke(main,['ui','clients']).exit_code!=0
        assert len(calls)==before
    finally:
        server.shutdown();thread.join();server.server_close()
