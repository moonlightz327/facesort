// Full-screen photo viewer.
//
// Grid thumbnails are 200px, which is enough to see that a photo exists and not
// nearly enough to tell whether the person in it is 张三 or 李四 — the one
// judgement the preview exists to support. Clicking any tile opens the shot
// large, with ←/→ to walk the group and a 1:1 zoom for the borderline calls.

import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { Icon, Spinner, cx } from "./ui.jsx";

/**
 * @param items  [{ src, name?, similarity?, persons?, reason? }]
 * @param index  position in `items` to show
 * @param onIndex(next) / onClose()
 */
export default function Lightbox({ items, index, onIndex, onClose }) {
  const item = items[index];
  const [image, setImage] = useState(null);
  const [error, setError] = useState(null);
  const [zoom, setZoom] = useState(false);
  const reqId = useRef(0);

  const go = useCallback(
    (delta) => {
      const next = index + delta;
      if (next >= 0 && next < items.length) onIndex(next);
    },
    [index, items.length, onIndex]
  );

  // Load the large decode for the current photo. A stale response from a photo
  // the user has already paged past must not overwrite the current one.
  useEffect(() => {
    if (!item) return;
    const id = ++reqId.current;
    setImage(null);
    setError(null);
    setZoom(false);
    api
      .imageData(item.src, 1600)
      .then((r) => {
        if (id !== reqId.current) return;
        if (r.ok) setImage(r.image);
        else setError(r.error || "无法读取这张照片");
      })
      .catch((e) => id === reqId.current && setError(String(e)));
  }, [item?.src]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") go(1);
      else if (e.key === "ArrowLeft") go(-1);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, onClose]);

  if (!item) return null;

  const sim = item.similarity;

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-slate-950/95 backdrop-blur-sm animate-fade"
      onClick={onClose}
    >
      {/* Top bar */}
      <div
        className="flex shrink-0 items-center gap-3 px-5 py-3 text-slate-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{item.name || baseName(item.src)}</div>
          <div className="truncate text-xs text-slate-400">
            {index + 1} / {items.length}
            {item.persons?.length ? ` · ${item.persons.join("、")}` : ""}
            {typeof sim === "number" ? ` · 相似度 ${sim.toFixed(2)}` : ""}
          </div>
        </div>
        <button
          onClick={() => api.openPath(item.src)}
          title="在访达中显示原文件"
          className="rounded-lg p-2 text-slate-300 hover:bg-white/10 hover:text-white"
        >
          <Icon name="finder" className="w-5 h-5" />
        </button>
        <button
          onClick={onClose}
          title="关闭（Esc）"
          className="rounded-lg p-2 text-slate-300 hover:bg-white/10 hover:text-white"
        >
          <Icon name="x" className="w-5 h-5" />
        </button>
      </div>

      {/* Stage */}
      <div className="relative flex min-h-0 flex-1 items-center justify-center px-4 pb-4">
        <NavButton side="left" disabled={index === 0} onClick={() => go(-1)} />
        <div
          className={cx(
            "flex h-full w-full items-center justify-center",
            zoom && "overflow-auto"
          )}
          onClick={(e) => e.stopPropagation()}
        >
          {error ? (
            <div className="flex items-center gap-2 text-sm text-red-300">
              <Icon name="warning" className="w-5 h-5" /> {error}
            </div>
          ) : image ? (
            <img
              src={image}
              alt=""
              onClick={() => setZoom((z) => !z)}
              title={zoom ? "点击缩小" : "点击放大"}
              className={cx(
                "rounded-lg shadow-2xl",
                zoom
                  ? "max-w-none cursor-zoom-out"
                  : "max-h-full max-w-full object-contain cursor-zoom-in"
              )}
            />
          ) : (
            <div className="flex items-center gap-3 text-sm text-slate-400">
              <Spinner className="w-5 h-5" /> 正在加载大图…
            </div>
          )}
        </div>
        <NavButton side="right" disabled={index === items.length - 1} onClick={() => go(1)} />
      </div>

      {item.reason && (
        <div
          className="shrink-0 px-5 pb-4 text-center text-xs text-slate-400"
          onClick={(e) => e.stopPropagation()}
        >
          {item.reason}
        </div>
      )}
    </div>
  );
}

function NavButton({ side, disabled, onClick }) {
  return (
    <button
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={cx(
        "absolute top-1/2 z-10 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white transition hover:bg-white/20",
        side === "left" ? "left-2" : "right-2",
        disabled && "pointer-events-none opacity-0"
      )}
    >
      <Icon name={side === "left" ? "arrowLeft" : "arrowRight"} className="w-5 h-5" />
    </button>
  );
}

function baseName(p) {
  return String(p).split("/").pop();
}
