// Repeating the alphabet makes a scrolled viewport ambiguous every 26 keys.
// A reproducible varied stream allows exact alignment without discarding keys.
export function echoInput(length, seed=817) {
  let state=seed>>>0;
  return Array.from({length},()=>{
    state=(Math.imul(state,1664525)+1013904223)>>>0;
    return String.fromCharCode(97+state%26);
  }).join('');
}

export function echoTextThroughCursor(buffer, columns, outputFooter=false) {
  const last=buffer.baseY+buffer.cursorY;
  let end=buffer.cursorX,text='';
  // tmux can leave its cursor ON the rightmost cell after filling a row.
  // The output footer has a required terminator, so include that cell and
  // let its exact frame reader verify completion. Ordinary echo is unchanged.
  if(outputFooter && end===columns-1)end=columns;
  for(let row=0;row<=last;row++)text+=buffer.getLine(row)?.translateToString(true,0,row===last?end:undefined)||'';
  return text;
}

// Serialized into the owned terminal probe. Each parse/render observer gets
// its own reader so parsed-but-never-rendered text cannot authorize a gap.
export function createEchoReader(expected, marker) {
  let seenMarker=false,verified=0,markerReads=0,scrolledReads=0;
  const read=(text, limit) => {
    if(!Number.isInteger(limit) || limit<0 || limit>expected.length)throw Error('Invalid observed input count');
    const markerAt=text.lastIndexOf(marker);
    let start=0,length;
    if(markerAt>=0) {
      const tail=text.slice(markerAt+marker.length);
      if(!expected.startsWith(tail))throw Error('Rendered echo does not match expected input');
      length=tail.length;
    } else {
      if(!seenMarker)throw Error('Echo marker disappeared before verification');
      if(text.length<64)throw Error('Insufficient visible echo context after scrolling');
      start=expected.indexOf(text);
      if(start<0)throw Error('Scrolled echo does not match expected input');
      length=start+text.length;
      const next=expected.indexOf(text,start+1);
      if(next>=0 && next+text.length<=limit)throw Error('Scrolled echo alignment is ambiguous');
      if(start>verified)throw Error('Unverified echo characters scrolled out of view');
    }
    if(length>limit)throw Error('Rendered echo is ahead of observed input');
    if(markerAt>=0)markerReads++;else scrolledReads++;
    seenMarker=true;verified=Math.max(verified,length);
    return length;
  };
  read.snapshot=()=>({verified,markerReads,scrolledReads});
  return read;
}

// The busy-output fixture redraws a bounded input suffix in a fixed footer.
// The offset proves alignment; prior parse/render continuity proves its prefix.
export function createOutputEchoReader(expected,marker) {
  let verified=0,reads=0,suffixReads=0,pendingReads=0;
  const read=(text,limit)=>{
    if(!Number.isInteger(limit)||limit<0||limit>expected.length)throw Error('Invalid observed input count');
    const at=text.lastIndexOf(marker+':');
    if(at<0 || !text.endsWith('|')){pendingReads++;return null;}
    const frame=text.slice(at+marker.length+1),match=/^(\d{6}):([a-z]*)\|$/.exec(frame);
    if(!match)throw Error('Malformed output-fixture echo footer');
    const start=Number(match[1]),tail=match[2],end=start+tail.length;
    if(start>verified)throw Error('Unverified echo prefix disappeared from footer');
    if(end>limit)throw Error('Rendered echo is ahead of observed input');
    if(tail!==expected.slice(start,end))throw Error('Output-fixture echo does not match expected input');
    if(tail.length>64 || (start>0&&tail.length!==64))throw Error('Output-fixture suffix has invalid length');
    verified=Math.max(verified,end);reads++;if(start)suffixReads++;
    return end;
  };
  read.snapshot=()=>({verified,reads,suffixReads,pendingReads});
  return read;
}

// Only record load text in rows included in an actual xterm render callback.
export function readRenderedOutput(buffer,range,cols,rows) {
  let maximum=0,observed=0;
  for(let row=Math.max(0,range.start);row<=Math.min(range.end,rows-7);row++) {
    const text=buffer.getLine(buffer.viewportY+row)?.translateToString(true)||'';
    if(!text.startsWith('load '))continue;
    if(text.length!==cols-1)continue; // A transport chunk may end mid-line.
    const match=/^load (\d{8}) ([A-Z]+)$/.exec(text);
    if(!match)throw Error('Malformed rendered output-load line');
    const sequence=Number(match[1]);
    if(match[2]!==String.fromCharCode(65+sequence%26).repeat(cols-15))throw Error('Corrupted rendered output-load line');
    maximum=Math.max(maximum,sequence);observed++;
  }
  return {maximum,observed};
}
