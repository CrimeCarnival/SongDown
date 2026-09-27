# 本机 QQ 模式使用教程

网页内入口：右侧「QQ 音乐格式」下的「本机 QQ 模式教程」，或打开 `/assets/qq-guide.html`。教程随代码部署，无须访问外部网站。

## 当前报错是什么意思

```text
unable to access process with pid ... from the current user account
```

QQ 音乐已经启动，但运行网页服务的 Python 进程无法附加到它。常见原因包括 Windows 用户不同、进程权限级别不同，或服务所在终端受进程访问限制。不是输入目录问题，也不代表 Cookie 过期。

## 按此顺序恢复

1. 先下载其他已完成的任务结果。在启动旧服务的终端按 `Ctrl+C`，确认服务停止；关闭浏览器不会停止服务。
2. 在项目目录找到 `start_local_qq.bat`，右键选择「以管理员身份运行」，自行确认 Windows 权限提示。使用与 QQ 音乐相同的 Windows 用户。
3. 保持服务终端打开，浏览器访问 <http://127.0.0.1:8766>，确认页面显示「本机 QQ 模式」，点击「检查环境」。
4. 服务重启会丢弃旧任务，请重新上传原始文件并转换。

也可以彻底退出 QQ 音乐，再将 QQ 音乐与服务都以普通权限启动。不要只提升浏览器权限；进程访问发生在 Python 服务里。刷新网页和更新 Cookie 都不能修复进程权限不匹配。

如果仍然无法附加，请在独立的 Windows PowerShell 中启动，而不是受限终端；不需要关闭安全软件。若错误变成 hook 加载失败，应检查 QQ 客户端版本兼容性。

## 首次准备

在项目目录执行（Python 3.10+）：

```powershell
python -m pip install -r requirements-web.txt -r requirements.txt
```

确认 FFmpeg 已加入 PATH，或保留已有的 `input/Tools/ff.exe`。MGG 还需要 qmdec：

```powershell
python -m pip install git+https://github.com/Sophomoresty/qmdec.git
```

此安装命令需要 Git。已有 `input/Tools/qmdec/src` 的工程优先使用其中源码。
启动 Windows 桌面版 QQ 音乐并登录，保持运行。

## 启动网页

双击 `start_local_qq.bat`；若发生访问权限错误，再按上文以管理员身份启动。该脚本：

- 优先使用项目的 `.venv\Scripts\python.exe`，否则使用 PATH 中的 Python。
- 仅监听 `127.0.0.1:8766`，临时数据使用独立的 `.web-data-qq` 目录。
- 不自动提权，不自动结束占用端口的进程。

手动启动时，在项目目录的 PowerShell 中执行：

```powershell
python run_web.py --local-qq --host 127.0.0.1 --port 8766
```

若依赖装在虚拟环境，改用：

```powershell
.\.venv\Scripts\python.exe run_web.py --local-qq --host 127.0.0.1 --port 8766
```

启动命令成功后，在浏览器打开 <http://127.0.0.1:8766>。不要误开 8765 上的通用服务。如果端口占用，先停止原服务，或更换启动端口并访问对应地址。

## 转换与下载

1. 点击「检查环境」。选项可用表示检测到依赖和进程，不能保证附加权限和文件版本兼容性。
2. MFLAC：添加文件，勾选「MFLAC → FLAC」，直接转换；此流程不依赖更新 Cookie。
3. MGG：点击「更新 Cookie」，成功后添加文件并转换；需要有效 Cookie 或密钥缓存，真实文件兼容性仍需逐个验证。
4. 完成后试听、单独下载或下载 ZIP。新一批转换前，先下载并删除上一批任务。
5. 用完后在服务终端按 `Ctrl+C` 停止。临时结果会过期，下载后再长期保存。

## 边界说明

本机模式只允许同一台 Windows 电脑访问。公网、Docker、手机浏览器不能直接读取这台电脑上的 QQ 音乐进程。网页按钮不能提升 Windows 进程权限，也不会要求你上传 Cookie。
