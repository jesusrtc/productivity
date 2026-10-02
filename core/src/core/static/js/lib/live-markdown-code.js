/* Fenced code stays editable while its Markdown container belongs to the UI. */
import {Annotation, ChangeSet, EditorSelection, EditorState, StateField} from '@codemirror/state';
import {Decoration, EditorView, WidgetType} from '@codemirror/view';
import {isolateHistory} from '@codemirror/commands';
import {syntaxTree} from '@codemirror/language';

const structure=Annotation.define();
const languages=[['','None'],['sql','SQL'],['python','Python'],['javascript','JavaScript'],['typescript','TypeScript'],
  ['json','JSON'],['bash','Bash'],['html','HTML'],['css','CSS'],['markdown','Markdown'],['yaml','YAML'],['xml','XML'],
  ['java','Java'],['c','C'],['cpp','C++'],['csharp','C#'],['go','Go'],['rust','Rust'],['ruby','Ruby'],['php','PHP'],
  ['swift','Swift'],['kotlin','Kotlin'],['scala','Scala'],['groovy','Groovy'],['protobuf','Protobuf'],['r','R'],['mermaid','Mermaid']];
const aliases={js:'javascript',ts:'typescript',py:'python',sh:'bash',shell:'bash',yml:'yaml',cs:'csharp','c++':'cpp',md:'markdown',text:'',plaintext:'',none:''};

export function codeFence(state,node) {
  const parts=[];for(let child=node.firstChild;child;child=child.nextSibling)parts.push(child);
  const marks=parts.filter(child=>child.name==='CodeMark'),info=parts.find(child=>child.name==='CodeInfo');
  const opening=state.doc.lineAt(marks[0].from),closing=marks.length>1?state.doc.lineAt(marks.at(-1).from):null;
  const raw=info?state.doc.sliceString(info.from,info.to).split(/\s/)[0].toLowerCase():'';
  return {from:node.from,to:node.to,opening,closing,marker:marks[0],language:aliases[raw]??raw,
    bodyFrom:Math.min(state.doc.length,opening.to+1),bodyTo:closing?Math.max(opening.to+1,closing.from-1):node.to,
    text:parts.filter(child=>child.name==='CodeText'),parts};
}
function fences(state) {
  const result=[];syntaxTree(state).iterate({enter:ref=>{if(ref.name==='FencedCode'){result.push(codeFence(state,ref.node));return false;}}});return result;
}
export const codeFences=StateField.define({
  create:fences,
  update:(value,tr)=>tr.docChanged||syntaxTree(tr.startState)!==syntaxTree(tr.state)?fences(tr.state):value,
});
function currentFence(view,from) { return view.state.field(codeFences).find(fence=>fence.from===from); }

export class CodeToolbar extends WidgetType {
  constructor(fence) { super();this.from=fence.from;this.language=fence.language; }
  eq(other) { return this.from===other.from&&this.language===other.language; }
  toDOM(view) {
    const bar=document.createElement('div');bar.className='lab-live-code-toolbar';bar.setAttribute('role','group');bar.setAttribute('aria-label','Code block');
    bar.addEventListener('keydown',event=>{if(!event.metaKey&&!event.ctrlKey)event.stopPropagation();});
    const label=document.createElement('label');label.textContent='Language';
    const select=document.createElement('select');select.setAttribute('aria-label','Code block language');
    const options=languages.some(([value])=>value===this.language)?languages:[...languages,[this.language,this.language]];
    for(const [value,text] of options){const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);}
    select.value=this.language;
    select.addEventListener('change',()=>{
      const fence=currentFence(view,this.from);if(!fence)return;
      view.dispatch({changes:{from:fence.marker.to,to:fence.opening.to,insert:select.value},
        annotations:[structure.of(true),isolateHistory.of('full')],userEvent:'input'});
      view.focus();
    });
    label.append(select);bar.append(label);
    const remove=document.createElement('button');remove.type='button';remove.textContent='Delete';remove.className='lab-live-code-delete';remove.setAttribute('aria-label','Delete code block');
    remove.addEventListener('mousedown',event=>event.preventDefault());
    remove.addEventListener('click',()=>{
      const fence=currentFence(view,this.from);if(!fence)return;
      view.dispatch({changes:{from:fence.from,to:fence.to},selection:{anchor:fence.from},annotations:[structure.of(true),isolateHistory.of('full')],userEvent:'input'});view.focus();
    });
    bar.append(remove);return bar;
  }
  ignoreEvent() { return true; }
}

