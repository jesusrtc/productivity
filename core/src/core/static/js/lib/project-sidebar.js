// Large project views load directory children on demand. The server persists
// small Git projections; this browser cache retains at most 2 MB of responses.
const ProjectSidebar = (() => {
  const cache = new Map(), pending = new Map();
  let bytes = 0;
  function remember(url, data) {
    const size = JSON.stringify(data).length * 2;
    if (cache.has(url)) bytes -= cache.get(url).size;
    cache.delete(url);
    if (size > 2 * 1024 * 1024) return;
    cache.set(url, {data, size, at: Date.now()}); bytes += size;
    while (bytes > 2 * 1024 * 1024 || cache.size > 64) {
      const key = cache.keys().next().value;
      bytes -= cache.get(key).size; cache.delete(key);
    }
  }
  async function fetchData(url) {
    if (pending.has(url)) return pending.get(url);
    const promise = (async () => {
      const response = await fetch(url);
      const data = await response.json();
      if (response.status === 202) return data;
      if (!response.ok) throw new Error(data.detail || 'Could not load project');
      remember(url, data);
      return data;
    })().finally(() => pending.delete(url));
    pending.set(url, promise);
    return promise;
  }
  function read(url, update, current) {
    if (!current()) return;
    const hit = cache.get(url);
    if (hit) update(hit.data);
    const updated = hit?.data.cache?.updated ? hit.data.cache.updated * 1000 : hit?.at;
    if (hit && Date.now() - Math.min(hit.at, updated) < 60000 && !hit.data.cache?.refreshing && !hit.data.cache?.stale) return;
    const refresh = async () => {
      if (!current() || document.hidden) return;
      try {
        const data = await fetchData(url);
        if (!current()) return;
        update(data);
        if (data.cache?.refreshing || data.cache?.stale) setTimeout(refresh, data.cache?.error ? 5000 : data.entries ? 200 : 75);
      } catch (error) {
        if (current()) update({error: error.message});
      }
    };
    void refresh();
  }
  function clear() { cache.clear(); bytes = 0; }
  return {read, clear};
})();
