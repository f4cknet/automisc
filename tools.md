# tools.md — AutoMisc 外部工具清单

> **角色**：automisc 可调用的**外部 misc 工具** + **安装指引**单一事实来源
> **状态**：v0.1 启动 + 2026-06-13 分支重整（per `prd.md §4.1 v0.1.0b`）
> **配套文档**：
> - [`AGENTS.md`](./AGENTS.md) — 项目治理
> - [`prd.md`](./prd.md) — 需求 + 任务看板 + 入口分流（[`§5 工具池`](./prd.md) + [`§6 入口分流表`](./prd.md)）
> - [`Architecture.md`](./Architecture.md) — 系统架构 + adapter 模式（[`§3 Core 调度层`](./Architecture.md) + [`§4 工具池层`](./Architecture.md) + [`§6 plug-in 机制`](./Architecture.md)）
>
> **本文档章节**：
> - §0 阅读指引
> - §1 状态图例
> - §2 工具池分类总表（按分支）
> - §3 按分支工具清单（含状态 + 安装指引）
> - §4 Python 包清单（含状态）
> - §5 入口分流与工具路由对照
> - §6 P0 工具优先级（v0.1 必须有 adapter）
> - §7 工具池后续演进（v0.5 / v1.0）
> - §8 变更日志

---

## 0. 阅读指引

| 你是谁 | 先看哪节 |
|---|---|
| **想快速了解工具池覆盖** | §2 总表 + §6 P0 优先级 |
| **想知道某个工具是否已装** | §3 按分支查 |
| **想装某个工具** | §3 安装指引列 |
| **想知道 Python 依赖装了什么** | §4 |
| **想看哪些工具对应哪个 subflow** | §5 |
| **v0.1 必须先做哪几个 adapter** | §6（P0 工具）|

---

## 1. 状态图例

| 图标 | 含义 | 处理建议 |
|---|---|---|
| ✅ | PATH 可直接 `subprocess.run([...])` 调用 | v0.1 直接写 adapter |
| ⚠️ | 源码/jar 在但需额外配置（pyenv shim / python2 wrapper / 需 brew 额外依赖）| v0.1 可写 adapter（带 wrapper 脚本） |
| ❌ | 未安装 / 源码缺失 | v0.1 不写 adapter；按 §3 安装指引手动装 |

> **判断标准**：本表状态基于 macOS 当前环境（2026-06-13 实测 `which` + `import` 抽查）。

---

## 2. 工具池分类总表（按分支 · per `prd.md §4.1 v0.1.0b`）

> **2026-06-13 重大调整**：从"按工具能力分类"（图片隐写/流量/压缩/内存/编码/二进制/音频/文档/二维码 9 个）改为**按"用户面对的题目类型"分支**。

```
MISC（根）
├── Forensics（取证）                  ← 独立分支
│   ├── Memory Forensics（内存取证）
│   ├── Disk Forensics（磁盘取证）
│   ├── Network Forensics（流量取证）
│   └── Log Forensics（日志取证）
├── Steganography（隐写术）
│   ├── Image Stego（图片隐写）
│   ├── Audio Stego（音频隐写）
│   └── Video Stego（视频隐写）
├── Encoding（编码分析）               ← 自编写函数，无外部工具
│   ├── Base 系列
│   ├── 古典密码
│   └── 自定义编码
└── Misc Others（其他）
    ├── 压缩包分析
    ├── Office 文档
    └── 脑洞题
```

**删去的旧分类**（per [`prd.md §3.2`](./prd.md) 非范围硬约束 + 用户决策）：
- ❌ OSINT（开源情报）—— 与 automisc"完全离线"产品定位冲突
- ❌ Blockchain（区块链）—— automisc 不做
- ❌ Games & VMs（游戏题 / VM 题）—— automisc 不做
- ❌ 二进制分析（独立 subflow）—— `strings/file/binwalk/xxd` 等基础工具下沉到各分支共享

