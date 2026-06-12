# 华电云盘客户端

面向操作系统课程设计与真实使用场景的 Windows 桌面网盘客户端。项目使用 PySide6 构建界面，通过 httpx 对接华电云盘/爱数 AnyShare RESTful API，支持云端文件浏览、搜索、上传下载、同步任务、日志查看、代理配置和 PyInstaller 打包。

默认连接真实华电云盘地址：

```text
https://pan.ncepu.edu.cn
```

`MOCK` 模式仅用于离线演示、单元测试和接口不可用时的兜底，不应替代真实 API 主线。

## 功能特性

- 真实华电云盘 RESTful API 对接，默认 API 前缀为 `/api`。
- OAuth2 授权登录，支持内置网页登录、授权码换取 token、refresh token 刷新。
- 云端文件页支持文档库入口、目录浏览、搜索、上传、下载、删除、重命名、移动、复制和新建文件夹。
- 首页仪表盘展示在线状态、容量信息、同步任务数、上传下载数量和最近错误。
- 同步任务支持本地到云端、云端到本地、双向同步。
- 同步引擎包含 watchdog 文件监听、事件合并、任务队列、worker 线程池和 SQLite 状态库。
- 支持 `.syncignore`、默认过滤规则和设置页自定义过滤规则。
- 支持冲突保留策略，默认使用 `keep_both`，避免直接覆盖用户本地修改。
- 支持 HTTP/HTTPS 代理、日志脱敏、可选加密上传。
- 支持 PyInstaller 打包为 Windows exe。

## 技术栈

- Python 3.10+
- PySide6
- httpx
- sqlite3
- watchdog
- cryptography
- keyring
- PyInstaller
- pytest / pytest-qt

## 环境要求

推荐环境：

- Windows 10/11
- Python 3.10 至 3.12
- 可访问 `https://pan.ncepu.edu.cn`
- 如校外网络无法直连，需先连接校园 VPN 或配置可用代理

说明：

- Python 3.13 下部分 Qt WebEngine 相关 wheel 可能不可用。如果内置网页登录无法启动，建议切换 Python 3.10 至 3.12。
- 程序启动不依赖 WinFsp、Dokany 或 FUSE 等可选系统组件。

## 快速开始

在项目根目录执行：

```powershell
python -m venv hdyp
.\hdyp\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python -m ncepu_cloud_client.main
```

也可以使用开发脚本启动：

```powershell
scripts\run_dev.ps1
```

如果 PowerShell 阻止脚本运行，可改用：

```powershell
python -m ncepu_cloud_client.main
```

## 登录与配置

首次启动会自动生成配置文件：

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
```

登录页分为两种模式：

- `REAL`: 连接真实华电云盘，需要填写云盘地址、Client ID 和 Client Secret。
- `MOCK`: 离线演示模式，不需要账号和网络。

右上角“设置”中可配置：

- API 前缀
- 认证地址
- Redirect URI
- OAuth Scope
- OAuth 扩展参数
- Token 认证方式
- SSO Credential ID
- HTTP/HTTPS 代理
- 手动 token 登录

## OAuth 登录流程

真实登录使用标准 OAuth2 授权码流程：

1. 客户端打开 `https://pan.ncepu.edu.cn` 官方网页登录页。
2. 用户在网页中完成学校账号登录。
3. 客户端跳转到 `/oauth2/auth` 请求授权。
4. 授权服务器回调 `http://127.0.0.1:8765/callback` 并返回 `code`。
5. 客户端调用 `/oauth2/token` 换取 `access_token` 和 `refresh_token`。
6. token 保存到系统 keyring；keyring 不可用时保存到用户数据目录的本地文件。

注意：

- 不要在源码中硬编码个人账号、密码、token 或 client secret。
- `client_id`、`client_secret`、`redirect_uri` 必须与服务器登记信息一致。
- 业务 API 请求使用 `Authorization: Bearer ACCESS_TOKEN`。
- GET 请求在必要时可回退到 `tokenid=ACCESS_TOKEN` 查询参数。

## 命令行工具

安装为可编辑包后，可使用：

