# FaceSort（分图）

按人物样本自动把拍摄的照片归入以**人名命名**的文件夹。你给每个人准备几张样本照，FaceSort 识别每张照片里的人是谁，复制/移动到对应人物的文件夹，支持自定义命名规则和多人合影处理。

> 开源、跨平台（macOS / Windows）。普通用户直接下载安装包即可用，命令行面向高级用户/自动化。规格见 `docs/SPEC.md`。

## 下载安装（普通用户）

从 [Releases](../../releases) 下载对应平台的安装包，双击即用，无需安装 Python 或任何依赖：

- **macOS**：`FaceSort.dmg` — 打开后把 FaceSort 拖进 Applications 即可。
- **Windows**：`FaceSort.exe` — 单文件，直接运行。

首次识别时会自动下载识别模型（约 300MB，到用户目录）。

> Releases 由 GitHub Actions 自动构建（见 `.github/workflows/build-release.yml`）：推一个 `v*` 标签就会同时打出 macOS DMG 和 Windows EXE 并发布到 Releases。

### 自己构建安装包

```bash
# macOS：产出 dist/FaceSort.app
./packaging/build_app.sh
# 再打成 DMG：产出 dist/FaceSort.dmg
./packaging/make_dmg.sh
```

Windows 上：`uv sync && (cd webui && npm ci && npm run build) && uv run pyinstaller packaging/FaceSort.spec --noconfirm`，产出 `dist/FaceSort.exe`。打包用 PyInstaller（`packaging/FaceSort.spec`，一份 spec 跨平台），已内含 onnxruntime / insightface / OpenCV / rawpy / pywebview 的运行时依赖与前端产物。

## 图形界面（推荐普通用户）

```bash
uv run facesort gui
```

打开一个原生 Mac 窗口，四步向导，全程无需命令行：

1. **人物样本** — 添加人物、选择样本照片，自动显示识别到的人脸，检测不到人脸的样本会红字提醒；样本会保存，下次打开仍在。
2. **整理设置** — 用系统对话框选照片目录/输出目录；多人合影策略用大白话卡片选择；识别严格度用「宽松—严格」滑杆；命名规则有预设 + 自定义 + 实时预览。
3. **预览确认** — 先按人物分好组给你看缩略图墙和各组张数，**这一步不动任何文件**，确认后才执行。
4. **开始整理** — 进度条 + 可取消；完成后显示各人张数、「在访达中打开」，并可对「拿不准像谁」的照片逐张改派。

界面自适应窗口大小，支持深/浅色。技术上是 React 前端 + pywebview 原生窗口，底层复用与命令行相同的引擎。

## 特性

- 🎯 基于样本比对识别人物（InsightFace buffalo_l：SCRFD 检测 + ArcFace 512 维嵌入）
- 📁 按人名建文件夹；命名规则可自定义（`{person}`/`{date}`/`{index}` 等变量）
- 👥 多人合影三种策略：归入主体 / 每人一份 / 单独放进合影
- 🛡️ 默认**复制不移动**，`--dry-run` 先看计划再动手，重名自动加序号**绝不覆盖**
- ⚡ SQLite 嵌入缓存：调阈值/换策略重跑无需重新识别，中断可续跑
- 🖼️ 支持 JPEG / PNG / HEIC / TIFF / WebP，以及相机 RAW（CR2/CR3/NEF/ARW/DNG 等）
- 📷 RAW+JPEG 同名成对时视作一张，一起归到同一文件夹（只识别 JPEG，RAW 搭便车）
- 📊 结束输出摘要 + `report.json`，含"拿不准像谁"的歧义列表供人工复核

## 安装

