// Shared by the native keyboard, click and resize probes. This function is
// serialized into their browser handlers, so it must have no module closure.
export function captureInputClock(event) {
  const handlerAt=performance.now(), wallEpoch=Date.now(), wallSampleEnd=performance.now();
  return {source:event.timeStamp,sourceEpoch:performance.timeOrigin+event.timeStamp,
    handlerAt,wallEpoch,wallSampleEnd};
}

export function validateInputClock(clock, sentEpoch) {
  if(!clock || ![clock.source,clock.sourceEpoch,clock.handlerAt,clock.wallEpoch,clock.wallSampleEnd,sentEpoch].every(Number.isFinite)) {
    return {valid:false,reason:'Missing or nonfinite input clock sample'};
  }
  const sampleMs=clock.wallSampleEnd-clock.handlerAt;
  const rawDeltaMs=clock.sourceEpoch-sentEpoch;
  // CDP translates wall time to monotonic ticks using the current clock pair.
  // performance.timeOrigin instead anchors at navigation and can drift from
  // Date.now(). Validate with a contemporaneous pair, retaining the raw delta.
  // Durations still use event.timeStamp directly; never subtract this offset
  // from a latency result or widen its 50/200 ms budget.
  const mappedDeltaMs=clock.source+clock.wallEpoch-(clock.handlerAt+clock.wallSampleEnd)/2-sentEpoch;
  if(sampleMs<0 || sampleMs>1)return {valid:false,reason:'Input clock sample was not tightly bracketed',sampleMs,rawDeltaMs,mappedDeltaMs};
  const valid=Math.abs(mappedDeltaMs)<=2;
  return {valid,...(valid?{}:{reason:'Event timestamp does not match dispatched source time'}),sampleMs,rawDeltaMs,mappedDeltaMs};
}
