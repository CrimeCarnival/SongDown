from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = PROJECT_ROOT / "input"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
HOOK_SCRIPT = PROJECT_ROOT / "hook_qq_music.js"
QMDEC_SRC = PROJECT_ROOT / "input" / "Tools" / "qmdec" / "src"
BUNDLED_FFMPEG = PROJECT_ROOT / "input" / "Tools" / "ff.exe"

LogCallback = Callable[[str], None]
ProgressCallback = Callable[["ConversionStats"], None]
CancelCallback = Callable[[], bool]


@dataclass
class ConversionStats:
    total: int = 0
    success: int = 0
    skipped: int = 0
    failed: int = 0


@dataclass
class ConversionOptions:
    input_dir: Path
    output_dir: Path
    convert_mflac: bool = True
    convert_mgg: bool = True
    convert_ogg: bool = True
    copy_lrc: bool = True
    keep_intermediate: bool = False
    convert_ncm: bool = False


def _log(log: LogCallback | None, message: str) -> None:
    if log:
        log(message)


def _is_cancelled(cancelled: CancelCallback | None) -> bool:
    return bool(cancelled and cancelled())


def _emit(progress: ProgressCallback | None, stats: ConversionStats) -> None:
    if progress:
        progress(ConversionStats(stats.total, stats.success, stats.skipped, stats.failed))


def ensure_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def find_ffmpeg() -> str | None:
    which = shutil.which("ffmpeg")
    if which:
        return which
    return str(BUNDLED_FFMPEG) if os.name == "nt" and BUNDLED_FFMPEG.exists() else None


def check_environment(options: ConversionOptions) -> list[str]:
    issues: list[str] = []
    if not options.input_dir.is_dir():
        issues.append(f"输入目录不存在: {options.input_dir}")

    if options.convert_ogg or options.convert_mgg or options.convert_mflac:
        if find_ffmpeg() is None:
            issues.append("未找到 ffmpeg，也未找到内置 input/Tools/ff.exe")

    if options.convert_mgg and not QMDEC_SRC.is_dir() and importlib.util.find_spec("qmdec") is None:
        issues.append(f"未找到 qmdec 源码目录: {QMDEC_SRC}")

    if options.convert_mflac and not HOOK_SCRIPT.is_file():
        issues.append(f"未找到 Frida hook 脚本: {HOOK_SCRIPT}")

    return issues


def scan_total_files(options: ConversionOptions) -> int:
    if not options.input_dir.is_dir():
        return 0

    suffixes: set[str] = set()
    if options.convert_mflac:
        suffixes.add(".mflac")
    if options.convert_mgg:
        suffixes.add(".mgg")
    if options.convert_ogg:
        suffixes.add(".ogg")
    if options.copy_lrc:
        suffixes.add(".lrc")
    if options.convert_ncm:
        suffixes.add(".ncm")

    return sum(1 for p in options.input_dir.rglob("*") if p.is_file() and p.suffix.lower() in suffixes)


def _files_with_suffix(input_dir: Path, suffix: str):
    return sorted(p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() == suffix)


def _transcode_mp3(ffmpeg: str, source: Path, target: Path) -> None:
    """Publish only complete outputs; uploaded OGG must actually be an OGG stream."""
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".convert-", suffix=".mp3", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        cmd = [ffmpeg, "-nostdin", "-y", "-loglevel", "error", "-protocol_whitelist", "file,pipe"]
        if source.suffix.lower() == ".ogg":
            cmd += ["-f", "ogg"]
        cmd += ["-i", str(source), "-q:a", "0", "-map", "0:a:0", str(temporary)]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        if result.returncode != 0 or temporary.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg 失败: {result.stderr.strip()[:1500]}")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def copy_lrc_files(
    input_dir: Path,
    output_dir: Path,
    stats: ConversionStats,
    log: LogCallback | None = None,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> None:
    for lrc in _files_with_suffix(input_dir, ".lrc"):
        if _is_cancelled(cancelled):
            _log(log, "已取消，停止复制歌词。")
            return

        rel = lrc.relative_to(input_dir)
        dst = output_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            stats.skipped += 1
            _log(log, f"跳过歌词（已存在）: {rel}")
            _emit(progress, stats)
            continue

        try:
            shutil.copy2(lrc, dst)
            stats.success += 1
            _log(log, f"复制歌词: {rel}")
        except Exception as exc:
            stats.failed += 1
            _log(log, f"[失败] 复制歌词 {rel}: {exc}")
        _emit(progress, stats)


