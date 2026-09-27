"""Process uploaded files independently; emit safe per-file results for the site."""
import json
import os
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

from audio_converter_core import ConversionOptions, ConversionStats, run_conversion
from conversion_errors import conversion_problem


def emit(kind, value):
    print(json.dumps({'kind': kind, 'value': value}, ensure_ascii=False), flush=True)


def main():
    root = Path(sys.argv[1]).resolve()
    tasks = json.loads((root / 'request.json').read_text(encoding='utf-8'))['tasks']
    files = sorted(p for p in (root / 'input').rglob('*') if p.is_file())
    total = ConversionStats(total=len(files))
    emit('stats', asdict(total))
    for index, source in enumerate(files):
        rel = source.relative_to(root / 'input')
        ext = source.suffix.lower()[1:]
        work = root / 'work' / str(index)
        messages = []
        emit('log', f'正在处理：{rel.as_posix()}')
        try:
            if ext not in tasks:
                raise ValueError('格式不支持')
            if ext == 'mflac' and os.name != 'nt':
                raise RuntimeError('QQ_BACKEND_UNAVAILABLE')
            # qmdec caches keys by file metadata. Reject unsafe cache filenames first.
            if ext == 'mgg':
                from audio_converter_core import QMDEC_SRC
                if str(QMDEC_SRC) not in sys.path:
                    sys.path.insert(0, str(QMDEC_SRC))
                try:
                    from qmdec.musicex import parse_file_tail
                except ImportError as exc:
                    raise RuntimeError('无法导入 qmdec') from exc
                import re
                if source.stat().st_size < 8:
                    raise ValueError('unsupported file format: truncated')
                try:
                    meta = parse_file_tail(source)
                except (OSError, ValueError) as exc:
                    raise ValueError('unsupported file format: corrupt metadata') from exc
                if meta is None:
                    raise ValueError('unsupported file format')
                for field in ('song_mid', 'filename'):
                    value = meta.get(field, '')
                    if value and (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,179}', value)):
                        raise ValueError('unsupported file format: unsafe metadata')
                if not 0 < meta.get('audio_size', 0) <= source.stat().st_size:
                    raise ValueError('unsupported file format: audio length')
            isolated = work / 'input' / rel
            isolated.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), isolated)
            options = ConversionOptions(work / 'input', work / 'output',
                convert_ncm=ext == 'ncm', convert_ogg=ext == 'ogg',
                convert_mgg=ext == 'mgg', convert_mflac=ext == 'mflac', copy_lrc=ext == 'lrc')
            stats = run_conversion(options, log=messages.append)
            if stats.failed or not stats.success:
                raise RuntimeError('conversion failed')
            outputs = [p for p in (work / 'output').rglob('*') if p.is_file()
                       and p.suffix.lower() in {'.mp3', '.flac', '.lrc'} and not p.name.startswith('.')]
            if not outputs:
                raise RuntimeError('conversion produced no output')
            for path in outputs:
                target = root / 'output' / path.relative_to(work / 'output')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), target)
            total.success += 1
            emit('file_result', dict(name=rel.as_posix(), status='success'))
            emit('log', f'转换成功：{rel.as_posix()}')
        except Exception as exc:
            messages.append(str(exc))
            total.failed += 1
            problem = conversion_problem(messages, ext)
            emit('file_result', dict(name=rel.as_posix(), status='failed', **problem))
            emit('log', f'转换失败：{rel.as_posix()}；{problem["reason"]}')
            # Detailed diagnostics stay in the service console, never in the API response.
            emit('diagnostic', dict(file=rel.as_posix(), messages=messages))
        finally:
            shutil.rmtree(work, ignore_errors=True)
        emit('stats', asdict(total))
    emit('done', asdict(total))
    return 1 if total.failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