class EmptyCodeBody extends WidgetType {
  constructor(from) { super();this.from=from; }
  eq(other) { return this.from===other.from; }
  toDOM(view) {
    const body=document.createElement('div');body.className='lab-live-empty-code-body';
    body.setAttribute('aria-label','Empty code block');body.textContent='\u200b';
    body.addEventListener('mousedown',event=>{
      event.preventDefault();const fence=currentFence(view,this.from);if(!fence)return;
      view.dispatch({changes:{from:fence.closing.from,insert:'\n'},selection:{anchor:fence.bodyFrom},
        annotations:structure.of(true),userEvent:'input'});view.focus();
    });return body;
  }
  ignoreEvent() { return true; }
}

function highlightCode(state,fence,decorations,cache,previous) {
  if(!fence.language||fence.language==='mermaid'||!window.hljs?.getLanguage(fence.language))return;
  for(const text of fence.text){
    const source=state.doc.sliceString(text.from,text.to),key=fence.language+'\0'+source;
    let tokens=previous?.get(key);
    if(!tokens){
      const host=document.createElement('div');host.innerHTML=window.hljs.highlight(source,{language:fence.language,ignoreIllegals:true}).value;
      tokens=[];let offset=0;
      const walk=node=>{
        if(node.nodeType===Node.TEXT_NODE){
          const classes=[];for(let parent=node.parentElement;parent&&parent!==host;parent=parent.parentElement)classes.push(...parent.classList);
          if(classes.length&&node.length)tokens.push({from:offset,to:offset+node.length,class:'lab-live-code-token '+classes.join(' ')});
          offset+=node.length;
        }else for(const child of node.childNodes)walk(child);
      };
      walk(host);
    }
    cache.set(key,tokens);
    for(const token of tokens)decorations.push(Decoration.mark({class:token.class}).range(text.from+token.from,text.from+token.to));
  }
}
export function decorateCode(state,fence,{addLine,replace,decorations,cache,previous}) {
  const first=state.doc.lineAt(fence.bodyFrom).number,last=state.doc.lineAt(fence.bodyTo).number;
  replace(fence.opening.from,fence.opening.to,new CodeToolbar(fence),true);
  if(fence.closing?.from===fence.bodyFrom)decorations.push(Decoration.widget({widget:new EmptyCodeBody(fence.from),block:true,side:-1}).range(fence.bodyFrom));
  else for(let number=first;number<=last;number++)addLine(state.doc.line(number).from,
      'lab-live-code-line lab-live-code-framed'+(number===first?' lab-live-code-first':'')+(number===last?' lab-live-code-last':''),{spellcheck:'false'});
  if(fence.closing){replace(fence.closing.from,fence.closing.to);addLine(fence.closing.from,'lab-live-boundary');}
  for(const part of fence.parts)if(part.name==='QuoteMark')replace(part.from,part.to);
  highlightCode(state,fence,decorations,cache,previous);
}

