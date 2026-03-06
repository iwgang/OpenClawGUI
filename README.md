# OpenClawGUI

OpenClaw 跨平台控制台 GUI，支持 macOS 和 Windows。

## 功能

- 启动/停止 OpenClaw 服务
- 系统托盘图标（状态指示）
- 实时日志显示（彩色高亮）
- 飞书消息通知
- 深色主题 UI

## 依赖安装

**macOS:**
```bash
pip install rumps pyobjc-framework-Cocoa
```

**Windows:**
```bash
pip install pystray pillow
```

**通用依赖:**
```bash
pip install pyinstaller
```

## 运行

```bash
python OpenClawGUI.py
```

## 打包

### macOS

```bash
pyinstaller --windowed --onedir \
  --name "OpenClawGUI" \
  --add-data "icons:icons" \
  OpenClawGUI.py
```

打包完成后应用位于 `dist/OpenClawGUI.app`

如有应用图标（.icns 格式），添加参数：
```bash
--icon "icons/app_icon.icns"
```

### Windows

```bash
pyinstaller --windowed --onedir ^
  --name "OpenClawGUI" ^
  --add-data "icons;icons" ^
  OpenClawGUI.py
```

打包完成后应用位于 `dist/OpenClawGUI/`

如有应用图标（.ico 格式），添加参数：
```bash
--icon "icons/app_icon.ico"
```

## 托盘图标

将以下图标放置于 `icons/` 目录：

- `tray_icon_on.png` - 服务运行中图标
- `tray_icon_off.png` - 服务停止图标

## 配置文件

`config.ini` 保存飞书用户 ID 配置，自动生成于程序目录。
