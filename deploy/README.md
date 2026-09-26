# 部署指南

## 选择服务器

应用和网页资源在同一服务器提供，浏览器无须连接 Google Fonts、jsDelivr、GitHub Raw 等外部资源。GitHub 只用来托管源代码，不作为用户访问网站的必经链路。

- 中国大陆服务器：访问线路通常更适合大陆用户，但网站上线前需要按云厂商要求完成 ICP 备案。
- 中国香港服务器：可先部署再从实际用户网络验证；不需大陆 ICP 备案，不代表任何运营商、任何地区均保证可达。
- 推荐起步规格：2 vCPU、2 GiB 内存、至少 10 GiB 可用磁盘。当前服务只运行一个转换任务，避免廉价机器被同时转码耗尽。

备案条件参考阿里云官方说明：<https://help.aliyun.com/en/icp-filing/basic-icp-service/user-guide/icp-filing-application-overview>。
目前没有用户提供的服务器或域名，因此未执行公网部署、DNS 配置、证书签发或大陆多运营商连通性验收。

## Docker Compose + HTTPS

1. 在服务器安装 Docker Engine 与 Compose v2，将域名 A 记录指向服务器；IPv6 不可用时不要配置 AAAA。
2. 放行入站 TCP 80、443，不需要暴露 8765。SSH 仅对管理员开放。
3. 获取仓库并生成配置：

   ```bash
   git clone https://github.com/CrimeCarnival/SongDown.git
   cd SongDown
   python3 scripts/init_deploy.py --domain music.example.com
   ```

4. 私下保存 `.env` 中的访问口令，然后启动：

   ```bash
   docker compose config --quiet
   docker compose up -d --build
   docker compose ps
   docker compose logs --tail=100 app caddy
   ```

5. 打开 `https://music.example.com`，使用口令登录。Caddy 自动申请并续期证书，需要域名正确解析并能访问证书服务。

Compose 将应用隔离在内部网络、以非 root 用户和只读根文件系统运行；临时数据放置于专用卷，上传缓冲在 tmpfs 中。容器配置内存、CPU、进程数量限制。会话和转换均由单个 Waitress 进程管理，不要改为多个 Gunicorn worker 或多副本部署。

## 中国网络构建与离线部署

运行时无需下载前端依赖。首次构建依赖 Docker Hub、Debian 软件仓库、Python 包源，国内访问速度取决于服务器网络。

可在 `.env` 中为 Python 安装单独指定可信镜像，例如：

```dotenv
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
```

如果目标服务器不能访问镜像仓库，在网络可用且与服务器 CPU 架构相同的机器构建并导出：

```bash
docker compose build app
docker pull caddy:2.10-alpine
docker save songdown:local caddy:2.10-alpine -o songdown-images.tar
```

通过 SSH/SCP 传输镜像归档和项目代码（不传歌曲、Cookie、旧任务数据），在服务器执行：

```bash
docker load -i songdown-images.tar
python3 scripts/init_deploy.py --domain music.example.com
docker compose up -d --no-build --pull never
```

镜像归档体积较大，不要提交到 GitHub 仓库。`.env` 应在目标主机生成并妥善保存。

## 原生部署与现有反向代理

安装 Python 与 FFmpeg，安装 `requirements-web.txt`，用系统服务启动 `python run_web.py`。为后台服务提供稳定的 `WEB_SECRET_KEY`、高熵 `WEB_ACCESS_TOKEN`、`WEB_COOKIE_SECURE=1`，由 Nginx/Caddy 将 HTTPS 请求代理到 `127.0.0.1:8765`。反向代理必须保留原始 Host；不要配置跨站 CORS。所有应用资源必须挂在域名根路径。

开发测试使用 HTTP 时仅在环回地址运行，并设置 `WEB_COOKIE_SECURE=0`。不要将开发配置直接用于公网。

## 上线验收

- 从中国移动、电信、联通的实际网络访问首页、登录、上传、试听和 ZIP 下载；检查 HTTPS 无警告。
- 准备自己有权使用的真实 NCM / OGG / LRC 文件，验证转换后的音频完整可播放。
- 在两组独立浏览器会话中验证不能互相下载对方的任务。
- 验证取消、删除和一小时后自动清理，不向外暴露 `.env`、Cookie、输入目录或服务端绝对路径。
- 查看磁盘、内存、任务超时和失败日志。健康检查返回成功仅代表 Web 服务运行，并不代表 QQ 格式可解密。
- 公网模式不提供 MGG、MFLAC 或更新 Cookie。此类功能使用 Windows 本机模式，并需要真实客户端与真实样本单独验证。

## 更新、回滚与数据

```bash
git pull --ff-only
docker compose up -d --build
```

更新会重启服务并清除旧的临时任务。先让正在转换的任务完成、下载结果。

回滚到已验证的 Git 提交后重新构建，或预先用 `docker tag songdown:local songdown:previous` 保存旧镜像。不要使用强制推送或自动重置用户未提交的修改。

`docker compose down` 不删除命名卷；`down -v` 会删除所有数据卷（包括 TLS 证书），不要作为常规更新命令。任务数据没有长期备份需求；`.env` 和 Caddy 证书卷需要按自己的运维策略保管。
