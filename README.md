# SongDown · 音频转换工作台

将本地音频转换工具做成可自托管的中文网页。前端资源全部随项目提供，不加载外部字体、统计脚本或 CDN。支持电脑与手机浏览器。

## 功能范围

| 功能 | 通用网页 / Docker | Windows 本机 QQ 模式 |
| --- | --- | --- |
| NCM → 原始 MP3 / FLAC | 支持，无二次压缩 | 支持 |
| OGG → 高质量 MP3 | 支持，需 FFmpeg | 支持，需 FFmpeg |
| LRC 歌词复制 | 支持 | 支持 |
| 多文件 / 文件夹、保留目录 | 支持 | 支持 |
| 进度、日志、取消、下载 ZIP | 支持 | 支持 |
| 音频试听、单文件下载 | 支持，取决于浏览器编解码能力 | 支持 |
| MGG → MP3 | 禁用 | 需 qmdec 和有效 Cookie 或密钥缓存 |
| MFLAC → FLAC | 禁用 | 需 FFmpeg、Frida、兼容版本的 QQ 音乐客户端 |
| 从 QQ 音乐更新 Cookie | 禁用 | 仅允许本机访问 |

MFLAC 输出会进行无损 FLAC 整理，并对原始音频 MD5 和样本数校验，以剔除 QQ 解密后残留的非音频尾部；校验失败不生成结果。

NCM 保留原始音频数据，尚不将容器中独立的封面、标题等元数据写入音频。NCM 解析格式参考 [ncmdump](https://github.com/taurusxin/ncmdump)。QQ 功能沿用原项目能力，其可用性取决于客户端与文件版本；环境检测通过不等于每个加密文件都能解密。

## 快速启动

需要 Python 3.10+（CI 使用 3.12）和安装在 PATH 中的 FFmpeg。

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux / macOS: source .venv/bin/activate
python -m pip install -r requirements-web.txt
python run_web.py
```

浏览器打开 <http://127.0.0.1:8765>。Windows 也可双击 `start_web.bat`。
已有项目中的 `input/Tools/ff.exe` 可在 Windows 自动识别；仓库不包含 FFmpeg 二进制文件。

单独运行 NCM 批处理：

```bash
python convert_ncm.py -i input -o output
```

## 公网部署（已提供配置，尚需服务器）

推荐自有域名 + 服务器 + Docker Compose + Caddy HTTPS。该项目有 Python 转换后端，不能直接运行在 GitHub Pages 上。

```bash
git clone https://github.com/CrimeCarnival/SongDown.git
cd SongDown
python scripts/init_deploy.py --domain music.example.com
# 将域名解析到服务器，开放 TCP 80/443，再执行：
docker compose up -d --build
```

脚本会生成 `.env`，并拒绝覆盖已有文件。使用其中 `WEB_ACCESS_TOKEN` 的值登录网页；请不要将 `.env` 上传到 GitHub。
完整说明见 [部署指南](deploy/README.md)，包括大陆 / 香港部署、离线传输镜像、回滚、持久卷和上线验收。

## Windows 本机 QQ 模式

详细步骤与权限错误排查见 [本机 QQ 模式教程](deploy/LOCAL_QQ.md)。网页右侧也提供同名入口。

推荐双击 `start_local_qq.bat`，然后访问 <http://127.0.0.1:8766>。若提示 `unable to access process`，先停止旧服务，再右键此脚本选择「以管理员身份运行」；仅刷新网页或更新 Cookie 不会修复进程权限。

```bash
python -m pip install -r requirements-web.txt -r requirements.txt
python -m pip install git+https://github.com/Sophomoresty/qmdec.git
# 先启动 QQ 音乐并登录，再运行：
python run_web.py --local-qq --port 8766
```

本机模式强制绑定环回地址，同时检查连接来源与 Host；禁止通过该模式向公网分享 QQ 凭据。
已有工程中的 `input/Tools/qmdec/src` 优先使用；若不存在则使用已安装的 qmdec。外部项目的源码与音乐文件不被打包到本仓库。
桌面界面仍可使用 `python GUI/app.py` 启动。

## 临时文件与限制

- 每批最多 100 个文件、整个 HTTP 请求最多 200 MiB；不接受 ZIP 上传。
- 每个浏览器会话最多两个未完成任务，全服务最多 20 个保留任务；单进程串行转换。
- 每个任务使用独立的随机目录，访问结果必须属于同一浏览器会话，即使知道任务地址也不能跨会话访问。
- 单任务最长 15 分钟，磁盘限额 1 GiB；失败的中间 MP3 不作为结果提供。
- 任务结束后清除上传文件，结果保留 1 小时（每 30 秒清理），也可手动立即删除。
- 任务为临时数据，服务重启会清除旧任务。不要将 `.web-data` 或 `/data` 指向其他重要目录，不要多个实例共用该目录。
- 公网绑定必须显式设置高熵 `WEB_ACCESS_TOKEN` 和 `WEB_SECRET_KEY`；Docker 通过 HTTPS 安全 Cookie 运行。
- 浏览器关闭后任务仍可运行至完成或超时；会话丢失后不能恢复其下载权限，文件仍会自动过期。

## 测试

```bash
python -m unittest -v test_ncm tests.test_web
node --check web/app.js
# 先启动网页服务，再进行真实 HTTP 测试：
python scripts/smoke_http.py
# 可选：浏览器端完整测试
python -m pip install -r requirements-test.txt
python scripts/browser_qa.py --channel msedge
# Linux CI 或无 Edge 的机器：python -m playwright install chromium
# python scripts/browser_qa.py --channel ""
```

测试会生成纯音音频，不依赖或提交用户歌曲。详细实测范围与未验证项见 [验证记录](VERIFICATION.md)。GitHub Actions 配置执行 Python 集成测试、JS 语法检查、容器构建与 HTTP 检查。

仅处理你有权使用的文件。本项目不提供歌曲下载或账号共享服务。
