// On-demand thumbnail loading.
//
// The Python side no longer ships a thumbnail per plan item — a 5000-photo
// shoot meant decoding 5000 originals before the preview could render, which is
// most of what 「正在生成分图方案」 used to be waiting on. Instead the page asks
// for the thumbnails it is actually about to draw, and this module coalesces
// those asks into batched bridge calls so scrolling a big group is a handful of
// round-trips rather than one per tile.

import React from "react";
import { api } from "./api.js";

const cache = new Map(); // "size:path" -> dataUri | null (null = unreadable)
const waiting = new Map(); // "size:path" -> [resolve]
let queue = [];
let timer = null;

const BATCH = 60; // matches the backend's per-call cap comfortably
const DEBOUNCE = 30; // ms; long enough to collect a screenful of tiles

const keyOf = (path, size) => `${size}:${path}`;

async function flush() {
  timer = null;
  const batch = queue.slice(0, BATCH);
  queue = queue.slice(BATCH);
  if (queue.length && !timer) timer = setTimeout(flush, 0);
  if (!batch.length) return;

  const size = batch[0].size;
  const paths = batch.filter((b) => b.size === size).map((b) => b.path);
  // Mixed sizes in one tick are rare; anything left over goes round again.
  const deferred = batch.filter((b) => b.size !== size);
  if (deferred.length) {
    queue = deferred.concat(queue);
    if (!timer) timer = setTimeout(flush, 0);
  }

  let map = {};
  try {
    const r = await api.thumbs(paths, size);
    map = (r && r.thumbs) || {};
  } catch {
    map = {};
  }
  for (const path of paths) {
    const k = keyOf(path, size);
    const uri = map[path] ?? null;
    cache.set(k, uri);
    (waiting.get(k) || []).forEach((fn) => fn(uri));
    waiting.delete(k);
  }
}

/** Resolve a thumbnail, from cache or a batched bridge call. */
export function loadThumb(path, size = 200) {
  const k = keyOf(path, size);
  if (cache.has(k)) return Promise.resolve(cache.get(k));
  return new Promise((resolve) => {
    const list = waiting.get(k);
    if (list) {
      list.push(resolve);
      return; // already queued by another tile
    }
    waiting.set(k, [resolve]);
    queue.push({ path, size });
    if (!timer) timer = setTimeout(flush, DEBOUNCE);
  });
}

export function cachedThumb(path, size = 200) {
  return cache.get(keyOf(path, size));
}

/**
 * Thumbnail for one photo, fetched only once the tile is near the viewport.
 * Returns [src, ref] — put the ref on the element you want observed.
 */
export function useLazyThumb(path, size = 200) {
  const [src, setSrc] = React.useState(() => cachedThumb(path, size));
  const [visible, setVisible] = React.useState(() => cachedThumb(path, size) !== undefined);
  const ref = React.useRef(null);

  React.useEffect(() => {
    setSrc(cachedThumb(path, size));
  }, [path, size]);

  React.useEffect(() => {
    if (visible || !ref.current) return;
    const el = ref.current;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          io.disconnect();
        }
      },
      // Start a screen early so tiles are filled in by the time they arrive.
      { rootMargin: "400px" }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [visible, path]);

  React.useEffect(() => {
    if (!visible) return;
    let live = true;
    loadThumb(path, size).then((uri) => live && setSrc(uri));
    return () => {
      live = false;
    };
  }, [visible, path, size]);

  return [src, ref];
}