```powershell
ncepu-cloud quota
ncepu-cloud libraries
ncepu-cloud doc-lib-quota DOC_LIB_ID
ncepu-cloud list /
ncepu-cloud search 课程资料
ncepu-cloud mkdir /课程资料
ncepu-cloud rename ITEM_ID 新名称.docx
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

## 同步说明

同步任务包含三种方向：

- 本地到云端
- 云端到本地
- 双向同步

同步机制：

- 本地文件变化由 watchdog 监听。
- 文件事件经过 debounce 合并后进入同步队列。
- worker 线程异步执行上传、下载和删除任务。
- SQLite 保存任务、传输记录、本地路径、远端 ID、checksum 和冲突信息。
- 删除同步默认关闭，避免误删。

冲突处理：

- 默认策略为 `keep_both`。
- 下载覆盖本地文件前会比较上次同步 checksum。
- 如果本地已被用户修改，会保留为 `filename.conflict-YYYYMMDD-HHMMSS.ext`，再下载云端版本。

过滤规则：

- 内置忽略临时文件、系统文件、虚拟环境、缓存目录和日志文件。
- 设置页可添加全局自定义规则。
- 同步根目录可添加 `.syncignore`。

## 运行测试

运行完整测试：

```powershell
python -m pytest
```

运行常用核心测试：

```powershell
python -m pytest tests\test_aishu_client_parsing.py tests\test_ui_pages.py tests\test_config.py tests\test_sync_engine.py
```

说明：

- `tests/integration/test_real_api.py` 面向真实 API 集成测试，运行前需要准备有效配置和账号权限。
- 单元测试不会要求提交真实 token 或个人账号信息。

## 打包 exe

推荐使用项目脚本：

```powershell
scripts\build_exe.ps1
```

或直接运行：

```powershell
python scripts\build_exe.py --onedir
```

输出位置：

```text
dist\NCEPUCloudClient\NCEPUCloudClient.exe
```

如果 `dist` 目录被正在运行的 exe 占用，可换一个输出目录：

```powershell
python scripts\build_exe.py --onedir --distpath dist-new
```

图标说明：

- `image\图标.png` 是原始图标资源。
- `assets\app.ico` 是打包用图标。
- 打包脚本会优先用 `image\图标.png` 生成 `assets\app.ico`，并把 `assets` 和 `image` 加入 PyInstaller 资源。

## 项目结构

```text
.
├── README.md
├── AGENTS.md
├── pyproject.toml
├── requirements.txt
├── assets/
│   ├── app.ico
│   ├── app.png
│   └── qss/
├── image/
│   └── 图标.png
├── scripts/
│   ├── build_exe.py
│   ├── build_exe.ps1
│   ├── build_exe.bat
│   ├── clean_build.bat
│   └── run_dev.*
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

主要模块：

- `api/`: 真实 AnyShare API adapter、mock client、错误类型和数据模型。
- `auth/`: OAuth URL 构建、网页登录流程、token 存储。
- `config/`: 配置模型和配置文件读写。
- `sync/`: 同步引擎、队列、worker、数据库、冲突处理和过滤规则。
- `ui/`: PySide6 页面、窗口、组件和样式。
- `security/`: keyring 与可选加密工具。
- `scripts/`: 开发启动、API 摘要提取和 exe 打包脚本。

## RESTful API 适配重点

当前真实 adapter 优先使用官方文档访问接口：

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

文档库根目录会识别官方结构：

```json
{
  "id": "gns://...",
  "name": "我的文档库",
  "type": "user_doc_lib"
}
```

对于权限不足或不可用的管理类兜底接口，客户端会跳过并继续使用用户可访问的文档访问接口。

## 安全与隐私

- 不提交 `config.toml`、token、密码、client secret 或个人账号。
- HTTP 日志会脱敏 URL、Authorization、access token、refresh token、client secret、password、signature 等敏感字段。
- refresh token 和 access token 优先保存到系统 keyring。
- keyring 不可用时，token 只保存在用户数据目录，不放入项目仓库。
- 代理用户名和密码不会明文输出到日志。

## 常见问题

### 登录后提示没有 refresh token

说明客户端没有拿到真正的 OAuth token，可能只是读到了网页登录 cookie 或网页端短期凭据。请退出登录后重新走 OAuth 授权流程。

### 登录后 REST API 提示 401

常见原因：

- token 已过期或不是 REST API token。
- 刚切换账号但旧 token 未清理。
- OAuth 客户端参数与服务器登记不一致。
- 当前账号没有访问对应文档库或接口的权限。

处理方式：

1. 右上角账号菜单选择“退出登录”。
2. 重新输入正确 `client_id` 和 `client_secret`。
3. 确认云盘地址为 `https://pan.ncepu.edu.cn`。
4. 重新登录。

### 打包时报 `PermissionError: VCRUNTIME140.dll`

通常是旧 exe 或 `dist` 目录中的文件正在被占用。请关闭正在运行的客户端后重试，或使用：

```powershell
python scripts\build_exe.py --onedir --distpath dist-new
```

### GitHub 推送失败

如果出现 GitHub 连接超时、TLS 握手失败或连接重置，请先确认浏览器能访问 GitHub。必要时配置代理：

```powershell
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
```

取消代理：

```powershell
git config --global --unset http.proxy
git config --global --unset https.proxy
```

## 版本状态

当前版本：`0.1.0`

项目仍处于课程设计和真实 API 适配阶段。真实学校网关可能存在权限、OAuth 客户端登记、代理和账号策略差异，遇到接口差异时应优先参考本项目的 API adapter 和本地 RESTfulAPI 文档进行兼容。
