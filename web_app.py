"""Self-hosted audio converter. Serve with run_web.py (one Waitress process)."""
from __future__ import annotations

import atexit
import hmac
import importlib.util
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, request, send_file, session
from werkzeug.exceptions import HTTPException

from audio_converter_core import PROJECT_ROOT, HOOK_SCRIPT, QMDEC_SRC, find_ffmpeg

TERMINAL = {"completed", "partial", "failed", "cancelled"}
TASKS = {"ncm", "ogg", "lrc", "mgg", "mflac"}


def safe_relative(raw: str) -> Path:
    """Keep Unicode folder names, reject traversal and Windows special names."""
    value = raw.replace("\\", "/")
    parts = value.split("/")
    if (not value or len(value) > 240 or len(parts) > 12 or
            PurePosixPath(value).is_absolute()):
        raise ValueError("文件路径无效或过长")
    for part in parts:
        if (not part or part in {".", ".."} or part.endswith((" ", ".")) or
                re.search(r'[<>:"|?*\x00-\x1f\x7f]', part) or
                re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)):
            raise ValueError("文件名包含不安全的路径或系统保留名称")
    return Path(*parts)


def capabilities(local_qq=False):
    ffmpeg = bool(find_ffmpeg())
    ncm = importlib.util.find_spec("Crypto") is not None
    qq = local_qq and os.name == "nt"
    process_running = False
    frida_ok = importlib.util.find_spec("frida") is not None
    if qq and frida_ok:
        try:
            import frida
            process_running = any(p.name.lower() == "qqmusic.exe"
                                  for p in frida.get_local_device().enumerate_processes())
        except Exception:
            pass
    qmdec = QMDEC_SRC.is_dir() or importlib.util.find_spec("qmdec") is not None
    return {
        "ncm": {"available": ncm, "label": "NCM → MP3 / FLAC", "detail": "保留原始音质" if ncm else "请安装 pycryptodome"},
        "ogg": {"available": ffmpeg, "label": "OGG → MP3", "detail": "高质量 MP3" if ffmpeg else "服务器未安装 FFmpeg"},
        "lrc": {"available": True, "label": "复制 LRC 歌词", "detail": "保留歌词与目录结构"},
        "mgg": {"available": qq and qmdec and ffmpeg, "label": "MGG → MP3", "detail": "需要有效 QQ Cookie 或密钥缓存" if qq else "需使用本机 QQ 模式"},
        "mflac": {"available": qq and process_running and ffmpeg and HOOK_SCRIPT.is_file(), "label": "MFLAC → FLAC", "detail": "依赖本机 QQ 客户端版本" if qq and process_running else "需本机 QQ 模式并启动 QQ 音乐"},
        "cookie": {"available": qq and process_running and qmdec, "label": "更新 QQ Cookie", "detail": "仅本机 QQ 模式可用"},
    }


@dataclass
class Job:
    id: str
    owner: str
    root: Path
    files: list[str]
    created: float = field(default_factory=time.time)
    finished: float = 0
    status: str = "queued"
    stats: dict = field(default_factory=lambda: dict(total=0, success=0, skipped=0, failed=0))
    logs: list[str] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    cancel: threading.Event = field(default_factory=threading.Event)
    process: subprocess.Popen | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)

    def snapshot(self):
        with self.lock:
            return dict(id=self.id, status=self.status, stats=dict(self.stats),
                        logs=list(self.logs), outputs=list(self.outputs), files=self.files,
                        created=self.created, finished=self.finished)

    def log(self, message):
        with self.lock:
            message = str(message).replace(str(self.root), "[任务目录]")
            self.logs.append(message[:2000])
            self.logs[:] = self.logs[-250:]