**精简后的统计**：

| 一级分支 | 子分支数 | 工具总数（✅/⚠️/❌）| v0.1 P0 adapter |
|---|---|---|---|
| **Forensics** | 4 | 14（6✅ / 1⚠️ / 7❌）| 6 |
| **Steganography** | 3 | 22（9✅ / 1⚠️ / 12❌）| 8 |
| **Encoding** | 3 | **0**（内置实现）| 0 |
| **Misc Others** | 3 | 10（5✅ / 0⚠️ / 5❌）| 3 |
| **共享基础工具** | — | 8（8✅）| 5 |
| **合计** | 14 | 54（28✅ / 2⚠️ / 24❌）| **22** |

> **v0.1 P0 实际 adapter 数**：22 个（远超 `prd.md §4.1 v0.1.6` 的 ≥5 要求）。**按 `AGENTS.md §2.1` 任务粒度（≤400 行 / PR），22 个 P0 adapter 必须分多个 PR 实施，建议每 PR 5-7 个 adapter**。

---

## 3. 按分支工具清单

### 3.1 Forensics / Memory Forensics（内存取证）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **vol.py (Volatility 2)** | ⚠️ | `misc/volatility2/`（原目录丢失，软链 `automisc/extend_tools/volatility2` 为空）| 内存镜像取证（profiles + plugins）| **v0.1 必须恢复安装**（blocker） |
| **vol3 (Volatility 3)** | ❌ | `pip install volatility3` | 现代内存取证 | v0.5 安装 |
| **strings** | ✅ | `/usr/bin/strings` | 内存字符串提取（含 FLAG / SSH_CLIENT / SESSION_KEY）| P0 |
| **binwalk** | ✅ | `/usr/local/bin/binwalk` | 内存镜像内嵌文件提取 | P0 |

### 3.2 Forensics / Disk Forensics（磁盘取证）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **fls / icat / mmls（sleuthkit）** | ❌ | `brew install sleuthkit` | 磁盘镜像文件系统解析（FAT16/NTFS/ext2/...）| v0.5 安装 |
| **photorec** | ✅ | `/usr/local/bin/photorec` | 文件雕刻 + 分区恢复 | P1 · v0.5 候选 |
| **testdisk** | ✅ | `/usr/local/bin/testdisk` | 分区恢复 + 文件系统修复 | P1 · v0.5 候选 |
| **7z** | ✅ | `/usr/local/bin/7z` | 磁盘镜像（VMDK/OVA）解压 | P1 |
| **kpartx / losetup** | ❌ | macOS 通过 `hdiutil attach` 替代 | Linux 专用，macOS 用 `hdiutil` | 不装 |
| **veracrypt** | ❌ | `brew install --cask veracrypt` | TrueCrypt/VeraCrypt 卷挂载 | v1.0 评估 |

### 3.3 Forensics / Network Forensics（流量取证）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **tshark** | ✅ | `/usr/local/bin/tshark` | CLI 抓包 + 协议解析 + `--export-objects http` | P0 · v0.1 必须 |
| **tcpdump** | ✅ | `/usr/sbin/tcpdump` | 原始抓包（速度优先）| P0 · v0.1 必须 |
| **wireshark** | ✅ | `/Applications/Wireshark.app/Contents/MacOS/wireshark` | GUI 流量分析（GUI 调用）| P1 · v0.5 候选 |
| **pcapfix** | ❌ | `brew install pcapfix` | 损坏 pcap 修复（缺 magic bytes / 校验和）| v0.5 安装 |
| **aircrack-ng** | ❌ | `brew install aircrack-ng` | WiFi WPA/WEP 破解 | v0.5 安装 |
| **multimon-ng** | ❌ | `brew install multimon-ng` | DTMF / POCSAG 解码 | v0.5 安装 |
| **scapy** | ❌ | `pip install scapy` | Python pcap 操作 | v0.5 安装 |
| **impacket** | ❌ | `pip install impacket` | NTLMv2 / Kerberos 解析（PCAP 中的 hashcat 提取）| v0.5 安装 |

