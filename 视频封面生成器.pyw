# -*- coding: utf-8 -*-
"""
视频封面批量生成器
给每个视频生成一张 1920x1080 的多格缩略图，文件名与视频一致（扩展名换成 .jpg）。

用法:
  双击运行            -> 图形界面
  拖文件夹到 exe/bat  -> 自动填入路径
  命令行              -> python 视频封面生成器.pyw --cli "<视频目录>" [4x4|4x3|3x4]
"""

import os
import sys
import subprocess
import threading
import queue
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except Exception:
    TkinterDnD = None
    DND_FILES = None
    HAS_DND = False

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))


def _pick_run_dir():
    """优先在程序目录建临时工作区；不可写时退到系统临时目录。"""
    try:
        os.makedirs(os.path.join(APP_DIR, ".work"), exist_ok=True)
        probe = os.path.join(APP_DIR, ".work", ".w")
        with open(probe, "w") as f:
            f.write("1")
        os.remove(probe)
        return APP_DIR
    except Exception:
        import tempfile
        return tempfile.mkdtemp(prefix="vcovers_")


RUN_DIR = _pick_run_dir()
WORK_DIR = os.path.join(RUN_DIR, ".work")
# 封面文字使用仓库自带的 Noto Sans SC（SIL Open Font License 1.1），可自由分发。
FONT_NAME = "NotoSansSC-Regular.otf"
FONT_DIR = os.path.join(RUN_DIR, "fonts")
FONT_FILE = os.path.join(FONT_DIR, FONT_NAME)

VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".ts", ".mov", ".wmv", ".flv", ".m4v")

LAYOUTS = {
    "4x4": dict(cols=4, rows=4, cw=480, ch=270, bar=False, subdir="",     suffix="",     label="4×4  16格（推荐，原生16:9无裁切）"),
    "4x3": dict(cols=4, rows=3, cw=480, ch=270, bar=True,  subdir="封面_4x3", suffix="_4x3", label="4×3  12格 + 底部信息条"),
    "3x4": dict(cols=3, rows=4, cw=640, ch=270, bar=False, subdir="封面_3x4", suffix="_3x4", label="3×4  12格（需裁切左右约25%）"),
}

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _out(msg):
    """打包成 --windowed 的 exe 后 sys.stdout 可能是 None，这里做保护。"""
    try:
        if sys.stdout is not None:
            sys.stdout.write(str(msg) + "\n")
            sys.stdout.flush()
    except Exception:
        pass


# ---------------------------------------------------------------- ffmpeg 定位
def find_tool(name):
    """按优先级查找 ffmpeg/ffprobe，全部返回绝对路径。"""
    exe = name + (".exe" if os.name == "nt" else "")
    cands = [
        os.path.join(APP_DIR, exe),
        os.path.join(APP_DIR, "bin", exe),
        os.path.join(APP_DIR, "ffmpeg", "bin", exe),
    ]
    env_home = os.environ.get("FFMPEG_HOME")
    if env_home:
        cands.insert(0, os.path.join(env_home, exe))
        cands.insert(0, os.path.join(env_home, "bin", exe))
    for c in cands:
        if os.path.isfile(c):
            return c
    return shutil.which(name)


FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")


# ---------------------------------------------------------------- 核心处理
def probe_duration(path):
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW,
            encoding="utf-8", errors="ignore",
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def fmt_dur(sec):
    sec = int(sec)
    return "%d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)


def prep_font():
    """把随程序附带的开源字体放到工作目录，供 drawtext 用相对路径引用。

    ffmpeg 滤镜参数里的路径不能带盘符冒号（会被当成参数分隔符），
    因此字体必须位于 cwd 之下的相对位置。
    """
    src = os.path.join(APP_DIR, "fonts", FONT_NAME)
    if os.path.isfile(src) and os.path.getsize(src) > 1000000:
        if os.path.abspath(src) == os.path.abspath(FONT_FILE):
            return True
        os.makedirs(FONT_DIR, exist_ok=True)
        if not (os.path.isfile(FONT_FILE) and
                os.path.getsize(FONT_FILE) == os.path.getsize(src)):
            try:
                shutil.copy2(src, FONT_FILE)
            except Exception:
                return False
        return True
    return os.path.isfile(FONT_FILE) and os.path.getsize(FONT_FILE) > 1000000


