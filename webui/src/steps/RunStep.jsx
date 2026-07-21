import React, { useEffect, useRef, useState } from "react";
import { api, onEvent } from "../api.js";
import { Button, Card, Icon, Spinner, Thumb, Badge, ProgressBar, cx } from "../ui.jsx";
import { StepHeader, StepNav } from "./StepShell.jsx";

export default function RunStep({ config, people, goto }) {
  const [progress, setProgress] = useState({ stage: "prepare", done: 0, total: 0 });
  const [running, setRunning] = useState(true);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const started = useRef(false);

  useEffect(() => {
    const off = onEvent((e) => e.event === "progress" && setProgress(e));
    return off;
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    api
      .organize(config)
      .then((r) => (r.ok ? setResult(r) : setError(r.error)))
      .catch((e) => setError(String(e)))
      .finally(() => setRunning(false));
  }, [config]);

  if (running) {
    const pct = progress.total ? (progress.done / progress.total) * 100 : 0;
    const label =
      progress.stage === "execute"
        ? `整理中 ${progress.done}/${progress.total}`
        : progress.stage === "analyze"
        ? `识别照片 ${progress.done}/${progress.total}`
        : "准备中…";
    return (
      <div>
        <StepHeader title="正在整理" desc="正在把照片归入对应文件夹，请稍候。" />
        <Card className="p-8">
          <div className="mb-4 flex items-center gap-3 text-sm text-slate-600 dark:text-slate-300">
            <Spinner className="w-5 h-5 text-indigo-600" />
            {label}
          </div>
          <ProgressBar value={pct} />
          {progress.current && (
            <div className="mt-3 truncate font-mono text-xs text-slate-400">{progress.current}</div>
          )}
          <div className="mt-6">
            <Button variant="outline" onClick={() => api.cancel()}>
              <Icon name="x" className="w-4 h-4" /> 取消（已完成的保留）
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <StepHeader title="整理未完成" />
        <Card className="p-6">
          <div className="flex items-start gap-3 text-red-600 dark:text-red-400">
            <Icon name="warning" className="mt-0.5 w-5 h-5 shrink-0" />
            <div className="text-sm">{error}</div>
          </div>
        </Card>
        <StepNav onBack={() => goto(2)} backLabel="返回预览" />
      </div>
    );
  }

  const report = result.report;
  const persons = Object.entries(report.persons || {});
  const exec = report.execution || {};

  return (
    <div className="animate-fade">
      <StepHeader
        title={result.cancelled ? "已取消（已完成部分保留）" : "整理完成 🎉"}
        desc={
          result.cancelled
            ? "你取消了整理，已经处理的照片保留在输出目录。"
            : "照片已按人物归好类。下面是本次结果。"
        }
      />

      <div className="mb-5 flex items-center justify-between rounded-xl bg-emerald-50 px-4 py-3 dark:bg-emerald-950/30">
        <div className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-300">
          <Icon name="check" className="w-4 h-4" />
          {config.move ? "已移动" : "已复制"} {(exec.copied || 0) + (exec.moved || 0)} 张
          {exec.skipped_existing ? ` · 跳过重复 ${exec.skipped_existing}` : ""}
          {exec.errors?.length ? ` · 出错 ${exec.errors.length}` : ""}
        </div>
        <Button variant="outline" onClick={() => api.openPath(result.outputDir)}>
          <Icon name="finder" className="w-4 h-4" /> 在访达中打开
        </Button>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {persons.map(([name, n]) => (
          <Card key={name} className="flex items-center justify-between p-3.5">
            <span className="truncate text-sm font-medium">{name}</span>
            <Badge tone="indigo">{n} 张</Badge>
          </Card>
        ))}
        <Card className="flex items-center justify-between p-3.5">
          <span className="text-sm text-slate-500">未识别</span>
          <Badge tone="amber">{report.unrecognized}</Badge>
        </Card>
        <Card className="flex items-center justify-between p-3.5">
          <span className="text-sm text-slate-500">无人脸</span>
          <Badge>{report.no_face}</Badge>
        </Card>
        {report.group > 0 && (
          <Card className="flex items-center justify-between p-3.5">
            <span className="text-sm text-slate-500">合影</span>
            <Badge>{report.group}</Badge>
          </Card>
        )}
      </div>

      {config.mode === "cluster" && persons.length > 0 && (
        <SaveClusters clusters={persons} outputDir={result.outputDir} />
      )}

      {result.ambiguous?.length > 0 && (
        <AmbiguousReview
          items={result.ambiguous}
          people={people}
          outputDir={result.outputDir}
        />
      )}

      <div className="mt-6 rounded-xl bg-slate-50 px-4 py-3 text-xs text-slate-400 dark:bg-slate-800/40">
        运行报告已保存到 <span className="font-mono">{result.outputDir}/report.json</span>
      </div>

      <StepNav
        onBack={() => goto(0)}
        backLabel="整理另一批"
        right={
          <Button variant="subtle" onClick={() => api.openPath(result.outputDir)}>
            <Icon name="folder" className="w-4 h-4" /> 打开输出目录
          </Button>
        }
      />
    </div>
  );
}