### 3.4 Forensics / Log Forensics（日志取证）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **grep / awk / sed / sort / uniq** | ✅ | macOS 自带 | 日志关键字 + 异常分析 | P0 |
| **evtx_dump** | ✅ | `misc/evtx_dump`（PyPI: `python-evtx`）| Windows .evtx 事件日志解析 | P0 · v0.1 必须 |
| **python-evtx（Python 包）** | ❌ | `pip install python-evtx` | .evtx 解析（提供 `evtx_dump`）| v0.1 必须装 |
| **7z** | ✅ | `/usr/local/bin/7z` | 解压 .evtx.bz2 / .log.tar.gz 等压缩日志 | 共享 |
| **journalctl（macOS N/A）** | ❌ | Linux 专用 | systemd 日志 | 不装 |

### 3.5 Steganography / Image Stego（图片隐写）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **binwalk** | ✅ | `/usr/local/bin/binwalk` | 嵌入文件检测 + 提取 | P0 |
| **zsteg** | ✅ | `/usr/local/bin/zsteg`（**Ruby gem**，不是 Python 包）| PNG/BMP LSB 全通道检测 | P0 |
| **steghide** | ✅ | `~/.local/bin/steghide` | JPEG/BMP/WAV/AU 隐写（口令）| P0 |
| **outguess** | ✅ | `/usr/local/bin/outguess` | JPEG 隐写 | P1 · v0.5 候选 |
| **stegdetect** | ✅ | `~/.local/bin/stegdetect` | JPEG 隐写检测（jsteg/OutGuess/F5/AppendX）| P1 · v0.5 候选 |
| **stegseek** | ✅ | `~/.local/bin/stegseek` | steghide 高速口令爆破 | P1 · v0.5 候选 |
| **pngcheck** | ✅ | `/usr/local/bin/pngcheck` | PNG chunk 结构验证 + IDAT / tEXt 分析 | P1 · v0.5 候选 |
| **foremost** | ✅ | `/usr/local/bin/foremost` | 图片嵌入文件雕刻 | P0 |
| **exiftool** | ✅ | `/usr/local/bin/exiftool` | EXIF 元数据（GPS / Make / Model / Software）| P0 |
| **F5-steganography** | ⚠️ | `misc/F5-steganography/`（已软链 `automisc/extend_tools/`）| JPEG F5 DCT 系数提取 + 解密 | 需 `java` + 手写 wrapper |
| **stegolsb** | ❌ | `pip install stegolsb` | 通用 LSB 隐写 | v0.5 安装 |
| **stegano** | ❌ | `pip install stegano` | 高级 LSB 工具 | v0.5 安装 |
| **stegcracker** | ❌ | `pip install stegcracker` | steghide 字典爆破 | v0.5 安装 |
| **apngdis** | ❌ | `brew install apngdis` | APNG 帧提取 | v0.5 安装 |
| **deepsound** | ❌ | Windows 工具（Wine）| DeepSound 隐写提取 | v1.0 评估 |

### 3.6 Steganography / Audio Stego（音频隐写）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **ffmpeg** | ✅ | `/usr/local/bin/ffmpeg` | 音频转码 + 频谱生成 + showspectrumpic 滤镜 | P0 · v0.1 必须 |
| **sox** | ❌ | `brew install sox` | 音频处理 + spectrogram 生成 + `sox -m` 多轨减法 | P0 · v0.1 必须装 |
| **audacity** | ❌ | `brew install --cask audacity` | GUI 音频分析（GUI 调用）| v0.5 安装 |
| **sonic-visualiser** | ❌ | `brew install --cask sonic-visualiser` | GUI 频谱分析 | v0.5 安装 |
| **MP3Stego** | ⚠️ | `misc/MP3Stego/`（源码）| MP3 隐写（口令）| 需编译 `Decode.exe`（Wine） |
| **steghide** | ✅ | `~/.local/bin/steghide` | WAV/AU 隐写 | 共享 |
| **deepsound2john.py** | ❌ | GitHub `deepsound2john.py` | DeepSound 哈希提取给 John | v1.0 评估 |

