/* Edit the Markdown source through document typography and local syntax reveals. */
import {ChangeSet, EditorSelection, EditorState, StateEffect, StateField} from '@codemirror/state';
import {Decoration, EditorView, WidgetType, keymap, showTooltip} from '@codemirror/view';
import {defaultKeymap, history, historyKeymap, isolateHistory} from '@codemirror/commands';
import {markdown} from '@codemirror/lang-markdown';
import {syntaxTree} from '@codemirror/language';
import {GFM} from '@lezer/markdown';
import {codeEditing, codeFence, CodeToolbar, decorateCode, exitCode} from './live-markdown-code.js';
import {editableTables, tableLayout, tableSelection} from './live-markdown-tables.js';

const focused = StateEffect.define();
const focusState = StateField.define({
  create: () => false,
  update(value, transaction) {
    for (const effect of transaction.effects) if (effect.is(focused)) value = effect.value;
    return value;
  },
});
const inlineFormats = {StrongEmphasis:['strong','lab-live-strong'], Emphasis:['em','lab-live-emphasis'],
  Strikethrough:['s','lab-live-strike'], InlineCode:['code','lab-live-code-inline'], Link:['a','lab-live-link'], Autolink:['a','lab-live-link']};
const inlineTypes = new Set([...Object.keys(inlineFormats), 'Image', 'Entity', 'Escape']);
const intersects = (state, from, to) => state.field(focusState) && state.selection.ranges.some(range =>
  range.empty ? range.head >= from && range.head <= to : range.from < to && range.to > from);
const children = node => { const result=[]; for(let child=node.firstChild;child;child=child.nextSibling)result.push(child); return result; };

class TextWidget extends WidgetType {
  constructor(text, className) { super(); Object.assign(this,{text,className}); }
  eq(other) { return this.text === other.text && this.className === other.className; }
  toDOM() { const node=document.createElement('span');node.className=this.className;node.textContent=this.text;return node; }
}
class TaskWidget extends WidgetType {
  constructor(from, checked) { super(); Object.assign(this,{from,checked}); }
  eq(other) { return this.from === other.from && this.checked === other.checked; }
  toDOM(view) {
    const input=document.createElement('input');input.type='checkbox';input.checked=this.checked;
    input.className='lab-live-task-check';input.setAttribute('aria-label',this.checked ? 'Mark item incomplete' : 'Mark item complete');
    input.addEventListener('mousedown',event=>event.preventDefault());
    input.addEventListener('change',()=>{view.dispatch({changes:{from:this.from+1,to:this.from+2,insert:input.checked?'x':' '},selection:{anchor:Math.min(view.state.doc.length,this.from+4)},userEvent:'input'});view.focus();});
    return input;
  }
  ignoreEvent() { return true; }
}
class EmptyTableCell extends WidgetType {
  constructor(from,attributes) { super();Object.assign(this,{from,attributes}); }
  eq(other) { return this.from===other.from&&this.attributes.class===other.attributes.class&&this.attributes.style===other.attributes.style; }
  toDOM(view) {
    const cell=document.createElement('span');for(const [name,value] of Object.entries(this.attributes))cell.setAttribute(name,value);
    cell.textContent='\u200b';cell.addEventListener('mousedown',event=>{event.preventDefault();view.dispatch({selection:{anchor:this.from}});view.focus();});return cell;
  }
  ignoreEvent() { return true; }
}
class RenderedMarkdown extends WidgetType {
  constructor(source, from, definitions, prepare, inline=false) { super(); Object.assign(this,{source,from,definitions,prepare,inline}); }
  eq(other) { return this.source===other.source && this.from===other.from && this.definitions===other.definitions && this.inline===other.inline; }
  toDOM(view) {
    const block=document.createElement(this.inline?'span':'div');
    block.className='lab-live-markdown-block assistant-markdown'+(this.inline?' lab-live-media':'');
    block.innerHTML=window.LabMarkdown.render(this.source+this.definitions);
    if(this.inline && block.firstElementChild?.tagName==='P')block.firstElementChild.replaceWith(...block.firstElementChild.childNodes);
    this.prepare?.(block);
    block.addEventListener('mousedown',event=>{
      if(event.button!==0 || event.target.closest('button, summary') || (event.metaKey||event.ctrlKey)&&event.target.closest('a'))return;
      event.preventDefault();
      const caret=document.caretPositionFromPoint?.(event.clientX,event.clientY);
      const fallback=!caret&&document.caretRangeFromPoint?.(event.clientX,event.clientY);
      const target=caret?.offsetNode||fallback?.startContainer, offset=caret?.offset??fallback?.startOffset??0;
      let position=this.inline?2:0, search=0;
      const walker=document.createTreeWalker(block,NodeFilter.SHOW_TEXT);
      for(let text=walker.nextNode();text;text=walker.nextNode()){
        if(text.parentElement.closest('button'))continue;
        const found=this.source.indexOf(text.data,search);
        if(found<0)continue;
        if(text===target){position=found+Math.min(offset,text.length);break;}
        // Noneditable previews may make native caret APIs return the widget's
        // parent. Measure the clicked text instead of jumping to its block start.
        const range=document.createRange();range.selectNodeContents(text);
        if([...range.getClientRects()].some(rect=>event.clientX>=rect.left&&event.clientX<=rect.right&&event.clientY>=rect.top&&event.clientY<=rect.bottom)){
          for(let index=0;index<text.length;index++){
            range.setStart(text,index);range.setEnd(text,index+1);
            const rect=[...range.getClientRects()].find(rect=>event.clientY>=rect.top&&event.clientY<=rect.bottom&&event.clientX<=rect.right);
            if(rect){position=found+index+(event.clientX>(rect.left+rect.right)/2?1:0);break;}
          }
          break;
        }
        search=found+text.length;
      }
      position=Math.min(this.from+this.source.length,this.from+position);
      view.dispatch({selection:{anchor:event.shiftKey?view.state.selection.main.anchor:position,head:position},effects:focused.of(true)});
      view.focus();
    });
    return block;
  }
  ignoreEvent() { return true; }
}