需要 [uv](https://docs.astral.sh/uv/)（`brew install uv`）。项目使用 Python 3.12。

```bash
cd 分图
uv sync                     # 创建环境并安装依赖
uv run facesort version     # 验证
```

首次运行会自动下载 buffalo_l 模型（约 300MB）到 `~/.insightface`。

## 样本目录规范

一个人一个子文件夹，**文件夹名即人名**，里面放 1 张以上清晰照片（建议正脸）：

```
samples/
├── 张三/
│   ├── 1.jpg
│   └── 2.jpg
└── 李四/
    └── a.jpg
```

同一人多张样本时，匹配取"与各张样本相似度的最大值"，抗坏样本。样本照里若有多张脸，取最大的那张并给出警告。

## 快速开始

```bash
# 1. 先干跑看看会怎么分（不动任何文件）
uv run facesort run --samples ./samples --input ./照片 --dry-run

# 2. 确认无误后正式整理（默认复制到 ./照片/_sorted/）
uv run facesort run --samples ./samples --input ./照片

# 3. 调试单张照片：看检测到几张脸、和各样本的相似度
uv run facesort inspect ./照片/IMG_1234.jpg --samples ./samples
```

## 命令行参数（`facesort run`）

| 参数 | 默认 | 说明 |
|---|---|---|
| `--samples` | 必填 | 样本库目录 |
| `--input` | 必填 | 待整理照片目录（递归） |
| `--output` | `<input>/_sorted` | 输出目录 |
| `--threshold` | `0.40` | 余弦相似度阈值，越高越严格 |
| `--multi-person` | `primary` | 多人策略：`primary`/`all`/`group` |
| `--folder-template` | `{person}` | 文件夹命名模板 |
| `--file-template` | `{orig_name}{ext}` | 文件命名模板 |
| `--move` | 关 | 移动而非复制 |
| `--dry-run` | 关 | 只打印计划，不动文件 |
| `--min-face` | `40` | 最小人脸边长(px)，过滤背景小脸 |
| `--weights` | `area=0.45,center=0.25,sim=0.30` | 主体评分权重 |
| `--group-subfolders` | 关 | 合影按 `张三+李四` 建子文件夹 |
| `--no-face-dir` / `--unknown-dir` / `--group-dir` | `_无人脸`/`_未识别`/`_合影` | 兜底文件夹名 |
| `--cache` | `<output>/.facesort_cache.sqlite` | 缓存路径 |
| `--plan-json` | 关 | dry-run 以 JSON 输出计划 |
| `-v/--verbose` | 关 | 打印每个执行动作 |

## 命名模板变量

在 `--folder-template` / `--file-template` 中使用：

| 变量 | 含义 |
|---|---|
| `{person}` | 人名（多人 primary 策略下为主体人名） |
| `{persons}` | 照片中所有匹配人名，`+` 连接 |
| `{date}` / `{datetime}` | 拍摄日期（EXIF，缺失回退文件修改时间） |
| `{orig_name}` / `{ext}` | 原文件名（不含扩展名）/ 扩展名 |
| `{index}` | 同文件夹内序号，支持格式化 `{index:03d}` |
| `{similarity}` | 匹配相似度 |

示例：

```bash
# 人名/日期_序号：  张三/2026-07-17_001.jpg
--folder-template "{person}" --file-template "{date}_{index:03d}{ext}"

# 按日期再按人：    2026-07-17/张三/原名.jpg
--folder-template "{date}/{person}"
```

人名中的 `/` 等非法路径字符会自动替换为 `_`。

## 多人合影策略

一张照片里有多个已登记的人时：

- **`primary`（默认）**：按主体评分选一个人归类。评分 = `0.45×人脸面积 + 0.25×居中度(高斯衰减) + 0.30×样本相似度`（权重可用 `--weights` 调）。**只在匹配到样本的人脸中选主体**——画面中央的路人不会赢过旁边匹配到的人。
- **`all`**：复制到每一个匹配到的人物文件夹（合影每人都留一份）。
- **`group`**：统一放进 `_合影/`，加 `--group-subfolders` 可按 `张三+李四` 建子文件夹。

## 无样本模式（自动聚类）

没有样本、或想让软件自己把同一个人的照片归到一起时，用聚类模式——它自动把长相相同的人分成「人物1/人物2…」文件夹，你事后按需重命名即可：

```bash
uv run facesort cluster --input ./照片 --dry-run     # 先看会分成几个人
uv run facesort cluster --input ./照片               # 复制到 ./照片/_clustered/
```

`--threshold` 越高分得越细（同一个人也可能被拆开），越低越容易把不同人并到一起。多人合影策略、命名模板、RAW 配对等与普通模式一致。

**在图形界面里**，无样本聚类完成后，结果页可以给每个「人物N」分组取个真实姓名并**一键存为样本**——之后切回「我有样本照片」模式就能直接按名字认出 TA，把聚类和样本两套流程打通。

## 归类去向一览

| 情况 | 去向 |
|---|---|
| 匹配到某人 | `<人名>/` |
| 检测不到人脸 | `_无人脸/` |
| 有人脸但都低于阈值 | `_未识别/` |
| 人脸小于 `--min-face` | 忽略该脸；全部忽略则视同无人脸 |
| 一张脸同时像两个人且差 < 0.05 | 取最高者，并记入 `report.json` 歧义列表 |

## 安全性

- 默认**复制**，原目录零改动；`--move` 才移动，跨磁盘卷用"复制+校验+删除"语义。
- `--dry-run` 只出计划不碰文件。
- 目标重名自动加 `-1/-2` 序号，**绝不覆盖**已有文件。
- copy 模式下重复运行幂等（借助缓存与已存在检测，不产生重复副本）。
- `Ctrl-C` 优雅停止，已完成部分保留，重跑续做。

## 开发与测试

```bash
uv run pytest              # 单元测试（matcher/organizer/templates/cache/scan，全部用假嵌入）
./scripts/smoke_test.sh    # 真实引擎冒烟测试（下载模型，跑 t1 合影图三种策略 + 缓存验证）
```

### 构建图形界面前端

前端源码在 `webui/`（React + Vite + Tailwind）。构建产物是一个自包含的 `facesort/gui/static/index.html`（JS/CSS 已内联），运行时不依赖 Node：

```bash
cd webui
npm install
npm run build     # vite build 后自动内联为单文件（见 scripts/inline_webui.py）
```

之后 `uv run facesort gui` 即可打开。修改前端后重新 `npm run build` 即可。

## 常见问题

**Q：为什么有些照片进了 `_未识别`？**
样本不够清晰或该人未登记。可先用 `facesort inspect <照片> --samples <样本目录>` 看相似度，必要时补充样本或适当降低 `--threshold`（如 0.35）。宁可进 `_未识别` 也不错归是刻意的保守设计。

**Q：调了参数想重跑，会很慢吗？**
不会。人脸识别结果缓存在 SQLite，重跑只做归类逻辑，秒级完成。

**Q：支持 RAW 吗？**
支持。CR2/CR3/NEF/ARW/DNG 等常见 RAW 会读取内嵌预览做识别（现代相机的内嵌预览通常是全尺寸，足够识别人脸）。若一张照片同时导出了 RAW 和 JPEG（同名），会视作一张一起归类，只识别 JPEG、RAW 跟随，省一半算力。Live Photo、视频仍在后续里程碑。

## 架构

`docs/SPEC.md` 有完整规格、验收标准与边界条件。核心模块：

```
facesort/core/
  engine.py      # insightface 封装（检测+嵌入），惰性加载
  matcher.py     # 样本匹配 + 主体评分（纯逻辑，可 mock 测试）
  organizer.py   # 计划生成 + 执行（copy/move/dry-run/冲突改名）
  templates.py   # 命名模板渲染
  cache.py       # SQLite 嵌入缓存
  cluster.py     # 无样本聚类（人物1..N，纯逻辑可 mock 测试）
  pipeline.py    # 端到端编排（进度回调 + 取消）
facesort/cli.py  # 命令行入口（run / cluster / inspect / gui / version）
facesort/gui/    # 图形界面
  app.py         # pywebview 原生窗口
  api.py         # JS↔Python 桥（复用 core，进度经 evaluate_js 推送前端）
  library.py     # 持久化人物样本库（~/Library/Application Support/FaceSort/people）
  thumbs.py      # 缩略图（base64 data URI，带缓存）
  static/        # 前端构建产物（单文件 index.html）
webui/           # 前端源码（React + Vite + Tailwind）
```

引擎与逻辑解耦：`matcher`/`organizer`/`templates`/`cache`/`cluster` 不依赖 insightface，全部用假嵌入单测。

## 许可证

[MIT](LICENSE)。识别能力基于 [InsightFace](https://github.com/deepinsight/insightface)（buffalo_l 模型），请遵循其各自的许可与使用条款。