### 3.7 Steganography / Video Stego（视频隐写）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **ffmpeg** | ✅ | `/usr/local/bin/ffmpeg` | 视频帧提取 + 多 stream 分离 + `ffprobe` | P0 · v0.1 必须 |
| **ffprobe** | ✅ | `/usr/local/bin/ffprobe` | 多 stream 视频元数据查询 | P0 |
| **vlc** | ❌ | `brew install --cask vlc` | GUI 视频播放（GUI 调用，验证视觉）| v0.5 安装 |
| **MP4Box（GPAC）** | ❌ | `brew install gpac` | MP4 容器解析 | v0.5 安装 |
| **mediainfo** | ❌ | `brew install mediainfo` | 视频元数据 | v0.5 安装 |

### 3.8 Encoding（编码分析 · 自编写）

> **无外部工具依赖**，全部走 Python 标准库 + `core/encoders/` 内置实现。
>
> 实现位置见 [`Architecture.md §3.5 可疑点扫描器`](./Architecture.md) + [`Architecture.md §4.4` 工具池层 + encoders 子目录](./Architecture.md)。

**实现类（Python 内置）**：

#### 3.8.1 Base 系列（`core/encoders/base.py`）

- base16 / base32 / base58 / base62 / base64 / base85 / base91
- base2048 / base32768 / base65536（CTF 罕见但出现过，per ctf-misc/encodings.md）
- `xxencode` / `yenc` / `uuencode`（古典）

#### 3.8.2 古典密码（`core/encoders/classical.py`）

- ROT13 / ROT47 / ROT18（ROT13 on letters + ROT5 on digits）
- Caesar brute force（穷举 26 个 shift）
- Vigenère（已知 key / 不知道 key）
- Atbash / Pigpen / Keyboard Shift（per ctf-misc/encodings.md）
- Affine / Rail Fence

#### 3.8.3 自定义编码（`core/encoders/custom.py`）

- BCD（Binary-Coded Decimal，每个 nibble 一位十进制）
- IEEE 754 Float（`struct.pack('>f', value)` 还原 4 字节 ASCII）
- UTF-16 endianness reversal（utf-16-LE ↔ utf-16-BE）
- Unicode Tags（U+E0000-U+E007F）/ Variation Selector Supplement（U+E0100-U+E01EF）
- Multi-layer auto-decoder（hex 优先于 base64，per ctf-misc/encodings.md）

**Python 依赖**：

| 包 | 状态 | 用途 | 备注 |
|---|---|---|---|
| **base65536** | ❌ | base65536 编解码 | v0.5 安装 |

### 3.9 Misc Others / Archive（压缩包分析）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **7z** | ✅ | `/usr/local/bin/7z` | 全格式解压（zip/rar/7z/tar.gz/bz2/xz）| P0 · v0.1 必须 |
| **unzip** | ✅ | `/usr/bin/unzip` | zip 解压 + 伪加密检查 | P0 |
| **file** | ✅ | `/usr/bin/file` | magic 识别压缩类型 | P0 |
| **john** | ❌ | `brew install john-jumbo` | 4-6 位数字爆破（zip/rar）| P0 · v0.1 必须装 |
| **hashcat** | ❌ | `brew install hashcat` | GPU 加速破解（zip/rar 哈希）| v0.5 安装 |
| **zipcrack.py** | ⚠️ | `misc/zipcrack.py`（未软链）| 纯 Python zip 4-6 位爆破 | v0.1 作为 john 缺失的 fallback |
| **rar / unrar** | ❌ | `brew install rar` | rar 创建 / 解压（区别于 unrar-only）| v0.5 安装 |

