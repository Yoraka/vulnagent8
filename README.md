# Agno CLI (`agno-cli`)

`agno-cli` 是一个命令行工具，旨在帮助开发者快速搭建、配置和管理 Agno 项目的本地开发环境，包括后端工作空间和前端 Agent UI。

## 功能

- **环境检查**：检查必要的依赖项，如 Docker, Python, Node.js, Git 等。
- **后端工作空间管理**：
    - 配置 `.env` 文件 (特别是 `TARGET_CODE_PATH`)。
    - 初始化 `secrets` 目录并提示配置 API Key 和 Base URL。
    - 创建 Python 虚拟环境 (`aienv`)。
    - 安装 `agno` Python 包。
    - 执行 `ag ws setup` 来设置工作空间。
    - 启动 (`ag ws up`) 和停止 (`ag ws down`) 后端服务。
- **前端 Agent UI 管理**：
    - 使用 `npx create-agent-ui@latest` 在指定目录安装前端项目。
    - 检查并确保 `npm install` 已运行。
    - 提供启动前端开发服务器的指令。
- **配置持久化**：CLI 会将工作空间路径和前端项目路径等配置保存在用户目录 (`~/.config/agno-cli/settings.json`)，方便后续命令使用。

## 安装

### 前提条件

在运行此 CLI 之前，请确保您的系统上已安装以下软件：

- Python 3.7+ (以及 pip)
- Node.js (以及 npm/npx)
- Docker Desktop (需要正在运行)
- Git

您可以通过 `agno-cli check-env` 命令检查这些依赖项。

### 从源码运行

1.  确保您有 `agno_cli.py` 文件。
2.  安装 `click` 库 (如果尚未安装):
    ```bash
    pip install click
    ```
3.  直接运行脚本:
    ```bash
    python agno_cli.py --help
    ```
    或者，您可以赋予其执行权限 (`chmod +x agno_cli.py`) 并将其放在 PATH 中的某个目录（或为其创建符号链接），以便像普通命令一样调用 (例如 `agno-cli --help`)。

### (未来) 通过 pip 安装 (如果打包)

```bash
pip install agno-cli
```
(注意: 这只是一个示例，实际包名和发布方式可能不同。)

## 使用方法

### 主要命令

#### 1. 全局设置 (`setup`)

这是推荐的首次运行命令，它会引导您完成所有必要的检查、配置和安装步骤。

```bash
python agno_cli.py setup [OPTIONS]
```

**选项:**

-   `--workspace-path PATH, -w PATH`: Agno 后端工作空间的根目录路径。如果 CLI 配置中已存在，则优先使用配置值，否则提示输入 (默认为当前目录 `.`)。
-   `--frontend-dir PATH, -f PATH`: 前端 Agent UI 项目的安装**父**目录。CLI 将在此目录下创建 `agent-ui` 项目。如果已配置则使用配置值，否则提示输入 (默认为 `~/agno-frontend-projects`)。
-   `--target-code-path PATH, -t PATH`: 待审查的项目代码库的绝对路径 (会写入后端 `.env` 文件)。如果提供，则直接使用；否则会在配置后端时提示输入。
-   `--api-key TEXT`: API Key (例如 OpenAI API Key)。如果提供，则直接使用；否则会在配置后端时提示输入。
-   `--base-url TEXT`: API Base URL。如果提供，则直接使用；否则会在配置后端时提示输入。

**示例:**

```bash
# 交互式设置，CLI 会提示输入未提供的路径和配置
python agno_cli.py setup

# 提供所有路径和部分配置
python agno_cli.py setup -w ./my-agno-workspace -f ~/my-frontend-setups -t /path/to/my/code-to-inspect --api-key "sk-..."
```

#### 2. 环境检查 (`check-env`)

单独运行环境依赖检查。

```bash
python agno_cli.py check-env
```

#### 3. 后端管理 (`backend`)

```bash
python agno_cli.py backend --help
```

-   **`backend configure`**: 配置后端工作空间的 `.env` 和 `secrets`。
    ```bash
    python agno_cli.py backend configure [-w PATH] [-t TARGET_PATH] [--api-key KEY] [--base-url URL]
    ```
-   **`backend install`**: 安装后端依赖 (创建venv, 安装 `agno`, 运行 `ag ws setup`)。
    ```bash
    python agno_cli.py backend install [-w PATH]
    ```
-   **`backend start`**: 启动后端服务 (`ag ws up`)。
    ```bash
    python agno_cli.py backend start [-w PATH]
    ```
-   **`backend stop`**: 停止后端服务 (`ag ws down`)。
    ```bash
    python agno_cli.py backend stop [-w PATH]
    ```

#### 4. 前端管理 (`frontend`)

```bash
python agno_cli.py frontend --help
```

-   **`frontend install`**: 安装前端 Agent UI。
    ```bash
    python agno_cli.py frontend install [-f FRONTEND_PARENT_DIR]
    ```
    安装完成后，CLI 会提供手动启动前端开发服务器的指令。
-   **`frontend whereis`**: 显示已配置的前端 Agent UI 项目的安装路径。
    ```bash
    python agno_cli.py frontend whereis
    ```

### 配置文件

CLI 会在 `~/.config/agno-cli/settings.json` (Linux/macOS) 或对应的用户配置目录 (Windows) 下存储以下信息：

-   `backend_workspace_path`: 后端工作空间的绝对路径。
-   `frontend_base_path`: 前端 Agent UI 安装的父目录的绝对路径。
-   `frontend_project_path`: 前端 Agent UI 项目的实际绝对路径 (例如 `frontend_base_path/agent-ui`)。

这些配置使得您在后续运行命令时不必每次都指定路径。

## 开发与贡献

(TODO: 添加关于如何为此 CLI 开发和贡献的说明)

## 注意事项

-   **YAML 文件编辑**: 当前版本的 CLI 在配置后端 `dev_app_secret.yaml` 时，会提示用户输入 API Key 和 Base URL，但**不会自动将这些值写入 YAML 文件**。用户需要根据提示手动检查并更新该文件。这是为了避免因自动修改复杂 YAML 结构而引入错误。
-   **`npx` 交互**: `npx create-agent-ui@latest` 命令在执行时可能会有交互式提示 (例如， "Ok to proceed? (y)"). CLI 会尝试自动输入 "y"，但请留意终端输出以防需要手动干预。
-   **错误处理**: CLI 包含了基本的错误捕获和提示，但如果遇到未预期的问题，请检查终端输出获取详细信息。

## 许可证

(TODO: 添加许可证信息，例如 MIT)
```
