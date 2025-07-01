import click
import os
import subprocess
import platform
import json
import shutil # 用于 cp
import sys # 用于获取 python解释器路径

# --- 配置 --- #
CLI_CONFIG_DIR = os.path.expanduser("~/.config/agno-cli")
CLI_CONFIG_FILE = os.path.join(CLI_CONFIG_DIR, "settings.json")
DEFAULT_VENV_NAME = "aienv" # 后端虚拟环境名称
DEFAULT_FRONTEND_PROJECT_NAME = "agent-ui" # npx 创建的前端项目目录名

# --- 辅助函数 --- #
def ensure_cli_config_dir():
    os.makedirs(CLI_CONFIG_DIR, exist_ok=True)

def load_cli_config():
    ensure_cli_config_dir()
    if not os.path.exists(CLI_CONFIG_FILE):
        return {}
    try:
        with open(CLI_CONFIG_FILE, 'r', encoding='utf-8') as f:
            # Handle empty file case
            content = f.read()
            if not content:
                return {}
            return json.loads(content)
    except json.JSONDecodeError:
        click.echo(click.style(f"警告: CLI 配置文件 {CLI_CONFIG_FILE} 损坏或为空，将使用空配置。", fg="yellow"))
        return {}
    except Exception as e:
        click.echo(click.style(f"读取CLI配置文件时发生错误: {e}", fg="red"))
        return {}

