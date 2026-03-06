# OpenClawGUI

OpenClaw 跨平台控制台 GUI，支持 macOS 和 Windows。

## 功能

- 启动/停止 OpenClaw 服务
- 系统托盘图标（状态指示）
- 实时日志显示（彩色高亮）
- 飞书消息通知
- 深色主题 UI

## 依赖安装

```bash
pip install pystray pillow
```

**macOS 额外安装（用于 Dock 图标点击恢复窗口）:**
```bash
pip install pyobjc-framework-Cocoa
```

## 运行

```bash
python OpenClawGUI.py
```

## 打包

**macOS:**
```bash
pyinstaller --windowed --onedir \
  --name "OpenClawGUI" \
  --icon "icons/icon.icns" \
  --add-data "icons:icons" \
  OpenClawGUI.py
```

**Windows:**
```bash
pyinstaller --windowed --onedir ^
  --name "OpenClawGUI" ^
  --icon "icons/icon.ico" ^
  --add-data "icons;icons" ^
  OpenClawGUI.py
```

打包完成后应用位于 `dist/` 目录。
