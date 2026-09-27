# SongDown · 音频转换工作台

统一的中文在线音频转换网页。前端资源全部随项目提供，不加载外部字体、统计脚本或 CDN。支持电脑与手机浏览器。

## 完整功能网站

访客在同一网页上传、转换、试听和下载，无需部署项目或安装 QQ 音乐。网站不再区分通用版和本机 QQ 版；服务端账号维护不向浏览器开放。

| 格式 | 输出 | 服务端要求 |
| --- | --- | --- |
| NCM | 原始 MP3 / FLAC | PyCryptodome |
| OGG | 高质量 MP3 | FFmpeg |
| MGG | MP3 | qmdec、FFmpeg、有效 Cookie 或密钥 |
| MFLAC | FLAC | Windows QQ 音乐、Frida 16.7.10、FFmpeg |
| LRC | 原歌词文件 | 无额外依赖 |

支持批量与文件夹上传、进度、取消、试听、单文件与 ZIP 下载。每个失败文件显示原因、建议和错误码；同批成功结果保留。服务端缺少组件时会明确报告，开放格式入口不代表服务器已准备好。

MFLAC 输出无损整理后核对原始 PCM MD5 与样本数，校验失败不提供结果。NCM 直接提取音频，暂不写入独立封面和标签。NCM 格式参考 [ncmdump](https://github.com/taurusxin/ncmdump)。

## 站长启动与部署

普通用户只需访问站长提供的网站地址。以下操作仅由站长执行。

完整 QQ 功能需要一台可运行兼容 QQ 音乐的 Windows 主机。当前尚无服务器或域名，未上线公网。GitHub Pages 不能运行本项目的 Python 后端。

离线组件包提供 Python 运行环境和依赖，解压后启动 `start_server.bat`，服务默认监听 `127.0.0.1:8765`。QQ 客户端由站长解压、启动并登录；访客不需要执行这些步骤。

包内用户提供的 QQMusic.rar 实际版本为 **19.51（兼容性未实测）**；已通过真实 MFLAC 转换的客户端为 **22.05 / 2205.23.22.21**。不能将这两个版本视为同一版本。

源码开发启动：

```powershell
python -m pip install -r requirements-web.txt -r requirements.txt
python -m pip install git+https://github.com/Sophomoresty/qmdec.git
python run_web.py
```

FFmpeg 需在 PATH，或 Windows 下置于 `input/Tools/ff.exe`。详细权限、登录维护及 Windows HTTPS 部署见 [服务端 QQ 教程](deploy/LOCAL_QQ.md)。Docker 配置仍可用于开发与 NCM / OGG 后端，但 Linux 容器不能运行原生 QQ 进程，不是完整 QQ 网站的部署方案。

## 网盘下载区

复制 `downloads.example.json` 为 `downloads.json`，填写 HTTPS 网盘链接、提取码和组件 ZIP 的 SHA256。也可用 `SONGDOWN_DOWNLOAD_CONFIG` 指向配置文件。字段仅用于公开展示，不要写账号凭据。

```powershell
python scripts/configure_downloads.py --url "https://你的网盘分享链接" --code "提取码" --archive "组件包.zip"
```

配置实时读取，刷新网页即可生效。链接未提供时显示待配置状态，不生成虚假下载链接。下载组件是站长维护操作，不是访客转换的前置步骤。

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