def list_videos(folder):
    out = []
    try:
        for n in sorted(os.listdir(folder)):
            p = os.path.join(folder, n)
            if os.path.isfile(p) and os.path.splitext(n)[1].lower() in VIDEO_EXTS:
                out.append(p)
    except OSError:
        pass
    return out


def extract_frames(video, dur, cfg, rel, log, on_frame=None):
    n = cfg["cols"] * cfg["rows"]
    os.makedirs(os.path.join(RUN_DIR, rel), exist_ok=True)
    ok = 0
    for k in range(n):
        t = (k + 0.5) * dur / n
        frame = os.path.join(RUN_DIR, rel, "f%03d.jpg" % k)
        try:
            subprocess.run(
                [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                 "-ss", "%.3f" % t, "-i", video,
                 "-frames:v", "1", "-an", "-sn",
                 "-vf", "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d"
                        % (cfg["cw"], cfg["ch"], cfg["cw"], cfg["ch"]),
                 "-q:v", "3", frame],
                capture_output=True, timeout=180, creationflags=NO_WINDOW,
            )
            if os.path.isfile(frame) and os.path.getsize(frame) > 0:
                ok += 1
        except Exception as e:
            log("    取帧失败 t=%.1fs: %s" % (t, e))
        if on_frame:
            on_frame(k + 1, n)
    return ok, n


def compose(video, dur, size_gb, cfg, rel, dest, log, show_label=False):
    base = os.path.basename(video)

    tile = ("tile=%dx%d:margin=0:padding=0,"
            "drawgrid=w=%d:h=%d:t=1:c=white@0.28"
            % (cfg["cols"], cfg["rows"], cfg["cw"], cfg["ch"]))

    vf = tile
    if show_label:
        title_txt = os.path.join(RUN_DIR, rel, "title.txt")
        with open(title_txt, "w", encoding="utf-8", newline="\n") as f:
            f.write("%s\n%s · %s GB" % (base, fmt_dur(dur), size_gb))
        font = "fontfile=fonts/%s:textfile=%s/title.txt" % (FONT_NAME, rel)
        if cfg["bar"]:
            vf += (",pad=1920:1080:0:0:color=0x0d0d0d,drawtext=" + font +
                   ":fontcolor=white@0.94:fontsize=54:line_spacing=16:x=72:y=862")
        else:
            vf += (",drawtext=" + font +
                   ":fontcolor=white@0.95:fontsize=46:line_spacing=14:"
                   "box=1:boxcolor=black@0.55:boxborderw=20:x=44:y=h-150")
    elif cfg["bar"]:
        vf += ",pad=1920:1080:0:0:color=0x0d0d0d"

    try:
        r = subprocess.run(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
             "-framerate", "1", "-i", rel + "/f%03d.jpg",
             "-vf", vf, "-frames:v", "1", "-update", "1", "-q:v", "2", dest],
            cwd=RUN_DIR, capture_output=True, text=True, timeout=300,
            creationflags=NO_WINDOW, encoding="utf-8", errors="ignore",
        )
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            return True, ""
        return False, (r.stderr or "").strip()[-300:]
    except Exception as e:
        return False, str(e)


