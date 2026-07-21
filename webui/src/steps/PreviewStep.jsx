import React, { useEffect, useRef, useState } from "react";
import { api, onEvent } from "../api.js";
import { Button, Card, Icon, Spinner, Thumb, Badge, ProgressBar, cx } from "../ui.jsx";
import { StepHeader, StepNav } from "./StepShell.jsx";

const KIND_STYLE = {
  person: { tone: "indigo", icon: "users" },
  group: { tone: "slate", icon: "image" },
  unrecognized: { tone: "amber", icon: "warning" },
  no_face: { tone: "slate", icon: "image" },
};

export default function PreviewStep({ config, preview, setPreview, goto }) {
  const [progress, setProgress] = useState({ stage: "prepare", done: 0, total: 0, current: null });
  const [running, setRunning] = useState(!preview);
  const [error, setError] = useState(null);
  const [openGroup, setOpenGroup] = useState(null);
  const started = useRef(false);

  useEffect(() => {
    const off = onEvent((e) => {
      if (e.event === "progress") setProgress(e);
    });
    return off;
  }, []);

  useEffect(() => {
    if (preview || started.current) return;
    started.current = true;
    setRunning(true);
    setError(null);
    api
      .preview(config)
      .then((r) => {
        if (r.ok) setPreview(r);
        else setError(r.error);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setRunning(false));
  }, [preview, config, setPreview]);

  const cancel = () => api.cancel();

  if (running) {
    const pct = progress.total ? (progress.done / progress.total) * 100 : 0;
    const stageLabel =
      progress.stage === "samples"
        ? "读取人物样本…"
        : progress.stage === "analyze"
        ? `识别照片 ${progress.done}/${progress.total}`
        : progress.stage === "scan"
        ? "扫描照片…"
        : "正在准备（首次需加载识别模型，请稍候）…";
    return (
      <div>
        <StepHeader title="预览分图" desc="正在分析照片，先算好会怎么分，之后你确认了才真正动文件。" />
        <Card className="p-8">
          <div className="mb-4 flex items-center gap-3 text-sm text-slate-600 dark:text-slate-300">
            <Spinner className="w-5 h-5 text-indigo-600" />
            {stageLabel}
          </div>
          <ProgressBar value={progress.stage === "analyze" ? pct : progress.stage === "prepare" ? 0 : 5} />
          {progress.current && progress.stage === "analyze" && (
            <div className="mt-3 truncate font-mono text-xs text-slate-400">{progress.current}</div>
          )}
          <div className="mt-6">
            <Button variant="outline" onClick={cancel}>
              <Icon name="x" className="w-4 h-4" /> 取消
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <StepHeader title="预览分图" />
        <Card className="p-6">
          <div className="flex items-start gap-3 text-red-600 dark:text-red-400">
            <Icon name="warning" className="mt-0.5 w-5 h-5 shrink-0" />
            <div>
              <div className="font-medium">无法预览</div>
              <div className="mt-1 text-sm">{error}</div>
            </div>
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
          自动分出 {preview.clusters} 个人物分组（人物1、人物2…）。整理完可在输出目录按需重命名文件夹；如果分得太细或把不同人并到一起，可返回上一步调整「分组精细度」。
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
        {[...people, ...others].map((g) => {
          const st = KIND_STYLE[g.kind];
          const isOpen = openGroup === g.key;
          const shown = isOpen ? g.items : g.items.slice(0, 8);
          return (
            <Card key={g.key} className="p-4">
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
                  <span className="font-semibold">{g.label}</span>
                  <Badge tone={st.tone}>{g.count} 张</Badge>
                </div>
                {g.items.length > 8 && (
                  <Button variant="ghost" onClick={() => setOpenGroup(isOpen ? null : g.key)}>
                    {isOpen ? "收起" : `查看全部 ${g.count} 张`}
                  </Button>
                )}
              </div>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-2">
                {shown.map((it) => (
                  <Thumb key={it.src} src={it.thumb} alt="" className="aspect-square" title={it.name} />
                ))}
                {!isOpen && g.items.length > 8 && (
                  <button
                    onClick={() => setOpenGroup(g.key)}
                    className="flex aspect-square items-center justify-center rounded-lg bg-slate-100 text-xs text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700"
                  >
                    +{g.items.length - 8}
                  </button>
                )}
              </div>
            </Card>
          );
        })}
      </div>

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
