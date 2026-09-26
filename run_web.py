"""Production entrypoint; always uses Waitress, never Flask's development server."""
import argparse
import os

from web_app import create_app


def main():
    parser = argparse.ArgumentParser(description="SongDown 音频转换网页")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--local-qq", action="store_true", help="启用仅本机可访问的 QQ 功能")
    args = parser.parse_args()
    local = args.host in {"127.0.0.1", "localhost"}
    if args.local_qq and (not local or os.name != "nt"):
        parser.error("本机 QQ 模式必须在 Windows 上绑定 127.0.0.1 或 localhost")
    if not local and len(os.environ.get("WEB_ACCESS_TOKEN", "")) < 24:
        parser.error("公网监听必须设置至少 24 字符的 WEB_ACCESS_TOKEN")
    if not local and len(os.environ.get("WEB_SECRET_KEY", "")) < 32:
        parser.error("公网监听必须设置至少 32 字符的 WEB_SECRET_KEY")
    from waitress import serve
    app = create_app({"LOCAL_QQ": args.local_qq})
    print(f"SongDown: http://{args.host}:{args.port}", flush=True)
    try:
        serve(app, host=args.host, port=args.port, threads=6,
              max_request_body_size=app.config["MAX_CONTENT_LENGTH"],
              channel_timeout=120, clear_untrusted_proxy_headers=True)
    finally:
        app.extensions["jobs"].close()


if __name__ == "__main__":
    main()