def resolve_inputs(paths):
    """把用户给的路径（文件夹 / 视频文件，可多个）展开成视频文件列表。"""
    found = []
    for p in paths:
        p = (p or "").strip().strip('"')
        if not p:
            continue
        if os.path.isdir(p):
            found.extend(list_videos(p))
        elif os.path.isfile(p) and os.path.splitext(p)[1].lower() in VIDEO_EXTS:
            found.append(p)
    seen, uniq = set(), []
    for p in found:
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def run_batch(videos, layout_key, overwrite=False, show_label=False, log=print, progress=None):
    cfg = dict(LAYOUTS[layout_key])
    # 4×3 且不叠加文字时，把行高改为 360 让网格直接铺满 1920×1080，不留空黑条
    if cfg["bar"] and not show_label:
        cfg["ch"] = 360
        cfg["bar"] = False
    if not videos:
        log("没有可处理的视频。")
        return 0, 0

    if show_label and not prep_font():
        log("警告: 找不到 fonts/%s，封面上的文字可能显示为方块。" % FONT_NAME)

    done = skipped = failed = 0
    total = len(videos)

    for idx, v in enumerate(videos, 1):
        folder = os.path.dirname(v) or "."
        dest_dir = os.path.join(folder, cfg["subdir"]) if cfg["subdir"] else folder
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except Exception as e:
            log("[%d/%d] 失败（无法创建输出目录）%s" % (idx, total, e))
            failed += 1
            continue
        name = os.path.splitext(os.path.basename(v))[0]
        dest = os.path.join(dest_dir, name + cfg["suffix"] + ".jpg")

        if os.path.isfile(dest) and not overwrite:
            log("[%d/%d] 跳过（已存在）%s" % (idx, total, os.path.basename(v)))
            skipped += 1
            if progress:
                progress(idx / float(total), idx, total)
            continue

        if progress:
            progress((idx - 1) / float(total), idx, total)

        def on_frame(k, n, _idx=idx):
            # 取帧大约占单个视频 85% 的耗时，剩下的留给合成
            if progress:
                progress(((_idx - 1) + 0.85 * k / float(max(n, 1))) / total, _idx, total)

        dur = probe_duration(v)
        if dur <= 0:
            log("[%d/%d] 失败（读不到时长）%s" % (idx, total, os.path.basename(v)))
            failed += 1
            continue

        size_gb = "%.1f" % (os.path.getsize(v) / 1024.0 / 1024.0 / 1024.0)
        log("[%d/%d] 正在处理 %s  (%s · %s GB)" % (idx, total, os.path.basename(v), fmt_dur(dur), size_gb))

        rel = ".work/%s_%d" % (layout_key, idx)
        ok, n = extract_frames(v, dur, cfg, rel, log, on_frame=on_frame)
        if ok == 0:
            log("    失败：一帧都没取到")
            failed += 1
            continue
        if ok < n:
            log("    提示：只取到 %d/%d 帧" % (ok, n))

        good, err = compose(v, dur, size_gb, cfg, rel, dest, log, show_label)
        if good:
            done += 1
            log("    ✓ 已生成 %s" % os.path.basename(dest))
            try:
                shutil.rmtree(os.path.join(RUN_DIR, rel))
            except Exception:
                pass
        else:
            failed += 1
            log("    ✗ 合成失败: %s" % err)

        if progress:
            progress(idx / float(total), idx, total)

    log("")
    log("完成：生成 %d 张，跳过 %d 张，失败 %d 张" % (done, skipped, failed))
    return done, failed


