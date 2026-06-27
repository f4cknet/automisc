# extend-tools/

> AutoMisc 跨平台外部 binary 分发（per **v0.5-platform-extend-tools** 治理变更 2026-06-27）
>
> 详见 [`../upgrade/v0.5-platform-extend-tools.md`](../upgrade/v0.5-platform-extend-tools.md)

---

## 这是啥？

AutoMisc 的 GUI 在 macOS 上 `automisc-gui` 直接跑就行（Homebrew 装工具）。在 Windows 上没有 brew，本目录**自带 4 个核心 binary** 让 Owner 跑 `pwsh ./extend-tools/install.ps1` 一次就齐活。

## 目录布局

```
extend-tools/
├── bin/
│   ├── win-x64/        Windows binaries（install.ps1 自动下载，不入 git）
│   └── macos/          macOS 暂留空（brew 优先，v0.5+ 评估）
├── manifest.yaml       工具 URL + SHA256 + 版本（入 git）
├── install.ps1         Windows 自动下载脚本（幂等，已下跳过）
├── install.sh          macOS 自动下载脚本（暂留 stub）
└── README.md           ← 本文件
```

## Windows 用户首次跑

```powershell
cd D:\hacktools\misc\automisc
pwsh ./extend-tools/install.ps1
# 等待 ~30s ~ 2min（取决于网速），下载完成即可跑 automisc-gui
```

**幂等**：第二次跑直接跳过已下好的（按文件存在判定）。

**失败处理**：单个工具下载失败不影响其他，最后汇总报告。

## 4 个核心工具

| 工具 | 用途 | 来源 | 大小 |
|---|---|---|---|
| **binwalk** | 扫描嵌入文件（per magic bytes） | [ReFirmLabs GitHub release](https://github.com/ReFirmLabs/binwalk/releases) | ~5MB |
| **exiftool** | 提取 EXIF / Office / PDF metadata | [exiftool.org](https://exiftool.org) standalone | ~10MB |
| **7zr** | 通用归档 (zip/7z/rar/tar/gz/bz2/xz 等 30+ 格式) | [7-zip.org](https://www.7-zip.org) 独立版 | ~1MB |
| **foremost** | 按 magic bytes 雕刻并分离嵌入文件 | [raddyfiy/foremost](https://github.com/raddyfiy/foremost) 第三方 fork | ~1MB |

## Windows 限制（已知 gap）

| 工具 | Windows 处理 | 替代 |
|---|---|---|
| **steghide** | ❌ 不可用（无官方 Windows 版） | v0.5+ 评估 Cygwin 编译 |
| **zsteg** | ❌ 不装（要 Ruby 300MB+） | 自研 `lsb_detect` 替代（v0.5-lsb-detector） |
| **stegseek** | ❌ 不可用（steghide 同款） | 跟 steghide 一起评估 |

**实际影响**：Windows 上 **JPEG / WAV / AU 有口令隐写题目做不了**（无 steghide）。PNG LSB 隐写 OK（lsb_detect 替代）。

## macOS 用户

**完全无感**：Homebrew 装的工具在 `/usr/local/bin` 或 `/opt/homebrew/bin`，`tools/paths.py:resolve_tool_binary` 先查 PATH，命中就走 PATH。

`bin/macos/` 目录暂留空。如果你想纯 extend-tools 跑（不装 brew），v0.5+ 评估。

## 升级工具版本

1. 改 `manifest.yaml` 的 `version` + `url`（新版本）
2. 删 `extend-tools/bin/win-x64/<tool>.exe`
3. 跑 `pwsh ./extend-tools/install.ps1`（会自动算 SHA256 写回 manifest）
4. 跑 `automisc-gui` 验证

## 故障排查

**Q: install.ps1 报"无法解析 manifest.yaml"**
A: 确认 manifest.yaml 存在且格式正确。手动检查：`Get-Content extend-tools/manifest.yaml`

**Q: 下载超时 / GitHub 限速**
A: 单个工具失败不影响其他；最终汇总报告。手动下：复制 manifest.yaml 的 url 到浏览器，保存到 `extend-tools/bin/win-x64/<tool>.exe`

**Q: 跑 GUI 工具还是报"找不到"**
A: 检查 `<tool>.exe` 是否在 `extend-tools/bin/win-x64/`；再跑一次 `automisc tools list` 看 adapter 是否注册（registry 层 vs binary 层是两回事）

**Q: 7z adapter 找不到 binary**
A: `bin/win-x64/7zr.exe` 是 7-Zip 独立版文件名；adapter 期望 `7z.exe`。`install.ps1` 会自动建 symlink `7z.exe → 7zr.exe`，如果失败手动：`cmd /c "mklink 7z.exe 7zr.exe"`（在 win-x64 目录里）

## 跟治理的关系

本目录是 **AGENTS.md §2.3 macOS only → multi-platform** 治理变更的产物（per §8 治理变更流程）。提案见 [`upgrade/v0.5-platform-extend-tools.md`](../upgrade/v0.5-platform-extend-tools.md)。