function completeFence(view,from,to,text) {
  const state=view.state,line=state.doc.lineAt(from);
  if(state.field(codeFences).some(fence=>from>=fence.bodyFrom&&to<=fence.bodyTo))return false;
  if(to>line.to||state.field(codeFences).some(fence=>fence.from<line.from&&fence.to>=from))return false;
  const candidate=state.doc.sliceString(line.from,from)+text+state.doc.sliceString(to,line.to);
  if(!/^ {0,3}`{3}$/.test(candidate))return false;
  const prefix=candidate.slice(0,-3),before=line.number>1&&state.doc.line(line.number-1).text.trim()?'\n':'';
  const after=line.to===state.doc.length?'\n\n':'\n';
  const insert=before+candidate+'\n\n'+prefix+'```'+after;
  view.dispatch({changes:{from:line.from,to:line.to,insert},selection:{anchor:line.from+before.length+candidate.length+1},
    annotations:[structure.of(true),isolateHistory.of('full')],userEvent:'input.type'});
  return true;
}
// Suppress deletion of delimiters, rather than rejecting a large selection:
// deleting selected code still clears its body and keeps a usable empty block.
function protectFences(tr) {
  if(tr.annotation(structure)||!tr.docChanged||!['input','delete','move.drop'].some(event=>tr.isUserEvent(event)))return true;
  return tr.startState.field(codeFences).flatMap(fence=>fence.closing?[fence.from,fence.bodyFrom,fence.bodyTo,fence.to]:[fence.from,fence.bodyFrom]);
}
function growFences(tr) {
  if(tr.annotation(structure)||!tr.docChanged||!['input','delete','move.drop'].some(event=>tr.isUserEvent(event)))return tr;
  const corrections=[];let emptyAnchor;
  for(const fence of tr.startState.field(codeFences)){
    if(!fence.closing)continue;
    const bodyFrom=tr.changes.mapPos(fence.bodyFrom,-1),bodyTo=tr.changes.mapPos(fence.bodyTo,1);
    if(fence.closing.from===fence.bodyFrom&&bodyTo>bodyFrom){
      corrections.push({from:bodyTo,insert:'\n'});emptyAnchor=bodyTo;
    }
    const body=tr.newDoc.sliceString(bodyFrom,bodyTo),marker=tr.startState.sliceDoc(fence.marker.from,fence.marker.to);
    const longest=Math.max(0,...[...body.matchAll(/^[ \t]*(`{3,}|~{3,})[ \t]*$/gm)]
      .filter(match=>match[1][0]===marker[0]).map(match=>match[1].length));
    if(longest<marker.length)continue;
    const closing=fence.parts.filter(part=>part.name==='CodeMark').at(-1),delimiter=marker[0].repeat(longest+1);
    for(const part of [fence.marker,closing])corrections.push({from:tr.changes.mapPos(part.from),to:tr.changes.mapPos(part.to),insert:delimiter});
  }
  if(!corrections.length)return tr;
  const changes=ChangeSet.of(corrections,tr.newDoc.length);
  const incoming=emptyAnchor!==undefined&&tr.newSelection.ranges.length===1&&tr.newSelection.main.empty?EditorSelection.single(emptyAnchor):tr.newSelection;
  const selection=EditorSelection.create(incoming.ranges.map(range=>EditorSelection.range(changes.mapPos(range.anchor,-1),changes.mapPos(range.head,-1))),incoming.mainIndex);
  return [tr,{changes,sequential:true,selection,annotations:[structure.of(true),isolateHistory.of('full')]}];
}
function keepCaretInBody(tr) {
  if(!tr.selection||tr.annotation(structure))return tr;
  const ranges=tr.startState.field(codeFences);
  const selection=tr.newSelection,adjusted=selection.ranges.map(range=>{
    if(!range.empty)return range;
    let head=range.head;
    for(const fence of ranges){
      const from=tr.changes.mapPos(fence.from),to=tr.changes.mapPos(fence.to),bodyFrom=tr.changes.mapPos(fence.bodyFrom),bodyTo=tr.changes.mapPos(fence.bodyTo);
      if(head>=from&&head<bodyFrom)head=bodyFrom;
      else if(fence.closing&&head>bodyTo&&head<=to)head=bodyTo;
    }
    return head===range.head?range:EditorSelection.cursor(head);
  });
  return adjusted.some((range,index)=>range!==selection.ranges[index])?[tr,{selection:EditorSelection.create(adjusted,selection.mainIndex)}]:tr;
}
export function exitCode(view,direction) {
  const state=view.state,range=state.selection.main;if(!range.empty)return false;
  const fence=state.field(codeFences).find(fence=>fence.closing&&range.head>=fence.bodyFrom&&range.head<=fence.bodyTo);
  if(!fence)return false;
  const line=state.doc.lineAt(range.head),boundary=state.doc.lineAt(direction>0?fence.bodyTo:fence.bodyFrom);
  if(line.number!==boundary.number)return false;
  let changes,anchor;
  if(direction>0){
    if(fence.to===state.doc.length){changes={from:fence.to,insert:'\n\n'};anchor=fence.to+2;}
    else anchor=fence.closing.to+1;
  }else if(fence.opening.from===0){changes={from:0,insert:'\n\n'};anchor=0;}
  else anchor=state.doc.lineAt(fence.opening.from-1).from;
  view.dispatch({changes,selection:{anchor},scrollIntoView:true,annotations:structure.of(true),userEvent:changes?'input':'select'});return true;
}
export const codeEditing=[codeFences,EditorView.inputHandler.of(completeFence),
  EditorState.changeFilter.of(protectFences),EditorState.transactionFilter.of(growFences),EditorState.transactionFilter.of(keepCaretInBody)];