### 3.10 Misc Others / Office（文档分析）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **exiftool** | ✅ | `/usr/local/bin/exiftool` | Office/PDF 元数据 + 隐藏字段 | P0 |
| **binwalk** | ✅ | `/usr/local/bin/binwalk` | 文档内嵌文件检测 | P0 |
| **pdftotext** | ⚠️ | `brew install poppler` 后 `/usr/local/bin/pdftotext` | PDF 文本提取 | v0.1 通过 exiftool + binwalk 间接覆盖，pdftotext 可选 |
| **mutool** | ❌ | `brew install mupdf-tools` | PDF 重组 + 对象提取（xref 隐藏页）| v0.5 安装 |
| **python-docx** | ✅ | `python3 -c "import docx"` ✅ | .docx 解析（XML 结构 + 隐藏文字 + macro）| v0.5 候选 |

### 3.11 Misc Others / Brainteaser（脑洞题）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **Python 标准库** | ✅ | macOS 自带 | 字符串/字符操作 + struct + re | 全部脑洞题 base |
| **z3-solver** | ❌ | `pip install z3-solver` | 约束求解（约束编码 / Boolean gate network）| v0.5 安装 |
| **PIL（Pillow）** | ✅ | `python3 -c "import PIL"` ✅ | 像素级脑洞题（图片当数据）| 已装 Python 包 |
| **qrcode / segno / pyzbar** | ❌ | `pip install qrcode segno pyzbar` | QR 生成 / 解析 / 重组 | v0.5 安装 |

### 3.12 共享基础工具（不挂 subflow · 各分支通用）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **strings** | ✅ | `/usr/bin/strings` | 提取可打印字符串（跨所有 binary 类文件）| P0 · 通用 |
| **file** | ✅ | `/usr/bin/file` | magic 识别（跨所有文件）| P0 · 通用 |
| **xxd** | ✅ | `/usr/bin/xxd` | hex dump / hex ↔ binary | P0 · 通用 |
| **hexdump** | ✅ | `/usr/bin/hexdump` | hex dump（BSD 风格）| P1 · 通用 |
| **grep** | ✅ | macOS 自带 | 文本搜索（flag / ctf / key）| P0 · 通用 |
| **exiftool** | ✅ | `/usr/local/bin/exiftool` | 元数据（跨图片 / Office / 部分 PDF）| P0 · 通用 |
| **foremost** | ✅ | `/usr/local/bin/foremost` | 文件雕刻（跨所有 binary 类文件）| P0 · 通用 |
| **scalpel** | ❌ | `brew install scalpel` | 高效文件雕刻（foremost 备选）| v0.5 安装 |

---

## 4. Python 包清单

