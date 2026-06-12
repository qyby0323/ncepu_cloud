# 华电云盘客户端

华电云盘客户端是一个基于 Python 和 PySide6 的桌面网盘客户端，面向华电云盘/爱数 AnyShare RESTful API。项目提供图形界面、命令行工具、同步引擎和 Windows exe 打包脚本，可用于云端文件管理、搜索、上传下载和本地目录同步。

默认服务地址：

```text
https://pan.ncepu.edu.cn
```

## Features

- 真实华电云盘 RESTful API 对接，默认 API 前缀为 `/api`。
- OAuth2 授权登录，支持授权码换取 token 与 refresh token 刷新。
- 云端文件管理：文档库入口、目录浏览、搜索、上传、下载、删除、重命名、移动、复制、新建文件夹。
- 同步任务：支持本地到云端、云端到本地、双向同步。
- 同步引擎：文件监听、事件合并、任务队列、worker 线程池、SQLite 状态库。
- 冲突处理：默认保留本地修改并生成冲突副本。
- 过滤规则：内置忽略规则、全局自定义规则、同步目录 `.syncignore`。
- 安全能力：token 脱敏日志、系统 keyring 存储、可选加密上传。
- 网络能力：HTTP/HTTPS 代理配置、超时处理、token 自动刷新。
- 打包支持：通过 PyInstaller 生成 Windows 桌面程序。
- MOCK 模式：用于离线演示和自动化测试，不替代真实 API。

## Tech Stack

- Python 3.10+
- PySide6
- httpx
- sqlite3
- watchdog
- cryptography
- keyring
- PyInstaller
- pytest / pytest-qt

## Requirements

推荐运行环境：

- Windows 10/11
- Python 3.10 至 3.12
- 可访问 `https://pan.ncepu.edu.cn`
- 如网络环境无法直连，需配置校园 VPN 或 HTTP/HTTPS 代理

说明：

- Python 3.13 下部分 Qt WebEngine 相关依赖可能没有可用 wheel，建议优先使用 Python 3.10 至 3.12。
- 主程序启动不依赖 WinFsp、Dokany 或 FUSE 等可选系统组件。

## Installation

克隆或下载项目后，在项目根目录创建虚拟环境并安装依赖：

```powershell
python -m venv hdyp
.\hdyp\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

## Usage

启动图形界面：

```powershell
python -m ncepu_cloud_client.main
```

或使用开发脚本：

```powershell
scripts\run_dev.ps1
```

如果 PowerShell 执行策略阻止脚本运行，可直接使用 Python 模块启动。

## Configuration

首次启动后会自动生成配置文件：

- Windows: `%APPDATA%\NCEPUCloudClient\config.toml`
- Linux: `~/.config/ncepu-cloud-client/config.toml`

核心配置示例：

```toml
[app]
mode = "real"
theme = "light"
language = "zh_CN"

[api]
base_url = "https://pan.ncepu.edu.cn"
api_prefix = "/api"
auth_url = "https://pan.ncepu.edu.cn"
client_id = ""
client_secret = ""
redirect_uri = "http://127.0.0.1:8765/callback"
oauth_scope = "offline openid all"
oauth_client_auth_method = "basic"
timeout_seconds = 30

[proxy]
enabled = false
http = ""
https = ""
username = ""
password = ""

[sync]
max_workers = 4
default_conflict_policy = "keep_both"
enable_delete_sync = false
enable_encryption = false
custom_ignore_rules = ""
```

登录页支持两种模式：

- `REAL`: 连接真实华电云盘，需要有效的云盘地址、Client ID 和 Client Secret。
- `MOCK`: 使用本地模拟数据，用于无网络演示和测试。

高级设置中可配置 API 前缀、认证地址、Redirect URI、OAuth Scope、OAuth 扩展参数、Token 认证方式、SSO 参数和代理。

## Authentication

真实登录使用 OAuth2 授权码流程：

1. 客户端打开华电云盘网页登录页。
2. 用户在网页登录页完成身份认证。
3. 客户端请求 `/oauth2/auth` 获取授权。
4. 授权服务器回调 `http://127.0.0.1:8765/callback` 并返回 `code`。
5. 客户端调用 `/oauth2/token` 换取 `access_token` 和 `refresh_token`。
6. token 优先保存到系统 keyring；keyring 不可用时保存到用户数据目录。

注意事项：

- 不要在源码中硬编码个人账号、密码、token 或 client secret。
- `client_id`、`client_secret`、`redirect_uri` 必须与服务端登记信息一致。
- 业务 API 请求默认使用 `Authorization: Bearer ACCESS_TOKEN`。
- 对 GET 请求，客户端可在必要时回退到 `tokenid=ACCESS_TOKEN` 查询参数。

## Command Line

安装为可编辑包后，可以使用 `ncepu-cloud` 命令：

```powershell
ncepu-cloud quota
ncepu-cloud libraries
ncepu-cloud doc-lib-quota DOC_LIB_ID
ncepu-cloud list /
ncepu-cloud search report
ncepu-cloud mkdir /documents
ncepu-cloud rename ITEM_ID new-name.docx
ncepu-cloud move ITEM_ID TARGET_DIR_ID
ncepu-cloud copy ITEM_ID TARGET_DIR_ID
ncepu-cloud delete ITEM_ID
ncepu-cloud register-client --name "NCEPU Cloud Client"
ncepu-cloud token-login ACCESS_TOKEN --refresh-token REFRESH_TOKEN
ncepu-cloud sso-login --params-json "{\"account\":\"...\"}"
```

也可以直接运行模块：

```powershell
python -m ncepu_cloud_client.cli.commands libraries
```

## Synchronization

同步任务支持三种方向：