def save_cli_config(config):
    ensure_cli_config_dir()
    try:
        with open(CLI_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        # click.echo(f"CLI配置已保存到 {CLI_CONFIG_FILE}")
    except Exception as e:
        click.echo(click.style(f"保存CLI配置文件时发生错误: {e}", fg="red"))

def get_python_executable():
    return sys.executable or "python3"

def run_command(command_list, cwd=None, env=None, shell=False, capture_output=True, text=True, check=False, input_text=None):
    """通用命令执行辅助函数"""
    if shell:
        command_to_run = ' '.join(command_list)
    else:
        command_to_run = command_list

    click.echo(f"Executing: {command_to_run} in {cwd or os.getcwd()}")
    try:
        process = subprocess.run(command_to_run, cwd=cwd, env=env, shell=shell,
                                 capture_output=capture_output, text=text, check=check,
                                 encoding='utf-8', input=input_text)
        if capture_output:
            return process.returncode == 0, process.stdout, process.stderr
        return process.returncode == 0, "", ""
    except subprocess.CalledProcessError as e:
        click.echo(click.style(f"命令执行失败 (CalledProcessError): {e}", fg="red"))
        stdout = e.stdout if hasattr(e, 'stdout') and e.stdout else ""
        stderr = e.stderr if hasattr(e, 'stderr') and e.stderr else str(e)
        return False, stdout, stderr
    except FileNotFoundError:
        cmd_name = command_list[0] if isinstance(command_list, list) else command_list.split()[0]
        click.echo(click.style(f"错误: 命令 '{cmd_name}' 未找到。请确保它已安装并在PATH中。", fg="red"))
        return False, "", f"Command not found: {cmd_name}"
    except Exception as e:
        click.echo(click.style(f"执行命令时发生未知错误: {e}", fg="red"))
        return False, "", str(e)

def get_venv_path(workspace_path, venv_name=DEFAULT_VENV_NAME):
    return os.path.join(workspace_path, venv_name)

def get_executable_in_venv(workspace_path, executable_name, venv_name=DEFAULT_VENV_NAME):
    venv_path = get_venv_path(workspace_path, venv_name)
    if platform.system() == "Windows":
        return os.path.join(venv_path, "Scripts", f"{executable_name}.exe")
    else:
        return os.path.join(venv_path, "bin", executable_name)

def run_ag_command(ag_command_parts, workspace_path, venv_name=DEFAULT_VENV_NAME):
    ag_executable = get_executable_in_venv(workspace_path, "ag", venv_name)
    if not os.path.exists(ag_executable):
        click.echo(click.style(f"错误: 'ag' 命令未在虚拟环境 {os.path.join(workspace_path, venv_name)} 中找到。", fg="red"))
        click.echo("请确保后端已正确安装 (例如通过 'agno-cli backend install')。")
        return False, "", "'ag' executable not found in venv"

    full_command = [ag_executable] + ag_command_parts
    return run_command(full_command, cwd=workspace_path, capture_output=True)

# --- Click Command Groups --- #
@click.group()
@click.pass_context
def cli(ctx):
    """Agno CLI 工具：辅助搭建、配置和管理 Agno 前后端开发环境。"""
    ctx.ensure_object(dict) # Ensure ctx.obj exists
    ctx.obj = load_cli_config()

# --- Top-level 'setup' command --- #
@cli.command()
@click.option('--workspace-path', '-w', default=None, type=click.Path(file_okay=False, dir_okay=True, resolve_path=True), help='Agno 后端工作空间的根目录路径。')
@click.option('--frontend-dir', '-f', default=None, type=click.Path(file_okay=False, dir_okay=True, resolve_path=True), help='前端 Agent UI 项目的安装父目录。')
@click.option('--target-code-path', '-t', default=None, type=click.Path(file_okay=False, dir_okay=True, resolve_path=True), help='待审查的项目代码库的绝对路径。') # removed exists=True for now, will be prompted
@click.option('--api-key', help='API Key (例如 OpenAI API Key)。')
@click.option('--base-url', help='API Base URL (如果使用自定义端点)。')
@click.pass_context
def setup(ctx, workspace_path, frontend_dir, target_code_path, api_key, base_url):
    """执行完整的环境检查、配置、前后端安装。"""
    config = ctx.obj
    click.echo(click.style("开始完整设置流程...", fg="cyan"))

    # --- 0. Determine workspace path and frontend base directory --- #
    if not workspace_path:
        workspace_path = config.get('backend_workspace_path')
        if not workspace_path:
            workspace_path = click.prompt("请输入 Agno 后端工作空间的根目录路径", default='.')
    workspace_path = os.path.abspath(workspace_path)
    # Workspace path doesn't have to exist yet if it's a git clone target, but for setup, assume it's where .env.example is.
    # os.makedirs(workspace_path, exist_ok=True) # Let's assume for now it should exist if not cloning.
    if not os.path.isdir(workspace_path): # Check if it's a directory IF it exists
         click.echo(click.style(f"警告: 后端工作空间路径 {workspace_path} 当前不是一个有效目录。后续步骤可能失败。", fg="yellow"))

    config['backend_workspace_path'] = workspace_path
    click.echo(f"后端工作空间路径设置为: {config['backend_workspace_path']}")

    if not frontend_dir:
        frontend_dir = config.get('frontend_base_path')
        if not frontend_dir:
            frontend_dir = click.prompt("请输入前端 Agent UI 项目的安装父目录", default=os.path.join(os.path.expanduser("~"), "agno-frontend-projects"))
    frontend_dir = os.path.abspath(frontend_dir)
    os.makedirs(frontend_dir, exist_ok=True)
    config['frontend_base_path'] = frontend_dir
    click.echo(f"前端基础目录设置为: {config['frontend_base_path']}")

    save_cli_config(config) # Save initial paths

    # --- 1. Environment Checks --- #
    click.echo(click.style("\n步骤 1: 环境检查", fg="blue"))
    ctx.invoke(check_env_command) # Call the check-env command

    # --- 2. Configure Backend Workspace --- #
    click.echo(click.style("\n步骤 2: 配置后端工作空间", fg="blue"))
    # Pass through explicitly provided args, otherwise they will be prompted in configure_backend_command_impl
    ctx.invoke(configure_backend_command,
               workspace_path=config['backend_workspace_path'],
               target_code_path=target_code_path, # Explicitly pass if provided
               api_key=api_key,
               base_url=base_url)


    # --- 3. Backend Installation --- #
    click.echo(click.style("\n步骤 3: 安装后端", fg="blue"))
    ctx.invoke(install_backend_command, workspace_path=config['backend_workspace_path'])

    # --- 4. Frontend Installation --- #
    click.echo(click.style("\n步骤 4: 安装前端 Agent UI", fg="blue"))
    ctx.invoke(install_frontend_command, frontend_dir_arg=config['frontend_base_path'])

    # Final save of config, though individual commands also save
    save_cli_config(config)
    click.echo(click.style("\n完整设置流程结束。", fg="cyan"))
    click.echo("请根据提示分别启动后端 (例如 'agno-cli backend start') 和前端服务。")

# --- Backend Group --- #
@cli.group("backend")
@click.pass_context
def backend_group(ctx):
    """管理后端工作空间。"""
    # Ensure config is loaded if backend commands are called directly
    if not ctx.obj:
        ctx.obj = load_cli_config()

def _ensure_backend_workspace_path(ctx, workspace_path_arg):
    config = ctx.obj
    workspace_path = workspace_path_arg or config.get('backend_workspace_path')
    if not workspace_path:
        click.echo(click.style("错误: 未找到后端工作空间路径配置。", fg="red"))
        click.echo("请先运行 'agno-cli setup' 或使用 '--workspace-path' 选项指定路径。")
        return None
    workspace_path = os.path.abspath(workspace_path)
    if not os.path.isdir(workspace_path):
        click.echo(click.style(f"错误: 配置的后端工作空间路径 '{workspace_path}' 不是一个有效目录。", fg="red"))
        return None
    # Save it back in case it was resolved via default '.' or passed via option and not saved yet
    config['backend_workspace_path'] = workspace_path
    save_cli_config(config)
    return workspace_path

@backend_group.command("configure")
@click.option('--workspace-path', '-w', default=None, type=click.Path(file_okay=False, dir_okay=True, resolve_path=True), help='Agno 后端工作空间的根目录路径。')
@click.option('--target-code-path', '-t', default=None, type=click.Path(file_okay=False, dir_okay=True, resolve_path=True), help='待审查的项目代码库的绝对路径。')
@click.option('--api-key', help='API Key。')
@click.option('--base-url', help='API Base URL。')
@click.pass_context
def configure_backend_command(ctx, workspace_path, target_code_path, api_key, base_url):
    """配置后端工作空间的 .env 和 secrets。"""
    ws_path = _ensure_backend_workspace_path(ctx, workspace_path)
    if not ws_path:
        return

    click.echo(f"开始配置后端工作空间: {ws_path}")

    # 2a. TARGET_CODE_PATH in .env
    env_example_path = os.path.join(ws_path, ".env.example")
    env_path = os.path.join(ws_path, ".env")

    if not os.path.exists(env_example_path):
        click.echo(click.style(f"警告: {env_example_path} 未找到。无法自动创建 .env。请确保工作空间结构正确。", fg="yellow"))
    elif not os.path.exists(env_path):
        try:
            shutil.copy(env_example_path, env_path)
            click.echo(f"已从 {env_example_path} 创建 {env_path}")
        except Exception as e:
            click.echo(click.style(f"错误: 无法从 {env_example_path} 复制到 {env_path}: {e}", fg="red"))
            return # Critical error

    # Get or update TARGET_CODE_PATH
    current_target_code_path_in_env = ""
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f_env_read:
                for line in f_env_read:
                    if line.strip().startswith("TARGET_CODE_PATH="):
                        current_target_code_path_in_env = line.strip().split('=', 1)[1]
                        break
        except Exception as e:
            click.echo(click.style(f"读取 {env_path} 时发生错误: {e}", fg="yellow"))

    final_target_code_path = target_code_path # Use CLI arg if provided
    if not final_target_code_path:
        final_target_code_path = click.prompt(
            "请输入待审查项目的绝对路径 (TARGET_CODE_PATH)",
            default=current_target_code_path_in_env or os.getcwd()
        )

    final_target_code_path = os.path.abspath(final_target_code_path)
    if not os.path.isdir(final_target_code_path):
        click.echo(click.style(f"错误: TARGET_CODE_PATH '{final_target_code_path}' 不是一个有效目录。", fg="red"))
        # Optionally, ask again or exit. For now, exit.
        return

    # Update .env file
    if os.path.exists(env_path):
        try:
            lines = []
            found = False
            with open(env_path, 'r', encoding='utf-8') as f_env_read:
                lines = f_env_read.readlines()

            with open(env_path, 'w', encoding='utf-8') as f_env_write:
                for i, line in enumerate(lines):
                    if line.strip().startswith("TARGET_CODE_PATH="):
                        lines[i] = f"TARGET_CODE_PATH={final_target_code_path}\n"
                        found = True
                        break
                if not found: # Add if not found
                    if lines and not lines[-1].endswith('\n'): # Ensure newline before appending
                        lines.append('\n')
                    lines.append(f"TARGET_CODE_PATH={final_target_code_path}\n")
                f_env_write.writelines(lines)
            click.echo(f"TARGET_CODE_PATH 已在 {env_path} 中设置为: {final_target_code_path}")
        except Exception as e:
            click.echo(click.style(f"更新 {env_path} 失败: {e}", fg="red"))
            return
    else:
        click.echo(click.style(f"错误: {env_path} 文件不存在，无法设置 TARGET_CODE_PATH。请先创建或确保 .env.example 存在。", fg="red"))
        return

    # 2b. secrets (dev_app_secret.yaml)
    example_secrets_dir = os.path.join(ws_path, "workspace", "example_secrets")
    secrets_dir = os.path.join(ws_path, "workspace", "secrets")
    dev_app_secret_yaml_path = os.path.join(secrets_dir, "dev_app_secret.yaml")
    example_dev_app_secret_yaml_path = os.path.join(example_secrets_dir, "dev_app_secret.yaml")

    if not os.path.exists(example_secrets_dir):
        click.echo(click.style(f"警告: 示例 secrets 目录 {example_secrets_dir} 未找到。", fg="yellow"))
    else:
        if not os.path.exists(secrets_dir):
            try:
                shutil.copytree(example_secrets_dir, secrets_dir)
                click.echo(f"已从 {example_secrets_dir} 完整复制到 {secrets_dir}")
            except Exception as e:
                click.echo(click.style(f"错误: 无法从 {example_secrets_dir} 复制到 {secrets_dir}: {e}", fg="red"))
                return
        elif not os.path.exists(dev_app_secret_yaml_path) and os.path.exists(example_dev_app_secret_yaml_path):
            # If secrets_dir exists but the specific yaml is missing, copy just that file.
            try:
                shutil.copy2(example_dev_app_secret_yaml_path, dev_app_secret_yaml_path)
                click.echo(f"已从 {example_dev_app_secret_yaml_path} 复制到 {dev_app_secret_yaml_path}")
            except Exception as e:
                 click.echo(click.style(f"无法复制 dev_app_secret.yaml: {e}", fg="red"))

    # Get API Key and Base URL
    # TODO: Implement PyYAML for safe editing if needed. For now, just collect and remind.
    final_api_key = api_key
    if not final_api_key: # Prompt if not passed as arg
        # Check dev_app_secret.yaml for existing values (rudimentary check)
        # This part would be much better with PyYAML
        existing_api_key_in_yaml = "" # Placeholder
        final_api_key = click.prompt("请输入 API Key (例如 OpenAI API Key)", default=existing_api_key_in_yaml, hide_input=True, show_default=False)

    final_base_url = base_url
    if not final_base_url:
        existing_base_url_in_yaml = "" # Placeholder
        final_base_url = click.prompt("请输入 API Base URL (如果非默认)", default=existing_base_url_in_yaml or "https://api.openai.com/v1")

    click.echo(click.style(f"请确保 API Key 和 Base URL 已正确配置在 {dev_app_secret_yaml_path}", fg="yellow"))
    click.echo(f"  API Key (您提供的): {'*' * len(final_api_key) if final_api_key else '未提供'}")
    click.echo(f"  Base URL (您提供的): {final_base_url if final_base_url else '未提供'}")
    click.echo("CLI 目前不会自动写入 YAML 文件。请手动检查并更新该文件如有必要。")

    # Save workspace_path to CLI config if it was determined here
    ctx.obj['backend_workspace_path'] = ws_path
    save_cli_config(ctx.obj)
    click.echo(click.style("后端配置完成。", fg="green"))

@backend_group.command("install")
@click.option('--workspace-path', '-w', default=None, type=click.Path(file_okay=False, dir_okay=True, resolve_path=True), help='Agno 后端工作空间的根目录路径。')
@click.pass_context
def install_backend_command(ctx, workspace_path):
    """安装后端依赖 (venv, agno, setup)。"""
    ws_path = _ensure_backend_workspace_path(ctx, workspace_path)
    if not ws_path:
        return

    click.echo(f"开始安装后端于: {ws_path}")

    venv_path = get_venv_path(ws_path)
    python_exe = get_python_executable()

    if not os.path.exists(os.path.join(venv_path, 'pyvenv.cfg')):
        click.echo(f"创建虚拟环境 {DEFAULT_VENV_NAME}...")
        success, _, err = run_command([python_exe, "-m", "venv", DEFAULT_VENV_NAME], cwd=ws_path)
        if not success:
            click.echo(click.style(f"创建虚拟环境失败: {err}", fg="red"))
            return
        click.echo(click.style("虚拟环境创建成功。", fg="green"))
    else:
        click.echo(f"虚拟环境 {venv_path} 已存在。")

    pip_executable = get_executable_in_venv(ws_path, "pip")
    click.echo("安装/更新 'agno' 包...")
    success, _, err = run_command([pip_executable, "install", "-U", "agno", "--disable-pip-version-check"], cwd=ws_path)
    if not success:
        click.echo(click.style(f"安装 'agno' 失败: {err}", fg="red"))
        return
    click.echo(click.style("'agno' 包安装/更新成功。", fg="green"))

    click.echo("执行 'ag ws setup'...")
    success, stdout, stderr = run_ag_command(["ws", "setup"], workspace_path=ws_path)
    if not success:
        click.echo(click.style(f"'ag ws setup' 执行失败。", fg="red"))
        if stderr: click.echo(f"Stderr: {stderr.strip()}")
        if stdout: click.echo(f"Stdout: {stdout.strip()}")
        return
    click.echo(click.style("'ag ws setup' 执行成功。", fg="green"))
    if stdout: click.echo(f"Output:\n{stdout.strip()}")

    save_cli_config(ctx.obj) # Save any path changes
    click.echo(click.style("后端安装完成。", fg="green"))

@backend_group.command("start")
@click.option('--workspace-path', '-w', default=None, type=click.Path(file_okay=False, dir_okay=True, resolve_path=True), help='Agno 后端工作空间的根目录路径。')
@click.pass_context
def start_backend_command(ctx, workspace_path):
    """启动后端服务 (ag ws up)。"""
    ws_path = _ensure_backend_workspace_path(ctx, workspace_path)
    if not ws_path:
        return

    click.echo(f"在 {ws_path} 中启动后端服务 ('ag ws up')...")
    click.echo("这可能需要一些时间。服务通常在后台启动 (Docker)。")
    success, stdout, stderr = run_ag_command(["ws", "up"], workspace_path=ws_path)
    if success:
        click.echo(click.style("后端启动命令 'ag ws up' 已成功派发。", fg="green"))
        click.echo("请检查 Docker Desktop 和服务日志 (e.g., 'docker logs <container_name>')。")
        click.echo("Playground 通常在 http://localhost:7777 (或其他后端配置的端口)。")
        if stdout: click.echo(f"Output:\n{stdout.strip()}")
    else:
        click.echo(click.style("'ag ws up' 执行失败。", fg="red"))
        if stderr: click.echo(f"Stderr: {stderr.strip()}")
        if stdout: click.echo(f"Stdout: {stdout.strip()}")

@backend_group.command("stop")
@click.option('--workspace-path', '-w', default=None, type=click.Path(file_okay=False, dir_okay=True, resolve_path=True), help='Agno 后端工作空间的根目录路径。')
@click.pass_context
def stop_backend_command(ctx, workspace_path):
    """停止后端服务 (ag ws down)。"""
    ws_path = _ensure_backend_workspace_path(ctx, workspace_path)
    if not ws_path:
        return

    click.echo(f"在 {ws_path} 中停止后端服务 ('ag ws down')...")
    success, stdout, stderr = run_ag_command(["ws", "down"], workspace_path=ws_path)
    if success:
        click.echo(click.style("后端停止命令 'ag ws down' 已成功执行。", fg="green"))
        if stdout: click.echo(f"Output:\n{stdout.strip()}")
    else:
        click.echo(click.style("'ag ws down' 执行失败。", fg="red"))
        if stderr: click.echo(f"Stderr: {stderr.strip()}")
        if stdout: click.echo(f"Stdout: {stdout.strip()}")

# --- Frontend Group --- #
@cli.group("frontend")
@click.pass_context
def frontend_group(ctx):
    """管理前端 Agent UI。"""
    if not ctx.obj: # Ensure config loaded if called directly
        ctx.obj = load_cli_config()

def _ensure_frontend_base_path(ctx, frontend_dir_arg):
    config = ctx.obj
    frontend_base_path = frontend_dir_arg or config.get('frontend_base_path')
    if not frontend_base_path:
        frontend_base_path = click.prompt(
            "请输入前端 Agent UI 项目的安装父目录",
            default=os.path.join(os.path.expanduser("~"), "agno-frontend-projects")
        )
    frontend_base_path = os.path.abspath(frontend_base_path)
    os.makedirs(frontend_base_path, exist_ok=True) # Ensure it exists

    config['frontend_base_path'] = frontend_base_path
    # No save_cli_config here, let calling command do it after all changes
    return frontend_base_path

@frontend_group.command("install")
@click.option('--frontend-dir', '-f', default=None, type=click.Path(file_okay=False, dir_okay=True, resolve_path=True), help='前端 Agent UI 项目的安装父目录。')
@click.pass_context
def install_frontend_command(ctx, frontend_dir_arg):
    """安装前端 Agent UI (使用 npx)。"""
    config = ctx.obj
    frontend_base_path = _ensure_frontend_base_path(ctx, frontend_dir_arg)
    if not frontend_base_path: # Should not happen if prompt is effective
        return

    click.echo(f"将在目录 {frontend_base_path} 中安装前端 Agent UI ({DEFAULT_FRONTEND_PROJECT_NAME})...")

    frontend_project_path = os.path.join(frontend_base_path, DEFAULT_FRONTEND_PROJECT_NAME)

    if os.path.isdir(frontend_project_path):
        if not click.confirm(f"目录 {frontend_project_path} 已存在。是否尝试覆盖并重新安装?", default=False):
            click.echo("安装取消。如果需要更新，请手动删除该目录或使用版本控制工具管理。")
            # Update config with existing path if not already set correctly
            if config.get('frontend_project_path') != frontend_project_path:
                 config['frontend_project_path'] = frontend_project_path
                 save_cli_config(config)
            _print_frontend_start_instructions(frontend_project_path)
            return
        else:
            click.echo(f"将删除现有目录 {frontend_project_path} 以重新安装...")
            try:
                shutil.rmtree(frontend_project_path)
            except Exception as e:
                click.echo(click.style(f"删除目录 {frontend_project_path} 失败: {e}", fg="red"))
                return

    click.echo(f"执行 'npx create-agent-ui@latest {DEFAULT_FRONTEND_PROJECT_NAME}'...")
    click.echo(click.style("npx 命令可能会提示您确认 (例如输入 'y')。请注意终端输出。", fg="yellow"))

    # For npx, it often asks "Ok to proceed? (y)". We can try to provide 'y\n'.
    # This is a common pattern for `create-react-app` like tools.
    success, stdout, stderr = run_command(
        ["npx", "create-agent-ui@latest", DEFAULT_FRONTEND_PROJECT_NAME],
        cwd=frontend_base_path,
        capture_output=True,
        input_text="y\n" # Try to auto-confirm 'y'
    )

    if not success:
        click.echo(click.style(f"前端安装失败 ('npx create-agent-ui@latest'):", fg="red"))
        if stderr: click.echo(f"Stderr: {stderr.strip()}")
        if stdout: click.echo(f"Stdout: {stdout.strip()}") # npx might put errors in stdout
        return
    click.echo(click.style(f"前端 Agent UI ('npx create-agent-ui@latest') 命令在 {frontend_project_path} 执行完毕。", fg="green"))
    if stdout and "You can now cd into the directory and run" not in stdout : # Avoid redundant messages if npx already printed instructions
        click.echo(f"Output:\n{stdout.strip()}")

    # Check node_modules (npx create-* usually runs install, but good to verify)
    node_modules_path = os.path.join(frontend_project_path, "node_modules")
    package_json_path = os.path.join(frontend_project_path, "package.json")

    if not os.path.isdir(node_modules_path) and os.path.exists(package_json_path):
        click.echo(f"'node_modules' 未找到。尝试在 {frontend_project_path} 中执行 'npm install'...")
        success_npm_install, _, err_npm_install = run_command(["npm", "install"], cwd=frontend_project_path)
        if not success_npm_install:
            click.echo(click.style(f"'npm install' 失败: {err_npm_install}", fg="red"))
            return
        click.echo(click.style("'npm install' 执行成功。", fg="green"))
    elif not os.path.exists(package_json_path):
         click.echo(click.style(f"警告: {package_json_path} 未找到。无法验证或运行 'npm install'。", fg="yellow"))
    else:
        click.echo(f"'node_modules' 目录已存在于 {frontend_project_path}。")

    config['frontend_base_path'] = frontend_base_path
    config['frontend_project_path'] = frontend_project_path
    save_cli_config(config)

    click.echo(click.style(f"前端 Agent UI 已成功准备在: {frontend_project_path}", fg="green"))
    _print_frontend_start_instructions(frontend_project_path)

def _print_frontend_start_instructions(project_path):
    click.echo("\n要启动前端开发服务器，请执行以下命令:")
    click.echo(click.style(f"  1. cd {project_path}", bold=True))
    click.echo(click.style(f"  2. npm run dev", bold=True))
    click.echo("\n启动后，您可以在浏览器中访问 http://localhost:3000。")
    click.echo("请确保后端服务已启动 (例如通过 'agno-cli backend start')。")


@frontend_group.command("whereis")
@click.pass_context
def frontend_whereis_command(ctx):
    """显示已配置的前端 Agent UI 项目的安装路径。"""
    config = ctx.obj
    frontend_proj_path = config.get('frontend_project_path')
    if frontend_proj_path and os.path.isdir(frontend_proj_path):
        click.echo(f"前端 Agent UI 项目配置的路径为: {frontend_proj_path}")
        _print_frontend_start_instructions(frontend_proj_path)
    else:
        click.echo("前端 Agent UI 尚未配置或路径无效。")
        click.echo("您可以尝试运行 'agno-cli frontend install' 或 'agno-cli setup'。")

# --- check-env command --- #
@cli.command("check-env")
@click.pass_context
def check_env_command(ctx):
    """执行环境依赖的详细检查。"""
    click.echo(click.style("开始环境检查...", fg="blue"))
    results = {}

    # 1. Network (simple ping)
    click.echo("检查网络连接 (ping 8.8.8.8)...")
    ping_cmd = ["ping", "-c", "1", "-W", "2", "8.8.8.8"] if platform.system() != "Windows" else ["ping", "-n", "1", "-w", "2000", "8.8.8.8"]
    net_success, _, _ = run_command(ping_cmd, capture_output=True)
    results["Network (ping 8.8.8.8)"] = "可达" if net_success else "不可达/超时"
    click.echo(f"  Network: {results['Network (ping 8.8.8.8)']}")

    # 2. OS
    results["OS"] = f"{platform.system()} {platform.release()}"
    click.echo(f"  OS: {results['OS']}")

    # 3. Docker
    click.echo("检查 Docker...")
    docker_version_success, dv_out, dv_err = run_command(["docker", "--version"], capture_output=True)
    results["Docker Version"] = dv_out.strip() if docker_version_success else f"未安装或未在PATH中 ({dv_err.strip()})"
    click.echo(f"  Docker Version: {results['Docker Version']}")
    if docker_version_success:
        docker_info_success, di_out, di_err = run_command(["docker", "info"], capture_output=True) # Checks daemon
        results["Docker Service"] = "运行中" if docker_info_success else f"未运行或访问受限 ({di_err.strip()})"
        click.echo(f"  Docker Service: {results['Docker Service']}")
    else:
        results["Docker Service"] = "无法检查 (Docker CLI 不可用)"
        click.echo(f"  Docker Service: {results['Docker Service']}")

    # 4. Python
    click.echo("检查 Python...")
    python_exe = get_python_executable()
    py_ver_success, pv_out, _ = run_command([python_exe, "--version"], capture_output=True)
    results["Python Version"] = pv_out.strip() if py_ver_success else "未找到"
    click.echo(f"  Python Version: {results['Python Version']}")

    # 5. Pip (assuming it's python_exe -m pip)
    click.echo("检查 Pip...")
    pip_ver_success, pip_out, _ = run_command([python_exe, "-m", "pip", "--version"], capture_output=True)
    results["Pip Version"] = pip_out.split()[1] if pip_ver_success and pip_out.split() else "未找到" # e.g. "pip 20.0.2 from ..."
    click.echo(f"  Pip Version: {results['Pip Version']}")

    # 6. Node.js
    click.echo("检查 Node.js...")
    node_ver_success, node_out, _ = run_command(["node", "--version"], capture_output=True)
    results["Node.js Version"] = node_out.strip() if node_ver_success else "未安装或未在PATH中"
    click.echo(f"  Node.js Version: {results['Node.js Version']}")

    # 7. npm
    click.echo("检查 npm...")
    npm_ver_success, npm_out, _ = run_command(["npm", "--version"], capture_output=True)
    results["npm Version"] = npm_out.strip() if npm_ver_success else "未安装或未在PATH中"
    click.echo(f"  npm Version: {results['npm Version']}")

    # 8. Git
    click.echo("检查 Git...")
    git_ver_success, git_out, _ = run_command(["git", "--version"], capture_output=True)
    results["Git Version"] = git_out.strip() if git_ver_success else "未安装或未在PATH中"
    click.echo(f"  Git Version: {results['Git Version']}")

    click.echo(click.style("\n环境检查完成。请检查以上各项是否满足项目要求。", fg="green" if all( "未" not in v and "不可达" not in v for k,v in results.items() if k != "OS") else "yellow" ))

if __name__ == '__main__':
    cli()
