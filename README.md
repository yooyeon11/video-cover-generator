# 视频封面批量生成器 · Video Cover Generator

给一批视频各生成一张 **1920×1080 的多格缩略图封面**，文件名与视频一致（扩展名换成 `.jpg`），直接保存在视频所在目录。适合媒体库、NAS、Jellyfin / Emby 之类的场景批量配图。

基于 `ffmpeg` 关键帧跳转取帧，一个 9 GB、2.5 小时的视频取 16 帧约 8 秒，不需要解码整片。

![layout](https://img.shields.io/badge/output-1920%C3%971080-blue) ![license](https://img.shields.io/badge/license-MIT-green) ![font](https://img.shields.io/badge/font-Noto%20Sans%20SC%20(OFL)-orange)

## 功能

- **三种输入方式**：把文件/文件夹拖进窗口、点「选视频」多选、或直接拖到 exe 图标上启动
- **自动去重**：文件夹和它里面的单个文件一起选中时不会重复处理
- **三种布局**：`4×4`（16 格，推荐）、`4×3`（12 格 + 信息条）、`3×4`（12 格）
- **水印可开关**：默认输出纯画面网格，不带任何文字；需要时勾选「在封面上叠加文件名/时长」
- **实时进度**：按取帧进度推进，单个大文件也能看到百分比变化
- **同名输出**：`视频名.mp4` → `视频名.jpg`，已存在则跳过，可勾选覆盖
- **命令行模式**：便于脚本化批处理

## 快速开始（用现成的 exe）

1. 从 [Releases](../../releases) 下载 `视频封面生成器.exe` 和 `fonts` 文件夹，放在同一目录。
2. 准备 `ffmpeg.exe` 与 `ffprobe.exe`（[Windows 构建下载](https://www.gyan.dev/ffmpeg/builds/)），放到以下任一位置：

   ```
   程序目录\ffmpeg\bin\ffmpeg.exe     ← 推荐
   程序目录\bin\ffmpeg.exe
   程序目录\ffmpeg.exe
   ```

   也可以加入 `PATH`，或设置环境变量 `FFMPEG_HOME` 指向其所在目录。
3. 双击 exe，拖入视频或文件夹，点「开始生成」。

> 仓库与 exe 均**不内置 ffmpeg**（两个可执行文件合计约 200 MB）。字体只在开启水印时才会用到，默认关闭水印时可以不带 `fonts` 文件夹。

## 从源码运行

需要 Windows + Python 3.9+（自带 tkinter）。

```bash
pip install -r requirements.txt
python 视频封面生成器.pyw
```

只依赖一个第三方库 `tkinterdnd2`（提供系统级拖放）；没装它也能运行，只是不能拖拽，仍可用按钮选择文件。

## 命令行

```bash
# 处理一个文件夹
python 视频封面生成器.pyw --cli "D:\视频目录"

# 混选多个文件夹和单个视频，指定布局、开启水印、覆盖已有封面
python 视频封面生成器.pyw --cli "D:\目录A" "E:\某个视频.mkv" 4x3 --label --overwrite
```

可选布局参数：`4x4`（默认）、`4x3`、`3x4`。
可选开关：`--label` 叠加文件名/时长，`--overwrite` 覆盖已存在的封面。

打包成 exe 后同样支持这些参数，日志会写到程序目录下的 `cli.log`。

## 布局规格

| 布局 | 帧数 | 单元格 | 成图 |
| --- | --- | --- | --- |
| `4x4` | 16 | 480×270 | 1920×1080 铺满，原生 16:9 零裁切 |
| `4x3` | 12 | 480×360（关闭水印时自动拉高） | 1920×1080 铺满 |
| `4x3` + 水印 | 12 | 480×270 | 1920×810 网格 + 270px 底部信息条 |
| `3x4` | 12 | 640×270 | 1920×1080，裁掉左右约 25% |

取帧位置按「每段中点」均分，覆盖片头、中段和片尾。格子之间为 1px 半透明白色分隔线。

## 自己打包 exe

双击 `build.bat`，或手动执行：

```bash
pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "视频封面生成器" --icon "绝对路径\app.ico" ^
  --collect-all tkinterdnd2 ^
  --distpath dist --workpath build --specpath build 视频封面生成器.pyw
```

打包后把 `fonts` 文件夹复制到 exe 同目录。仓库里的 GitHub Actions 工作流会在每次 push 时自动构建一份 Windows 产物（Actions → Build Windows exe）。

> 两个已踩过的坑：`--icon` 传相对路径会被解析到 `--specpath` 指定的目录而找不到文件，必须给绝对路径；`--windowed` 打包后 `sys.stdout` 为 `None`，代码里所有输出都要做空值保护。

## 字体与许可

- 项目代码：**MIT**，见 [LICENSE](LICENSE)。
- 封面文字使用 **Noto Sans SC / Noto Sans CJK SC Regular**，按 **SIL Open Font License 1.1** 授权，可自由分发，许可证全文见 [`fonts/OFL.txt`](fonts/OFL.txt)，来源 [notofonts/noto-cjk](https://github.com/notofonts/noto-cjk)。
- 不使用、也不随项目分发微软雅黑等系统字体。
