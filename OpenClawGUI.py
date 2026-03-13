import tkinter as tk
from tkinter import scrolledtext, ttk
import os
import sys
import configparser
import subprocess
import threading
import queue
import re
import webbrowser
import getpass
import platform
import json
from datetime import datetime

# 平台判断
OS_TYPE = platform.system()
IS_MAC = OS_TYPE == "Darwin"
IS_WIN = OS_TYPE == "Windows"

# 平台相关字体
if IS_MAC:
    UI_FONT = "SF Pro Display"
    CODE_FONT = "Menlo"
else:
    UI_FONT = "Microsoft YaHei"
    CODE_FONT = "Consolas"


class Tooltip:
    """简易提示框"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None
        widget.bind("<Enter>", self.schedule_show)
        widget.bind("<Leave>", self.hide)

    def schedule_show(self, _event=None):
        self.hide()
        self.id = self.widget.after(300, self.show)

    def show(self):
        if self.tip_window:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.wm_attributes("-topmost", True)
        label = tk.Label(tw, text=self.text, justify="left",
                         background="#2d3748", foreground="#eaeaea",
                         relief="solid", borderwidth=1,
                         font=(UI_FONT, 10), padx=8, pady=5)
        label.pack()

    def hide(self, event=None):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()


class OpenClawGUI:
    # 频道名称映射
    CHANNEL_NAME_MAP = {
        "feishu": "飞书",
        "qqbot": "QQ",
    }
    # 频道ID标签映射
    CHANNEL_ID_LABEL_MAP = {
        "feishu": "飞书用户 ID",
        "qqbot": "QQ OpenID",
    }
    # 频道 target 前缀映射
    CHANNEL_TARGET_PREFIX = {
        "feishu": "",
        "qqbot": "qqbot:c2c:",
    }

    def __init__(self, root, tray_manager):
        self.root = root
        self.tray = tray_manager

        # 窗口尺寸
        self.window_width = 1080
        self.window_height = 850

        # 先隐藏窗口并设置大小，避免闪烁
        self.root.withdraw()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - self.window_width) // 2
        y = (sh - self.window_height) // 2
        self.root.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")

        # 标题显示系统版本
        os_name = "macOS" if IS_MAC else "Windows"
        self.root.title(f"OpenClaw GUI 控制台 v1.5.1 ({os_name})")

        # 设置窗口图标
        if getattr(sys, 'frozen', False):
            icon_base = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
        else:
            icon_base = os.path.dirname(os.path.abspath(__file__))

        if IS_WIN:
            icon_path = os.path.join(icon_base, "icons", "icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        else:
            icon_path = os.path.join(icon_base, "icons", "icon.png")
            if os.path.exists(icon_path):
                icon_img = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(True, icon_img)
                self._window_icon = icon_img  # 保持引用防止被垃圾回收

        # 环境路径补丁 (macOS)
        if IS_MAC:
            os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + os.environ.get("PATH", "")

        if getattr(sys, 'frozen', False):
            self.current_dir = os.path.dirname(sys.executable)
        else:
            self.current_dir = os.path.dirname(os.path.abspath(__file__))

        # 配置文件放在用户目录，无权限问题且升级不丢失
        self.config_dir = os.path.join(os.path.expanduser("~"), ".openclawgui")
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
        self.config_file = os.path.join(self.config_dir, "config.ini")
        self.is_running = False
        self.process = None
        self.has_notified = False
        self.restart_count = 0  # 重启次数计数
        self.max_restart = 3    # 最大重启次数
        self.cached_models = []  # 缓存的模型列表

        # 加载配置
        self.config = self.load_config()

        self.setup_menu()
        self.setup_ui()

        self.root.deiconify()  # 显示窗口
        self._check_openclaw_update()  # 后台检查更新

        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        # macOS: 点击 Dock 图标时恢复窗口
        if IS_MAC:
            self.root.createcommand('tk::mac::ReopenApplication', lambda: self.root.after(10, self.show_window))
            self._setup_mac_dock_handler()

    def setup_ui(self):
        # 配色方案
        self.colors = {
            "bg": "#1a1a2e",
            "card": "#16213e",
            "accent": "#0f3460",
            "highlight": "#e94560",
            "text": "#eaeaea",
            "text_dim": "#8892a0",
            "success": "#4ade80",
            "log_bg": "#0d1117"
        }
        c = self.colors
        self.root.configure(bg=c["bg"])

        # 配置 ttk 样式
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Card.TFrame", background=c["card"])
        style.configure("Main.TFrame", background=c["bg"])
        # Windows 按钮需要更大的 padding 才能完整显示文字
        btn_padding = (20, 8) if IS_WIN else (12, 6)
        style.configure("TButton", padding=btn_padding, font=(UI_FONT, 12))
        style.map("TButton",
            background=[("active", c["accent"]), ("!active", c["card"])],
            foreground=[("active", "white"), ("!active", c["text"])])
        style.configure("Start.TButton", padding=btn_padding, font=(UI_FONT, 12, "bold"))
        style.map("Start.TButton",
            background=[("active", "#22c55e"), ("!active", c["success"])],
            foreground=[("active", "white"), ("!active", "#0d1117")])
        style.configure("Stop.TButton", padding=btn_padding, font=(UI_FONT, 12))
        style.map("Stop.TButton",
            background=[("active", "#dc2626"), ("!active", c["highlight"])],
            foreground=[("active", "white"), ("!active", "white")])
        # 滚动条样式
        style.configure("Vertical.TScrollbar", width=10, background=c["accent"], troughcolor=c["log_bg"])

        # 顶部标题栏
        header = tk.Frame(self.root, bg=c["bg"], pady=15)
        header.pack(fill="x", padx=20)
        tk.Label(header, text="OpenClaw GUI 控制台", font=(UI_FONT, 18, "bold"), bg=c["bg"], fg=c["text"]).pack(side="left")
        self.status_label = tk.Label(header, text="● 已停止", font=(UI_FONT, 12), bg=c["bg"], fg=c["text_dim"])
        self.status_label.pack(side="right")

        # 状态通知 + 消息频道（合并为一行，使用 grid 实现 1:1 平分）
        config_row = tk.Frame(self.root, bg=c["bg"])
        config_row.pack(fill="x", padx=20, pady=(0, 5))
        config_row.columnconfigure(0, weight=1, uniform="half")
        config_row.columnconfigure(1, weight=1, uniform="half")

        # 左半边：状态通知
        notify_card = tk.Frame(config_row, bg=c["card"], pady=6, padx=15)
        notify_card.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        notify_row = tk.Frame(notify_card, bg=c["card"])
        notify_row.pack(fill="x")
        tk.Label(notify_row, text="状态通知", font=(UI_FONT, 12), bg=c["card"], fg=c["text_dim"]).pack(side="left")

        self.notify_summary_label = tk.Label(notify_row, text="", font=(CODE_FONT, 12), bg=c["card"], fg=c["text"])
        self.notify_summary_label.pack(side="left", padx=15)
        self._update_notify_summary()

        notify_btn = tk.Label(notify_row, text="配置", font=(UI_FONT, 11), bg=c["card"], fg=c["text_dim"])
        notify_btn.pack(side="right")
        notify_btn.bind("<Button-1>", lambda e: self.open_notify_config_window())
        notify_btn.bind("<Enter>", lambda e: notify_btn.config(fg=c["highlight"]))
        notify_btn.bind("<Leave>", lambda e: notify_btn.config(fg=c["text_dim"]))

        # 右半边：消息频道
        channel_card = tk.Frame(config_row, bg=c["card"], pady=6, padx=15)
        channel_card.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        channel_row = tk.Frame(channel_card, bg=c["card"])
        channel_row.pack(fill="x")
        tk.Label(channel_row, text="消息频道", font=(UI_FONT, 12), bg=c["card"], fg=c["text_dim"]).pack(side="left")

        self.channel_summary_label = tk.Label(channel_row, text="", font=(CODE_FONT, 12), bg=c["card"], fg=c["text"])
        self.channel_summary_label.pack(side="left", padx=15)
        self._update_channel_summary()

        channel_btn = tk.Label(channel_row, text="配置", font=(UI_FONT, 11), bg=c["card"], fg=c["text_dim"])
        channel_btn.pack(side="right")
        channel_btn.bind("<Button-1>", lambda e: self.open_channel_config_window())
        channel_btn.bind("<Enter>", lambda e: channel_btn.config(fg=c["highlight"]))
        channel_btn.bind("<Leave>", lambda e: channel_btn.config(fg=c["text_dim"]))

        # 实时运行信息
        info_card = tk.Frame(self.root, bg=c["card"], pady=12, padx=15)
        info_card.pack(fill="x", padx=20, pady=(0, 10))

        info_row1 = tk.Frame(info_card, bg=c["card"])
        info_row1.pack(fill="x", pady=(0, 6))
        tk.Label(info_row1, text="当前模型", font=(UI_FONT, 11), bg=c["card"], fg=c["text_dim"]).pack(side="left")
        self.model_label = tk.Label(info_row1, text="获取中...", font=(CODE_FONT, 11, "bold"), bg=c["card"], fg=c["text_dim"])
        self.model_label.pack(side="left", padx=15)

        # 切换按钮（初始隐藏，加载完成后显示）
        self.model_switch_btn = tk.Label(info_row1, text="切换", font=(UI_FONT, 11), bg=c["card"], fg=c["text_dim"], cursor="hand2")
        self.model_switch_btn.bind("<Button-1>", lambda e: self.open_model_switch_window())
        self.model_switch_btn.bind("<Enter>", lambda e: self.model_switch_btn.config(fg=c["highlight"]))
        self.model_switch_btn.bind("<Leave>", lambda e: self.model_switch_btn.config(fg=c["text_dim"]))
        # 不立即 pack，等加载完成后再显示

        self._load_current_model()  # 异步加载当前模型

        info_row2 = tk.Frame(info_card, bg=c["card"])
        info_row2.pack(fill="x", pady=(0, 6))
        tk.Label(info_row2, text="后台地址", font=(UI_FONT, 11),
                 bg=c["card"], fg=c["text_dim"]).pack(side="left")
        self.url_label = tk.Label(info_row2, text="暂无地址", font=(CODE_FONT, 11),
                                   bg=c["card"], fg=c["text_dim"])
        self.url_label.pack(side="left", padx=15)
        self.url_label.bind("<Button-1>", lambda e: self.open_browser())

        info_row3 = tk.Frame(info_card, bg=c["card"])
        info_row3.pack(fill="x")
        tk.Label(info_row3, text="OpenClaw版本", font=(UI_FONT, 11),
                 bg=c["card"], fg=c["text_dim"]).pack(side="left")
        self.version_label = tk.Label(info_row3, text="获取中...", font=(CODE_FONT, 11),
                                       bg=c["card"], fg=c["text_dim"])
        self.version_label.pack(side="left", padx=15)
        self._load_openclaw_version()  # 异步加载版本

        # 控制按钮区
        btn_frame = tk.Frame(self.root, bg=c["bg"], pady=8)
        btn_frame.pack(fill="x", padx=20)

        self.start_btn = ttk.Button(btn_frame, text="▶  启动守护", command=self.start_guard, style="Start.TButton")
        self.start_btn.pack(side="left")

        self.stop_btn = ttk.Button(btn_frame, text="■  强制停止", command=self.stop_guard, style="Stop.TButton")
        self.stop_btn.pack(side="left", padx=10)

        # 日志区标题
        log_header = tk.Frame(self.root, bg=c["bg"], pady=8)
        log_header.pack(fill="x", padx=20)
        tk.Label(log_header, text="运行日志", font=(UI_FONT, 12),bg=c["bg"], fg=c["text_dim"]).pack(side="left")
        clear_link = tk.Label(log_header, text="清空", font=(UI_FONT, 11), bg=c["bg"], fg=c["text_dim"])
        clear_link.pack(side="right")
        clear_link.bind("<Button-1>", lambda e: self.clear_log())
        clear_link.bind("<Enter>", lambda e: clear_link.config(fg=c["highlight"]))
        clear_link.bind("<Leave>", lambda e: clear_link.config(fg=c["text_dim"]))

        # 日志显示区
        log_container = tk.Frame(self.root, bg=c["log_bg"], padx=1, pady=1)
        log_container.pack(expand=True, fill="both", padx=20, pady=(0, 15))

        self.log_area = tk.Text(
            log_container, bg=c["log_bg"], fg=c["text"],
            borderwidth=0, highlightthickness=0,
            font=(CODE_FONT, 11), wrap="word", padx=10, pady=10
        )
        log_scrollbar = ttk.Scrollbar(log_container, orient="vertical", command=self.log_area.yview, style="Vertical.TScrollbar")
        self.log_area.configure(yscrollcommand=log_scrollbar.set)
        log_scrollbar.pack(side="right", fill="y")
        self.log_area.pack(side="left", expand=True, fill="both")

        # 配置日志高亮
        self.log_area.tag_configure("success", foreground=c["success"])
        self.log_area.tag_configure("error", foreground=c["highlight"])
        self.log_area.tag_configure("info", foreground="#60a5fa")
        self.log_area.tag_configure("warning", foreground="#fbbf24")
        self.log_area.tag_configure("gateway", foreground="#a78bfa")
        self.log_area.tag_configure("time", foreground=c["text_dim"])

        # ANSI 颜色映射
        self.ansi_colors = {
            "30": "#4a4a4a", "31": "#f87171", "32": "#4ade80", "33": "#fbbf24",
            "34": "#60a5fa", "35": "#c084fc", "36": "#22d3ee", "37": "#e5e5e5",
            "90": "#737373", "91": "#fca5a5", "92": "#86efac", "93": "#fde047",
            "94": "#93c5fd", "95": "#d8b4fe", "96": "#67e8f9", "97": "#ffffff",
        }
        # 为每个 ANSI 颜色创建 tag
        for code, color in self.ansi_colors.items():
            self.log_area.tag_configure(f"ansi_{code}", foreground=color)

    def clear_log(self):
        self.log_area.delete("1.0", "end")

    def parse_ansi(self, text):
        """解析 ANSI 颜色码，返回 [(文本, tag), ...] 列表"""
        segments = []
        current_tag = None
        last_end = 0

        for match in re.finditer(r'\x1b\[([0-9;]*)m', text):
            # 添加前面的文本
            if match.start() > last_end:
                segments.append((text[last_end:match.start()], current_tag))

            # 解析颜色码
            codes = match.group(1).split(';')
            for code in codes:
                if code == '0' or code == '':
                    current_tag = None  # 重置
                elif code in self.ansi_colors:
                    current_tag = f"ansi_{code}"

            last_end = match.end()

        # 添加剩余文本
        if last_end < len(text):
            segments.append((text[last_end:], current_tag))

        return segments

    def log(self, content, tag=None, use_ansi=False):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_area.insert("end", f"[{ts}] ", "time")

        if use_ansi and '\x1b[' in content:
            # 解析 ANSI 颜色并分段显示
            segments = self.parse_ansi(content)
            for text, ansi_tag in segments:
                if text:
                    self.log_area.insert("end", text, ansi_tag)
            self.log_area.insert("end", "\n")
        else:
            # 原有的关键词匹配逻辑
            if tag is None:
                low = content.lower()
                if any(x in low for x in ["error", "fail", "错误", "失败"]):
                    tag = "error"
                elif any(x in low for x in ["warning", "warn", "retry"]):
                    tag = "warning"
                elif any(x in low for x in ["ready", "success", "connected", "✅", "成功"]):
                    tag = "success"
                elif "[gateway]" in low or "gateway" in low:
                    tag = "gateway"
                elif ">>>" in content:
                    tag = "info"
            self.log_area.insert("end", f"{content}\n", tag)

        self.log_area.see("end")

    def update_status(self, running):
        if running:
            self.status_label.config(text="● 运行中", fg=self.colors["success"])
        else:
            self.status_label.config(text="● 已停止", fg=self.colors["text_dim"])

    def start_guard(self, is_restart=False):
        if self.is_running: return
        if not is_restart:
            self.restart_count = 0  # 用户点击启动按钮时重置计数
        self.is_running = True
        self.has_notified = False
        self.tray.set_status(True)
        self.start_btn.config(state="disabled")
        self.update_status(True)
        self.log(">>> 正在启动引擎...")
        threading.Thread(target=self.guard_loop, daemon=True).start()

    def strip_ansi(self, text):
        return re.sub(r'\x1b\[[0-9;]*m', '', text)

    def guard_loop(self):
        try:
            self.process = subprocess.Popen("openclaw gateway --force --allow-unconfigured",
                                         shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, encoding='utf-8', errors='replace')
            for line in iter(self.process.stdout.readline, ''):
                if not self.is_running: break
                raw_line = line.strip()
                if not raw_line: continue
                # 使用 ANSI 颜色解析显示日志
                self.root.after(0, lambda l=raw_line: self.log(l, use_ansi=True))
                # 用于逻辑判断的纯文本
                clean_line = self.strip_ansi(raw_line)
                if "agent model:" in clean_line:
                    model_name = clean_line.split("agent model:")[-1].strip()
                    self.root.after(0, lambda m=model_name: self.model_label.config(text=m, fg=self.colors["success"]))
                if "host mounted at" in clean_line:
                    match = re.search(r'http://[0-9.]+:[0-9]+', clean_line)
                    if match:
                        url = match.group(0)
                        self.root.after(0, lambda u=url: self.url_label.config(text=u, fg="#60a5fa"))
                if not self.has_notified:
                    low_line = clean_line.lower()
                    if ("ws" in low_line and "client ready" in low_line) or ("websocket client started" in low_line):
                        self.has_notified = True
                        self.root.after(0, lambda: self.status_label.config(text="● 运行中 (已连通)", fg=self.colors["success"]))
                        start_info = (
                            f"🚀 [OpenClaw 系统启动]\n"
                            f"操作用户：{getpass.getuser()}\n"
                            f"电脑名称：{platform.node()}\n"
                            f"当前模型：{self.model_label.cget('text')}\n"
                            f"启动时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        self.root.after(0, lambda info=start_info: self._send_feishu_msg(info))
            self.process.wait()
        except Exception as ex:
            err_msg = str(ex)
            self.root.after(0, lambda msg=err_msg: self.log(f"运行时错误: {msg}"))
        finally:
            if self.is_running:  # 异常退出，自动重启
                self.restart_count += 1
                if self.restart_count <= self.max_restart:
                    restart_msg = (
                        f"⚠️ [OpenClaw 异常重启]\n"
                        f"操作用户：{getpass.getuser()}\n"
                        f"电脑名称：{platform.node()}\n"
                        f"检测时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"重启次数：{self.restart_count}/{self.max_restart}\n"
                        f"系统正在自动恢复..."
                    )
                    self.root.after(0, lambda: self.log(f"⚠️ 检测到异常退出，正在自动重启 ({self.restart_count}/{self.max_restart})...", "warning"))
                    self.root.after(0, lambda msg=restart_msg: self._send_feishu_msg(msg))
                    # 重置状态，以便 start_guard 能正常启动
                    self.is_running = False
                    self.root.after(2000, lambda: self.start_guard(is_restart=True))  # 2秒后重启
                else:
                    fail_msg = (
                        f"❌ [OpenClaw 重启失败]\n"
                        f"操作用户：{getpass.getuser()}\n"
                        f"电脑名称：{platform.node()}\n"
                        f"检测时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"已达到最大重启次数 ({self.max_restart} 次)，请手动检查"
                    )
                    self.root.after(0, lambda: self.log(f"❌ 已达到最大重启次数 ({self.max_restart} 次)，请手动检查", "error"))
                    self.root.after(0, lambda msg=fail_msg: self._send_feishu_msg(msg))
                    self.is_running = False
                    self.root.after(0, self._ui_reset)
            else:  # 正常停止
                self.root.after(0, self._ui_reset)

    def open_browser(self):
        url = self.url_label.cget("text")
        if url.startswith("http"):
            webbrowser.open(url)

    def _load_current_model(self, retry=0):
        """异步加载当前模型和模型列表"""
        def load():
            self.cached_models = self._get_available_models()
            current_model = None
            for m in self.cached_models:
                if m['default']:
                    current_model = m['name']
                    break

            def update_ui():
                self.model_switch_btn.pack(side="right")  # 始终显示切换按钮
                if current_model:
                    self.model_label.config(text=current_model, fg=self.colors["success"])
                elif self.cached_models:
                    # 有模型但没有默认的
                    self.model_label.config(text="未配置默认模型", fg=self.colors["text_dim"])
                elif retry < 2:
                    # 获取失败，重试（最多重试2次）
                    self.root.after(1000, lambda: self._load_current_model(retry + 1))
                else:
                    # 重试后仍失败
                    self.model_label.config(text="获取失败", fg=self.colors["text_dim"])

            self.root.after(0, update_ui)
        threading.Thread(target=load, daemon=True).start()

    def _get_current_model(self):
        """获取当前默认模型"""
        try:
            result = subprocess.run("openclaw models list", shell=True, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'default' in line and 'Tags' not in line:
                        parts = line.split()
                        if parts:
                            return parts[0]
        except:
            pass
        return None

    def _get_available_models(self):
        """获取可用的模型列表（Auth=yes）"""
        models = []
        try:
            result = subprocess.run("openclaw models list", shell=True, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                # 找到表头行的位置
                header_index = -1
                for i, line in enumerate(lines):
                    if 'Model' in line and 'Input' in line and 'Auth' in line:
                        header_index = i
                        break

                # 只解析表头之后的行
                if header_index >= 0:
                    for line in lines[header_index + 1:]:
                        if not line.strip():
                            continue
                        parts = line.split()
                        # 模型行至少有 5 列：Model Input Ctx Local Auth
                        if len(parts) >= 5:
                            model_name = parts[0]
                            input_type = parts[1]
                            context = parts[2]
                            local = parts[3]
                            auth = parts[4]
                            tags = parts[5] if len(parts) > 5 else ''
                            # 只显示 Auth=yes 的模型
                            if auth == 'yes':
                                is_default = 'default' in tags
                                models.append({
                                    'name': model_name,
                                    'input': input_type,
                                    'context': context,
                                    'default': is_default
                                })
        except Exception as e:
            print(f"[DEBUG] _get_available_models error: {e}")
        return models

    def open_model_switch_window(self):
        """打开模型切换窗口"""
        switch_win = tk.Toplevel(self.root)
        switch_win.title("切换模型")
        switch_win.geometry("550x480")
        switch_win.resizable(False, False)
        switch_win.configure(bg=self.colors["bg"])
        x = self.root.winfo_x() + 280
        y = self.root.winfo_y() + 200
        switch_win.geometry(f"+{x}+{y}")

        c = self.colors

        # 标题
        tk.Label(switch_win, text="选择模型", font=(UI_FONT, 14, "bold"),
                 bg=c["bg"], fg=c["text"]).pack(pady=(15, 10))

        # 直接使用缓存的模型列表，如果没有才异步加载
        def show_models(models):
            if not models:
                tk.Label(switch_win, text="未找到可用模型", font=(UI_FONT, 12),
                         bg=c["bg"], fg=c["text_dim"]).pack(pady=20)
                return

            # 模型列表容器
            list_frame = tk.Frame(switch_win, bg=c["bg"])
            list_frame.pack(fill="both", expand=True, padx=20, pady=5)

            # 创建 Canvas 和滚动条
            canvas = tk.Canvas(list_frame, bg=c["bg"], highlightthickness=0)
            scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
            scrollable_frame = tk.Frame(canvas, bg=c["bg"])

            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )

            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            # 选中的模型
            selected_var = tk.StringVar()
            current_model = self.model_label.cget("text")
            selected_var.set(current_model)

            # 模型列表
            for model in models:
                row = tk.Frame(scrollable_frame, bg=c["bg"])
                row.pack(fill="x", pady=3)

                is_current = (model['name'] == current_model)
                name_text = model['name']
                if is_current:
                    name_text += "  (当前)"

                rb = tk.Radiobutton(row, text=name_text, variable=selected_var, value=model['name'],
                                    font=(CODE_FONT, 11), bg=c["bg"], fg=c["success"] if is_current else c["text"],
                                    activebackground=c["bg"], selectcolor=c["bg"], anchor="w")
                rb.pack(side="left", fill="x", expand=True)

            # 按钮区
            btn_frame = tk.Frame(switch_win, bg=c["bg"])
            btn_frame.pack(fill="x", padx=20, pady=15)

            # 状态提示
            status_label = tk.Label(btn_frame, text="", font=(UI_FONT, 11), bg=c["bg"], fg=c["text_dim"])
            status_label.pack(side="left")

            def apply_model():
                model_name = selected_var.get()
                if model_name and model_name != current_model:
                    # 禁用按钮，显示处理中
                    apply_btn.config(state="disabled")
                    cancel_btn.config(state="disabled")
                    status_label.config(text="正在切换...", fg=c["text_dim"])
                    self._switch_model(model_name, switch_win, status_label, apply_btn, cancel_btn)
                else:
                    switch_win.destroy()

            cancel_btn = ttk.Button(btn_frame, text="取消", command=switch_win.destroy)
            cancel_btn.pack(side="right", padx=(10, 0))

            apply_btn = ttk.Button(btn_frame, text="应用", command=apply_model, style="Start.TButton")
            apply_btn.pack(side="right")

        # 优先使用缓存，没有缓存才异步加载
        if self.cached_models:
            show_models(self.cached_models)
        else:
            loading_label = tk.Label(switch_win, text="正在加载模型列表...", font=(UI_FONT, 12),
                                      bg=c["bg"], fg=c["text_dim"])
            loading_label.pack(pady=20)

            def load_models():
                models = self._get_available_models()
                self.cached_models = models
                # 同时更新主界面的当前模型显示
                current_model = None
                for m in models:
                    if m['default']:
                        current_model = m['name']
                        break
                def update():
                    loading_label.destroy()
                    show_models(models)
                    # 如果主界面显示的是"获取失败"，则更新
                    if current_model and self.model_label.cget("text") in ("获取中...", "获取失败"):
                        self.model_label.config(text=current_model, fg=self.colors["success"])
                self.root.after(0, update)

            threading.Thread(target=load_models, daemon=True).start()

    def _switch_model(self, model_name, switch_win=None, status_label=None, apply_btn=None, cancel_btn=None):
        """切换模型"""
        def switch():
            try:
                result = subprocess.run(f'openclaw models set "{model_name}"', shell=True, capture_output=True, text=True, timeout=30)
                # 检查是否成功：returncode=0 且输出包含 Default model
                if result.returncode == 0 and 'Default model:' in result.stdout:
                    # 更新缓存中的 default 状态
                    for m in self.cached_models:
                        m['default'] = (m['name'] == model_name)
                    self.root.after(0, lambda: self.model_label.config(text=model_name, fg=self.colors["success"]))
                    self.root.after(0, lambda: self.log(f"✅ 模型已切换为: {model_name}", "success"))
                    # 成功后关闭窗口
                    if switch_win:
                        self.root.after(0, switch_win.destroy)
                else:
                    self.root.after(0, lambda: self.log(f"❌ 模型切换失败", "error"))
                    # 失败后恢复按钮
                    if switch_win:
                        def restore():
                            status_label.config(text="切换失败", fg=self.colors["error"])
                            apply_btn.config(state="normal")
                            cancel_btn.config(state="normal")
                        self.root.after(0, restore)
            except Exception as e:
                self.root.after(0, lambda: self.log(f"❌ 模型切换失败: {e}", "error"))
                if switch_win:
                    def restore():
                        status_label.config(text="切换失败", fg=self.colors["error"])
                        apply_btn.config(state="normal")
                        cancel_btn.config(state="normal")
                    self.root.after(0, restore)
        threading.Thread(target=switch, daemon=True).start()

    def _load_openclaw_version(self):
        """异步加载 openclaw 版本"""
        def load():
            version = self._get_openclaw_version()
            self.root.after(0, lambda: self.version_label.config(text=version))
        threading.Thread(target=load, daemon=True).start()

    def _get_openclaw_version(self):
        """获取 openclaw 版本"""
        try:
            result = subprocess.run("openclaw --version", shell=True, capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                # 输出格式: OpenClaw 2026.3.11 (29dc654)
                return result.stdout.strip().replace("OpenClaw ", "")
        except:
            pass
        return "未知"

    def _check_openclaw_update(self):
        """后台检查 openclaw 更新"""
        def check():
            try:
                result = subprocess.run("openclaw update --dry-run", shell=True, capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    output = result.stdout
                    current = None
                    target = None
                    for line in output.split('\n'):
                        if 'Current version:' in line:
                            current = line.split(':')[-1].strip()
                        elif 'Target version:' in line:
                            target = line.split(':')[-1].strip()
                    if current and target and current != target:
                        self.root.after(0, lambda: self._show_update_hint(target))
            except:
                pass
        threading.Thread(target=check, daemon=True).start()

    def _show_update_hint(self, new_version):
        """显示更新提示"""
        current_text = self.version_label.cget("text")
        self.version_label.config(text=f"{current_text}  ⬆ 有新版本 {new_version}")

        # 添加点击链接
        hint_label = tk.Label(self.version_label.master, text="(查看更新内容)",
                              font=(UI_FONT, 10), bg=self.colors["card"], fg="#60a5fa", cursor="hand2")
        hint_label.pack(side="left", padx=5)
        hint_label.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/openclaw/openclaw/releases"))
        hint_label.bind("<Enter>", lambda e: hint_label.config(fg="#93c5fd"))
        hint_label.bind("<Leave>", lambda e: hint_label.config(fg="#60a5fa"))

    def stop_guard(self):
        self.is_running = False
        self.log(">>> 执行强制清理序列...")
        def kill_logic():
            subprocess.run("openclaw gateway stop", shell=True, capture_output=True)
            if IS_MAC:
                subprocess.run("pkill -9 openclaw", shell=True, capture_output=True)
                subprocess.run("lsof -ti:18789 | xargs kill -9", shell=True, capture_output=True)
            elif IS_WIN:
                subprocess.run("taskkill /F /IM openclaw.exe", shell=True, capture_output=True)
                subprocess.run('for /f "tokens=5" %a in (\'netstat -aon ^| findstr :18789\') do taskkill /f /pid %a', shell=True, capture_output=True)
            if self.process: self.process.terminate()
            self.root.after(0, self._ui_reset)
            self.root.after(0, lambda: self.log("✅ 系统已重置"))
        threading.Thread(target=kill_logic, daemon=True).start()

    def _ui_reset(self):
        self.start_btn.config(state="normal")
        self.is_running = False
        self.tray.set_status(False)
        self.update_status(False)
        self.url_label.config(text="暂无地址", fg=self.colors["text_dim"])

    def load_config(self):
        """加载配置，返回配置字典"""
        config = configparser.ConfigParser()
        result = {"notify_channel": "feishu", "ids": {}}
        if os.path.exists(self.config_file):
            config.read(self.config_file)
            result["notify_channel"] = config.get("Settings", "notify_channel", fallback="feishu")
            # 加载各频道 ID
            for key in self.CHANNEL_NAME_MAP.keys():
                result["ids"][key] = config.get("Settings", f"{key}_id", fallback="")
            # 兼容旧配置
            if not result["ids"].get("feishu"):
                result["ids"]["feishu"] = config.get("Settings", "TargetUser", fallback="")
        return result

    def save_config(self):
        """保存配置"""
        config = configparser.ConfigParser()
        config["Settings"] = {"notify_channel": self.config.get("notify_channel", "feishu")}
        for key, value in self.config["ids"].items():
            config["Settings"][f"{key}_id"] = value
        with open(self.config_file, "w") as f:
            config.write(f)

    def _get_openclaw_json_path(self):
        """获取 openclaw.json 路径"""
        return os.path.join(os.path.expanduser("~"), ".openclaw", "openclaw.json")

    def _load_openclaw_channels(self):
        """从 openclaw.json 读取频道列表，返回 [(key, enabled), ...]"""
        json_path = self._get_openclaw_json_path()
        if not os.path.exists(json_path):
            return []
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            channels = data.get("channels", {})
            result = []
            for key, cfg in channels.items():
                enabled = cfg.get("enabled", False) if isinstance(cfg, dict) else False
                result.append((key, enabled))
            return result
        except Exception:
            return []

    def _get_enabled_channel(self):
        """获取当前启用的频道 key 列表"""
        channels = self._load_openclaw_channels()
        return [key for key, enabled in channels if enabled]

    def _set_channels_enabled(self, enabled_keys):
        """设置哪些频道为 enabled"""
        json_path = self._get_openclaw_json_path()
        if not os.path.exists(json_path):
            return
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            channels = data.get("channels", {})
            for key in channels:
                if isinstance(channels[key], dict):
                    channels[key]["enabled"] = (key in enabled_keys)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _get_channel_display_name(self, key):
        """获取频道显示名称"""
        return self.CHANNEL_NAME_MAP.get(key, key)

    def _update_notify_summary(self):
        """更新状态通知摘要显示"""
        notify_channel = self.config.get("notify_channel", "feishu")
        channel_name = self._get_channel_display_name(notify_channel)
        target_id = self.config["ids"].get(notify_channel, "")
        if target_id:
            display_id = target_id if len(target_id) <= 20 else target_id[:17] + "..."
            self.notify_summary_label.config(text=f"{channel_name}: {display_id}", fg=self.colors["success"])
        else:
            self.notify_summary_label.config(text=f"{channel_name}: 未配置ID", fg=self.colors["text_dim"])

    def _update_channel_summary(self):
        """更新消息频道摘要显示"""
        enabled_channels = self._get_enabled_channel()
        if enabled_channels:
            names = [self._get_channel_display_name(k) for k in enabled_channels]
            self.channel_summary_label.config(text="、".join(names), fg=self.colors["success"])
        else:
            channels = self._load_openclaw_channels()
            if channels:
                self.channel_summary_label.config(text="未启用任何频道", fg=self.colors["text_dim"])
            else:
                self.channel_summary_label.config(text="暂未配置任何频道", fg=self.colors["text_dim"])

    def open_notify_config_window(self):
        """打开状态通知配置窗口"""
        config_win = tk.Toplevel(self.root)
        config_win.title("状态通知配置")
        win_height = 450 if IS_WIN else 360
        x = self.root.winfo_x() + 175
        y = self.root.winfo_y() + 150
        config_win.geometry(f"550x{win_height}+{x}+{y}")
        config_win.resizable(False, False)
        config_win.configure(bg=self.colors["bg"])

        c = self.colors

        # 标题
        tk.Label(config_win, text="状态通知配置", font=(UI_FONT, 14, "bold"),
                 bg=c["bg"], fg=c["text"], pady=15).pack()

        # 提示说明
        tk.Label(config_win, text="用于发送系统启动、重启等状态通知消息，配置接收通知的平台和用户ID",
                 font=(UI_FONT, 10), bg=c["bg"], fg=c["text_dim"], wraplength=500).pack(pady=(0, 10))

        # 频道选择
        channel_frame = tk.Frame(config_win, bg=c["card"], padx=20, pady=15)
        channel_frame.pack(fill="x", padx=20, pady=(0, 10))

        tk.Label(channel_frame, text="通知频道", font=(UI_FONT, 12),
                 bg=c["card"], fg=c["text_dim"]).pack(anchor="w")

        channel_var = tk.StringVar(value=self.config.get("notify_channel", "feishu"))
        radio_frame = tk.Frame(channel_frame, bg=c["card"])
        radio_frame.pack(fill="x", pady=(8, 0))

        for key, name in self.CHANNEL_NAME_MAP.items():
            rb = tk.Radiobutton(radio_frame, text=name, variable=channel_var, value=key,
                                font=(UI_FONT, 11), bg=c["card"], fg=c["text"],
                                selectcolor=c["accent"], activebackground=c["card"], activeforeground=c["text"])
            rb.pack(side="left", padx=(0, 20))

        # 各频道 ID 输入
        id_frame = tk.Frame(config_win, bg=c["card"], padx=20, pady=15)
        id_frame.pack(fill="x", padx=20, pady=(0, 10))

        id_entries = {}
        for key, name in self.CHANNEL_NAME_MAP.items():
            row = tk.Frame(id_frame, bg=c["card"])
            row.pack(fill="x", pady=5)
            id_label = self.CHANNEL_ID_LABEL_MAP.get(key, f"{name}用户 ID")
            tk.Label(row, text=id_label, font=(UI_FONT, 11), bg=c["card"], fg=c["text_dim"], width=12, anchor="w").pack(side="left")
            entry = tk.Entry(row, bg=c["accent"], fg="white", insertbackground="white",
                             font=(UI_FONT, 11), borderwidth=0, highlightthickness=1,
                             highlightbackground=c["accent"], highlightcolor=c["highlight"])
            entry.insert(0, self.config["ids"].get(key, ""))
            entry.pack(side="left", fill="x", expand=True, padx=(10, 0), ipady=5)
            id_entries[key] = entry

        # 按钮区
        btn_frame = tk.Frame(config_win, bg=c["bg"])
        btn_frame.pack(pady=20)

        def do_save():
            self.config["notify_channel"] = channel_var.get()
            for key, entry in id_entries.items():
                self.config["ids"][key] = entry.get().strip()
            self.save_config()
            self._update_notify_summary()
            self.log("💾 状态通知配置已保存")
            config_win.after(10, config_win.destroy)

        ttk.Button(btn_frame, text="保存", command=do_save).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="取消", command=lambda: config_win.after(10, config_win.destroy)).pack(side="left", padx=5)

    def open_channel_config_window(self):
        """打开消息频道配置窗口（多选）"""
        channels = self._load_openclaw_channels()
        if not channels:
            self.log("❌ 未发现任何频道配置，请先配置 ~/.openclaw/openclaw.json", "error")
            return

        config_win = tk.Toplevel(self.root)
        config_win.title("消息频道配置")
        # 根据频道数量调整高度
        base_height = 220 if IS_WIN else 180
        win_height = base_height + len(channels) * 35
        config_win.geometry(f"350x{win_height}")
        config_win.resizable(False, False)
        config_win.configure(bg=self.colors["bg"])
        x = self.root.winfo_x() + 225
        y = self.root.winfo_y() + 150
        config_win.geometry(f"+{x}+{y}")

        c = self.colors

        # 标题
        tk.Label(config_win, text="启用消息频道", font=(UI_FONT, 14, "bold"),
                 bg=c["bg"], fg=c["text"], pady=15).pack()

        # 提示说明
        tk.Label(config_win, text="选择启用哪些频道接收用户消息",
                 font=(UI_FONT, 10), bg=c["bg"], fg=c["text_dim"]).pack(pady=(0, 10))

        # 频道多选
        check_frame = tk.Frame(config_win, bg=c["card"], padx=20, pady=15)
        check_frame.pack(fill="x", padx=20)

        enabled_keys = self._get_enabled_channel()
        check_vars = {}
        for key, _ in channels:
            name = self._get_channel_display_name(key)
            var = tk.BooleanVar(value=(key in enabled_keys))
            cb = tk.Checkbutton(check_frame, text=name, variable=var,
                                font=(UI_FONT, 11), bg=c["card"], fg=c["text"],
                                selectcolor=c["accent"], activebackground=c["card"], activeforeground=c["text"])
            cb.pack(anchor="w", pady=3)
            check_vars[key] = var

        # 按钮区
        btn_frame = tk.Frame(config_win, bg=c["bg"])
        btn_frame.pack(pady=20)

        def do_save():
            selected = [key for key, var in check_vars.items() if var.get()]
            self._set_channels_enabled(selected)
            self._update_channel_summary()
            self.log("💾 消息频道配置已保存")
            config_win.after(10, config_win.destroy)

        ttk.Button(btn_frame, text="保存", command=do_save).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="取消", command=lambda: config_win.after(10, config_win.destroy)).pack(side="left", padx=5)

    def setup_menu(self):
        menubar = tk.Menu(self.root)
        tools = tk.Menu(menubar, tearoff=0)
        tools.add_command(label="发送测试消息", command=self.open_test_msg_window)
        tools.add_separator()
        tools.add_command(label="清空日志区", command=self.clear_log)
        menubar.add_cascade(label="工具", menu=tools)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于作者", command=self.show_about)
        menubar.add_cascade(label="关于", menu=help_menu)
        self.root.config(menu=menubar)

    def open_test_msg_window(self):
        test_win = tk.Toplevel(self.root)
        test_win.title("发送测试消息")
        win_height = 260 if IS_WIN else 220
        test_win.geometry(f"400x{win_height}")
        test_win.resizable(False, False)
        test_win.configure(bg=self.colors["bg"])
        x = self.root.winfo_x() + 200
        y = self.root.winfo_y() + 180
        test_win.geometry(f"+{x}+{y}")

        c = self.colors

        # 频道选择
        tk.Label(test_win, text="选择频道:", font=(UI_FONT, 12), bg=c["bg"], fg=c["text"]).pack(pady=(15, 5))
        channel_var = tk.StringVar(value=self.config.get("notify_channel", "feishu"))
        channel_frame = tk.Frame(test_win, bg=c["bg"])
        channel_frame.pack()
        for key, name in self.CHANNEL_NAME_MAP.items():
            rb = tk.Radiobutton(channel_frame, text=name, variable=channel_var, value=key,
                                font=(UI_FONT, 11), bg=c["bg"], fg=c["text"],
                                selectcolor=c["accent"], activebackground=c["bg"], activeforeground=c["text"])
            rb.pack(side="left", padx=10)

        # 内容输入
        tk.Label(test_win, text="输入测试内容:", font=(UI_FONT, 12), bg=c["bg"], fg=c["text"]).pack(pady=(15, 5))
        entry = tk.Entry(test_win, font=(UI_FONT, 12), width=35, bg=c["accent"], fg="white", insertbackground="white")
        entry.insert(0, "这是一条来自控制台的测试消息")
        entry.pack(padx=20, pady=5, ipady=5)
        entry.focus_set()

        def perform_send():
            content = entry.get().strip()
            channel = channel_var.get()
            target_id = self.config["ids"].get(channel, "").strip()
            if not target_id:
                channel_name = self._get_channel_display_name(channel)
                self.log(f"❌ {channel_name}未配置用户ID", "error")
                test_win.after(10, test_win.destroy)
                return
            if content:
                self._send_msg_to_channel(channel, f"🔔 [控制台测试]\n内容: {content}")
                test_win.after(10, test_win.destroy)

        ttk.Button(test_win, text="立即发送", command=perform_send).pack(pady=20)

    def show_about(self):
        about_win = tk.Toplevel(self.root)
        about_win.title("关于 OpenClawGUI")
        win_height = 220 if IS_WIN else 180
        about_win.geometry(f"350x{win_height}")
        about_win.resizable(False, False)
        about_win.configure(bg=self.colors["bg"])
        x = self.root.winfo_x() + 225
        y = self.root.winfo_y() + 180
        about_win.geometry(f"+{x}+{y}")

        tk.Label(about_win, text="OpenClawGUI 控制台", font=(UI_FONT, 14, "bold"),
                 bg=self.colors["bg"], fg=self.colors["text"], pady=15).pack()
        tk.Label(about_win, text="作者：iWgang", font=(UI_FONT, 12),
                 bg=self.colors["bg"], fg=self.colors["text_dim"]).pack()

        link = tk.Label(about_win, text="Github: github.com/iwgang", fg="#60a5fa",
                        font=(UI_FONT, 11), bg=self.colors["bg"])
        link.pack(pady=10)
        link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/iwgang"))
        link.bind("<Enter>", lambda e: link.config(fg=self.colors["highlight"]))
        link.bind("<Leave>", lambda e: link.config(fg="#60a5fa"))

        ttk.Button(about_win, text="关闭", command=lambda: about_win.after(10, about_win.destroy)).pack(pady=10)

    def _send_msg(self, msg):
        """发送状态通知消息"""
        channel = self.config.get("notify_channel", "feishu")
        self._send_msg_to_channel(channel, msg)

    def _send_msg_to_channel(self, channel, msg):
        """发送消息到指定频道"""
        target_id = self.config["ids"].get(channel, "").strip()
        if not target_id:
            return
        channel_name = self._get_channel_display_name(channel)
        target_prefix = self.CHANNEL_TARGET_PREFIX.get(channel, "")
        full_target = f"{target_prefix}{target_id}"

        self.log(f">>> [通知] 推送{channel_name}消息...", "info")

        def _send():
            try:
                clean_msg = msg.replace("\r\n", "\\n").replace("\n", "\\n")
                subprocess.run(f'openclaw message send --channel {channel} --target "{full_target}" --message "{clean_msg}"',
                               shell=True, capture_output=True, text=True)
                self.root.after(0, lambda: self.log(f"✅ {channel_name}通知已送达", "success"))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"❌ {channel_name}通知失败: {e}", "error"))
        threading.Thread(target=_send, daemon=True).start()

    def _send_feishu_msg(self, msg):
        """兼容旧调用，转发到 _send_msg"""
        self._send_msg(msg)

    def hide_window(self):
        self.root.withdraw()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        if IS_MAC:
            try:
                from AppKit import NSApp
                NSApp.activateIgnoringOtherApps_(True)
            except (ImportError, AttributeError):
                pass

    def _setup_mac_dock_handler(self):
        """设置 macOS Dock 点击处理"""
        try:
            from AppKit import NSApp, NSObject, NSApplicationActivationPolicyRegular
            from Foundation import NSObject
            import objc

            gui_self = self

            class AppDelegate(NSObject):
                def applicationShouldHandleReopen_hasVisibleWindows_(self, app, hasVisibleWindows):
                    gui_self.root.after(10, gui_self.show_window)
                    return True

            delegate = AppDelegate.alloc().init()
            NSApp.setDelegate_(delegate)
            # 保持引用防止被回收
            self._app_delegate = delegate
        except (ImportError, Exception):
            pass

    def quit_app(self):
        if self.is_running:
            self.is_running = False
            subprocess.run("openclaw gateway stop", shell=True, capture_output=True)
            if IS_MAC:
                subprocess.run("pkill -9 openclaw", shell=True, capture_output=True)
                subprocess.run("lsof -ti:18789 | xargs kill -9", shell=True, capture_output=True)
            elif IS_WIN:
                subprocess.run("taskkill /F /IM openclaw.exe", shell=True, capture_output=True)
            if self.process: self.process.terminate()
        self.tray.stop()
        self.root.quit()


# --- 托盘管理器 (pystray) ---
class TrayManager:
    def __init__(self, gui_callback):
        import pystray
        from PIL import Image

        self.pystray = pystray
        self.gui_callback = gui_callback
        self.icon = None
        self._running = False

        # 图标路径
        if getattr(sys, 'frozen', False):
            if hasattr(sys, '_MEIPASS'):
                base_dir = sys._MEIPASS
            else:
                base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        self.icon_on_path = os.path.join(base_dir, "icons", "tray_icon_on.png")
        self.icon_off_path = os.path.join(base_dir, "icons", "tray_icon_off.png")

        self.icon_on = self._load_icon(self.icon_on_path)
        self.icon_off = self._load_icon(self.icon_off_path)

    def _load_icon(self, path):
        from PIL import Image
        if os.path.exists(path):
            return Image.open(path)
        # 创建默认图标
        img = Image.new('RGB', (64, 64), color='gray')
        return img

    def start(self):
        menu = self.pystray.Menu(
            self.pystray.MenuItem("显示控制面板", self._show_panel, default=True),
            self.pystray.Menu.SEPARATOR,
            self.pystray.MenuItem("启动服务", self._start_service),
            self.pystray.MenuItem("停止服务", self._stop_service),
            self.pystray.Menu.SEPARATOR,
            self.pystray.MenuItem("彻底退出", self._quit_app)
        )

        self.icon = self.pystray.Icon("OpenClawGUI", self.icon_off, "OpenClawGUI", menu)
        self._running = True
        threading.Thread(target=self._run_icon, daemon=True).start()

    def _run_icon(self):
        self.icon.run()

    def stop(self):
        self._running = False
        if self.icon:
            self.icon.stop()

    def set_status(self, running):
        if self.icon:
            if running:
                self.icon.icon = self.icon_on
            else:
                self.icon.icon = self.icon_off

    def _show_panel(self):
        self.gui_callback("SHOW")

    def _start_service(self):
        self.gui_callback("START")

    def _stop_service(self):
        self.gui_callback("STOP")

    def _quit_app(self):
        self.gui_callback("QUIT")


if __name__ == "__main__":
    root = tk.Tk()
    gui = None
    cmd_queue = queue.Queue()

    def handle_tray_command(cmd):
        # 将命令放入队列，由主线程处理
        cmd_queue.put(cmd)

    def process_queue():
        # 主线程轮询队列处理命令
        try:
            while True:
                cmd = cmd_queue.get_nowait()
                if gui is None:
                    continue
                if cmd == "SHOW":
                    gui.show_window()
                elif cmd == "START":
                    gui.start_guard()
                elif cmd == "STOP":
                    gui.stop_guard()
                elif cmd == "QUIT":
                    gui.quit_app()
                    return  # 退出后不再继续轮询
        except queue.Empty:
            pass
        root.after(100, process_queue)  # 每 100ms 检查一次队列

    tray = TrayManager(handle_tray_command)
    tray.start()

    gui = OpenClawGUI(root, tray)
    root.after(100, process_queue)  # 启动队列轮询
    root.mainloop()
