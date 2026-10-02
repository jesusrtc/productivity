/* Editable table cells use native Markdown offsets, with forgiving separators. */
import {EditorSelection} from '@codemirror/state';
import {EditorView} from '@codemirror/view';
const row=source=>window.LabMarkdown.tableCells(source);
const delimiter=source=>{
  const cells=row(source).cells;return cells.length>0&&cells.every(cell=>/^:?-+:?$/.test(cell.text));
};
function rowElements(context,source,offset) {
  const {cells,pipes}=row(source),elements=[];
  for(const cell of cells)elements.push(context.elt('TableCell',offset+cell.from,offset+cell.to,context.parser.parseInline(cell.text,offset+cell.from)));
  for(const pipe of pipes)elements.push(context.elt('TableDelimiter',offset+pipe,offset+pipe+1));
  return elements.sort((a,b)=>a.from-b.from||a.to-b.to);
}
class EditableTableParser {
  constructor() { this.rows=null; }
  nextLine(context,line,leaf) {
    if(this.rows===null){
      this.rows=false;
      if(delimiter(line.text.slice(line.pos)))this.rows=[
        context.elt('TableHeader',leaf.start,leaf.start+leaf.content.length,rowElements(context,leaf.content,leaf.start)),
        context.elt('TableDelimiter',context.lineStart+line.pos,context.lineStart+line.text.length),
      ];
    }else if(this.rows)this.rows.push(context.elt('TableRow',context.lineStart+line.pos,context.lineStart+line.text.length,
      rowElements(context,line.text.slice(line.pos),context.lineStart+line.pos)));
    return false;
  }
  finish(context,leaf) {
    if(!this.rows)return false;
    context.addLeafElement(leaf,context.elt('Table',leaf.start,leaf.start+leaf.content.length,this.rows));return true;
  }
}
export const editableTables={parseBlock:[{
  name:'Table',
  leaf:(_context,leaf)=>row(leaf.content).pipes.length?new EditableTableParser():null,
  endLeaf:(context,line,leaf)=>!leaf.parsers.some(parser=>parser instanceof EditableTableParser)&&row(line.text.slice(line.basePos)).pipes.length>0&&delimiter(context.peekLine()),
  before:'SetextHeading',
}]};
export function tableLayout(state,table) {
  const rows=[];let separator;
  for(let child=table.firstChild;child;child=child.nextSibling){
    if(child.name==='TableHeader'||child.name==='TableRow'){
      const cells=[];for(let cell=child.firstChild;cell;cell=cell.nextSibling)if(cell.name==='TableCell')cells.push(cell);
      rows.push({node:child,cells});
    }else if(child.name==='TableDelimiter')separator=child;
  }
  const columns=Math.max(1,...rows.map(row=>row.cells.length)),align=separator?row(state.doc.sliceString(separator.from,separator.to)).cells.map(cell=>
    cell.text.startsWith(':')&&cell.text.endsWith(':')?'center':cell.text.endsWith(':')?'right':'left'):[];
  return {rows,columns,align};
}

// CodeMirror's ordinary coordinate lookup assumes one flowing text line. A
// table row has independently wrapped cells, so use the browser's text caret.
function tableRange(view,event,type) {
  const cell=document.elementFromPoint(event.clientX,event.clientY)?.closest('.lab-live-table-cell');
  if(!cell||!view.contentDOM.contains(cell))return EditorSelection.cursor(view.posAtCoords({x:event.clientX,y:event.clientY},false));
  const from=Number(cell.dataset.cellFrom),to=Number(cell.dataset.cellTo);
  const caret=document.caretPositionFromPoint?.(event.clientX,event.clientY),fallback=!caret&&document.caretRangeFromPoint?.(event.clientX,event.clientY);
  const node=caret?.offsetNode||fallback?.startContainer,offset=caret?.offset??fallback?.startOffset??0;
  const position=node&&cell.contains(node)?Math.max(from,Math.min(to,view.posAtDOM(node,offset))):to;
  if(type>=3)return EditorSelection.range(from,to);
  const word=type===2&&view.state.wordAt(position);
  return word?EditorSelection.range(Math.max(from,word.from),Math.min(to,word.to)):EditorSelection.cursor(position);
}
export const tableSelection=EditorView.mouseSelectionStyle.of((view,event)=>{
  if(event.button!==0||!event.target.closest('.lab-live-table-cell'))return null;
  const type=event.detail;let start=tableRange(view,event,type),selection=view.state.selection;
  return {
    update(update){if(update.docChanged){start=start.map(update.changes);selection=selection.map(update.changes);}},
    get(event,extend,multiple){
      let range=tableRange(view,event,type);
      if(extend)return selection.replaceRange(selection.main.extend(range.from,range.to));
      if(start.head!==range.head){
        const from=Math.min(start.from,range.from),to=Math.max(start.to,range.to);
        range=range.head>=start.head?EditorSelection.range(from,to):EditorSelection.range(to,from);
      }
      return multiple?selection.addRange(range):EditorSelection.create([range]);
    },
  };
});
