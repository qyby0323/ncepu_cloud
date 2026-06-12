# NCEPU Cloud Client

华电云盘客户端是一个面向课程设计和实际使用的桌面网盘客户端，默认对接真实华电云盘/爱数 RESTful API，并保留 mock 模式用于测试和无网络演示。

## 功能截图

> 截图占位：运行 `python -m ncepu_cloud_client.main` 后可看到登录页、首页仪表盘、云端文件、同步任务、传输列表、日志和设置页面。

## 环境要求

- Python 3.10+
- Windows 10/11，Linux 可运行基础功能
- 推荐使用虚拟环境

## 安装依赖

```bash
pip install -r requirements.txt
pip install -e .
```

## 运行开发版

```bash
python -m ncepu_cloud_client.main
```

Windows 也可运行：

```powershell
scripts\run_dev.ps1
```

`scripts/run_dev.*` 会自动把本地 `src` 加入 `PYTHONPATH`，适合未执行 `pip install -e .` 时直接从源码启动。如果 PySide6 未安装，程序会输出安装提示。CLI 可直接用于调试真实 API：

```bash
python -m ncepu_cloud_client.cli.commands quota
python -m ncepu_cloud_client.cli.commands libraries
python -m ncepu_cloud_client.cli.commands doc-lib-quota DOC_LIB_ID
python -m ncepu_cloud_client.cli.commands list /
python -m ncepu_cloud_client.cli.commands search 课程资料
python -m ncepu_cloud_client.cli.commands mkdir /课程资料
python -m ncepu_cloud_client.cli.commands rename ITEM_ID 新名称.docx
python -m ncepu_cloud_client.cli.commands move ITEM_ID TARGET_DIR_ID
python -m ncepu_cloud_client.cli.commands copy ITEM_ID TARGET_DIR_ID
python -m ncepu_cloud_client.cli.commands delete ITEM_ID
python -m ncepu_cloud_client.cli.commands register-client --name "NCEPU Cloud Client"
python -m ncepu_cloud_client.cli.commands token-login ACCESS_TOKEN --refresh-token REFRESH_TOKEN
python -m ncepu_cloud_client.cli.commands sso-login --params-json "{\"account\":\"...\"}"
```

## 配置真实 API

首次启动会自动生成配置文件：

- Windows: `%APPDATA%/NCEPUCloudClient/config.toml`
- Linux: `~/.config/ncepu-cloud-client/config.toml`

关键配置：

```toml
[app]
mode = "real"

[api]
base_url = "https://pan.ncepu.edu.cn"
api_prefix = "/api"
auth_url = "https://pan.ncepu.edu.cn"
client_id = ""
client_secret = ""
redirect_uri = "http://127.0.0.1:8765/callback"
oauth_scope = "offline openid all"
oauth_client_auth_method = "basic"
```

`mode = "real"` 是默认模式。`mode = "mock"` 只用于测试和演示兜底，不能替代真实 API adapter。

官方 AnyShare 文档中的业务接口完整地址形态是 `https://{host}:{port}/api/...`。如果学校实际网关已经把 `/api` 映射到根路径，可以在设置页把 `API 前缀` 清空。

## 登录说明

登录页现在分为两层：

- 主登录页左下角可切换 `REAL` / `MOCK`。`REAL` 只显示云盘地址、Client ID、Client Secret 和“保存密码”；`MOCK` 不需要账号信息。
- 右上角“设置”进入登录设置，可配置 API 前缀、认证地址、Redirect URI、OAuth Scope、OAuth 扩展参数、SSO、Token 登录和代理。

支持 OAuth2 桌面登录流程：

1. UI 或 CLI 打开授权地址。
2. 本地临时服务监听 `127.0.0.1:8765/callback`。
3. 收到 `code` 后请求 `/oauth2/token`。
4. token 通过 keyring 保存，keyring 不可用时保存到用户数据目录的私有 JSON 文件。

如果学校环境需要 SSO 或额外参数，请在设置页或配置文件补充，不要修改源码硬编码。

如果服务器允许 OAuth 动态注册，可用 `register-client` 获取 `client_id/client_secret`，并手动写入设置页或配置文件。

也支持手动 token 登录，适合答辩演示或真实 OAuth 网关暂不可用时验证业务 API。

如果点击“登录真实华电云盘”后浏览器跳到 `/oauth2/fallbacks/error` 并显示 `invalid_client` 或 nginx `404 Not Found`，这通常不是目录/文件 API 错误，而是 OAuth 客户端未通过认证。处理顺序：

1. 确认 `Auth URL`、`Client ID`、`Client Secret`、`Redirect URI` 与学校/AnyShare 管理端登记的信息完全一致。
2. 如果没有正式 OAuth 客户端，先尝试“动态注册 OAuth 客户端”，拿到返回的 `client_id/client_secret` 后保存再登录。
3. 如果学校关闭了动态注册，需要从学校开放平台或云盘管理员处申请客户端参数。
4. 如果网关要求额外参数，可在“OAuth 扩展参数”中填写 JSON，例如 `{"tenant":"ncepu"}`。
5. 仍无法 OAuth 登录时，可用“使用 Token 进入”临时验证业务 API。

云端文件页的根目录会优先显示真实 API 返回的文档库入口，进入某个文档库后再调用目录浏览接口；UI 会同时保存路径和远端 ID，以兼容 `gns://...` 形式的对象标识。

## 整理官方 API 文档

手动解压 `RESTfulAPI.zip` 后，可运行：

```powershell
python scripts\extract_api_summary.py
```

