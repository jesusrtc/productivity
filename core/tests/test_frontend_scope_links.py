"""Late reads and repeated mounts preserve the active checkout's link ownership."""
from .test_frontend_terminal_ui import ROOT, _run_node


def test_scope_links_ignore_late_reads_and_keep_cached_buttons_clickable():
    module = (ROOT/'core/src/core/static/js/lib/scope-links.js').read_text()
    result = _run_node(r"""
const replies={},calls=[],opened=[];
const window={LabExternalLinks:{open:async url=>opened.push({url})},
  AssistantView:{openLinkedTask:async(link,options)=>{if(options.isCurrent())opened.push({id:link.document_id,tab:link.tab_id,whole:options.wholeDocument})}}};
const fetch=url=>new Promise(resolve=>replies[decodeURIComponent(url.split('path=')[1])]=data=>resolve({ok:true,json:async()=>data}));
const host=path=>({dataset:{scopeLinks:path},isConnected:true,paintCount:0,buttons:[],
  set innerHTML(value){this.paintCount++;this.edit={};this.buttons=Array.from(value.matchAll(/data-scope-link="(\d+)"/g),m=>({dataset:{scopeLink:m[1]}}));},
  querySelector(){return this.edit;},querySelectorAll(){return this.buttons;}});
""" + module + """
(async()=>{
  let active='/old';const old=host('/old'),current=host('/new');
  const first=window.LabScopeLinks.mount(old,()=>active==='/old');
  active='/new';old.isConnected=false;
  const second=window.LabScopeLinks.mount(current,()=>active==='/new');
  replies['/old']({links:[{kind:'external',url:'https://old.invalid'}],revision:'old'});
  replies['/new']({links:[{kind:'internal',document_id:'doc',tab_id:'tab',title:'Doc / Tab'},
    {kind:'internal',document_id:'doc',tab_id:null,title:'Doc'},
    {kind:'external',url:'https://new.invalid'}],revision:'new'});
  await Promise.all([first,second]);
  await window.LabScopeLinks.mount(current,()=>active==='/new');
  for(const button of current.buttons)await button.onclick();
  active='/another';await current.buttons[0].onclick();
  process.stdout.write(JSON.stringify({oldPaint:old.paintCount,newPaint:current.paintCount,opened}));
})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1});
""")
    assert result == {'oldPaint':0,'newPaint':1,'opened':[
        {'id':'doc','tab':'tab','whole':False}, {'id':'doc','tab':None,'whole':True}, {'url':'https://new.invalid'}]}
