# FaceSort · 分图

**Sort your photos into folders by who's in them.**
给每个人几张样例照片，FaceSort 就能把成百上千张照片自动分到每个人的文件夹里。

**Language / 语言 —— [English](#english) · [中文](#中文)**

<sub>GitHub 不支持网页脚本，所以这里用锚点链接切换语言：点上面的 English / 中文 即可跳到对应版本。</sub>

---

<a id="english"></a>
## English

[English](#english) · [中文](#中文)

FaceSort looks at each photo, figures out who's in it, and copies it into a folder named after that person. Give it a few sample photos of each person once — it does the rest. No cloud, everything runs on your own Mac / PC.

### Download & install

Grab the installer for your system from the [**Releases**](../../releases) page:

| System | File | How |
|---|---|---|
| macOS | `FaceSort.dmg` | Open it, drag **FaceSort** into **Applications**. |
| Windows | `FaceSort.exe` | Just run it (single file). |

- **First launch may show a warning** because the app isn't signed with a paid developer certificate. On macOS: right‑click the app → **Open** → **Open**. On Windows: **More info** → **Run anyway**.
- The first time you sort photos, it downloads the face model once (~300 MB). After that it works offline.

### How to use

The app walks you through 4 steps:

1. **People** — Add each person and pick a few clear photos of them (front‑facing works best). Or, if you don't have samples, choose **"Auto‑group"** and skip this.
2. **Settings** — Pick the folder of photos to sort and where results go. Choose how group photos are handled and how folders are named (there are ready‑made presets).
3. **Preview** — See exactly how everything will be sorted, grouped by person, **before a single file moves**.
4. **Sort** — It copies photos into per‑person folders and shows a summary. You can review any photos it wasn't sure about.

**Group photos** (more than one person) — you pick what happens: put it with the **main person**, give **everyone a copy**, or keep it in a separate **"group"** folder.

**No sample photos?** Auto‑group finds people who look the same and sorts them into "Person 1 / Person 2…". You can then name each group and **save it**, so next time FaceSort recognizes them by name automatically.

**It's safe by default** — photos are **copied**, never moved (originals stay put); nothing is ever overwritten; and you always preview before anything happens.

### FAQ

- **Some photos went to "Unrecognized" — why?** The samples weren't clear enough, or that person isn't added. Add more/clearer samples, or lower the strictness slider a bit.
- **Does it support RAW?** Yes — CR2/CR3/NEF/ARW/DNG and more. If a shot has both a RAW and a JPEG, they're kept together.
- **Changing a setting and re‑sorting — is it slow?** No. Results are cached, so re‑runs are near‑instant.
- **Is my data uploaded anywhere?** No. Everything runs locally on your machine.

### For power users

There's also a command line (`facesort run` / `facesort cluster`) and a Python codebase. See [`docs/SPEC.md`](docs/SPEC.md) for details and [build instructions](#building-from-source).

<a id="building-from-source"></a>
<details>
<summary>Building from source</summary>

Requires [uv](https://docs.astral.sh/uv/) and Node.js.

```bash
uv sync
cd webui && npm ci && npm run build && cd ..
uv run facesort gui                      # run the app
./packaging/build_app.sh                 # macOS: build FaceSort.app
./packaging/make_dmg.sh                  # macOS: build FaceSort.dmg
```

Releases (macOS `.dmg` + Windows `.exe`) are built automatically by GitHub Actions when a `v*` tag is pushed.
</details>

### License

[MIT](LICENSE). Face recognition is powered by [InsightFace](https://github.com/deepinsight/insightface); please follow its terms.

---

<a id="中文"></a>
## 中文

[English](#english) · [中文](#中文)

FaceSort（分图）会看每一张照片、认出里面是谁，然后把它复制到以那个人名字命名的文件夹里。你只要给每个人准备几张样例照片，剩下的交给它。全程在你自己的电脑上运行，不上传云端。

### 下载安装

到 [**Releases**](../../releases) 页面下载对应系统的安装包：

| 系统 | 文件 | 怎么装 |
|---|---|---|
| macOS | `FaceSort.dmg` | 打开后把 **FaceSort** 拖进 **Applications**。 |
| Windows | `FaceSort.exe` | 单文件，直接双击运行。 |

- **首次打开可能弹安全提示**（因为没有购买开发者签名证书）。macOS：右键点应用 →**打开** →**打开**。Windows：点 **更多信息** → **仍要运行**。
- 第一次整理照片时会自动下载一次人脸模型（约 300MB），之后就能离线使用。

### 怎么用

界面会带着你走 4 步：

1. **人物** — 添加每个人，给 TA 选几张清晰的照片（正脸最好）。没有样例照片的话，直接选 **"自动分组"** 跳过这步。
2. **设置** — 选要整理的照片文件夹和输出位置；选合影怎么处理、文件夹怎么命名（有现成模板可选）。
3. **预览** — 在**任何文件被动之前**，先按人物分好组给你看清楚会怎么分。
4. **开始整理** — 把照片复制进各人的文件夹，给出汇总；拿不准像谁的照片可以逐张复核。

**合影**（照片里不止一个人）由你决定怎么放：归给**主要人物**、**每个人都存一份**、或单独放进**"合影"**文件夹。

**没有样例照片？** 自动分组会把长得一样的人聚到一起，分成"人物1 / 人物2…"。你可以给每组取个名字并**保存**，下次 FaceSort 就能直接按名字认出 TA。

**默认很安全** —— 照片是**复制**、不是移动（原图不动）；绝不覆盖已有文件；每次动手前都先给你预览。

### 常见问题

- **有些照片进了"未识别"是为什么？** 样例不够清晰，或那个人没添加。多加几张清晰样例，或把严格度滑杆调低一点。
- **支持 RAW 吗？** 支持，CR2/CR3/NEF/ARW/DNG 等都行。同一张照片如果同时有 RAW 和 JPEG，会放到一起。
- **改个设置重新整理会很慢吗？** 不会。结果有缓存，重跑几乎是秒出。
- **我的照片会被上传吗？** 不会，全部在你本机运行。

### 进阶用法

也有命令行（`facesort run` / `facesort cluster`）和完整 Python 代码。详见 [`docs/SPEC.md`](docs/SPEC.md) 和[从源码构建](#从源码构建)。

<a id="从源码构建"></a>
<details>
<summary>从源码构建</summary>

需要 [uv](https://docs.astral.sh/uv/) 和 Node.js。

```bash
uv sync
cd webui && npm ci && npm run build && cd ..
uv run facesort gui                      # 运行程序
./packaging/build_app.sh                 # macOS：构建 FaceSort.app
./packaging/make_dmg.sh                  # macOS：构建 FaceSort.dmg
```

Releases（macOS `.dmg` + Windows `.exe`）在推送 `v*` 标签时由 GitHub Actions 自动构建。
</details>

### 许可证

[MIT](LICENSE)。人脸识别基于 [InsightFace](https://github.com/deepinsight/insightface)，请遵循其使用条款。
