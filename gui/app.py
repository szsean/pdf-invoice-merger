# -*- coding: utf-8 -*-
"""发票 PDF 合并工具 - Tkinter 界面。"""
import os
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.merger import default_desktop_dir, merge

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    def make_root():
        return TkinterDnD.Tk()

    DRAG_AVAILABLE = True
except ImportError:
    def make_root():
        return tk.Tk()

    DRAG_AVAILABLE = False


class MergerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.files: list[str] = []
        self._build_ui()
        if DRAG_AVAILABLE:
            root.drop_target_register(DND_FILES)
            root.dnd_bind("<<Drop>>", self._on_drop)

    def _build_ui(self):
        self.root.title("发票 PDF 合并工具")
        self.root.geometry("560x520")
        self.root.minsize(480, 440)

        pad = {"padx": 10, "pady": 6}

        # 文件列表区
        ttk.Label(self.root, text="1. 添加发票 PDF（支持拖拽多个文件到窗口）").pack(anchor="w", **pad)
        list_frame = ttk.Frame(self.root)
        list_frame.pack(fill="both", expand=True, **pad)
        self.listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED)
        scroll = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", **pad)
        ttk.Button(btn_frame, text="添加文件", command=self.add_files).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="移除选中", command=self.remove_selected).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="清空列表", command=self.clear_files).pack(side="left", padx=6)

        # 目标页数
        page_frame = ttk.Frame(self.root)
        page_frame.pack(fill="x", **pad)
        ttk.Label(page_frame, text="2. 目标页数 n：").pack(side="left")
        self.pages_var = tk.StringVar(value="1")
        spin = ttk.Spinbox(page_frame, from_=1, to=99, width=5, textvariable=self.pages_var)
        spin.pack(side="left", padx=6)
        ttk.Label(page_frame, text="（m 个文件合并为 n 页）").pack(side="left")

        # 输出目录
        dir_frame = ttk.Frame(self.root)
        dir_frame.pack(fill="x", **pad)
        ttk.Label(dir_frame, text="3. 输出目录：").pack(side="left")
        self.dir_var = tk.StringVar(value=default_desktop_dir())
        ttk.Entry(dir_frame, textvariable=self.dir_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(dir_frame, text="浏览…", command=self.choose_dir).pack(side="left")

        # 生成按钮
        self.merge_btn = ttk.Button(self.root, text="生成合并 PDF", command=self.start_merge)
        self.merge_btn.pack(fill="x", padx=10, pady=10, ipady=6)

        # 状态栏
        self.status_var = tk.StringVar(
            value="拖拽支持：已启用" if DRAG_AVAILABLE else "拖拽支持：未启用（可点击“添加文件”选择）"
        )
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w").pack(
            fill="x", side="bottom"
        )

    # ---------- 文件操作 ----------
    def _add_paths(self, paths):
        added = 0
        for p in paths:
            p = p.strip("{}")  # tkinterdnd2 对含空格路径会加大括号
            if p.lower().endswith(".pdf") and os.path.isfile(p) and p not in self.files:
                self.files.append(p)
                self.listbox.insert("end", p)
                added += 1
        if added:
            self._set_status(f"已添加 {added} 个文件，当前共 {len(self.files)} 个")
        elif paths:
            self._set_status("未添加新文件（仅支持本地 PDF 文件，且不能重复）")

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择发票 PDF", filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")]
        )
        self._add_paths(list(paths))

    def _on_drop(self, event):
        self._add_paths(self.root.tk.splitlist(event.data))

    def remove_selected(self):
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)
            del self.files[i]
        self._set_status(f"当前共 {len(self.files)} 个文件")

    def clear_files(self):
        self.files.clear()
        self.listbox.delete(0, "end")
        self._set_status("列表已清空")

    def choose_dir(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.dir_var.set(d)

    # ---------- 合并 ----------
    def start_merge(self):
        try:
            n = int(self.pages_var.get())
            if n < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("输入有误", "目标页数必须是不小于 1 的整数")
            return
        if not self.files:
            messagebox.showwarning("输入有误", "请先添加至少一个 PDF 文件")
            return
        out_dir = self.dir_var.get().strip() or None
        self.merge_btn.configure(state="disabled")
        self._set_status("正在生成，请稍候…")
        threading.Thread(target=self._do_merge, args=(n, out_dir), daemon=True).start()

    def _do_merge(self, n, out_dir):
        try:
            out_path = merge(self.files, n, out_dir)
        except Exception as e:
            self.root.after(0, self._merge_failed, e)
        else:
            self.root.after(0, self._merge_done, out_path)

    def _merge_done(self, out_path):
        self.merge_btn.configure(state="normal")
        self._set_status(f"已生成：{out_path}")
        if messagebox.askyesno("完成", f"已生成：\n{out_path}\n\n是否打开所在文件夹？"):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(out_path)])

    def _merge_failed(self, err):
        self.merge_btn.configure(state="normal")
        self._set_status(f"生成失败：{err}")
        messagebox.showerror("生成失败", str(err))

    def _set_status(self, text):
        self.status_var.set(text)


def run():
    root = make_root()
    MergerApp(root)
    root.mainloop()
