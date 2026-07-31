import React, { useEffect, useRef, useState } from "react";
import { api, onEvent } from "../api.js";
import { Button, Card, Icon, LazyThumb, Spinner, Badge, ProgressBar, cx } from "../ui.jsx";
import { StepHeader, StepNav } from "./StepShell.jsx";
import ModelSetup from "../ModelSetup.jsx";
import ModelProgress from "../ModelProgress.jsx";
import Lightbox from "../Lightbox.jsx";
import { stageLabel, stagePercent } from "../stages.js";

// How many tiles a group shows collapsed, and how many more each 「显示更多」
// adds. Groups run to thousands of photos on a real shoot, so the DOM is paged
// even when the group is expanded.
const COLLAPSED = 8;
const PAGE = 120;

const KIND_STYLE = {
  person: { tone: "indigo", icon: "users" },
  group: { tone: "slate", icon: "image" },
  unrecognized: { tone: "amber", icon: "warning" },
  no_face: { tone: "slate", icon: "image" },
};

export default function PreviewStep({ config, setConfig, preview, setPreview, goto,
                                     task, setTask, model, setModel }) {
  const [progress, setProgress] = useState({ stage: "prepare", done: 0, total: 0, current: null });
  const [modelProgress, setModelProgress] = useState(null);
  const [running, setRunning] = useState(!preview);
  const [error, setError] = useState(null);
  const [cancelled, setCancelled] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [modelIssue, setModelIssue] = useState(null); // model status when missing
  const [openGroup, setOpenGroup] = useState(null);
  // Which photo is open full-screen: {items, index}. Kept here rather than per
  // group so ←/→ can walk the whole group the tile came from.
  const [viewing, setViewing] = useState(null);
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
      // The model may still be downloading; show that instead of a blank
      // "preparing" state the user cannot interpret.
      if (e.event === "model") setModelProgress(e.phase === "done" ? null : e);
    });
    return off;
  }, []);

  const run = React.useCallback(() => {
    setRunning(true);
    setError(null);
    setCancelled(false);
    setCancelling(false);
    setModelIssue(null);
    setTask?.("preview");
    api
      .preview(config)
      .then((r) => {
        if (r.ok) {
          setPreview(r);
        } else if (r.cancelled) {
          setCancelled(true);
        } else {
          setError(r.error);
          if (r.modelMissing) setModelIssue(r.model);
        }
      })
      .catch((e) => setError(String(e)))
      .finally(() => {
        setRunning(false);
        setModelProgress(null);
        setTask?.(null);
      });
  }, [config, setPreview, setTask]);

  useEffect(() => {
    // `started` is a ref and resets on unmount, so also bail when a task is
    // already in flight — otherwise leaving to 设置 and coming back fires a
    // second preview that the Python side rejects as 「已有任务在进行中」.
    if (preview || started.current || task) return;
    started.current = true;
    run();
  }, [preview, run, task]);

  // Some phases cannot be interrupted mid-flight (building the onnx sessions is
  // a synchronous C++ call), so acknowledge the click immediately instead of
  // leaving the button looking dead.
  const cancel = () => {
    setCancelling(true);
    api.cancel();
  };

  if (running) {
    const label = stageLabel(progress);
    const pct = stagePercent(progress);
    return (
      <div>
        <StepHeader title="预览分图" desc="正在分析照片，先算好会怎么分，之后你确认了才真正动文件。" />
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
              {progress.current && progress.stage === "analyze" && (
                <div className="mt-3 truncate font-mono text-xs text-slate-400">
                  {progress.current}
                </div>
              )}
              <LiveTally tally={progress.tally} />
            </>
          )}
          <div className="mt-6">
            <Button variant="outline" onClick={cancel} disabled={cancelling}>
              <Icon name="x" className="w-4 h-4" />
              {cancelling ? "正在取消…" : modelProgress ? "取消下载" : "取消"}
            </Button>
            {cancelling && (
              <p className="mt-2 text-xs text-slate-400">
                已收到取消请求，正在结束当前照片后停止。
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
        <StepHeader title="预览分图" desc="已取消，没有任何文件被改动。" />
        <Card className="p-6">
          <div className="flex items-center gap-3 text-sm text-slate-600 dark:text-slate-300">
            <Icon name="x" className="w-5 h-5 shrink-0 text-slate-400" />
            预览已取消。可以重新预览，或返回上一步调整设置。
          </div>
          <div className="mt-4">
            <Button onClick={run}>
              <Icon name="refresh" className="w-4 h-4" /> 重新预览
            </Button>
          </div>
        </Card>
        <StepNav onBack={() => goto(1)} />
      </div>
    );
  }

  if (error) {
    // A missing model is a setup problem the user can fix right here, so it gets
    // the install panel instead of a raw ConnectTimeout dump.
    if (modelIssue) {
      return (
        <div>
          <StepHeader title="预览分图" desc="识别模型还没准备好，装好后即可继续。" />
          <ModelSetup
            model={modelIssue}
            onReady={(m) => {
              setModelIssue(null);
              setModel?.(m);
              run();
            }}
          />
          <StepNav onBack={() => goto(1)} />
        </div>
      );
    }
    return (
      <div>
        <StepHeader title="预览分图" />
        <Card className="p-6">
          <div className="flex items-start gap-3 text-red-600 dark:text-red-400">
            <Icon name="warning" className="mt-0.5 w-5 h-5 shrink-0" />
            <div>
              <div className="font-medium">无法预览</div>
              <div className="mt-1 whitespace-pre-wrap text-sm">{error}</div>
            </div>
          </div>
          <div className="mt-4">
            <Button variant="outline" onClick={run}>
              <Icon name="refresh" className="w-4 h-4" /> 重试
            </Button>
          </div>
        </Card>
        <StepNav onBack={() => goto(1)} />
      </div>
    );
  }

  if (!preview) return null;

  const people = preview.groups.filter((g) => g.kind === "person");
  const others = preview.groups.filter((g) => g.kind !== "person");
  const totalMatched = people.reduce((n, g) => n + g.count, 0);

  return (
    <div className="animate-fade">
      <StepHeader
        title="预览分图"
        desc="以下是即将的归类结果，现在还没有动任何文件。确认无误后再开始整理。"
      />

      {config.mode === "cluster" && preview.clusters != null && (
        <div className="mb-5 flex items-start gap-2 rounded-xl bg-indigo-50 px-4 py-3 text-sm text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
          <Icon name="users" className="mt-0.5 w-4 h-4 shrink-0" />
          <span>
            自动分出 {preview.clusters} 个人物分组。
            <b>可以直接在下面给每组取名</b>，整理时就会用这个名字建文件夹（留空则用 人物1、人物2…）。
            如果分得太细或把不同人并到一起，可返回上一步调整「分组精细度」。
          </span>
        </div>
      )}

      <div className="mb-5 grid grid-cols-4 gap-3">
        <Stat label="照片总数" value={preview.total} />
        <Stat label={config.mode === "cluster" ? "已分组" : "已归类到人"} value={totalMatched} tone="indigo" />
        <Stat label="未识别" value={sumKind(preview, "unrecognized")} tone="amber" />
        <Stat label="无人脸" value={sumKind(preview, "no_face")} />
      </div>

      {preview.multiPersonPhotos > 0 && (
        <div className="mb-5 flex items-start gap-2 rounded-xl bg-indigo-50 px-4 py-3 text-sm text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
          <Icon name="users" className="mt-0.5 w-4 h-4 shrink-0" />
          共有 {preview.multiPersonPhotos} 张多人合影，当前按「
          {config.multiPerson === "primary" ? "归入主要人物" : config.multiPerson === "all" ? "每人都存一份" : "单独放进合影"}
          」处理。想换方式可返回上一步，重跑很快（已有缓存）。
        </div>
      )}

      <div className="space-y-4">
        {[...people, ...others].map((g) => (
          <GroupCard
            key={g.key}
            group={g}
            isOpen={openGroup === g.key}
            onToggle={() => setOpenGroup(openGroup === g.key ? null : g.key)}
            onView={(index) => setViewing({ items: g.items, index })}
            nameEditor={
              config.mode === "cluster" && g.kind === "person" ? (
                <ClusterName
                  cluster={g.label}
                  value={config.clusterNames?.[g.label] || ""}
                  onChange={(name) =>
                    setConfig((c) => ({
                      ...c,
                      clusterNames: { ...(c.clusterNames || {}), [g.label]: name },
                    }))
                  }
                />
              ) : null
            }
          />
        ))}
      </div>

      {viewing && (
        <Lightbox
          items={viewing.items}
          index={viewing.index}
          onIndex={(index) => setViewing((v) => ({ ...v, index }))}
          onClose={() => setViewing(null)}
        />
      )}

      {preview.ambiguous?.length > 0 && (
        <div className="mt-4 flex items-start gap-2 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
          <Icon name="warning" className="mt-0.5 w-4 h-4 shrink-0" />
          有 {preview.ambiguous.length} 张照片「拿不准像谁」，整理完成后可在结果页逐张复核改派。
        </div>
      )}

      <StepNav
        onBack={() => goto(1)}
        onNext={() => goto(3)}
        nextLabel={config.move ? "开始整理（移动）" : "开始整理（复制）"}
      />
    </div>
  );
}

