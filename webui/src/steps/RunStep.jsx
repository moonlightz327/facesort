import React, { useEffect, useRef, useState } from "react";
import { api, onEvent } from "../api.js";
import { Button, Card, Icon, LazyThumb, Spinner, Badge, ProgressBar, cx } from "../ui.jsx";
import { StepHeader, StepNav } from "./StepShell.jsx";
import ModelProgress from "../ModelProgress.jsx";
import Lightbox from "../Lightbox.jsx";
import { stageLabel, stagePercent } from "../stages.js";

export default function RunStep({ config, people, setPeople, goto,
                                 runResult, setRunResult, task, setTask, startOver }) {
  const [progress, setProgress] = useState({ stage: "prepare", done: 0, total: 0 });
  const [modelProgress, setModelProgress] = useState(null);
  // A finished run lives in app state, so coming back to this step shows the
  // previous result instead of silently copying every photo a second time.
  const [running, setRunning] = useState(!runResult);
  const [error, setError] = useState(null);
  const [cancelled, setCancelled] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const result = runResult;
  const started = useRef(false);

  useEffect(() => {
    const off = onEvent((e) => {
      if (e.event === "progress") {
        setProgress(e);
        // Analysis has started, so the model is ready regardless of whether a
        // terminal model event arrived — never let the model panel cover the
        // 识别照片 X/N progress bar.
        setModelProgress(null);
      }
      if (e.event === "model") setModelProgress(e.phase === "done" ? null : e);
    });
    return off;
  }, []);

  useEffect(() => {
    // Same as PreviewStep: never re-issue on remount. For organize this is
    // the difference between showing progress again and copying every photo
    // a second time.
    if (started.current || runResult || task) return;
    started.current = true;
    setTask?.("organize");
    api
      .organize(config)
      .then((r) => {
        if (r.ok) setRunResult(r);
        else if (r.cancelled) setCancelled(true);
        else setError(r.error);
      })
      .catch((e) => setError(String(e)))
      .finally(() => {
        setRunning(false);
        setModelProgress(null);
        setTask?.(null);
      });
  }, [config, runResult, setRunResult, setTask, task]);

  if (running) {
    const label = stageLabel(progress, { executing: true });
    const pct = stagePercent(progress);
    return (
      <div>
        <StepHeader title="正在整理" desc="正在把照片归入对应文件夹，请稍候。" />
        <Card className="p-8">
          {modelProgress ? (
            <ModelProgress progress={modelProgress} />
          ) : (
            <>
              <div className="mb-4 flex items-center gap-3 text-sm text-slate-600 dark:text-slate-300">
                <Spinner className="w-5 h-5 text-indigo-600" />
                {label}
              </div>
              <ProgressBar value={pct} />
              {progress.current && (
                <div className="mt-3 truncate font-mono text-xs text-slate-400">
                  {progress.current}
                </div>
              )}
            </>
          )}
          <div className="mt-6">
            <Button
              variant="outline"
              onClick={() => {
                setCancelling(true);
                api.cancel();
              }}
              disabled={cancelling}
            >
              <Icon name="x" className="w-4 h-4" />
              {cancelling
                ? "正在取消…"
                : modelProgress
                ? "取消下载"
                : "取消（已完成的保留）"}
            </Button>
            {cancelling && (
              <p className="mt-2 text-xs text-slate-400">
                已收到取消请求，正在结束当前照片后停止；已整理好的照片会保留。
              </p>
            )}
          </div>
        </Card>
      </div>
    );
  }

  if (cancelled) {
    return (
      <div>
        <StepHeader title="已取消" desc="整理尚未开始，没有任何文件被改动。" />
        <Card className="p-6">
          <div className="flex items-center gap-3 text-sm text-slate-600 dark:text-slate-300">
            <Icon name="x" className="w-5 h-5 shrink-0 text-slate-400" />
            你取消了本次整理。
          </div>
        </Card>
        <StepNav onBack={() => goto(2)} backLabel="返回预览" />
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
  const isCluster = config.mode === "cluster";

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
          {/* APFS clones share storage with the original, so sorting a shoot
              does not need a second copy of it on disk. Worth saying: it is the
              difference between needing 200GB free and needing none. */}
          {exec.cloned > 0 && (
            <span className="text-emerald-600/80 dark:text-emerald-400/80">
              {" "}· 其中 {exec.cloned} 张为秒级克隆，未额外占用空间
            </span>
          )}
        </div>
        <Button variant="outline" onClick={() => api.openPath(result.outputDir)}>
          <Icon name="finder" className="w-4 h-4" /> 在访达中打开
        </Button>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {persons.map(([name, n]) => (
          <PersonTile
            key={name}
            name={name}
            count={n}
            outputDir={result.outputDir}
          />
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

      {isCluster && persons.length > 0 && (
        <SaveClusters
          clusters={persons}
          outputDir={result.outputDir}
          people={people}
          setPeople={setPeople}
        />
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

      <div className="mt-8 flex items-center justify-between border-t border-slate-200 pt-5 dark:border-slate-800">
        <Button variant="outline" onClick={startOver}>
          <Icon name="refresh" className="w-4 h-4" /> 整理另一批
        </Button>
        <Button variant="subtle" onClick={() => api.openPath(result.outputDir)}>
          <Icon name="folder" className="w-4 h-4" /> 打开输出目录
        </Button>
      </div>
    </div>
  );
}

function AmbiguousReview({ items, people, outputDir }) {
  const [resolved, setResolved] = useState({});
  const [viewing, setViewing] = useState(null);
  // The whole point of this list is deciding who someone is, so every row can
  // be opened full-screen and paged through with ←/→.
  const photos = items.map((a) => ({
    src: a.photo,
    persons: (a.candidates || []).filter(Boolean),
    similarity: a.similarity,
    reason: `${a.person} ${a.similarity?.toFixed(2)} vs ${a.second_person} ${a.second_similarity?.toFixed(2)}`,
  }));

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
        这些照片在两个人之间很接近。点缩略图可放大看清，选一个人可把这张照片额外复制到 TA 的文件夹。
      </p>
      <div className="space-y-3">
        {items.map((a, i) => {
          const done = resolved[a.photo];
          const names = people.map((p) => p.name);
          const candidates = (a.candidates || []).filter(Boolean);
          return (
            <div key={a.photo} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-800">
              <LazyThumb
                path={a.photo}
                className="h-16 w-16 shrink-0"
                onOpen={() => setViewing(i)}
              />
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
      {viewing != null && (
        <Lightbox
          items={photos}
          index={viewing}
          onIndex={setViewing}
          onClose={() => setViewing(null)}
        />
      )}
    </Card>
  );
}

/**
 * One result folder, renameable in place. Covers the plain "I want this folder
 * called something else" case for both modes — no sample library involved.
 */
function PersonTile({ name, count, outputDir }) {
  const [current, setCurrent] = useState(name);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  const [busy, setBusy] = useState(false);

  const commit = async () => {
    const next = draft.trim();
    if (!next || next === current) {
      setEditing(false);
      setDraft(current);
      return;
    }
    setBusy(true);
    const r = await api.renameGroup(outputDir, current, next);
    setBusy(false);
    if (r.ok) {
      setCurrent(r.name);
      setDraft(r.name);
      setEditing(false);
    } else {
      alert(r.error);
    }
  };

  return (
    <Card className="flex items-center justify-between gap-2 p-3.5">
      {editing ? (
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") {
              setDraft(current);
              setEditing(false);
            }
          }}
          className="min-w-0 flex-1 rounded-lg border border-indigo-400 bg-white px-2 py-1 text-sm outline-none dark:bg-slate-800"
        />
      ) : (
        <button
          onClick={() => setEditing(true)}
          className="group flex min-w-0 items-center gap-1.5"
          title="重命名这个文件夹"
        >
          <span className="truncate text-sm font-medium">{current}</span>
          <Icon
            name="pencil"
            className="w-3.5 h-3.5 shrink-0 text-slate-300 group-hover:text-indigo-500"
          />
        </button>
      )}
      {busy ? <Spinner className="w-4 h-4 text-indigo-500" /> : <Badge tone="indigo">{count} 张</Badge>}
    </Card>
  );
}

/**
 * Closes the loop between the sample-free mode and the sample library: name a
 * detected group, and its clearest faces are stored as reference samples (and
 * the output folder renamed to match) so the next shoot can be sorted by name.
 */
function SaveClusters({ clusters, outputDir, people, setPeople }) {
  const [names, setNames] = useState(() =>
    Object.fromEntries(clusters.map(([c]) => [c, ""]))
  );
  const [saved, setSaved] = useState({}); // cluster -> {name, saved, mergedInto}
  const [busy, setBusy] = useState(null);
  const existing = (people || []).map((p) => p.name);

  const save = async (cluster) => {
    const name = (names[cluster] || "").trim();
    if (!name) return;
    setBusy(cluster);
    const r = await api.saveClusterAsPerson(outputDir, cluster, name, 4, true);
    setBusy(null);
    if (!r.ok) {
      alert(r.error);
      return;
    }
    setSaved((s) => ({
      ...s,
      [cluster]: { name: r.name, saved: r.saved, mergedInto: r.mergedInto },
    }));
    // Push the refreshed library straight into app state — without this the new
    // person only showed up after a restart, so it never felt saved.
    if (r.people) setPeople(r.people);
  };

  const savedCount = Object.keys(saved).length;

  return (
    <Card className="mb-4 p-5">
      <div className="mb-1 flex items-center gap-2">
        <Icon name="users" className="w-4 h-4 text-indigo-500" />
        <h2 className="text-sm font-semibold">记住这些人（存为样本）</h2>
      </div>
      <p className="mb-4 text-xs leading-relaxed text-slate-400">
        给分组取个名字保存：软件会挑出这一组里最清晰的正脸存进人物库，并把输出文件夹一并改名。
        下次用「我有样本照片」模式，就能直接按名字认出 TA。填已有的人名则会并入那个人。
      </p>
      <div className="space-y-2.5">
        {clusters.map(([cluster, n]) => {
          const done = saved[cluster];
          return (
            <div key={cluster} className="flex items-center gap-3">
              <span className="w-24 shrink-0 truncate text-sm text-slate-500" title={cluster}>
                {cluster} <span className="text-xs text-slate-400">·{n}</span>
              </span>
              {done ? (
                <span className="flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
                  <Icon name="check" className="w-4 h-4" />
                  {done.mergedInto ? `已并入「${done.name}」` : `已存为「${done.name}」`}
                  <span className="text-xs text-slate-400">（{done.saved} 张样本）</span>
                </span>
              ) : (
                <>
                  <input
                    value={names[cluster]}
                    onChange={(e) => setNames((s) => ({ ...s, [cluster]: e.target.value }))}
                    onKeyDown={(e) => e.key === "Enter" && save(cluster)}
                    placeholder="输入真实姓名，如「张三」"
                    list="facesort-people"
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
      <datalist id="facesort-people">
        {existing.map((n) => (
          <option key={n} value={n} />
        ))}
      </datalist>
      {savedCount > 0 && (
        <div className="mt-4 flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2.5 text-xs text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300">
          <Icon name="check" className="w-4 h-4 shrink-0" />
          已保存 {savedCount} 个人物到人物库，下次可直接用「我有样本照片」模式识别。
        </div>
      )}
    </Card>
  );
}
