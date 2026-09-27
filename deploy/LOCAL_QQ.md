# QQ 转换服务端维护（站长使用）

网站只有一个完整功能入口。访客通过浏览器上传转换，不部署、不安装 QQ，也不提供 Cookie。Python 服务必须与 QQ 音乐运行在同一台 Windows 主机上；不能附加访客电脑上的进程。

## 组件与版本

组件包包含用户提供的 QQMusic.rar、独立 Python 3.13.15 x64、Frida 16.7.10、网页依赖、qmdec 0.2.0、FFmpeg 和项目源码。保留第三方许可证及文件校验清单，不包含测试歌曲、账号登录数据或密钥缓存。

QQMusic.rar 的 QQMusic.exe 文件版本是 19.51，尚未实际验证解密。先前真实 MFLAC 测试成功使用 22.05（安装目录 2205.23.22.21）。两者不同，19.51 若出现组件不兼容，不要把环境检测当作转换成功。Frida 17 改动了脚本接口，本项目固定 16.7.10。

## 启动

1. 将整个组件包解压到可写目录，保留目录结构。
2. 用解压软件展开 QQMusic.rar，启动 QQMusic.exe 并登录有相应文件使用权限的账号。不要同时启动多个版本。包内客户端由用户提供，没有执行其中安装/卸载批处理。
3. 双击 start_server.bat。无需另外安装 Python 或在线下载依赖。打开 http://127.0.0.1:8765。
4. 用自己的实际文件验证 NCM、OGG、MFLAC、MGG；环境检查只表示依赖/进程被发现。
5. MGG 若提示密钥不可用，在服务器运行 update_qq_cookie.bat，凭据只保存于该包的 private-profile 下，不传给网页。此操作不会修复 MFLAC 进程附加权限。

组件包中的本地启动仅供站长准备服务，访客上线后直接访问 HTTPS 域名。

## QQ 已启动但无法附加

`unable to access process ... from the current user account` 表示 Python 服务没有权限访问 QQ 进程。

先保存完成的结果，在旧服务终端按 Ctrl+C 停止；确保 QQ 与 Python 属于同一个 Windows 用户、相同权限级别，再运行 start_server.bat。若 QQ 以管理员身份运行，也需右键以管理员身份启动服务。可以将两者均以普通权限重启。

不要仅提升浏览器权限；不要关闭安全软件。受限终端无法附加时改用独立 PowerShell。服务重启后重新上传原文件。如果权限问题解决后出现 hook/导出函数失败，需核对 QQ 客户端版本。

## 部署到公网

需要 Windows 主机、域名与 HTTPS 反向代理，目前用户尚未提供服务器。站长在 Windows 登录会话中保持 QQ 运行；无桌面的系统服务账户可能无法访问该进程。

服务仍监听 127.0.0.1:8765，由同机 Caddy / IIS 转发 HTTPS。设置稳定且保密的 WEB_SECRET_KEY（至少 32 字符）、WEB_ACCESS_TOKEN（至少 24 字符）及 WEB_COOKIE_SECURE=1。可在启动终端设置环境变量后执行 start_server.bat。访问口令由站长发给访客，不是 QQ 密码。

Caddy 配置示例（域名必须替换并完成 DNS）：

```caddyfile
music.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

只对外开放 80/443，不开放 8765。Caddy 需另外安装并在部署时验证。不要公开 QQ 远程桌面、private-profile、日志或整个应用目录。Python 服务只提供规定的网页与任务接口；/api/cookie 已关闭。

中国用户访问无需连接外部前端 CDN。QQ 获取在线密钥仍依赖腾讯服务；正式上线后还需按实际部署区域完成域名要求、HTTPS 和多运营商访问测试。Linux Docker 无法提供原生 MFLAC 解密，应使用 Windows 后端。

## 网盘链接

上传生成的 SongDown-Windows-Components.zip，再运行 app/scripts/configure_downloads.py，或填写 app/downloads.json。配置在网页刷新时读取。下载区明确显示包内 19.51 与已验证 22.05 的区别。