# ---------------------------------------------------------------- 图形界面
def main_gui(initial_targets=None):
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    root.title("视频封面批量生成器")
    root.geometry("860x640")
    root.minsize(760, 560)
    root.configure(bg="#f5f6f8")

    style = ttk.Style()
    try:
        style.theme_use("vista")
    except Exception:
        pass
    style.configure("TLabel", background="#f5f6f8", foreground="#1f2328")
    style.configure("Hint.TLabel", foreground="#6b7280")
    style.configure("TButton", padding=(12, 6))
    style.configure("Go.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(16, 8))
    style.configure("TRadiobutton", background="#f5f6f8", foreground="#1f2328")
    style.configure("TCheckbutton", background="#f5f6f8", foreground="#1f2328")

    state = {"targets": [], "running": False}
    msgq = queue.Queue()

    # ---- 顶部：输入源
    top = ttk.Frame(root, padding=(18, 16, 18, 4))
    top.pack(fill="x")
    ttk.Label(top, text="视频文件夹 / 视频文件", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")

    row = ttk.Frame(top)
    row.pack(fill="x", pady=(6, 0))
    path_var = tk.StringVar()
    entry = ttk.Entry(row, textvariable=path_var, font=("Microsoft YaHei UI", 9), state="readonly")
    entry.pack(side="left", fill="x", expand=True, ipady=4)

    def add_targets(paths):
        for p in paths:
            p = os.path.normpath((p or "").strip().strip('"'))
            if not os.path.exists(p):
                continue
            if os.path.isdir(p) or os.path.splitext(p)[1].lower() in VIDEO_EXTS:
                if p not in state["targets"]:
                    state["targets"].append(p)
        refresh()

    def pick_dir():
        d = filedialog.askdirectory(title="选择包含视频的文件夹")
        if d:
            add_targets([d])

    def pick_files():
        fs = filedialog.askopenfilenames(
            title="选择一个或多个视频",
            filetypes=[("视频文件", " ".join("*" + e for e in VIDEO_EXTS)), ("所有文件", "*.*")])
        if fs:
            add_targets(list(fs))

    ttk.Button(row, text="选文件夹", command=pick_dir, width=10).pack(side="left", padx=(8, 0))
    ttk.Button(row, text="选视频", command=pick_files, width=10).pack(side="left", padx=(6, 0))
    ttk.Button(row, text="清空", command=lambda: (state["targets"].clear(), refresh()),
               width=6).pack(side="left", padx=(6, 0))

    hint = ttk.Label(top, text="", style="Hint.TLabel", wraplength=800, justify="left")
    hint.pack(anchor="w", pady=(8, 0))

    def refresh():
        ts = state["targets"]
        if not ts:
            path_var.set("")
            hint.configure(text="把视频或文件夹直接拖到窗口里，或用右上角按钮选择。")
            return
        if len(ts) == 1:
            path_var.set(ts[0])
        else:
            nd = sum(1 for p in ts if os.path.isdir(p))
            nf = len(ts) - nd
            parts = []
            if nf:
                parts.append("%d 个视频" % nf)
            if nd:
                parts.append("%d 个文件夹" % nd)
            path_var.set("已选择 " + " + ".join(parts))
        n = len(resolve_inputs(ts))
        hint.configure(text="待处理视频 %d 个 · 封面与视频同名，保存在视频所在目录" % n)

    # ---- 拖放
    if HAS_DND:
        def on_drop(event):
            try:
                items = list(root.tk.splitlist(event.data))
            except Exception:
                items = [event.data]
            add_targets(items)

        for w in (root, entry):
            try:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", on_drop)
            except Exception:
                pass

    # ---- 中部：布局
    mid = ttk.Frame(root, padding=(18, 6, 18, 8))
    mid.pack(fill="x")
    ttk.Label(mid, text="封面布局", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
    layout_var = tk.StringVar(value="4x4")
    for key in ("4x4", "4x3", "3x4"):
        ttk.Radiobutton(mid, text=LAYOUTS[key]["label"], value=key,
                        variable=layout_var).pack(anchor="w", pady=1)

    opts = ttk.Frame(root, padding=(18, 0, 18, 8))
    opts.pack(fill="x")
    overwrite_var = tk.BooleanVar(value=False)
    open_after_var = tk.BooleanVar(value=True)
    label_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(opts, text="在封面上叠加文件名/时长", variable=label_var).pack(side="left")
    ttk.Checkbutton(opts, text="覆盖已存在的同名封面", variable=overwrite_var).pack(side="left", padx=(18, 0))
    ttk.Checkbutton(opts, text="完成后打开文件夹", variable=open_after_var).pack(side="left", padx=(18, 0))

    # ---- 操作区
    act = ttk.Frame(root, padding=(18, 4, 18, 8))
    act.pack(fill="x")
    go_btn = ttk.Button(act, text="开始生成", style="Go.TButton")
    go_btn.pack(side="left")
    prog = ttk.Progressbar(act, mode="determinate")
    prog.pack(side="left", fill="x", expand=True, padx=(14, 0))
    status = ttk.Label(act, text="就绪", style="Hint.TLabel", width=18)
    status.pack(side="left", padx=(10, 0))

    # ---- 日志
    box = ttk.Frame(root, padding=(18, 0, 18, 16))
    box.pack(fill="both", expand=True)
    log_text = tk.Text(box, wrap="none", font=("Microsoft YaHei UI", 9),
                       bg="#ffffff", fg="#25282c", relief="flat",
                       highlightthickness=1, highlightbackground="#d8dbe0")
    scroll = ttk.Scrollbar(box, orient="vertical", command=log_text.yview)
    log_text.configure(yscrollcommand=scroll.set, state="disabled")
    scroll.pack(side="right", fill="y")
    log_text.pack(side="left", fill="both", expand=True)

    def log(msg):
        msgq.put(("log", msg))

    def pump():
        try:
            while True:
                kind, payload = msgq.get_nowait()
                if kind == "log":
                    log_text.configure(state="normal")
                    log_text.insert("end", payload + "\n")
                    log_text.see("end")
                    log_text.configure(state="disabled")
                elif kind == "progress":
                    frac, cur, tot = payload
                    prog["value"] = int(frac * 1000)
                    status.configure(text="%d/%d  %d%%" % (cur, tot, int(frac * 100)))
                elif kind == "done":
                    go_btn.configure(state="normal")
                    state["running"] = False
                    status.configure(text="完成")
                    prog["value"] = prog["maximum"]
                    if open_after_var.get() and payload:
                        try:
                            os.startfile(payload)
                        except Exception:
                            pass
        except queue.Empty:
            pass
        root.after(120, pump)

    def worker(videos, layout, overwrite, show_label):
        try:
            run_batch(videos, layout, overwrite, show_label, log=log,
                      progress=lambda f, c, t: msgq.put(("progress", (f, c, t))))
        except Exception as e:
            log("异常: %s" % e)
        finally:
            msgq.put(("done", os.path.dirname(videos[0]) if videos else ""))

    def start():
        if state["running"]:
            return
        if not FFMPEG:
            messagebox.showerror("缺少 ffmpeg", "没找到 ffmpeg.exe。\n请把它放在程序目录下，或设置环境变量 FFMPEG_HOME。")
            return
        videos = resolve_inputs(state["targets"])
        if not videos:
            messagebox.showwarning("没有视频", "请先拖入或选择视频文件夹 / 视频文件。")
            return
        log_text.configure(state="normal")
        log_text.delete("1.0", "end")
        log_text.configure(state="disabled")
        state["running"] = True
        go_btn.configure(state="disabled")
        prog["maximum"] = 1000
        prog["value"] = 0
        status.configure(text="准备中…")
        log("ffmpeg: %s" % FFMPEG)
        log("待处理: %d 个视频" % len(videos))
        log("")
        threading.Thread(target=worker,
                         args=(videos, layout_var.get(), overwrite_var.get(), label_var.get()),
                         daemon=True).start()

    go_btn.configure(command=start)
    root.bind("<Return>", lambda e: start())

    if initial_targets:
        add_targets(initial_targets)
    else:
        refresh()

    pump()
    root.mainloop()


# ---------------------------------------------------------------- 入口
def main():
    args = [a for a in sys.argv[1:]]

    if "--selftest" in args:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
        root.title("selftest")
        ttk.Label(root, text="ok").pack()
        ok_dnd = False
        if HAS_DND:
            try:
                root.drop_target_register(DND_FILES)
                ok_dnd = True
            except Exception:
                ok_dnd = False
        root.after(200, root.destroy)
        root.mainloop()
        _out("GUI_OK dnd=%s ffmpeg=%s" % (ok_dnd, bool(FFMPEG)))
        return 0

    if "--cli" in args:
        i = args.index("--cli")
        rest = args[i + 1:]
        targets = [a for a in rest if os.path.exists(a)]
        if not targets:
            _out("usage: --cli <文件夹或视频路径> [更多路径...] [4x4|4x3|3x4] [--label] [--overwrite]")
            return 2
        layout = next((a for a in rest if a in LAYOUTS), "4x4")
        show_label = "--label" in args
        overwrite = "--overwrite" in args
        lines = []

        def logline(msg):
            _out(msg)
            lines.append(str(msg))

        videos = resolve_inputs(targets)
        logline("ffmpeg: %s" % FFMPEG)
        logline("待处理: %d 个视频" % len(videos))
        last = [-1]

        def prog(frac, cur, tot):
            pct = int(frac * 100)
            if pct >= last[0] + 10 or (pct == 100 and last[0] != 100):
                last[0] = pct
                logline("    进度 %d%%（%d/%d）" % (pct, cur, tot))

        d, f = run_batch(videos, layout, overwrite=overwrite,
                         show_label=show_label, log=logline, progress=prog)
        try:
            with open(os.path.join(RUN_DIR, "cli.log"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
        except Exception:
            pass
        _out("RESULT done=%d failed=%d" % (d, f))
        return 0 if f == 0 else 1

    initial = [os.path.normpath(a) for a in args
               if not a.startswith("--") and os.path.exists(a)]
    main_gui(initial)
    return 0


if __name__ == "__main__":
    sys.exit(main())