function metadata(state, previous) {
  if(previous?.doc===state.doc)return previous;
  const body=state.doc.toString(), tokens=window.marked.lexer(body), disclosures=[];
  const definitions='\n\n'+Object.entries(tokens.links||{}).map(([label,link])=>
    `[${label}]: <${link.href}>${link.title?' "'+link.title.replace(/"/g,'\\"')+'"':''}`).join('\n');
  let offset=0;
  for(let index=0;index<tokens.length;index++){
    const token=tokens[index];let raw=token.raw;
    if(token.type==='html' && /^\s*<details\b/i.test(raw)){
      let depth=(raw.match(/<details\b/gi)||[]).length-(raw.match(/<\/details>/gi)||[]).length;
      while(depth>0 && index+1<tokens.length){
        const next=tokens[++index].raw;raw+=next;
        depth+=(next.match(/<details\b/gi)||[]).length-(next.match(/<\/details>/gi)||[]).length;
      }
      const from=body.indexOf(raw,offset);
      if(from>=0)disclosures.push({from,to:from+raw.replace(/\n+$/,'').length,source:raw});
    }
    const from=body.indexOf(raw,offset);if(from>=0)offset=from+raw.length;
  }
  return {doc:state.doc,body,definitions,disclosures,linkDestinations:new Map()};
}

