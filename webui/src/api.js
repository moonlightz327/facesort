// Thin wrapper over the pywebview Python bridge (window.pywebview.api).
// Also provides a progress event bus fed by Python via window.__facesort_event.

const listeners = new Set();

window.__facesort_event = (evt) => {
  listeners.forEach((fn) => {
    try {
      fn(evt);
    } catch (e) {
      /* ignore listener errors */
    }
  });
};

export function onEvent(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

// The `window.pywebview.api` object appears BEFORE the bridge can actually accept
// calls; the reliable readiness signal is the `pywebviewready` event. We attach a
// listener at module-load time (runs before the event fires) so we never miss it,
// then gate every call on it — calling too early otherwise hangs.
let _ready = false;
window.addEventListener("pywebviewready", () => {
  _ready = true;
});

let readyPromise = null;
export function whenReady() {
  if (readyPromise) return readyPromise;
  readyPromise = new Promise((resolve) => {
    if (_ready) return resolve();
    window.addEventListener("pywebviewready", () => resolve(), { once: true });
    // Belt-and-suspenders: resolve once the flag flips, in case the event fired
    // between module load and this promise being created.
    const t = setInterval(() => {
      if (_ready) {
        clearInterval(t);
        resolve();
      }
    }, 50);
  });
  return readyPromise;
}

async function call(name, ...args) {
  await whenReady();
  return window.pywebview.api[name](...args);
}

export const api = {
  bootstrap: () => call("bootstrap"),
  warmUp: () => call("warm_up"),
  listPeople: () => call("list_people"),
  addPerson: (name) => call("add_person", name),
  removePerson: (name) => call("remove_person", name),
  removeSample: (path) => call("remove_sample", path),
  pickSampleFiles: () => call("pick_sample_files"),
  addSamples: (name, paths) => call("add_samples", name, paths),
  pickFolder: (title) => call("pick_folder", title),
  previewName: (folder, file) => call("preview_name", folder, file),
  preview: (cfg) => call("preview", cfg),
  organize: (cfg) => call("organize", cfg),
  cancel: () => call("cancel"),
  reassign: (src, person, outputDir, move) =>
    call("reassign", src, person, outputDir, move),
  saveClusterAsPerson: (outputDir, clusterName, newName) =>
    call("save_cluster_as_person", outputDir, clusterName, newName),
  openPath: (path) => call("open_path", path),
};
