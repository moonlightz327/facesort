import React, { useEffect, useState } from "react";
import { api, onEvent } from "./api.js";
import { Button, Card, Icon, Badge } from "./ui.jsx";
import ModelProgress from "./ModelProgress.jsx";

/**
 * Install / manage the recognition model.
 *
 * The model is a ~289MB zip that insightface normally pulls straight from
 * github.com — unreachable on a lot of networks, which used to surface as a raw
 * ConnectTimeout. Here the user gets: retry across mirrors, pick a specific
 * mirror, or install a zip they downloaded themselves — and can do all of it
 * ahead of time from 设置 rather than discovering it mid-sort.
 */
export default function ModelSetup({ model, onReady, compact = false, manage = false }) {
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
  const installed = !!model?.installed;

  const download = async () => {
    setBusy(true);
    setError(null);
    setProgress({ phase: "connect", done: 0, total: 0, detail: "正在连接…" });
    const r = await api.downloadModel(source || null);
    setBusy(false);
    setProgress(null);
    if (r.ok) onReady?.(r.model);
    else if (!r.cancelled) setError(r.error);
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

  return (
    <Card className={compact ? "p-4" : "p-6"}>
      <div className="mb-1 flex items-center gap-2">
        {installed ? (
          <>
            <Icon name="check" className="w-4 h-4 text-emerald-500" />
            <h2 className="text-sm font-semibold">人脸识别模型</h2>
            <Badge tone="green">已安装</Badge>
          </>
        ) : (
          <>
            <Icon name="warning" className="w-4 h-4 text-amber-500" />
            <h2 className="text-sm font-semibold">需要先安装人脸识别模型</h2>
            <Badge tone="amber">未安装</Badge>
          </>
        )}
      </div>

      <p className="mb-4 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        {installed ? (
          <>模型已就绪，整理照片时无需联网。如果怀疑文件损坏，可以重新下载或重新导入。</>
        ) : (
          <>
            识别功能需要一个约 {model?.sizeMB || 289}MB 的模型（只需装一次）。
            默认下载源在国内常常连不上，已内置多个加速镜像会自动逐个尝试；万一都失败，
            可以自己下载
            <span className="mx-1 font-mono">buffalo_l.zip</span>后手动导入。{" "}
            <b className="text-slate-600 dark:text-slate-300">
              建议现在就装好，免得整理照片时才开始等下载。
            </b>
          </>
        )}
      </p>

      {busy && progress ? (
        <ModelProgress
          progress={progress}
          onCancel={() => api.cancelModelDownload()}
          className="mb-4"
        />
      ) : (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Button onClick={download} disabled={busy} variant={installed ? "outline" : "primary"}>
            <Icon name={installed ? "refresh" : "check"} className="w-4 h-4" />
            {installed ? "重新下载" : "自动下载模型"}
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

      {(manage || !installed) && (
        <details className="text-xs text-slate-400">
          <summary className="cursor-pointer select-none hover:text-slate-600 dark:hover:text-slate-200">
            手动导入怎么做？
          </summary>
          <div className="mt-2 space-y-1 leading-relaxed">
            <p>1. 在能上网的机器上下载 buffalo_l.zip（约 289MB），例如从 GitHub 的 insightface v0.7 发布页。</p>
            <p>2. 把 zip 拷到本机，点上面的「手动导入 zip」选中它即可。</p>
            <p className="break-all">
              安装位置：<span className="font-mono">{model?.modelDir}</span>
            </p>
          </div>
        </details>
      )}
    </Card>
  );
}