| 包 | 状态 | 用途 | 备注 |
|---|---|---|---|
| **PIL（Pillow）** | ✅ | 图像读取 + LSB 提取 + 像素脑洞 | P0 |
| **pwn（pwntools）** | ✅ | 通用 CTF 工具库（含 base64/hex/远程交互）| P0 |
| **lxml** | ✅ | XML 解析（OOXML / Plist / Kitty 协议）| P1 |
| **docx（python-docx）** | ✅ | .docx 解析 | P1 |
| **numpy** | ❌ | 数值计算 + 图像处理（频谱 / FFT）| P0 · `pip install numpy` |
| **requests** | ❌ | （**保留**：虽然 automisc 不联网，但保留供 CTFd API 等离线场景使用，per [`prd.md §3.3`](./prd.md) 占位说明）| P1 · `pip install requests` |
| **z3-solver** | ❌ | 约束求解（约束编码 / Boolean gate network）| P0 · `pip install z3-solver` |
| **matplotlib** | ❌ | 频谱图 + 直方图绘图 | P1 · `pip install matplotlib` |
| **scipy** | ❌ | 信号处理 + 频谱分析（FFT / 时频分析）| P1 · `pip install scipy` |
| **magic（python-magic-bin）** | ❌ | file 类型识别（macOS 用 `python-magic-bin`）| P0 · `pip install python-magic-bin` |
| **dnslib** | ❌ | DNS 解析（DNS 隐写题 / dnscat2 reassembly）| P1 · `pip install dnslib` |
| **zsteg（**注意：实为 Ruby gem**）** | ✅（PATH） | PNG/BMP LSB（不在 Python 包）| 已在 §3.5 修正 |
| **Crypto（pycryptodome）** | ❌ | 古典密码 + AES/DES | P1 · `pip install pycryptodome` |
| **pikepdf** | ❌ | PDF 操作 + 解密 | P1 · `pip install pikepdf` |
| **zstandard** | ❌ | zstd 解压（CTF 偶尔出现）| P1 · `pip install zstandard` |
| **mutagen** | ❌ | 音频元数据 | P1 · `pip install mutagen` |
| **segno / pyzbar / qrcode** | ❌ | QR 生成 / 解析 | P2 · `pip install segno pyzbar qrcode` |
| **stegano / stegolsb / stegcracker** | ❌ | 高级 LSB + 爆破 | P2 · `pip install stegano stegolsb stegcracker` |
| **base65536** | ❌ | base65536 编码 | P1 · `pip install base65536` |
| **python-evtx** | ❌ | .evtx 事件日志解析（提供 `evtx_dump` CLI）| P0 · v0.1 必须 `pip install python-evtx` |

> **自动检测范围**：v0.1 启动时，Core 调度层应在启动时调用 `check_dependencies()`，对 §6 P0 工具做可达性检查，缺失时 GUI 提示并降级（而非阻塞启动）。

---

## 5. 入口分流与工具路由对照

> 完整入口分流表见 [`prd.md §6`](./prd.md)。本节是分流表 → 工具池的"反向索引"。

| subflow（来自 `prd.md §6`）| 推荐初始工具（来自本文件）| fallback 工具 |
|---|---|---|
| **Memory Forensics** | vol.py + strings + binwalk | vol3 / photorec（雕刻）|
| **Disk Forensics** | 7z（解 VMDK/OVA）+ photorec + testdisk | sleuthkit（fls/icat）/ veracrypt |
| **Network Forensics** | tshark + tcpdump + file | wireshark（GUI 辅助）/ pcapfix / scapy |
| **Log Forensics** | grep + awk + sed + evtx_dump | 7z（解压 .evtx.bz2）+ python-evtx |
| **Image Stego** | exiftool + zsteg + foremost + binwalk | steghide / outguess / stegdetect / stegseek / F5 |
| **Audio Stego** | ffmpeg（频谱）| sox / audacity / DeepSound / MP3Stego |
| **Video Stego** | ffmpeg + ffprobe（多 stream 提取）| vlc（视觉验证）/ MP4Box / mediainfo |
| **Encoding** | （**内置实现**）`core/encoders/base.py` + `classical.py` + `custom.py` | 全部内置，无外部依赖 |
| **Archive** | 7z + unzip + file | john（爆破）/ hashcat（GPU 爆破）/ zipcrack.py |
| **Office** | exiftool + binwalk + python-docx | pdftotext / mutool |
| **Brainteaser** | Python 标准库 + z3-solver + Pillow | 全部脑洞题通用 base |
| **未知二进制** | file + strings + binwalk + foremost + xxd | exiftool / scalpel / hexdump |

---

## 6. P0 工具优先级（v0.1 必须有 adapter）

> **依据** [`prd.md §4.1 v0.1.6`](./prd.md)：v0.1 必须落地 **≥5 个 adapter**。
> **当前实际 P0 工具数：22 个**（覆盖全部 11 个 subflow）。

### 6.1 P0 工具清单（22 个 · 按 subflow 排列）

