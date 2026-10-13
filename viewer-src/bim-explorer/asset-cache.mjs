/** Immutable model assets only. Never use this cache for live telemetry. */
export async function verifiedAsset(path, sha256, {fetchBuffer, verify, cacheStorage = globalThis.caches, origin = globalThis.location?.origin, onRead = () => {}}) {
  let cache, key, cacheIssue;
  if (cacheStorage && origin && /^[a-f0-9]{64}$/i.test(sha256)) {
    key = `${origin}/__verified_bim_assets__/${sha256.toLowerCase()}`;
    try { cache = await cacheStorage.open('grimes-verified-geometry-v1'); } catch { /* Private mode/storage denied: network still works. */ }
  }
  if (cache) {
    try {
      const response = await cache.match(key);
      if (response) {
        const buffer = await response.arrayBuffer();
        await verify(buffer, sha256);
        onRead({path, bytes: buffer.byteLength, source: 'verified-cache'});
        return buffer;
      }
    } catch (error) { cacheIssue=error.message; try { await cache.delete(key); } catch { /* Best effort only. */ } }
  }
  const buffer = await fetchBuffer(path);
  await verify(buffer, sha256);
  if (cache) {
    try { await cache.put(key, new Response(buffer, {headers: {'Content-Type': 'application/octet-stream'}})); } catch (error) { cacheIssue=error.message; /* Quota errors must not prevent opening a model. */ }
  }
  onRead({path, bytes: buffer.byteLength, source: 'network', ...(cacheIssue?{cacheIssue}:{})});
  return buffer;
}