def convert_ogg_files(
    input_dir: Path,
    output_dir: Path,
    stats: ConversionStats,
    log: LogCallback | None = None,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> None:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        _log(log, "[错误] 未找到 ffmpeg，跳过 OGG 转 MP3。")
        stats.failed += len(_files_with_suffix(input_dir, ".ogg"))
        _emit(progress, stats)
        return

    for ogg in _files_with_suffix(input_dir, ".ogg"):
        if _is_cancelled(cancelled):
            _log(log, "已取消，停止 OGG 转 MP3。")
            return

        rel = ogg.relative_to(input_dir)
        target_dir = output_dir / rel.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        mp3 = target_dir / f"{ogg.stem}.mp3"

        if mp3.exists():
            stats.skipped += 1
            _log(log, f"跳过 OGG（mp3 已存在）: {rel}")
            _emit(progress, stats)
            continue

        _log(log, f"转换 OGG -> MP3: {rel}")
        try:
            _transcode_mp3(ffmpeg, ogg, mp3)
            stats.success += 1
            _log(log, f"  -> {mp3.relative_to(output_dir)}")
        except Exception as exc:
            stats.failed += 1
            _log(log, f"  [失败] {exc}")
        _emit(progress, stats)


def _load_qmdec(log: LogCallback | None = None):
    if str(QMDEC_SRC) not in sys.path:
        sys.path.insert(0, str(QMDEC_SRC))
    try:
        from qmdec.cli import decrypt_file, load_config
        return decrypt_file, load_config
    except ImportError as exc:
        _log(log, f"[错误] 无法导入 qmdec: {exc}")
        return None, None


def convert_mgg_files(
    input_dir: Path,
    output_dir: Path,
    stats: ConversionStats,
    log: LogCallback | None = None,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
    keep_intermediate: bool = False,
) -> None:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        _log(log, "[错误] 未找到 ffmpeg，跳过 MGG 转 MP3。")
        stats.failed += len(_files_with_suffix(input_dir, ".mgg"))
        _emit(progress, stats)
        return

    decrypt_file, load_config = _load_qmdec(log)
    if decrypt_file is None or load_config is None:
        stats.failed += len(_files_with_suffix(input_dir, ".mgg"))
        _emit(progress, stats)
        return

    config = load_config()
    if not config.get("cookie"):
        _log(log, "[警告] qmdec 未登录；如果没有 ekey 缓存，MGG 解密会失败。")

    for mgg in _files_with_suffix(input_dir, ".mgg"):
        if _is_cancelled(cancelled):
            _log(log, "已取消，停止 MGG 转 MP3。")
            return

        rel = mgg.relative_to(input_dir)
        target_dir = output_dir / rel.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        mp3 = target_dir / f"{mgg.stem}.mp3"

        if mp3.exists():
            stats.skipped += 1
            _log(log, f"跳过 MGG（mp3 已存在）: {rel}")
            _emit(progress, stats)
            continue

        _log(log, f"解密并转换 MGG -> MP3: {rel}")
        try:
            result = decrypt_file(mgg, target_dir, config, no_tag=True)
            if not result.get("ok"):
                raise RuntimeError(result.get("error", "解密失败"))

            decoded = Path(result["output"])
            if decoded.suffix.lower() == ".mp3":
                if decoded != mp3:
                    os.replace(decoded, mp3)
            else:
                _transcode_mp3(ffmpeg, decoded, mp3)
                if not keep_intermediate and decoded.exists():
                    decoded.unlink()

            stats.success += 1
            _log(log, f"  -> {mp3.relative_to(output_dir)}")
        except Exception as exc:
            stats.failed += 1
            _log(log, f"  [失败] {exc}")
        _emit(progress, stats)


def _flac_streaminfo(path: Path) -> tuple[int, bytes]:
    with path.open("rb") as stream:
        if stream.read(4) != b"fLaC":
            raise ValueError("解密结果不是有效的 FLAC")
        header = stream.read(4)
        if len(header) != 4 or header[0] & 127 != 0 or int.from_bytes(header[1:], "big") != 34:
            raise ValueError("FLAC STREAMINFO 无效")
        info = stream.read(34)
        if len(info) != 34:
            raise ValueError("FLAC STREAMINFO 已截断")
        return int.from_bytes(info[10:18], "big"), info[18:34]


def _normalize_flac(source: Path, target: Path) -> None:
    """Remove non-audio trailers through lossless encoding, proving PCM equality.

    QQ's decryptor can leave encrypted trailer bytes after the last FLAC frame.
    A successful ffmpeg exit alone is insufficient: compare STREAMINFO's original
    PCM MD5 and sample count against the newly encoded file before publication.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("MFLAC 输出校验需要 FFmpeg")
    original_info, original_md5 = _flac_streaminfo(source)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".flac-", suffix=".flac", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        result = subprocess.run(
            [ffmpeg, "-nostdin", "-y", "-v", "error", "-protocol_whitelist", "file,pipe",
             "-f", "flac", "-i", str(source), "-map", "0:a:0", "-map_metadata", "0",
             "-c:a", "flac", "-compression_level", "5", str(temporary)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"FLAC 无损整理失败: {result.stderr[:1000]}")
        new_info, new_md5 = _flac_streaminfo(temporary)
        samples_mask = (1 << 36) - 1
        if original_info >> 36 != new_info >> 36 or not new_info & samples_mask:
            raise ValueError("FLAC 音频参数或样本数异常")
        if original_info & samples_mask and (original_info & samples_mask) != (new_info & samples_mask):
            raise ValueError("FLAC 样本数校验失败，未生成输出")
        if any(original_md5):
            if original_md5 != new_md5:
                raise ValueError("FLAC 音频 MD5 校验失败，未生成输出")
        elif result.stderr.strip():
            raise ValueError("FLAC 存在解码错误且缺少原始 MD5，无法确认音频完整性")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def convert_mflac_files(
    input_dir: Path,
    output_dir: Path,
    stats: ConversionStats,
    log: LogCallback | None = None,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> None:
    try:
        import frida
    except ImportError as exc:
        _log(log, f"[错误] 未安装 frida，跳过 MFLAC 解密: {exc}")
        stats.failed += len(_files_with_suffix(input_dir, ".mflac"))
        _emit(progress, stats)
        return

    try:
        session = frida.attach("QQMusic.exe")
    except Exception as exc:
        _log(log, f"[错误] 无法附加 QQMusic.exe，请先启动 QQ音乐: {exc}")
        stats.failed += len(_files_with_suffix(input_dir, ".mflac"))
        _emit(progress, stats)
        return

    try:
        script = session.create_script(HOOK_SCRIPT.read_text(encoding="utf-8"))
        script.load()
    except Exception as exc:
        session.detach()
        _log(log, f"[错误] 加载 Frida hook 失败: {exc}")
        stats.failed += len(_files_with_suffix(input_dir, ".mflac"))
        _emit(progress, stats)
        return

    try:
        for mflac in _files_with_suffix(input_dir, ".mflac"):
            if _is_cancelled(cancelled):
                _log(log, "已取消，停止 MFLAC 解密。")
                return

            rel = mflac.relative_to(input_dir)
            target_dir = output_dir / rel.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            flac = target_dir / f"{mflac.stem}.flac"

            if flac.exists():
                stats.skipped += 1
                _log(log, f"跳过 MFLAC（flac 已存在）: {rel}")
                _emit(progress, stats)
                continue

            tmp = target_dir / hashlib.md5(str(rel).encode("utf-8")).hexdigest()
            _log(log, f"解密 MFLAC -> FLAC: {rel}")
            try:
                script.exports_sync.decrypt(str(mflac), str(tmp.resolve()))
                _normalize_flac(tmp, flac)
                tmp.unlink(missing_ok=True)
                stats.success += 1
                _log(log, f"  -> {flac.relative_to(output_dir)}")
            except Exception as exc:
                stats.failed += 1
                if tmp.exists():
                    tmp.unlink()
                _log(log, f"  [失败] {exc}")
            _emit(progress, stats)
    finally:
        session.detach()


def convert_ncm_files(input_dir, output_dir, stats, log=None, progress=None, cancelled=None):
    from ncm_decoder import ConversionCancelled, decode_ncm

    for source in sorted(input_dir.rglob("*")):
        if not source.is_file() or source.suffix.lower() != ".ncm":
            continue
        if _is_cancelled(cancelled):
            return
        rel = source.relative_to(input_dir)
        try:
            target, created = decode_ncm(source, output_dir / rel.parent, cancelled)
            if created:
                stats.success += 1
                _log(log, f"转换 NCM: {rel} -> {target.relative_to(output_dir)}")
            else:
                stats.skipped += 1
                _log(log, f"跳过 NCM（输出已存在）: {rel}")
        except ConversionCancelled:
            return
        except Exception as exc:
            stats.failed += 1
            _log(log, f"[失败] NCM {rel}: {exc}")
        _emit(progress, stats)


def run_conversion(
    options: ConversionOptions,
    log: LogCallback | None = None,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> ConversionStats:
    options.input_dir = Path(options.input_dir).resolve()
    options.output_dir = Path(options.output_dir).resolve()
    stats = ConversionStats(total=scan_total_files(options))
    _emit(progress, stats)

    issues = check_environment(options)
    if issues:
        for issue in issues:
            _log(log, f"[错误] {issue}")
        stats.failed = stats.total
        _emit(progress, stats)
        return stats

    ensure_output_dir(options.output_dir)
    _log(log, f"输入目录: {options.input_dir}")
    _log(log, f"输出目录: {options.output_dir}")
    _log(log, f"待处理文件数: {stats.total}")

    if stats.total == 0:
        _log(log, "没有找到需要处理的文件。")
        return stats

    if options.convert_mflac:
        convert_mflac_files(options.input_dir, options.output_dir, stats, log, progress, cancelled)
    if options.convert_mgg and not _is_cancelled(cancelled):
        convert_mgg_files(
            options.input_dir,
            options.output_dir,
            stats,
            log,
            progress,
            cancelled,
            keep_intermediate=options.keep_intermediate,
        )
    if options.convert_ogg and not _is_cancelled(cancelled):
        convert_ogg_files(options.input_dir, options.output_dir, stats, log, progress, cancelled)
    if options.convert_ncm and not _is_cancelled(cancelled):
        convert_ncm_files(options.input_dir, options.output_dir, stats, log, progress, cancelled)
    if options.copy_lrc and not _is_cancelled(cancelled):
        copy_lrc_files(options.input_dir, options.output_dir, stats, log, progress, cancelled)

    if _is_cancelled(cancelled):
        _log(log, "任务已取消。")
    _log(log, f"转换完成：成功 {stats.success}，跳过 {stats.skipped}，失败 {stats.failed}")
    return stats