| # | 工具 | 分支 / 子分支 | 安装依赖 |
|---|---|---|---|
| 1 | **binwalk** | Stego/Image + Forensics/Memory + 通用 | ✅ 已装 |
| 2 | **strings** | Forensics/Memory + 通用 | ✅ 已装 |
| 3 | **foremost** | Stego/Image + 通用 | ✅ 已装 |
| 4 | **exiftool** | Stego/Image + Misc/Office + 通用 | ✅ 已装 |
| 5 | **tshark** | Forensics/Network | ✅ 已装 |
| 6 | **tcpdump** | Forensics/Network | ✅ 已装 |
| 7 | **file** | Misc/Archive + 通用 | ✅ 已装 |
| 8 | **7z** | Forensics/Disk + Misc/Archive + Forensics/Log | ✅ 已装 |
| 9 | **steghide** | Stego/Image + Stego/Audio | ✅ 已装 |
| 10 | **zsteg** | Stego/Image | ✅ 已装（Ruby gem） |
| 11 | **ffmpeg** | Stego/Audio + Stego/Video | ✅ 已装 |
| 12 | **ffprobe** | Stego/Video | ✅ 已装 |
| 13 | **unzip** | Misc/Archive | ✅ 已装 |
| 14 | **xxd** | 通用 | ✅ 已装 |
| 15 | **grep** | Forensics/Log + 通用 | ✅ 已装 |
| 16 | **evtx_dump** | Forensics/Log | ⚠️ 需 `pip install python-evtx` |
| 17 | **vol.py** | Forensics/Memory | ⚠️ **必须先恢复 vol2 安装** |
| 18 | **john** | Misc/Archive | ❌ v0.1 必须装 `brew install john-jumbo` |
| 19 | **zbar** | Misc/Brainteaser（QR）| ❌ v0.1 必须装 `brew install zbar` |
| 20 | **sox** | Stego/Audio | ❌ v0.1 必须装 `brew install sox` |
| 21 | **python-magic-bin** | 通用（file 类型识别 Python）| ❌ v0.1 必须 `pip install python-magic-bin` |
| 22 | **numpy** | 通用（图像/频谱处理）| ❌ v0.1 必须 `pip install numpy` |

### 6.2 P0 实施顺序（按 PR 拆分 · per `AGENTS.md §2.1` ≤400 行/PR）

| PR | 任务 | adapter 数 | 依赖 |
|---|---|---|---|
| **v0.1.0b-PR1** | 共享基础工具（binwalk / strings / file / xxd / foremost / exiftool）| 6 | 无 |
| **v0.1.0b-PR2** | Stego/Image 主工具（zsteg / steghide / binwalk 复用）| 2 | 复用 PR1 |
| **v0.1.0b-PR3** | Forensics/Network（tshark / tcpdump）| 2 | 无 |
| **v0.1.0b-PR4** | Stego/Audio+Video（ffmpeg / ffprobe）| 2 | 无 |
| **v0.1.0b-PR5** | Misc/Archive（7z / unzip / john 安装 + adapter）| 3 | 无 |
| **v0.1.0b-PR6** | Forensics/Log（grep / evtx_dump + python-evtx 安装）| 2 | python-evtx 安装 |
| **v0.1.0b-PR7** | Forensics/Memory（vol.py 恢复 + adapter）| 1 | vol.py 恢复安装（blocker） |
| **v0.1.0b-PR8** | Misc/Brainteaser QR（zbar 安装 + adapter）| 1 | zbar 安装 |
| **v0.1.0b-PR9** | Python 包：python-magic-bin + numpy 安装 + 基础依赖 | 3 | pip 安装 |

> **判断**：v0.1 阶段 22 个 P0 adapter 分 9 个 PR，平均每 PR 2-3 个 adapter，远低于 400 行限制。

### 6.3 Encoding（自编写）的 P0 实现

