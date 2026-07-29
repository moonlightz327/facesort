import React from "react";
import { Icon, ProgressBar, Spinner, cx } from "./ui.jsx";

const MB = (n) => `${(n / 1e6).toFixed(1)} MB`;

function duration(sec) {
  if (sec == null || !isFinite(sec) || sec < 0) return null;
  if (sec < 60) return `${Math.round(sec)} 秒`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return s ? `${m} 分 ${s} 秒` : `${m} 分`;
}

const PHASE_LABEL = {
  connect: "正在连接下载源",
  download: "正在下载识别模型",
  extract: "正在解压模型",
  copy: "正在安装内置模型",
  load: "正在加载识别模型",
};

/**
 * Detailed view of model provisioning: which mirror, how far along as a
 * percentage, transfer speed and ETA.
 *
 * The percentage is the headline number — a 289MB download over an unknown
 * connection is the one place users most need to know whether it is moving.
 */
export default function ModelProgress({ progress, onCancel, className }) {
  if (!progress) return null;
  const { phase, done, total, percent, bytesPerSec, etaSeconds, source,
          attempt, attempts, detail } = progress;

  const pct = percent != null ? percent : total ? (done / total) * 100 : 0;
  const downloading = phase === "download";
  const indeterminate = phase === "extract" || phase === "load" || phase === "copy";
  const eta = duration(etaSeconds);

  return (
    <div className={cx("rounded-xl bg-slate-50 p-4 dark:bg-slate-800/50", className)}>
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2 text-sm font-medium">
          <Spinner className="w-4 h-4 shrink-0 text-indigo-600" />
          <span className="truncate">{PHASE_LABEL[phase] || "正在准备"}</span>
        </div>
        {downloading && (
          <span className="shrink-0 text-lg font-semibold tabular-nums text-indigo-600 dark:text-indigo-400">
            {pct.toFixed(1)}%
          </span>
        )}
      </div>

      <ProgressBar
        value={indeterminate ? 100 : pct}
        className={indeterminate ? "animate-pulse" : ""}
      />

      <div className="mt-2 space-y-1 text-xs text-slate-500 dark:text-slate-400">
        {downloading && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 tabular-nums">
            <span>
              {MB(done)} / {MB(total)}
            </span>
            {bytesPerSec > 0 && <span>{MB(bytesPerSec)}/s</span>}
            {eta && <span>剩余约 {eta}</span>}
          </div>
        )}
        {detail && <div>{detail}</div>}
        {source && (
          <div className="flex items-center gap-1.5">
            <Icon name="folder" className="w-3.5 h-3.5 shrink-0" />
            <span className="truncate">
              下载源：{source}
              {attempts > 1 && `（第 ${attempt}/${attempts} 个）`}
            </span>
          </div>
        )}
        {indeterminate && <div>这一步没有进度条，通常十几秒内完成。</div>}
      </div>

      {onCancel && (
        <button
          onClick={onCancel}
          className="mt-3 text-xs text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
        >
          取消
        </button>
      )}
    </div>
  );
}