脚本会从 Redoc HTML 中提取 OpenAPI 路径摘要并生成 `docs/openapi-summary.md`。

## 同步任务

同步引擎包含：

- watchdog 文件监听
- debounce 事件合并
- 线程安全任务队列
- worker 线程池
- SQLite 状态表
- 上传/下载进度记录

删除同步默认关闭，避免误删。

同步任务页可设置方向：

- 本地到云端
- 云端到本地
- 双向同步

启动同步时，`云端到本地` 和 `双向同步` 会先在后台扫描远端目录树，把远端文件加入下载队列；本地到云端方向由 watchdog 监听新增和修改事件。下载成功后会写入 SQLite 的本地路径与远端 ID 映射，便于后续删除同步和冲突处理使用。

启用“同步删除”后，本地删除事件会通过 SQLite 中保存的远端 ID 映射进入远端删除队列。该功能默认关闭。

默认冲突策略为 `keep_both`。远端下载覆盖本地文件前，worker 会先比较本地文件与上次同步时保存的 checksum；如果本地已被用户修改，会把本地版本保留为 `filename.conflict-YYYYMMDD-HHMMSS.ext`，再下载云端版本到原路径，并在 SQLite 中标记冲突副本。

## 过滤规则

默认过滤：

```gitignore
*.tmp
*.temp
~$*
.DS_Store
Thumbs.db
desktop.ini
.git/
.svn/
.hg/
__pycache__/
node_modules/
.venv/
venv/
*.pyc
*.log
```

设置页可维护全局自定义过滤规则，每行一条。同步目录下也可放置 `.syncignore`，支持空行、注释、通配符和目录规则。实际同步时会合并默认规则、设置页全局规则和当前同步目录的 `.syncignore`。

## 代理说明

设置页可配置 HTTP/HTTPS 代理。所有真实 API 请求都会读取配置。校外无法直连时，请先连接学校 VPN，或配置可用代理。

如代理需要认证，可以填写代理用户名和密码，程序会在发起请求时拼接到代理 URL，不会写入网络日志。

HTTP 日志会对 URL 用户名密码、token、授权码、签名、密码、`client_secret` 等敏感字段做脱敏。错误提示会保留请求路径、状态码和摘要，但不会输出真实 token 或 secret。

## 加密上传

设置页可保存加密口令到系统 keyring。同步任务启用“加密上传”后，worker 会在上传前生成 `.ncepuenc` 文件，下载 `.ncepuenc` 后会还原成本地原文件。口令不写入 `config.toml`。

上传链路支持官方对象存储授权协议。普通文件会调用 `osbeginupload` / 对象存储 PUT / `osendupload`；超过阈值的大文件会调用 `osinitmultiupload` / `osuploadpart` / `oscompleteupload`，并在每个分片完成后更新进度。

## 打包 exe

应用图标来源为 `image/图标.png`。运行时会优先使用这张图作为应用图标、任务栏图标、窗口标签图标和主界面左上角图标；打包脚本会把 `image/` 一起加入 PyInstaller 资源，并在构建时生成 `assets/app.ico`。

```powershell
scripts\build_exe.ps1
```

或：

```bash
python scripts/build_exe.py --onedir
```

目标输出：

```text
dist/NCEPUCloudClient/NCEPUCloudClient.exe
```

## 常见错误

- `缺少 client_id/client_secret`: 在设置页或配置文件填写 OAuth 参数。
- 浏览器显示 `invalid_client` 或 `/oauth2/fallbacks/error` 404：OAuth 客户端无效或认证方式不被网关接受，先动态注册或填写管理员发放的 `client_id/client_secret/redirect_uri`，必要时补 `OAuth 扩展参数`。
- `401`: token 过期或无效，尝试刷新或重新登录。
- `403`: 当前账号没有访问权限。
- `404`: 云端路径或文件不存在。
- `代理连接失败`: 检查 VPN、代理地址、用户名和密码。
- `PySide6 not installed`: 执行 `pip install PySide6`。

## 课程设计亮点

- 多线程同步队列
- 文件监听与 debounce
- SQLite 状态维护
- RESTful API 网络编程
- token 鉴权与自动刷新
- 代理访问
- 可选 AES-GCM 加密上传
- 可选 FUSE/WinFsp 虚拟文件系统设计与只读核心原型
- Windows exe 打包脚本

## 目录结构

```text
ncepu-cloud-client/
  README.md
  AGENTS.md
  requirements.txt
  pyproject.toml
  prompt.md
  src/
  tests/
  docs/
  scripts/
  assets/
  build/
```

## 最终验收清单

- [x] Windows 桌面客户端可启动
- [x] UI 美观，包含登录页、首页、云端文件页、同步任务页、设置页、日志页
- [x] 支持真实华电云盘 API 配置
- [x] 支持真实登录 / token 获取
- [x] 支持云端目录浏览
- [x] 支持创建云端文件夹
- [x] 支持上传文件
- [x] 支持下载文件
- [x] 支持删除文件
- [x] 支持重命名文件
- [x] 支持本地目录自动同步
- [x] 支持同步任务队列
- [x] 支持多线程上传 / 下载
- [x] 支持同步进度显示
- [x] 支持过滤规则
- [x] 支持冲突处理
- [x] 支持代理配置
- [x] 支持日志查看
- [x] 支持配置文件管理
- [x] 支持可选加密上传
- [x] 支持 Windows exe 打包
- [x] 提供 README
- [x] 提供 AGENTS.md
- [x] 提供 docs/api-notes.md
- [x] 提供 docs/design.md
- [x] 提供 docs/build-exe.md
- [x] 提供基础测试