| 模块 | 内容 | 估时 |
|---|---|---|
| `core/encoders/base.py` | base16/32/58/62/64/85/91 + base2048/32768/65536 | 2h |
| `core/encoders/classical.py` | ROT13/47/18 + Caesar brute force + Vigenère + Atbash + Pigpen + Keyboard Shift + Affine + Rail Fence | 3h |
| `core/encoders/custom.py` | BCD + IEEE 754 + UTF-16 endianness + Unicode Tags + Variation Selector + Multi-layer auto-decoder | 3h |
| `core/encoders/__init__.py` + unit test | 注册 + 测试 | 1h |
| **小计** | | **9h** |

> Encoding 不算 adapter，是 Core 内部能力，**不计入 §6.2 P0 PR 拆分**。

---

## 7. 工具池后续演进

### 7.1 v0.5（per [`prd.md §10.2`](./prd.md)）

- P1 工具批量追加：outguess / stegdetect / stegseek / pngcheck / sleuthkit / pcapfix / aircrack-ng / multimon-ng / scapy / impacket / hashcat / mutool / python-evtx / sox / audacity / sonic-visualiser / vlc / MP4Box / mediainfo / zbar / qrencode / apngdis / scalpel
- Python 包补齐：numpy / requests / matplotlib / scipy / python-magic-bin / dnslib / pycryptodome / pikepdf / zstandard / mutagen / base65536 / z3-solver / segno / pyzbar / qrcode / stegano / stegolsb / stegcracker

### 7.2 v1.0（per [`prd.md §10.3`](./prd.md)）

- DAG 编排要求工具输出**结构化 type system**（per [`Architecture.md §9.1`](./Architecture.md) 兼容点）
- 每个 adapter 补 `outputs: list[str]` 字段（per [`Architecture.md §9.2`](./Architecture.md)）
- DeepSound + Wine 集成评估（macOS 上的可行性）
- Encoding 子模块补全：RSA / AES / SM4 / Brainfuck / Ook! / Malbolge / Piet（per ctf-misc/encodings.md）

---

## 8. 变更日志

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-06-13 | 1.0 | 初版：扫描 `ctf-forensics/` + `ctf-misc/` md + 当前 macOS 环境 `which` + Python 包抽查，按 9 个 subflow 分类 |
| 2026-06-13 | **2.0** | **重大分支重整**（per `prd.md §4.1 v0.1.0b`）：从"按工具能力分类"改为"按用户面对的题目类型分支"——MISC / Forensics (4) / Steganography (3) / Encoding (内置) / Misc Others (3) = **11 个 subflow**，54 个工具（28✅ / 2⚠️ / 24❌）。**删去**：OSINT / Blockchain / Games & VMs（与 automisc 完全离线定位冲突）。**合并下沉**：原"二进制分析"独立 subflow 降为"共享基础工具"；原"文档分析"归入 Misc Others / Office。**新增 P0**：22 个 adapter（远超 ≥5 要求），分 9 个 PR 实施。**Encoding 自编写**：明确无外部工具依赖，3 个 Python 模块（base / classical / custom）共 9h |
| 2026-06-13 | **2.1** | **v0.1.0b-PR1 实施完成**：实现共享基础工具 6 个 adapter（`tools/shared/{file,strings,binwalk,foremost,exiftool,xxd}.py`）；**61 pytest unit tests 100% PASS**；端到端 smoke 命中关键可疑点（flag/PNG magic/base64/file_header）；CLI 入口 `python -m automisc tools list` + `python -m automisc run --tool X --file Y` 可用。**未做**：PR2-PR9（Stego/Network/Audio+Video/Archive/Log/Memory/Brainteaser/Python 包）按 §6.2 计划待实施 |

---

> **最后一条**：
> 本文档是 automisc 工具池的**单一事实来源**。任何"我要装什么 / 缺什么 / 怎么调"问题先查这里。
> 任务看板在 [`prd.md §3`](./prd.md) + adapter 实现规范在 [`Architecture.md §6`](./Architecture.md)。