function previewDecorations(state, prepare, previous) {
  const meta=metadata(state,previous), {body,definitions}=meta, decorations=[], atomic=[], lines=new Map(), opaque=[],codeHighlights=new Map();
  const addLine=(from,className,attributes={})=>{
    const start=state.doc.lineAt(from).from, row=lines.get(start)||{classes:new Set(),attributes:{}};
    row.classes.add(className);Object.assign(row.attributes,attributes);lines.set(start,row);
  };
  const replace=(from,to,widget,block=false)=>{
    if(to<=from)return;
    const range=Decoration.replace({widget,block}).range(from,to);decorations.push(range);
    if(!block)atomic.push(range);
  };
  const syntax=(from,to,reveal=false,widget)=>{
    if(to<=from)return;
    if(reveal)decorations.push(Decoration.mark({class:'lab-live-syntax'}).range(from,to));
    else replace(from,to,widget);
  };
  for(const group of meta.disclosures){
    if(intersects(state,group.from,group.to))continue;
    opaque.push(group);replace(group.from,group.to,new RenderedMarkdown(group.source,group.from,definitions,prepare),true);
  }
  const tree=syntaxTree(state), formats=[], active=new Set();
  tree.iterate({enter:node=>{if(inlineTypes.has(node.name))formats.push(node.node);}});
  if(state.field(focusState))for(const selection of state.selection.ranges){
    const containing=formats.filter(node=>selection.from>=node.from && selection.to<=node.to).sort((a,b)=>(a.to-a.from)-(b.to-b.from));
    if(containing.length)active.add(containing[0].from+':'+containing[0].to);
    else if(!selection.empty)for(const node of formats)if(selection.from<node.to && selection.to>node.from)active.add(node.from+':'+node.to);
  }
  tree.iterate({enter:ref=>{
    const node=ref.node,{name,from,to}=node;
    if(opaque.some(range=>from>=range.from && to<=range.to))return false;
    const raw=body.slice(from,to), local=active.has(from+':'+to), parts=children(node);
    if(/^ATXHeading[1-6]$|^SetextHeading[12]$/.test(name)){
      const level=Number(name.slice(-1));addLine(from,'lab-live-heading lab-live-heading-'+level,{role:'heading','aria-level':String(level)});
    }
    if(inlineFormats[name]){
      const [tagName,className]=inlineFormats[name];
      let start=from,end=to,attributes={};
      const marks=parts.filter(child=>/^(EmphasisMark|StrikethroughMark|CodeMark|LinkMark)$/.test(child.name));
      if(marks.length){start=marks[0].to;end=marks[1]?.from??to;}
      if(name==='Link'||name==='Autolink'){
        let href=meta.linkDestinations.get(raw);
        if(href===undefined){
          href=previous?.definitions===definitions?previous.linkDestinations.get(raw):undefined;
          if(href===undefined){
            const fragment=document.createElement('div');fragment.innerHTML=window.LabMarkdown.render(raw+definitions);
            prepare?.(fragment);href=fragment.querySelector('a')?.getAttribute('href')??null;
          }
          meta.linkDestinations.set(raw,href);
        }
        if(href!==null)attributes.href=href;
        // URL spacing and brackets stay local to their own link, never the paragraph.
        const closing=marks[1];if(name==='Link'&&closing)syntax(closing.from,to,local);
        if(marks[0])syntax(marks[0].from,marks[0].to,local);
        if(name==='Autolink'&&marks[1])syntax(marks[1].from,marks[1].to,local);
      }else for(const mark of marks)syntax(mark.from,mark.to,local);
      if(end>start)decorations.push(Decoration.mark({tagName,class:className,attributes}).range(start,end));
      // Marks are handled as a unit, but nested inline formatting still renders.
      for(const child of parts)if(/Mark$/.test(child.name)||['URL','LinkTitle','LinkLabel'].includes(child.name))opaque.push({from:child.from,to:child.to});
    }else if(name==='Image'){
      if(!local){replace(from,to,new RenderedMarkdown(raw,from,definitions,prepare,true));return false;}
      for(const child of parts)if(child.name==='LinkMark')syntax(child.from,child.to,true);
      return false;
    }else if(name==='Entity'||name==='Escape'){
      if(local)syntax(from,to,true);
      else{const text=document.createElement('span');text.innerHTML=window.LabMarkdown.render(raw);replace(from,to,new TextWidget(text.textContent,'lab-live-literal'));}
      return false;
    }else if(name==='HeaderMark'){
      const line=state.doc.lineAt(from), trailing=body.slice(to,line.to).match(/^\s+/)?.[0].length||0;
      if(!node.parent.name.startsWith('Setext'))syntax(from,to+trailing,intersects(state,from,to+trailing));
      else{addLine(from,'lab-live-boundary'+(intersects(state,from,to)?' lab-live-source':''));syntax(from,to,intersects(state,from,to));}
    }else if(name==='ListMark'){
      const end=to+(body.slice(to).match(/^[ \t]+/)?.[0].length||0), task=node.parent.getChild('Task');
      addLine(from,'lab-live-list');syntax(from,end,intersects(state,from,to),task?undefined:new TextWidget(/^\d/.test(raw)?raw:'•','lab-live-list-marker'));
    }else if(name==='TaskMarker'){
      syntax(from,to,intersects(state,from,to),new TaskWidget(from,/x/i.test(raw)));
    }else if(name==='QuoteMark'){
      addLine(from,'lab-live-quote');syntax(from,to+(body[to]===' '?1:0),intersects(state,from,to));
    }else if(name==='FencedCode'||name==='CodeBlock'){
      if(name==='FencedCode'){
        const fence=codeFence(state,node);
        if(fence.language==='mermaid'&&!intersects(state,from,to)){
          decorations.push(Decoration.widget({widget:new CodeToolbar(fence),block:true,side:-1}).range(from));
          replace(from,to,new RenderedMarkdown(raw,from,definitions,prepare),true);
        }else decorateCode(state,fence,{addLine,replace,decorations,cache:codeHighlights,previous:previous?.codeHighlights});
        return false;
      }
      for(let number=state.doc.lineAt(from).number;number<=state.doc.lineAt(to).number;number++)addLine(state.doc.line(number).from,'lab-live-code-line');
    }else if(name==='CodeMark'&&node.parent.name==='FencedCode'){
      const line=state.doc.lineAt(from), reveal=intersects(state,line.from,line.to);
      addLine(from,'lab-live-boundary'+(reveal?' lab-live-source':''));syntax(line.from,line.to,reveal);
    }else if(name==='Table'){
      const {rows,columns,align}=tableLayout(state,node);
      for(const [index,row] of rows.entries()){
        addLine(row.node.from,'lab-live-table-row'+(index===0?' lab-live-table-header':'')+(index===rows.length-1?' lab-live-table-last':''),
          {style:'--lab-table-columns:'+columns,'data-table-row':String(index)});
        let position=row.node.from;
        for(const [column,cell] of row.cells.entries()){
          replace(position,cell.from);position=cell.to;
          const attributes={class:'lab-live-table-cell'+(column===columns-1?' lab-live-table-cell-end':''),
            style:'grid-column:'+(column+1)+';grid-row:1;text-align:'+(align[column]||'left'),
            'data-cell-from':String(cell.from),'data-cell-to':String(cell.to)};
          if(cell.to>cell.from)decorations.push(Decoration.mark({attributes}).range(cell.from,cell.to));
          else decorations.push(Decoration.widget({widget:new EmptyTableCell(cell.from,attributes),side:1}).range(cell.from));
        }
        replace(position,row.node.to);
      }
    }else if(name==='TableCell'){
      // Cells are laid out together so every row shares the same columns.
    }else if(name==='TableDelimiter'){
      const whole=node.parent.name==='Table';
      if(whole){addLine(from,'lab-live-table-divider');replace(from,to);}
    }else if(name==='HorizontalRule'){
      if(intersects(state,from,to))syntax(from,to,true);else replace(from,to,new TextWidget('','lab-live-rule'));
    }else if(name==='HTMLBlock'||name==='HTMLTag'){
      const tags=[...raw.matchAll(/<[^>]*>/g)];
      for(const tag of tags)syntax(from+tag.index,from+tag.index+tag[0].length,intersects(state,from+tag.index,from+tag.index+tag[0].length));
      if(name==='HTMLBlock'&&tags.length&&raw.replace(/<[^>]*>/g,'').trim()==='')addLine(from,'lab-live-boundary'+(intersects(state,from,to)?' lab-live-source':''));
    }else if(name==='LinkReference'){
      if(intersects(state,from,to))syntax(from,to,true);
      else{replace(from,to);addLine(from,'lab-live-boundary');}
      return false;
    }
  }});
  for(const [from,row] of lines)decorations.push(Decoration.line({attributes:{...row.attributes,class:[...row.classes].join(' ')}}).range(from));
  return {decorations:Decoration.set(decorations,true),atomic:Decoration.set(atomic,true),metadata:{...meta,codeHighlights}};
}

