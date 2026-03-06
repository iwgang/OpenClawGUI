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


class OpenClawGUI:
    def __init__(self, root, tray_manager):
        self.root = root
        self.tray = tray_manager

        # 标题显示系统版本
        os_name = "macOS" if IS_MAC else "Windows"
        self.root.title(f"OpenClawGUI 控制台 v1.1 ({os_name})")

        # 环境路径补丁 (macOS)
        if IS_MAC:
            os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + os.environ.get("PATH", "")

        if getattr(sys, 'frozen', False):
            self.current_dir = os.path.dirname(sys.executable)
        else:
            self.current_dir = os.path.dirname(os.path.abspath(__file__))

        self.config_file = os.path.join(self.current_dir, "config.ini")
        self.is_running = False
        self.process = None
        self.has_notified = False

        self.window_width = 800
        self.window_height = 600
        self.center_window()
        self.setup_menu()
        self.setup_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        # macOS: 点击 Dock 图标时恢复窗口
        if IS_MAC:
            self.root.createcommand('tk::mac::ReopenApplication', lambda: self.root.after(10, self.show_window))
            self._setup_mac_dock_handler()

    def center_window(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{self.window_width}x{self.window_height}+{(sw-self.window_width)//2}+{(sh-self.window_height)//2}")

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
        style.configure("TButton", padding=(12, 6), font=(UI_FONT, 12))
        style.map("TButton",
            background=[("active", c["accent"]), ("!active", c["card"])],
            foreground=[("active", "white"), ("!active", c["text"])])
        style.configure("Start.TButton", font=(UI_FONT, 12, "bold"))
        style.map("Start.TButton",
            background=[("active", "#22c55e"), ("!active", c["success"])],
            foreground=[("active", "white"), ("!active", "#0d1117")])
        style.configure("Stop.TButton", font=(UI_FONT, 12))
        style.map("Stop.TButton",
            background=[("active", "#dc2626"), ("!active", c["highlight"])],
            foreground=[("active", "white"), ("!active", "white")])

        # 顶部标题栏
        header = tk.Frame(self.root, bg=c["bg"], pady=15)
        header.pack(fill="x", padx=20)
        tk.Label(header, text="OpenClawGUI 控制台", font=(UI_FONT, 18, "bold"),
                 bg=c["bg"], fg=c["text"]).pack(side="left")
        self.status_label = tk.Label(header, text="● 已停止", font=(UI_FONT, 12),
                                      bg=c["bg"], fg=c["text_dim"])
        self.status_label.pack(side="right")

        # 配置卡片
        config_card = tk.Frame(self.root, bg=c["card"], pady=15, padx=15)
        config_card.pack(fill="x", padx=20, pady=(0, 10))

        config_row = tk.Frame(config_card, bg=c["card"])
        config_row.pack(fill="x")
        tk.Label(config_row, text="飞书用户 ID", font=(UI_FONT, 12),
                 bg=c["card"], fg=c["text_dim"]).pack(side="left")

        self.id_entry = tk.Entry(config_row, bg=c["accent"], fg="white",
                                  insertbackground="white", font=(UI_FONT, 12),
                                  borderwidth=0, highlightthickness=1,
                                  highlightbackground=c["accent"], highlightcolor=c["highlight"])
        self.id_entry.insert(0, self.load_config())
        self.id_entry.pack(side="left", fill="x", expand=True, padx=15, ipady=6)

        ttk.Button(config_row, text="保存配置", command=self.manual_save).pack(side="right")

        # 实时运行信息
        info_card = tk.Frame(self.root, bg=c["card"], pady=12, padx=15)
        info_card.pack(fill="x", padx=20, pady=(0, 10))

        info_row1 = tk.Frame(info_card, bg=c["card"])
        info_row1.pack(fill="x", pady=(0, 6))
        tk.Label(info_row1, text="当前模型", font=(UI_FONT, 11),
                 bg=c["card"], fg=c["text_dim"]).pack(side="left")
        self.model_label = tk.Label(info_row1, text="等待启动...", font=(CODE_FONT, 11, "bold"),
                                     bg=c["card"], fg=c["text_dim"])
        self.model_label.pack(side="left", padx=15)

        info_row2 = tk.Frame(info_card, bg=c["card"])
        info_row2.pack(fill="x")
        tk.Label(info_row2, text="后台地址", font=(UI_FONT, 11),
                 bg=c["card"], fg=c["text_dim"]).pack(side="left")
        self.url_label = tk.Label(info_row2, text="暂无地址", font=(CODE_FONT, 11),
                                   bg=c["card"], fg=c["text_dim"])
        self.url_label.pack(side="left", padx=15)
        self.url_label.bind("<Button-1>", lambda e: self.open_browser())

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
        tk.Label(log_header, text="运行日志", font=(UI_FONT, 12),
                 bg=c["bg"], fg=c["text_dim"]).pack(side="left")
        clear_link = tk.Label(log_header, text="清空", font=(UI_FONT, 11),
                              bg=c["bg"], fg=c["text_dim"])
        clear_link.pack(side="right")
        clear_link.bind("<Button-1>", lambda e: self.clear_log())
        clear_link.bind("<Enter>", lambda e: clear_link.config(fg=c["highlight"]))
        clear_link.bind("<Leave>", lambda e: clear_link.config(fg=c["text_dim"]))

        # 日志显示区
        log_container = tk.Frame(self.root, bg=c["log_bg"], padx=1, pady=1)
        log_container.pack(expand=True, fill="both", padx=20, pady=(0, 15))

        self.log_area = scrolledtext.ScrolledText(
            log_container, bg=c["log_bg"], fg=c["text"],
            borderwidth=0, highlightthickness=0,
            font=(CODE_FONT, 11), wrap="word", padx=10, pady=10
        )
        self.log_area.pack(expand=True, fill="both")

        # 配置日志高亮
        self.log_area.tag_configure("success", foreground=c["success"])
        self.log_area.tag_configure("error", foreground=c["highlight"])
        self.log_area.tag_configure("info", foreground="#60a5fa")
        self.log_area.tag_configure("warning", foreground="#fbbf24")
        self.log_area.tag_configure("gateway", foreground="#a78bfa")
        self.log_area.tag_configure("time", foreground=c["text_dim"])

    def clear_log(self):
        self.log_area.delete("1.0", "end")

    def log(self, content, tag=None):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_area.insert("end", f"[{ts}] ", "time")
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

    def start_guard(self):
        if self.is_running: return
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
                                         shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in iter(self.process.stdout.readline, ''):
                if not self.is_running: break
                clean_line = self.strip_ansi(line.strip())
                if not clean_line: continue
                self.root.after(0, lambda l=clean_line: self.log(l))
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
        except Exception as e:
            self.root.after(0, lambda: self.log(f"运行时错误: {e}"))
        finally:
            self.root.after(0, self._ui_reset)

    def open_browser(self):
        url = self.url_label.cget("text")
        if url.startswith("http"):
            webbrowser.open(url)

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
        self.model_label.config(text="已停止", fg=self.colors["text_dim"])
        self.url_label.config(text="暂无地址", fg=self.colors["text_dim"])

    def load_config(self):
        config = configparser.ConfigParser()
        if os.path.exists(self.config_file):
            config.read(self.config_file)
            return config.get("Settings", "TargetUser", fallback="")
        return ""

    def manual_save(self):
        config = configparser.ConfigParser()
        config["Settings"] = {"TargetUser": self.id_entry.get()}
        with open(self.config_file, "w") as f: config.write(f)
        self.log("💾 配置保存成功")

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
        test_win.geometry("400x150")
        test_win.resizable(False, False)
        test_win.configure(bg=self.colors["bg"])
        x = self.root.winfo_x() + 200
        y = self.root.winfo_y() + 200
        test_win.geometry(f"+{x}+{y}")

        tk.Label(test_win, text="输入测试内容:", font=(UI_FONT, 12),
                 bg=self.colors["bg"], fg=self.colors["text"]).pack(pady=15)
        entry = tk.Entry(test_win, font=(UI_FONT, 12), width=35,
                         bg=self.colors["accent"], fg="white", insertbackground="white")
        entry.insert(0, "这是一条来自控制台的测试消息")
        entry.pack(padx=20, pady=5, ipady=5)
        entry.focus_set()

        def perform_send():
            content = entry.get().strip()
            if content:
                self._send_feishu_msg(f"🔔 [控制台测试]\n内容: {content}")
                test_win.destroy()

        ttk.Button(test_win, text="立即发送", command=perform_send).pack(pady=15)

    def show_about(self):
        about_win = tk.Toplevel(self.root)
        about_win.title("关于 OpenClawGUI")
        about_win.geometry("350x180")
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

        ttk.Button(about_win, text="关闭", command=about_win.destroy).pack(pady=10)

    def _send_feishu_msg(self, msg):
        target_id = self.id_entry.get().strip()
        if not target_id: return
        self.log(">>> [通知] 推送飞书消息...", "info")
        def _send():
            try:
                clean_msg = msg.replace("\r\n", "\\n").replace("\n", "\\n")
                subprocess.run(f'openclaw message send --channel feishu --target "{target_id}" --message "{clean_msg}"',
                               shell=True, capture_output=True, text=True)
                self.root.after(0, lambda: self.log("✅ 飞书通知已送达", "success"))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"❌ 飞书通知失败: {e}", "error"))
        threading.Thread(target=_send, daemon=True).start()

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
            self.pystray.MenuItem("显示控制面板", self._show_panel),
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
