#!/usr/bin/env bash
# extend-tools/install.sh
# AutoMisc 跨平台 extend-tools macOS 安装脚本 (per v0.5-platform-extend-tools 治理变更)
#
# 用法:
#   cd /path/to/automisc
#   ./extend-tools/install.sh
#
# v0.5 阶段: macOS 优先 Homebrew (extend-tools/ 暂留空)
#   brew install binwalk exiftool p7zip foremost
#   brew install ruby  # 如果要装 zsteg (可选, 推荐用 lsb_detect 替代)
#   gem install zsteg # 可选
#
# v0.5+ 评估: macOS extend-tools/ 实装 (跟 win-x64/ 同样结构)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BIN_DIR="$REPO_ROOT/extend-tools/bin/macos"

echo "=== AutoMisc extend-tools macOS 安装 (v0.5-platform-extend-tools) ==="
echo ""
echo "策略: Homebrew 优先, extend-tools/bin/macos/ 暂留空"
echo ""

# 检查 brew
if ! command -v brew &> /dev/null; then
    echo "⚠️  Homebrew 未安装, 请先装 Homebrew:" >&2
    echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"" >&2
    exit 1
fi

# 推荐安装的 4 个核心工具
BREW_TOOLS=("binwalk" "exiftool" "p7zip" "foremost")

echo "推荐 Homebrew 装 4 个核心工具:"
for tool in "${BREW_TOOLS[@]}"; do
    if command -v "$tool" &> /dev/null; then
        echo "  ✓ $tool (已装)"
    else
        echo "  ↓ $tool (待装)"
    fi
done
echo ""

# 自动装缺失的（可选，避免破坏 brew 用户已有配置）
read -p "自动装缺失的工具? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    for tool in "${BREW_TOOLS[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            echo "[brew install] $tool ..."
            brew install "$tool"
        fi
    done
    echo ""
    echo "✓ 全部完成"
else
    echo "跳过安装, 手动跑: brew install ${BREW_TOOLS[*]}"
fi

echo ""
echo "验证: python -m automisc tools list  (应该能看到所有 adapter)"
echo "GUI: automisc-gui"