- 本地到云端
- 云端到本地
- 双向同步

同步流程：

1. watchdog 监听本地目录变化。
2. debounce 合并短时间内的重复文件事件。
3. 同步任务进入线程安全队列。
4. worker 线程执行上传、下载或删除。
5. SQLite 保存任务状态、传输记录、远端 ID、本地路径、checksum 和冲突记录。

删除同步默认关闭。启用后，本地删除事件会根据 SQLite 中保存的远端 ID 映射提交远端删除任务。

默认冲突策略为 `keep_both`。当下载可能覆盖本地文件时，客户端会比较上次同步 checksum；如果本地文件已被修改，会保存为冲突副本，再下载云端版本到原路径。

## Ignore Rules

同步过滤规则由三部分组成：

- 内置默认规则。
- 设置页中的全局自定义规则。
- 同步目录下的 `.syncignore`。

默认会忽略临时文件、系统文件、虚拟环境、缓存目录和日志文件。规则格式兼容常见 gitignore 风格，包括空行、注释、通配符和目录规则。

## API Compatibility

真实 API adapter 位于：

```text
src/ncepu_cloud_client/api/aishu_client.py
```

当前优先适配的接口包括：

- `GET /efast/v1/entry-doc-lib`
- `GET /efast/v1/owned-doc-lib`
- `GET /efast/v1/quota/user`
- `POST /efast/v1/dir/list`
- `POST /efast/v1/file/osdownload`
- `POST /efast/v1/file/osbeginupload`
- `POST /efast/v1/file/osendupload`
- `POST /efast/v1/file/osinitmultiupload`
- `POST /efast/v1/file/osuploadpart`
- `POST /efast/v1/file/oscompleteupload`

文档库根目录支持官方文档访问结构：

```json
{
  "id": "gns://...",
  "name": "我的文档库",
  "type": "user_doc_lib"
}
```

对于权限不足或不可用的管理类兜底接口，客户端会跳过并继续使用用户可访问的文档访问接口。

## Testing

运行完整测试：

```powershell
python -m pytest
```

运行核心测试：

```powershell
python -m pytest tests\test_aishu_client_parsing.py tests\test_ui_pages.py tests\test_config.py tests\test_sync_engine.py
```

真实 API 集成测试位于 `tests/integration/`，运行前需要准备有效配置和账号权限。

## Build

使用项目脚本打包 Windows exe：

```powershell
scripts\build_exe.ps1
```

或直接运行：

```powershell
python scripts\build_exe.py --onedir
```

默认输出：

```text
dist\NCEPUCloudClient\NCEPUCloudClient.exe
```

如果默认输出目录被正在运行的程序占用，可指定新目录：

```powershell
python scripts\build_exe.py --onedir --distpath dist-new
```

图标资源：

- `image\图标.png`: 原始图标资源。
- `assets\app.ico`: exe 打包图标。
- 打包脚本会优先使用 `image\图标.png` 生成 `assets\app.ico`，并将 `assets` 与 `image` 加入 PyInstaller 资源。

## Project Structure

```text
.
├── README.md
├── AGENTS.md
├── pyproject.toml
├── requirements.txt
├── assets/
├── image/
├── scripts/
├── src/
│   └── ncepu_cloud_client/
│       ├── api/
│       ├── app/
│       ├── auth/
│       ├── cli/
│       ├── config/
│       ├── mount/
│       ├── security/
│       ├── services/
│       ├── sync/
│       ├── ui/
│       └── utils/
└── tests/
```

模块说明：

- `api/`: 真实 API adapter、mock client、错误类型和数据模型。
- `auth/`: OAuth URL 构建、网页登录流程和 token 存储。
- `config/`: 配置模型和配置文件读写。
- `sync/`: 同步引擎、任务队列、worker、数据库、冲突处理和过滤规则。
- `ui/`: PySide6 页面、窗口、组件和样式。
- `security/`: keyring 与可选加密工具。
- `scripts/`: 开发启动、API 摘要提取和 exe 打包脚本。

## Security

- 不提交 `config.toml`、token、密码、client secret 或个人账号。
- HTTP 日志会脱敏 URL、Authorization、access token、refresh token、client secret、password、signature 等敏感字段。
- refresh token 和 access token 优先保存到系统 keyring。
- keyring 不可用时，token 只保存在用户数据目录。
- 代理用户名和密码不会明文输出到日志。

## Troubleshooting

### Missing refresh token

客户端没有拿到完整 OAuth token 时会提示缺少 refresh token。请退出登录后重新执行 OAuth 授权流程。

### REST API returns 401

常见原因：

- token 已过期或不是 REST API token。
- 刚切换账号但旧 token 未清理。
- OAuth 客户端参数与服务端登记不一致。
- 当前账号没有访问对应文档库或接口的权限。

建议处理：

1. 在账号菜单中退出登录。
2. 确认云盘地址为 `https://pan.ncepu.edu.cn`。
3. 检查 `client_id`、`client_secret` 和 `redirect_uri`。
4. 重新登录。

### PermissionError while building exe

如果打包时报 `PermissionError`，通常是旧 exe 或 `dist` 目录中的文件正在被占用。请关闭正在运行的客户端后重试，或使用新的输出目录：

```powershell
python scripts\build_exe.py --onedir --distpath dist-new
```

### PySide6 WebEngine is unavailable

如果内置网页登录不可用，优先检查 Python 版本和 PySide6 安装情况。建议使用 Python 3.10 至 3.12，并重新安装依赖：

```powershell
pip install -r requirements.txt
```

## Version

当前版本：`0.1.0`

## License

本仓库尚未声明开源许可证。使用、分发或二次开发前，请先确认项目所有者的授权要求。