class JobManager:
    def __init__(self, root, ttl=3600, timeout=900, max_jobs=20, quota=1024**3):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs = {}
        self.lock = threading.RLock()
        self.upload_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="conversion")
        self.ttl, self.timeout, self.max_jobs, self.quota = ttl, timeout, max_jobs, quota
        self.stopping = threading.Event()
        # This private data directory is exclusively owned by this single-process service.
        for path in self.root.iterdir():
            if path.is_dir() and re.fullmatch(r"[a-f0-9]{32}", path.name):
                shutil.rmtree(path)
        self.janitor = threading.Thread(target=self._janitor, daemon=True)
        self.janitor.start()

    def _janitor(self):
        while not self.stopping.wait(30):
            self.cleanup()

    def cleanup(self):
        with self.lock:
            for job_id, job in list(self.jobs.items()):
                if job.finished and time.time() - job.finished > self.ttl:
                    try:
                        shutil.rmtree(job.root)
                    except OSError:
                        continue  # An active download may still hold a Windows handle.
                    del self.jobs[job_id]

    def disk_usage(self):
        total = 0
        for path in self.root.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except FileNotFoundError:
                pass  # A converter may atomically rename its temporary output.
        return total

    def close(self):
        self.stopping.set()
        with self.lock:
            for job in self.jobs.values():
                job.cancel.set()
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.janitor.join(timeout=2)

    @staticmethod
    def stop_process(process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=15)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=15)

    def run(self, job):
        process = None
        try:
            if job.cancel.is_set():
                with job.lock:
                    job.status = "cancelled"
                return
            with job.lock:
                job.status = "running"
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            # A converter never receives the service access key or Flask signing key.
            for name in ("WEB_ACCESS_TOKEN", "WEB_SECRET_KEY"):
                env.pop(name, None)
            kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
            process = subprocess.Popen(
                [sys.executable, str(PROJECT_ROOT / "web_worker.py"), str(job.root)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", env=env, **kwargs)
            job.process = process
            received_done = threading.Event()

            def read_events():
                for line in process.stdout:
                    try:
                        event = json.loads(line)
                        kind, value = event["kind"], event["value"]
                        if kind in {"stats", "done"}:
                            with job.lock:
                                job.stats = value
                            if kind == "done":
                                received_done.set()
                        elif kind == "log":
                            job.log(value)
                    except (ValueError, KeyError, TypeError):
                        job.log(line.strip())

            reader = threading.Thread(target=read_events, daemon=True)
            reader.start()
            deadline = time.monotonic() + self.timeout
            timed_out = False
            storage_exceeded = False
            next_storage_check = time.monotonic()
            while process.poll() is None:
                if time.monotonic() >= next_storage_check:
                    storage_exceeded = self.disk_usage() > self.quota
                    next_storage_check = time.monotonic() + 2
                if job.cancel.wait(0.15) or time.monotonic() >= deadline or storage_exceeded:
                    timed_out = not job.cancel.is_set()
                    self.stop_process(process)
                    break
            reader.join(timeout=5)
            process.stdout.close()
            with job.lock:
                if job.cancel.is_set():
                    job.status = "cancelled"
                    job.log("任务已取消；未完成文件不会提供下载。")
                elif timed_out:
                    job.status = "failed"
                    job.log("临时存储已达到上限，任务已停止。" if storage_exceeded else "任务超过运行时间限制，已停止。")
                elif not received_done.is_set():
                    job.status = "failed"
                    job.log("转换进程异常退出，请检查服务日志或输入文件。")
                else:
                    failed = job.stats["failed"]
                    job.status = "partial" if failed and job.stats["success"] else "failed" if failed else "completed"
                    for path in sorted((job.root / "output").rglob("*")):
                        if path.is_file() and path.suffix.lower() in {".mp3", ".flac", ".lrc"} and not path.name.startswith("."):
                            job.outputs.append(dict(name=path.relative_to(job.root / "output").as_posix(), size=path.stat().st_size))
                    if job.outputs:
                        with zipfile.ZipFile(job.root / "results.zip", "w", compression=zipfile.ZIP_STORED) as archive:
                            for output in job.outputs:
                                archive.write(job.root / "output" / output["name"], output["name"])
        except Exception:
            with job.lock:
                job.status = "failed"
                job.outputs.clear()
            job.log("服务处理任务失败，请检查服务端日志。")
            import logging
            logging.exception("Conversion job failed: %s", job.id)
        finally:
            if process is not None and process.poll() is None:
                self.stop_process(process)
            with job.lock:
                job.finished = time.time()
                job.process = None
            shutil.rmtree(job.root / "input", ignore_errors=True)
            if job.status in {"cancelled", "failed"}:
                shutil.rmtree(job.root / "output", ignore_errors=True)


def create_app(config=None):
    app = Flask(__name__, static_folder="web", static_url_path="/assets")
    app.config.update(
        SECRET_KEY=os.environ.get("WEB_SECRET_KEY") or secrets.token_hex(32),
        ACCESS_TOKEN=os.environ.get("WEB_ACCESS_TOKEN", ""),
        LOCAL_QQ=False,
        DATA_DIR=os.environ.get("WEB_DATA_DIR", str(PROJECT_ROOT / ".web-data")),
        MAX_CONTENT_LENGTH=200 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=512 * 1024,
        MAX_FORM_PARTS=150,
        JOB_TTL=3600, JOB_TIMEOUT=900, MAX_JOBS=20, DISK_QUOTA=1024**3,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=os.environ.get("WEB_COOKIE_SECURE", "0") == "1",
    )
    if config:
        app.config.update(config)
    manager = JobManager(app.config["DATA_DIR"], app.config["JOB_TTL"], app.config["JOB_TIMEOUT"],
                         app.config["MAX_JOBS"], app.config["DISK_QUOTA"])
    app.extensions["jobs"] = manager
    atexit.register(manager.close)

    @app.before_request
    def guard():
        if app.config["LOCAL_QQ"]:
            if request.remote_addr not in {"127.0.0.1", "::1"} or request.host.split(":")[0] not in {"127.0.0.1", "localhost"}:
                abort(403, "本机 QQ 模式仅允许本机访问")
        if request.method in {"POST", "DELETE", "PUT", "PATCH"}:
            if request.headers.get("X-Requested-With") != "AudioWorkbench":
                abort(403, "无效的请求来源，请通过网页操作")
            origin = request.headers.get("Origin")
            if origin and urlsplit(origin).netloc != request.host:
                abort(403, "不允许跨站请求")
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                abort(403, "不允许跨站请求")
        if "owner" not in session:
            session["owner"] = secrets.token_hex(24)
        public = request.path in {"/", "/api/health", "/api/session"} or request.path.startswith("/assets/")
        if not public and app.config["ACCESS_TOKEN"] and not session.get("authenticated"):
            abort(401, "请输入访问口令")

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description if error.code != 413 else "上传内容过大，请拆分批次（每批最多 200 MB）"), error.code

    @app.get("/")
    def index():
        return send_file(PROJECT_ROOT / "web" / "index.html")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    @app.route("/api/session", methods=["GET", "POST", "DELETE"])
    def access():
        if request.method == "DELETE":
            session.clear()
        elif request.method == "POST":
            token = (request.get_json(silent=True) or {}).get("token", "")
            if not isinstance(token, str) or not hmac.compare_digest(token.encode(), app.config["ACCESS_TOKEN"].encode()):
                abort(401, "访问口令不正确")
            session["authenticated"] = True
        return jsonify(authenticated=not app.config["ACCESS_TOKEN"] or bool(session.get("authenticated")),
                       required=bool(app.config["ACCESS_TOKEN"]))

    @app.get("/api/capabilities")
    def environment():
        return jsonify(tasks=capabilities(app.config["LOCAL_QQ"]),
                       mode="local" if app.config["LOCAL_QQ"] else "public",
                       limits=dict(bytes=app.config["MAX_CONTENT_LENGTH"], files=100, ttl=app.config["JOB_TTL"]))

    def owned(job_id):
        with manager.lock:
            job = manager.jobs.get(job_id)
        if job is None or job.owner != session["owner"]:
            abort(404, "任务不存在或已过期")
        return job

    @app.post("/api/jobs")
    def submit():
        manager.cleanup()
        if not manager.upload_lock.acquire(blocking=False):
            abort(429, "正在接收其他上传，请稍后重试")
        root = None
        try:
            with manager.lock:
                if len(manager.jobs) >= manager.max_jobs:
                    abort(429, "任务已满，请删除旧任务或稍后重试")
                if sum(j.owner == session["owner"] and not j.finished for j in manager.jobs.values()) >= 2:
                    abort(429, "每个会话最多同时提交两个任务")
            # Reserve room for input, decoded output and the downloadable archive.
            if manager.disk_usage() + 4 * (request.content_length or app.config["MAX_CONTENT_LENGTH"]) > manager.quota:
                abort(503, "临时存储空间不足，请删除旧任务后重试")
            uploads = request.files.getlist("files")
            if not uploads or len(uploads) > 100:
                abort(400, "请选择 1–100 个文件")
            try:
                tasks = json.loads(request.form.get("tasks", "[]"))
            except ValueError:
                abort(400, "任务选项无效")
            if not isinstance(tasks, list) or not tasks or any(not isinstance(x, str) or x not in TASKS for x in tasks):
                abort(400, "请选择有效的转换任务")
            caps = capabilities(app.config["LOCAL_QQ"])
            if any(not caps[t]["available"] for t in tasks):
                abort(400, "所选任务在当前环境不可用，请刷新环境状态")
            paths, seen, output_keys = [], set(), set()
            for upload in uploads:
                try:
                    rel = safe_relative(upload.filename or "")
                except ValueError as exc:
                    abort(400, str(exc))
                if rel.suffix.lower()[1:] not in tasks:
                    abort(400, f"文件类型未启用或不支持：{rel.name}")
                key = rel.as_posix().casefold()
                # Multiple encrypted formats with the same stem may map to one output.
                output_key = (rel.parent / rel.stem).as_posix().casefold() + ("|lrc" if rel.suffix.lower() == ".lrc" else "|audio")
                if key in seen or output_key in output_keys:
                    abort(400, f"文件重名或输出名称冲突：{rel.name}")
                seen.add(key)
                output_keys.add(output_key)
                paths.append(rel)
            job_id = secrets.token_hex(16)
            root = manager.root / job_id
            (root / "input").mkdir(parents=True)
            for upload, rel in zip(uploads, paths):
                dest = root / "input" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                upload.save(dest)
                if not dest.stat().st_size:
                    abort(400, f"文件为空：{rel.name}")
            (root / "request.json").write_text(json.dumps(dict(tasks=tasks)), encoding="utf-8")
            job = Job(job_id, session["owner"], root, [p.as_posix() for p in paths])
            job.stats["total"] = len(paths)
            with manager.lock:
                manager.jobs[job_id] = job
            manager.executor.submit(manager.run, job)
            root = None
            return jsonify(job.snapshot()), 202
        finally:
            if root is not None:
                shutil.rmtree(root, ignore_errors=True)
            manager.upload_lock.release()

    @app.get("/api/jobs/<job_id>")
    def status(job_id):
        return jsonify(owned(job_id).snapshot())

    @app.post("/api/jobs/<job_id>/cancel")
    def cancel(job_id):
        job = owned(job_id)
        with job.lock:
            if not job.finished:
                job.cancel.set()
        return jsonify(job.snapshot())

    @app.delete("/api/jobs/<job_id>")
    def delete(job_id):
        job = owned(job_id)
        if not job.finished:
            abort(409, "请先取消任务，等待停止后再删除")
        with manager.lock:
            try:
                shutil.rmtree(job.root)
            except OSError:
                abort(409, "文件正在下载，请稍后删除")
            manager.jobs.pop(job_id, None)
        return jsonify(deleted=True)

    @app.get("/api/jobs/<job_id>/archive")
    def archive(job_id):
        job = owned(job_id)
        if not job.finished or not job.outputs:
            abort(409, "暂无可下载的结果")
        return send_file(job.root / "results.zip", as_attachment=True, download_name="转换结果.zip")

    @app.get("/api/jobs/<job_id>/files/<path:name>")
    def download(job_id, name):
        job = owned(job_id)
        if not job.finished or name not in {o["name"] for o in job.outputs}:
            abort(404)
        path = job.root / "output" / name
        return send_file(path, as_attachment=request.args.get("preview") != "1", download_name=path.name)

    @app.post("/api/cookie")
    def cookie():
        if not app.config["LOCAL_QQ"] or not capabilities(True)["cookie"]["available"]:
            abort(403, "更新 Cookie 仅限本机 QQ 模式，且必须启动 QQ 音乐")
        with manager.lock:
            if any(not j.finished for j in manager.jobs.values()):
                abort(409, "请等待转换任务完成")
        from update_cookie import update_cookie
        try:
            result = update_cookie()
        except Exception:
            abort(503, "更新失败，请确认 QQ 音乐已登录且权限足够")
        if not result.get("ok"):
            abort(503, "无法提取 Cookie，请检查 QQ 音乐登录状态和客户端版本")
        # Never return a Cookie, account identifier or credential length to the browser.
        return jsonify(ok=True, message="Cookie 已更新")

    return app