function AmbiguousReview({ items, people, outputDir }) {
  const [resolved, setResolved] = useState({});

  const assign = async (photo, person) => {
    const r = await api.reassign(photo, person, outputDir, false);
    if (r.ok) setResolved((s) => ({ ...s, [photo]: person }));
    else alert(r.error);
  };

  return (
    <Card className="mb-2 p-5">
      <div className="mb-1 flex items-center gap-2">
        <Icon name="warning" className="w-4 h-4 text-amber-500" />
        <h2 className="text-sm font-semibold">拿不准像谁的照片（{items.length}）</h2>
      </div>
      <p className="mb-4 text-xs text-slate-400">
        这些照片在两个人之间很接近。选一个人可把这张照片额外复制到 TA 的文件夹。
      </p>
      <div className="space-y-3">
        {items.map((a) => {
          const done = resolved[a.photo];
          const names = people.map((p) => p.name);
          const candidates = (a.candidates || []).filter(Boolean);
          return (
            <div key={a.photo} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-800">
              <Thumb src={a.thumb} alt="" className="h-16 w-16 shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs text-slate-400">{a.photo.split("/").pop()}</div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  {candidates.map((name) => (
                    <button
                      key={name}
                      onClick={() => assign(a.photo, name)}
                      className={cx(
                        "rounded-lg px-2.5 py-1 text-xs font-medium",
                        done === name
                          ? "bg-emerald-500 text-white"
                          : "bg-slate-100 text-slate-700 hover:bg-indigo-100 hover:text-indigo-700 dark:bg-slate-800 dark:text-slate-200"
                      )}
                    >
                      {name}
                      {name === a.person && <span className="ml-1 opacity-60">{a.similarity?.toFixed(2)}</span>}
                      {name === a.second_person && <span className="ml-1 opacity-60">{a.second_similarity?.toFixed(2)}</span>}
                    </button>
                  ))}
                </div>
              </div>
              {done && (
                <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                  <Icon name="check" className="w-4 h-4" /> 已归到 {done}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function SaveClusters({ clusters, outputDir }) {
  const [names, setNames] = useState(() =>
    Object.fromEntries(clusters.map(([c]) => [c, ""]))
  );
  const [saved, setSaved] = useState({}); // cluster -> saved name
  const [busy, setBusy] = useState(null);

  const save = async (cluster) => {
    const name = (names[cluster] || "").trim();
    if (!name) return;
    setBusy(cluster);
    const r = await api.saveClusterAsPerson(outputDir, cluster, name);
    setBusy(null);
    if (r.ok) setSaved((s) => ({ ...s, [cluster]: r.name }));
    else alert(r.error);
  };

  return (
    <Card className="mb-4 p-5">
      <div className="mb-1 flex items-center gap-2">
        <Icon name="users" className="w-4 h-4 text-indigo-500" />
        <h2 className="text-sm font-semibold">记住这些人（存为样本）</h2>
      </div>
      <p className="mb-4 text-xs text-slate-400">
        给自动分出的分组取个名字并保存，下次用「我有样本照片」模式就能直接按名字认出 TA。
      </p>
      <div className="space-y-2.5">
        {clusters.map(([cluster, n]) => {
          const done = saved[cluster];
          return (
            <div key={cluster} className="flex items-center gap-3">
              <span className="w-20 shrink-0 text-sm text-slate-500">
                {cluster} <span className="text-xs text-slate-400">·{n}</span>
              </span>
              {done ? (
                <span className="flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
                  <Icon name="check" className="w-4 h-4" /> 已存为「{done}」
                </span>
              ) : (
                <>
                  <input
                    value={names[cluster]}
                    onChange={(e) => setNames((s) => ({ ...s, [cluster]: e.target.value }))}
                    onKeyDown={(e) => e.key === "Enter" && save(cluster)}
                    placeholder="输入真实姓名，如「张三」"
                    className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-800"
                  />
                  <Button
                    variant="subtle"
                    onClick={() => save(cluster)}
                    disabled={busy === cluster || !names[cluster].trim()}
                  >
                    {busy === cluster ? <Spinner className="w-4 h-4" /> : "保存"}
                  </Button>
                </>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
