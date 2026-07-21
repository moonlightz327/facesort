import React, { useState } from "react";
import { api } from "../api.js";
import { Button, Card, Icon, Spinner, Thumb, Badge, cx } from "../ui.jsx";
import { StepHeader, StepNav } from "./StepShell.jsx";

export default function SamplesStep({ people, setPeople, config, setConfig, goto }) {
  const cluster = config.mode === "cluster";
  const [flags, setFlags] = useState({}); // sample path -> {ok, warning}

  return (
    <div>
      <StepHeader
        title="人物样本"
        desc="选择整理方式：用你提供的样本照识别指定的人，或让软件自动把长相相同的人分组。"
      />

      {/* Mode switch */}
      <div className="mb-5 grid grid-cols-2 gap-3">
        <ModeCard
          active={!cluster}
          onClick={() => setConfig((c) => ({ ...c, mode: "sample" }))}
          emoji="🧑‍🤝‍🧑"
          title="我有样本照片"
          desc="为每个人提供样本，照片归入对应人名的文件夹"
        />
        <ModeCard
          active={cluster}
          onClick={() => setConfig((c) => ({ ...c, mode: "cluster" }))}
          emoji="✨"
          title="自动分组（无样本）"
          desc="软件自动把同一个人聚到一起，命名为人物1/人物2…"
        />
      </div>

      {cluster ? (
        <Card className="flex flex-col items-center justify-center gap-3 py-14 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-100 text-indigo-500 dark:bg-indigo-950 dark:text-indigo-300">
            <Icon name="users" className="w-7 h-7" />
          </div>
          <p className="max-w-md text-sm text-slate-500 dark:text-slate-400">
            无样本模式不需要登记人物。下一步选好照片目录后，软件会自动把长相相同的人聚成
            「人物1 / 人物2…」文件夹，整理完你可以按需重命名。
          </p>
          <StepNav onNext={() => goto(1)} nextLabel="选择照片" />
        </Card>
      ) : (
        <SampleManager
          people={people}
          setPeople={setPeople}
          flags={flags}
          setFlags={setFlags}
          goto={goto}
        />
      )}
    </div>
  );
}

function ModeCard({ active, onClick, emoji, title, desc }) {
  return (
    <button
      onClick={onClick}
      className={cx(
        "rounded-2xl border p-4 text-left transition",
        active
          ? "border-indigo-500 bg-indigo-50 ring-2 ring-indigo-500/20 dark:bg-indigo-950/40"
          : "border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700"
      )}
    >
      <div className="mb-1.5 text-2xl">{emoji}</div>
      <div className={cx("text-sm font-semibold", active && "text-indigo-700 dark:text-indigo-300")}>
        {title}
      </div>
      <div className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">{desc}</div>
    </button>
  );
}

function SampleManager({ people, setPeople, flags, setFlags, goto }) {
  const [newName, setNewName] = useState("");
  const [adding, setAdding] = useState(false);
  const [busyPerson, setBusyPerson] = useState(null);

  const refresh = async () => setPeople(await api.listPeople());

  const addPerson = async () => {
    const name = newName.trim();
    if (!name) return;
    setAdding(true);
    const r = await api.addPerson(name);
    setAdding(false);
    if (r.ok) {
      setNewName("");
      await refresh();
    } else {
      alert(r.error);
    }
  };

  const addSamples = async (name) => {
    const paths = await api.pickSampleFiles();
    if (!paths || paths.length === 0) return;
    setBusyPerson(name);
    const r = await api.addSamples(name, paths);
    if (r.ok) {
      setFlags((f) => {
        const next = { ...f };
        for (const s of r.samples) next[s.path] = { ok: s.ok, warning: s.warning };
        return next;
      });
    }
    await refresh();
    setBusyPerson(null);
  };

  const removePerson = async (name) => {
    if (!confirm(`删除人物「${name}」及其样本？`)) return;
    await api.removePerson(name);
    await refresh();
  };

  const removeSample = async (path) => {
    await api.removeSample(path);
    await refresh();
  };

  const readyCount = people.filter((p) => p.samples?.length).length;

  return (
    <div>
      <Card className="mb-5 p-4">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addPerson()}
              placeholder="输入人物姓名，例如「张三」"
              className="w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-800"
            />
          </div>
          <Button onClick={addPerson} disabled={adding || !newName.trim()}>
            {adding ? <Spinner className="w-4 h-4" /> : <Icon name="plus" className="w-4 h-4" />}
            添加人物
          </Button>
        </div>
      </Card>

      {people.length === 0 ? (
        <Card className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-400 dark:bg-slate-800">
            <Icon name="users" className="w-7 h-7" />
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            还没有登记任何人物。先在上方添加一个人，再为 TA 添加样本照片。
          </p>
        </Card>
      ) : (
        <div className="space-y-4">
          {people.map((p) => (
            <Card key={p.name} className="p-4">
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <span className="text-base font-semibold">{p.name}</span>
                  {p.samples?.length ? (
                    <Badge tone="green">{p.samples.length} 张样本</Badge>
                  ) : (
                    <Badge tone="amber">缺少样本</Badge>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <Button variant="subtle" onClick={() => addSamples(p.name)} disabled={busyPerson === p.name}>
                    {busyPerson === p.name ? <Spinner className="w-4 h-4" /> : <Icon name="plus" className="w-4 h-4" />}
                    添加样本
                  </Button>
                  <Button variant="danger" onClick={() => removePerson(p.name)} className="px-2.5">
                    <Icon name="trash" className="w-4 h-4" />
                  </Button>
                </div>
              </div>

              {p.samples?.length ? (
                <div className="grid grid-cols-[repeat(auto-fill,minmax(84px,1fr))] gap-2.5">
                  {p.samples.map((s) => {
                    const flag = flags[s.path];
                    const bad = flag && flag.ok === false;
                    const warn = flag && flag.ok && flag.warning;
                    return (
                      <div key={s.path} className="group relative">
                        <Thumb
                          src={s.thumb}
                          alt=""
                          className={cx(
                            "aspect-square ring-2",
                            bad ? "ring-red-500" : warn ? "ring-amber-400" : "ring-transparent"
                          )}
                        />
                        {(bad || warn) && (
                          <div
                            className={cx(
                              "absolute inset-x-0 bottom-0 flex items-center gap-1 px-1 py-0.5 text-[10px] leading-tight text-white",
                              bad ? "bg-red-600/90" : "bg-amber-500/90"
                            )}
                            title={flag.warning}
                          >
                            <Icon name="warning" className="w-3 h-3 shrink-0" />
                            <span className="truncate">{bad ? "无人脸" : "多张脸"}</span>
                          </div>
                        )}
                        <button
                          onClick={() => removeSample(s.path)}
                          className="absolute right-1 top-1 hidden rounded-md bg-black/60 p-1 text-white group-hover:block hover:bg-black/80"
                          title="移除此样本"
                        >
                          <Icon name="x" className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="rounded-lg bg-slate-50 px-3 py-2.5 text-xs text-slate-400 dark:bg-slate-800/50">
                  点击「添加样本」选择这个人的照片。检测不到人脸的样本会被标记提醒。
                </p>
              )}
            </Card>
          ))}
        </div>
      )}

      <StepNav
        onNext={() => goto(1)}
        nextDisabled={readyCount < 1}
        right={
          readyCount < 1 && people.length > 0 ? (
            <span className="text-xs text-amber-600 dark:text-amber-400">至少需要一个人有样本照片</span>
          ) : null
        }
      />
    </div>
  );
}
