// Repeating the alphabet makes a scrolled viewport ambiguous every 26 keys.
// A reproducible varied stream allows exact alignment without discarding keys.
export function echoInput(length, seed=817) {
  let state=seed>>>0;
  return Array.from({length},()=>{
    state=(Math.imul(state,1664525)+1013904223)>>>0;
    return String.fromCharCode(97+state%26);
  }).join('');
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
