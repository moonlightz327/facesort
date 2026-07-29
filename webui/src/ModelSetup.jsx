import React, { useEffect, useState } from "react";
import { api, onEvent } from "./api.js";
import { Button, Card, Icon, Spinner, ProgressBar, cx } from "./ui.jsx";

/**
 * Recovery UI for a missing recognition model.
 *
 * The model is a ~289MB zip that insightface normally pulls straight from
 * github.com — unreachable on a lot of networks, which surfaced as a raw
 * ConnectTimeout. Here the user gets: retry across mirrors, pick a specific
 * mirror, or install a zip they downloaded themselves.
 */
export default function ModelSetup({ model, onReady, compact = false }) {
  const [progress, setProgress] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [source, setSource] = useState("");

  useEffect(() => {
    return onEvent((e) => {
      if (e.event !== "model") return;
      if (e.phase === "done") setProgress(null);
      else setProgress(e);
    });
  }, []);

  const sources = model?.sources || [];

  const download = async () => {
    setBusy(true);
    setError(null);
    setProgress({ phase: "download", done: 0, total: 0, detail: "正在连接…" });
    const r = await api.downloadModel(source || null);
    setBusy(false);
    setProgress(null);
    if (r.ok) onReady?.(r.model);
    else setError(r.error);
  };

  const importZip = async () => {
    const path = await api.pickModelZip();
    if (!path) return;
    setBusy(true);
    setError(null);
    const r = await api.installModelZip(path);
    setBusy(false);
    setProgress(null);
    if (r.ok) onReady?.(r.model);
    else setError(r.error);
  };

  const pct = progress?.total ? (progress.done / progress.total) * 100 : 0;
  const mb = (n) => `${(n / 1e6).toFixed(0)}MB`;

  return (
    <Card className={compact ? "p-4" : "p-6"}>
      <div className="mb-1 flex items-center gap-2">
        <Icon name="warning" className="w-4 h-4 text-amber-500" />
        <h2 className="text-sm font-semibold">需要先安装人脸识别模型</h2>
      </div>
      <p className="mb-4 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        首次使用需要下载识别模型（约 {model?.sizeMB || 289}MB，只需一次）。
        默认下载源在国内常常连不上，下面已内置多个加速镜像；如果全部失败，可以自己下载
        <span className="mx-1 font-mono">buffalo_l.zip</span>后手动导入。
      </p>

      {busy && progress ? (
        <div className="mb-4">
          <div className="mb-2 flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
            <Spinner className="w-4 h-4 text-indigo-600" />
            {progress.phase === "download"
              ? progress.total
                ? `正在从${progress.source || "镜像"}下载 ${mb(progress.done)} / ${mb(progress.total)}`
                : progress.detail || "正在连接…"
              : progress.detail || "正在安装…"}
          </div>
          <ProgressBar value={progress.phase === "download" ? pct : 100} />
          <button
            onClick={() => api.cancelModelDownload()}
            className="mt-3 text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
          >
            取消下载
          </button>
        </div>
      ) : (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Button onClick={download} disabled={busy}>
            <Icon name="check" className="w-4 h-4" /> 自动下载模型
          </Button>
          <Button variant="outline" onClick={importZip} disabled={busy}>
            <Icon name="folder" className="w-4 h-4" /> 手动导入 zip
          </Button>
          {sources.length > 1 && (
            <select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs outline-none focus:border-indigo-500 dark:border-slate-700 dark:bg-slate-800"
            >
              <option value="">自动（依次尝试全部镜像）</option>
              {sources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {error && (
        <div className="mb-3 whitespace-pre-wrap rounded-lg bg-red-50 px-3 py-2.5 text-xs leading-relaxed text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      )}

      <details className="text-xs text-slate-400">
        <summary className="cursor-pointer select-none hover:text-slate-600 dark:hover:text-slate-200">
          手动导入怎么做？
        </summary>
        <div className="mt-2 space-y-1 leading-relaxed">
          <p>
            1. 在能上网的机器上下载 buffalo_l.zip（约 289MB），例如从 GitHub 的
            insightface v0.7 发布页。
          </p>
          <p>2. 把 zip 拷到本机，点上面的「手动导入 zip」选中它即可。</p>
          <p className="text-slate-400">
            模型会安装到 <span className="font-mono">{model?.modelDir}</span>
          </p>
        </div>
      </details>
    </Card>
  );
}