const formatTypes={'**':'StrongEmphasis','*':'Emphasis','~~':'Strikethrough','`':'InlineCode'};
function hasFormatText(state,from,to,ignored) {
  let cursor=from;
  for(const span of ignored){
    if(span.to<=cursor)continue;
    if(span.from>=to)break;
    if(span.from>cursor&&/\S/.test(state.doc.sliceString(cursor,Math.min(to,span.from))))return true;
    cursor=Math.max(cursor,span.to);if(cursor>=to)return false;
  }
  return cursor<to&&/\S/.test(state.doc.sliceString(cursor,to));
}
function selectionFormatting(state, marker) {
  let {from:start,to:end}=state.selection.main;
  if(start===end){const word=state.wordAt(start);if(word){start=word.from;end=word.to;}}
  const runs=[],ignored=[],blocks=[];
  syntaxTree(state).iterate({from:start,to:end,enter:ref=>{
    const node=ref.node;
    if(inlineFormats[ref.name])ignored.push(...children(node).filter(child=>/Mark$/.test(child.name)||['URL','LinkTitle','LinkLabel'].includes(child.name)));
    if(ref.name===formatTypes[marker]){
      const marks=children(node).filter(child=>/^(EmphasisMark|StrikethroughMark|CodeMark)$/.test(child.name));
      if(marks.length===2&&node.from<end&&node.to>start)runs.push({from:marks[0].to,to:marks[1].from,marks});
    }
    if(/Mark$/.test(ref.name)||['URL','LinkTitle','LinkLabel'].includes(ref.name))ignored.push({from:ref.from,to:ref.to});
    if(ref.name==='Paragraph'||/^ATXHeading[1-6]$|^SetextHeading[12]$|^TableCell$/.test(ref.name)){
      const marks=children(node).filter(child=>child.name==='HeaderMark');
      blocks.push({from:Math.max(start,marks[0]?.from===node.from?marks[0].to:node.from),to:Math.min(end,marks.at(-1)?.from>node.from?marks.at(-1).from:node.to)});
    }
  }});
  // Whitespace and hidden Markdown delimiters do not make an otherwise fully
  // formatted selection mixed. Literal stars in code remain ordinary content.
  let cursor=start,all=runs.length>0;
  for(const span of [...runs,...ignored].sort((a,b)=>a.from-b.from)){
    if(span.to<=cursor)continue;
    if(span.from>cursor&&/\S/.test(state.doc.sliceString(cursor,Math.min(end,span.from)))){all=false;break;}
    cursor=Math.max(cursor,span.to);if(cursor>=end)break;
  }
  if(cursor<end&&/\S/.test(state.doc.sliceString(cursor,end)))all=false;
  return {start,end,runs,blocks,all,ignored:ignored.sort((a,b)=>a.from-b.from)};
}
function formatSelection(view, marker) {
  const state=view.state,{start,end,runs,blocks,all,ignored}=selectionFormatting(state,marker);
  const marks=new Map(runs.flatMap(run=>run.marks.map(mark=>[mark.from,mark])));
  const remove=state.changes([...marks.values()].sort((a,b)=>a.from-b.from).map(mark=>({from:mark.from,to:mark.to})));
  const doc=remove.apply(state.doc),from=remove.mapPos(start),to=remove.mapPos(end),insertions=new Map();
  const insert=(position,text)=>insertions.set(position,(insertions.get(position)||'')+text);
  const wrap=(start,end,delimiter)=>{
    const text=doc.sliceString(start,end),leading=text.match(/^\s*/)[0].length,trailing=text.match(/\s*$/)[0].length;
    if(leading===text.length)return;
    insert(start+leading,delimiter);insert(end-trailing,delimiter);
  };
  // Split only intersected runs, retaining formatting outside the selection.
  for(const run of runs){
    const delimiter=marker==='`'?state.doc.sliceString(run.marks[0].from,run.marks[0].to):marker;
    if(run.from<start&&hasFormatText(state,run.from,start,ignored))wrap(remove.mapPos(run.from),from,delimiter);
    if(run.to>end&&hasFormatText(state,end,run.to,ignored))wrap(to,remove.mapPos(run.to),delimiter);
  }
  if(!all){
    let delimiter=marker;
    if(marker==='`')delimiter='`'.repeat(Math.max(0,...[...doc.sliceString(from,to).matchAll(/`+/g)].map(match=>match[0].length))+1);
    const spans=blocks.length?blocks:[{from:start,to:end}];
    for(const span of spans){
      if(span.to<=span.from)continue;
      wrap(remove.mapPos(span.from),remove.mapPos(span.to),delimiter);
    }
    if(from===to)insert(from,delimiter+delimiter);
  }
  const add=ChangeSet.of([...insertions].sort((a,b)=>a[0]-b[0]).map(([from,insert])=>({from,insert})),doc.length);
  const changes=remove.compose(add);
  const anchor=from===to?from+marker.length:add.mapPos(from,1),head=from===to?anchor:add.mapPos(to,-1);
  view.dispatch({changes,selection:EditorSelection.range(Math.min(anchor,head),Math.max(anchor,head)),userEvent:'input',annotations:isolateHistory.of('full')});
  view.focus();return true;
}
function formattingTooltip(state) {
  const range=state.selection.main;if(range.empty||!state.field(focusState))return null;
  return {pos:range.from,end:range.to,above:true,create(view){
    const dom=document.createElement('div');dom.className='lab-live-format-toolbar';dom.setAttribute('role','toolbar');dom.setAttribute('aria-label','Format selected text');
    dom.addEventListener('focusout',()=>queueMicrotask(()=>{
      if(!view.hasFocus&&!dom.contains(document.activeElement))view.dispatch({effects:focused.of(false)});
    }));
    for(const [label,text,marker] of [['Bold','B','**'],['Italic','I','*'],['Strikethrough','S','~~'],['Inline code','‹›','`']]){
      const button=document.createElement('button');button.type='button';button.textContent=text;button.title=label;button.setAttribute('aria-label',label);button.setAttribute('aria-pressed',String(selectionFormatting(state,marker).all));
      button.addEventListener('mousedown',event=>event.preventDefault());button.onclick=()=>formatSelection(view,marker);dom.append(button);
    }
    return {dom,update(update){for(const button of dom.querySelectorAll('button')){const marker={'Bold':'**','Italic':'*','Strikethrough':'~~','Inline code':'`'}[button.getAttribute('aria-label')];button.setAttribute('aria-pressed',String(selectionFormatting(update.state,marker).all));}}};
  }};
}

const slashActions=[
  {id:'fold',label:'Foldable content',description:'Toggle a section open or closed',keywords:'toggle details collapse fold html',text:'<details>\n<summary>Toggle title</summary>\n\nContent\n\n</details>',select:'Toggle title'},
  {id:'h1',label:'Heading 1',description:'Large section heading',keywords:'title heading',text:'# Heading',select:'Heading'},
  {id:'h2',label:'Heading 2',description:'Medium section heading',keywords:'heading',text:'## Heading',select:'Heading'},
  {id:'h3',label:'Heading 3',description:'Small section heading',keywords:'heading',text:'### Heading',select:'Heading'},
  {id:'bullet',label:'Bullet list',description:'An unordered list',keywords:'list unordered',text:'- List item',select:'List item'},
  {id:'number',label:'Numbered list',description:'An ordered list',keywords:'list ordered',text:'1. List item',select:'List item'},
  {id:'task',label:'To-do list',description:'A list with checkboxes',keywords:'task checkbox checklist todo',text:'- [ ] To-do',select:'To-do'},
  {id:'quote',label:'Quote',description:'A block quote',keywords:'blockquote',text:'> Quote',select:'Quote'},
  {id:'code',label:'Code block',description:'A fenced block of code',keywords:'code fence',text:'```\nCode\n```',select:'Code'},
  {id:'table',label:'Table',description:'A table with two columns',keywords:'table columns',text:'| Column 1 | Column 2 |\n| --- | --- |\n| Value | Value |',select:'Column 1'},
  {id:'divider',label:'Divider',description:'A horizontal line',keywords:'rule separator',text:'---\n\n'},
];
const slashNavigation=StateEffect.define();
function slashMatch(state) {
  const range=state.selection.main;if(!range.empty||!state.field(focusState))return null;
  const line=state.doc.lineAt(range.head),match=state.doc.sliceString(line.from,range.head).match(/^\s*\/([\w -]*)$/);
  if(!match||state.doc.sliceString(range.head,line.to).trim())return null;
  for(let node=syntaxTree(state).resolveInner(range.head,-1);node;node=node.parent){
    if(['FencedCode','CodeBlock','InlineCode','Link','Image','HTMLBlock'].includes(node.name))return null;
  }
  const from=line.from+match[0].indexOf('/'),query=match[1].trim().toLowerCase();
  return {from,to:range.head,query,actions:slashActions.filter(action=>(action.label+' '+action.keywords).toLowerCase().includes(query))};
}
const slashState=StateField.define({
  create:()=>({match:null,index:0,dismissed:null}),
  update(value,transaction){
    const match=slashMatch(transaction.state),signature=match?match.from+':'+match.to+':'+match.query:null;
    let dismissed=transaction.docChanged||transaction.selection?null:value.dismissed;
    let index=match?.from===value.match?.from&&match?.query===value.match?.query?value.index:0;
    for(const effect of transaction.effects)if(effect.is(slashNavigation)){
      if(effect.value==='dismiss')dismissed=signature;
      else if(match?.actions.length)index=(index+effect.value+match.actions.length)%match.actions.length;
    }
    return {match:signature!==dismissed?match:null,index,dismissed};
  },
});
function applySlashAction(view,action) {
  const {match}=view.state.field(slashState);if(!match)return false;
  const offset=action.select?action.text.indexOf(action.select):action.text.length;
  view.dispatch({changes:{from:match.from,to:match.to,insert:action.text},selection:EditorSelection.range(match.from+offset,match.from+offset+(action.select?.length||0)),userEvent:'input',annotations:isolateHistory.of('full')});
  view.focus();return true;
}
function slashKey(view,action) {
  const {match,index}=view.state.field(slashState);if(!match)return false;
  if(action==='accept')return match.actions[index]?applySlashAction(view,match.actions[index]):false;
  view.dispatch({effects:slashNavigation.of(action)});return true;
}
function slashTooltip(state) {
  const {match}=state.field(slashState);if(!match)return null;
  return {pos:match.from,above:false,create:createSlashTooltip};
}
function createSlashTooltip(view) {
  const dom=document.createElement('div');dom.className='lab-live-slash-menu';dom.setAttribute('role','menu');dom.setAttribute('aria-label','Insert a block');
  const title=document.createElement('div');title.className='lab-live-slash-title';title.textContent='Insert a block';dom.append(title);
  let shown=null;
  const render=()=>{
    const current=view.state.field(slashState);if(!current.match)return;
    const actions=current.match.actions;
    if(!shown||shown.length!==actions.length||shown.some((action,index)=>action!==actions[index])){
      dom.querySelectorAll('button, .lab-live-slash-empty').forEach(node=>node.remove());
      for(const action of actions){
        const button=document.createElement('button');button.type='button';button.setAttribute('role','menuitem');
        const label=document.createElement('span');label.textContent=action.label;const description=document.createElement('small');description.textContent=action.description;button.append(label,description);
        button.addEventListener('mousedown',event=>event.preventDefault());button.onclick=()=>applySlashAction(view,action);dom.append(button);
      }
      if(!actions.length){const empty=document.createElement('div');empty.className='lab-live-slash-empty';empty.textContent='No actions found';dom.append(empty);}
      shown=actions;
    }
    dom.querySelectorAll('button').forEach((button,index)=>{button.classList.toggle('is-selected',index===current.index);button.setAttribute('aria-current',String(index===current.index));});
  };
  render();
  dom.addEventListener('focusout',()=>queueMicrotask(()=>{if(!view.hasFocus&&!dom.contains(document.activeElement))view.dispatch({effects:focused.of(false)});}));
  return {dom,update:render,positioned(){dom.querySelector('.is-selected')?.scrollIntoView({block:'nearest'});}};
}

window.LabMarkdownEditor = {
  create(parent,{body,onChange,onSave,prepare,prepareHeadings}) {
    const preview=StateField.define({
      create:state=>previewDecorations(state,prepare),
      update:(value,transaction)=>transaction.docChanged||transaction.selection||syntaxTree(transaction.startState)!==syntaxTree(transaction.state)||transaction.effects.some(effect=>effect.is(focused))
        ?previewDecorations(transaction.state,prepare,value.metadata):value,
      provide:field=>[EditorView.decorations.from(field,value=>value.decorations),EditorView.atomicRanges.of(view=>view.state.field(field).atomic)],
    });
    const view=new EditorView({parent,state:EditorState.create({doc:body,extensions:[
      focusState,markdown({extensions:[GFM,editableTables]}),codeEditing,tableSelection,preview,history(),EditorView.lineWrapping,slashState,
      EditorView.contentAttributes.of({'aria-label':'Current tab Markdown',spellcheck:'true'}),
      showTooltip.compute(['doc','selection',focusState],formattingTooltip),showTooltip.compute([slashState],slashTooltip),
      keymap.of([{key:'ArrowDown',run:view=>slashKey(view,1)||exitCode(view,1)},{key:'ArrowUp',run:view=>slashKey(view,-1)||exitCode(view,-1)},
        {key:'Enter',run:view=>slashKey(view,'accept')},{key:'Escape',run:view=>slashKey(view,'dismiss')},
        {key:'Mod-s',run:()=>{onSave();return true;}},{key:'Mod-b',run:view=>formatSelection(view,'**')},
        {key:'Mod-i',run:view=>formatSelection(view,'*')},{key:'Mod-e',run:view=>formatSelection(view,'`')},
        ...defaultKeymap,...historyKeymap]),
      EditorView.updateListener.of(update=>{
        if(update.docChanged)onChange(update.state.doc.toString());
        if(update.docChanged||update.viewportChanged)prepareHeadings?.(update.view.contentDOM);
      }),
      EditorView.domEventHandlers({
        focus:(_event,editor)=>{queueMicrotask(()=>{if(!editor.state.field(focusState))editor.dispatch({effects:focused.of(true)});});},
        blur:(_event,editor)=>{queueMicrotask(()=>{
          if(!editor.hasFocus&&!(editor.dom.contains(document.activeElement)&&document.activeElement?.closest('.lab-live-format-toolbar, .lab-live-slash-menu, .lab-live-code-toolbar')))editor.dispatch({effects:focused.of(false)});
        });},
        click:event=>{const link=event.target.closest('a.lab-live-link');if(!link)return false;event.preventDefault();if((event.metaKey||event.ctrlKey)&&link.hasAttribute('href'))window.LabExternalLinks?.open(link.href,{clientOnly:true});return false;},
      }),
    ]})});
    prepareHeadings?.(view.contentDOM);
    return {view,get value(){return view.state.doc.toString();},set value(value){if(value!==view.state.doc.toString())view.dispatch({changes:{from:0,to:view.state.doc.length,insert:value}});},
      sectionAt(position){
        const headings=[],groups=view.state.field(preview).metadata.disclosures;
        syntaxTree(view.state).iterate({enter:node=>{if(/^ATXHeading[1-6]$|^SetextHeading[12]$/.test(node.name))headings.push({from:node.from,to:node.to,level:Number(node.name.slice(-1))});}});
        const heading=headings.find(node=>position>=view.state.doc.lineAt(node.from).from&&position<=node.to);
        if(!heading)return '';
        const groupAt=from=>groups.find(group=>from>=group.from&&from<group.to);
        const scope=groupAt(heading.from);
        const next=headings.find(node=>node.from>heading.from&&node.level<=heading.level&&groupAt(node.from)===scope);
        return view.state.doc.sliceString(heading.from,next?.from??scope?.to??view.state.doc.length);
      },
      focus:()=>view.focus(),destroy:()=>view.destroy()};
  },
};
