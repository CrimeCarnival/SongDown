# 第三方依赖与来源

公开源码包仅包含本项目的转换封装、网页、测试和部署配置，不包含用户音乐、Cookie、密钥缓存、qmdec 源码或 FFmpeg 可执行文件。

- 既有 QQ MFLAC Frida hook 源自本项目原有代码。原 README 指向 [yllhwa/decrypt-mflac-frida](https://github.com/yllhwa/decrypt-mflac-frida)。本次保留该来源说明；未为第三方代码重新声明许可证。
- NCM 容器与密钥流格式参考 [taurusxin/ncmdump](https://github.com/taurusxin/ncmdump)；本项目使用独立 Python 封装，并包含边界检查和临时文件处理。
- 可选 QQ 解码器 [Sophomoresty/qmdec](https://github.com/Sophomoresty/qmdec) 由使用者单独安装，按该项目自身条款使用。
- Flask、Waitress、PyCryptodome 通过 `requirements-web.txt` 安装。测试使用 Playwright、Requests、Mutagen。
- FFmpeg 由运行环境安装；Docker 镜像使用 Debian 的 FFmpeg 软件包。分发构建镜像时，须保留其软件包许可信息并遵守其中组件的许可要求。
- Caddy 用作 HTTPS 反向代理，由官方容器镜像提供。

本项目不包含第三方音乐，也不授予音乐作品的复制或分发权。

## 单独分发的 Windows 组件 ZIP

组件 ZIP 不进入 GitHub 源码仓库。包含用户指定 QQMusic.rar（文件版本 19.51，不声称为官方安装包）、Python 官方嵌入式运行时、PyPI 依赖、qmdec 上游固定提交 c4b22f0e5683f99fda079f1cd9e9f6cdd39d1ce9，以及 imageio-ffmpeg 0.6.0 Windows wheel 中的 FFmpeg 7.1 gyan essentials binary。

组件内 licenses/SOURCES.txt、FFmpeg 构建/许可说明、GPLv3 全文、qmdec README 与各包 dist-info 保留依赖出处及许可。Python 官方 SHA256 在构建脚本中固定核对；manifest.json 记录包内文件和依赖轮子的 SHA256。QQ 压缩包按用户提供的原件复制，不混入当前客户端登录目录。第三方各自许可证不由本项目替换。
