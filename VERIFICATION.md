# 验证记录

验证日期：2026-09-27。环境：Windows、Python 3.13、Waitress、Microsoft Edge（Playwright）。测试输出与用户音频仅保留在本机，不包含在 GitHub 源码包中。

## 已实测通过

- 21 项自动化测试：NCM MP3/FLAC 分块解码；取消与清理；中文路径；大小写扩展名；真实 FFmpeg 转码；失败输出清理；FLAC 非音频尾部清理、原始 PCM MD5 校验和损坏拒绝；文件夹结构与 ZIP 内容；Range 试听；会话隔离、访问口令、跨站请求拒绝；路径穿越、重名、空文件与伪造 OGG 播放列表拒绝；大小、数量和存储配额；任务超时、TTL；本机模式访问限制；公网启动配置及密钥生成不覆盖。
- 真实 HTTP 流程：健康检查、环境能力、上传、子进程处理、状态、文件下载、ZIP、删除。
- Edge 浏览器：文件夹上传、批量转换、音频媒体加载、ZIP 下载、刷新恢复任务、删除、重复提示、清空；1440px 桌面与 390px 手机布局无横向溢出；无外部网络资源请求、无页面 JavaScript 异常。
- 前端 JavaScript 语法检查。
- GitHub Actions 在 Linux 上已通过全部 21 项测试、生产 Docker 镜像构建、只读非 root 容器 HTTP 冒烟测试和 Caddy 配置验证：[运行记录](https://github.com/CrimeCarnival/SongDown/actions/runs/36279246461)，代码提交 `62c097e`。
- Cookie 接口通过权限及防泄漏单测；同时在真实 QQ 客户端环境中通过网页更新成功，响应仅包含 `ok` 和 `message`，未显示或上传凭据。公网模式禁止该接口。

## 用户提供的真实样本

| 样本 | 输入大小 | 输出 | 音频参数 | 验证结果 |
| --- | ---: | --- | --- | --- |
| NCM 样本 | 70,940,788 字节 | FLAC | 96 kHz / 24-bit / 双声道，211.302 秒 | 浏览器上传转换下载通过；严格完整解码零错误；PCM MD5 与 STREAMINFO 一致 |
| MFLAC 样本 | 31,445,362 字节 | FLAC | 44.1 kHz / 16-bit / 双声道，261.507 秒 | 通过本机 QQ 网页完成转换；无损整理后 MD5 与原始值一致，严格完整解码零错误 |

MFLAC 样本最初解密后带有非音频尾部，普通 FFmpeg 即使报错也可能返回 0；现已修复输出处理，并在真实样本验收中使用 `-xerror` 和错误输出检查，避免把可部分播放的文件当作完整成功。
本机 QQ 功能需要运行服务的用户有权访问 QQMusic.exe。首次受限进程测试无法附加；允许访问本机 QQ 进程后，真实转换通过。运行网页和 QQ 音乐时应使用相匹配的账号与权限级别。

## 尚未验证或需上线后验证

- MGG 缺少用户真实样本，尚未进行端到端实测。不能将其他格式的通过视为 MGG 已通过。
- NCM 未承诺覆盖所有历史或未来版本；样本通过不代表所有文件都能处理。
- 用户尚无服务器，因此公网域名、HTTPS 签发、中国大陆三网可用性未验收。项目提供部署配置，不宣称已经上线。

## 复现

```bash
python -m unittest -v test_ncm tests.test_web
node --check web/app.js
python run_web.py
# 另一个终端：
python scripts/smoke_http.py
python scripts/browser_qa.py --channel msedge
```

真实样本检查：安装 `requirements-test.txt`，启动通用服务或本机 QQ 模式后，将有权使用的文件路径传给 `scripts/real_audio_qa.py`。它只向指定本机网页上传，结果保存于被 Git 忽略的 `.test-artifacts/real-results/`，不会自动上传至 GitHub。