/**
 * Per-person counts as recognition runs. Photos are matched one at a time on
 * the way through, so there is no reason to make the user stare at a bare
 * progress bar until the very end to learn how the split is going.
 */
function LiveTally({ tally }) {
  if (!tally?.length) return null;
  return (
    <div className="mt-4 border-t border-slate-100 pt-3 dark:border-slate-800">
      <div className="mb-2 text-xs text-slate-400">已认出（还在继续）</div>
      <div className="flex flex-wrap gap-1.5">
        {tally.map(([name, n]) => (
          <span
            key={name}
            className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2.5 py-1 text-xs text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300"
          >
            {name}
            <b className="tabular-nums font-semibold">{n}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * One classification bucket. Collapsed it shows a strip of tiles; expanded it
 * pages through the group so a 3000-photo person does not put 3000 nodes in the
 * DOM. Any tile opens full-screen — at 96px you often cannot tell who is in a
 * shot, which is exactly the call this step asks the user to make.
 */
function GroupCard({ group: g, isOpen, onToggle, onView, nameEditor }) {
  const st = KIND_STYLE[g.kind];
  const [limit, setLimit] = useState(PAGE);

  useEffect(() => {
    if (!isOpen) setLimit(PAGE);
  }, [isOpen]);

  const shown = isOpen ? g.items.slice(0, limit) : g.items.slice(0, COLLAPSED);
  const hidden = g.items.length - shown.length;

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span
            className={cx(
              "flex h-8 w-8 items-center justify-center rounded-lg",
              g.kind === "person"
                ? "bg-indigo-100 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300"
                : g.kind === "unrecognized"
                ? "bg-amber-100 text-amber-600 dark:bg-amber-950 dark:text-amber-300"
                : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
            )}
          >
            <Icon name={st.icon} className="w-4 h-4" />
          </span>
          {nameEditor || <span className="font-semibold">{g.label}</span>}
          <Badge tone={st.tone}>{g.count} 张</Badge>
        </div>
        {g.items.length > COLLAPSED && (
          <Button variant="ghost" onClick={onToggle}>
            {isOpen ? "收起" : `查看全部 ${g.count} 张`}
          </Button>
        )}
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-2">
        {shown.map((it, i) => (
          <LazyThumb
            key={it.src}
            path={it.src}
            className="aspect-square"
            title={`${it.name}${it.reason ? `\n${it.reason}` : ""}`}
            onOpen={() => onView(i)}
          />
        ))}
        {hidden > 0 && (
          <button
            onClick={() => (isOpen ? setLimit((n) => n + PAGE) : onToggle())}
            className="flex aspect-square items-center justify-center rounded-lg bg-slate-100 text-xs text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700"
          >
            +{hidden}
          </button>
        )}
      </div>
      {isOpen && hidden > 0 && (
        <div className="mt-3 text-center">
          <Button variant="ghost" onClick={() => setLimit((n) => n + PAGE)}>
            再显示 {Math.min(hidden, PAGE)} 张（还有 {hidden} 张）
          </Button>
        </div>
      )}
    </Card>
  );
}

/**
 * Inline rename for an auto-detected cluster. Naming happens before anything is
 * written, so the folder is created as 「张三」 from the start rather than being
 * renamed off 人物1 afterwards.
 */
function ClusterName({ cluster, value, onChange }) {
  const [editing, setEditing] = useState(!!value);

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="group flex items-center gap-1.5 font-semibold hover:text-indigo-600 dark:hover:text-indigo-400"
        title="给这一组取个名字"
      >
        {cluster}
        <Icon name="pencil" className="w-3.5 h-3.5 text-slate-300 group-hover:text-indigo-500" />
      </button>
    );
  }
  return (
    <div className="flex items-center gap-1.5">
      <input
        autoFocus={!value}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => !value && setEditing(false)}
        placeholder={cluster}
        className="w-36 rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-sm font-semibold outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-800"
      />
      {value && <span className="text-xs text-slate-400">原 {cluster}</span>}
    </div>
  );
}

function sumKind(preview, kind) {
  return preview.groups.filter((g) => g.kind === kind).reduce((n, g) => n + g.count, 0);
}

function Stat({ label, value, tone = "slate" }) {
  const tones = {
    slate: "text-slate-900 dark:text-slate-100",
    indigo: "text-indigo-600 dark:text-indigo-400",
    amber: "text-amber-600 dark:text-amber-400",
  };
  return (
    <Card className="p-4">
      <div className="text-xs text-slate-400">{label}</div>
      <div className={cx("mt-1 text-2xl font-semibold tabular-nums", tones[tone])}>{value}</div>
    </Card>
  );
}
