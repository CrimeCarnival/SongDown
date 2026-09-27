"""Stable, visitor-facing conversion errors. Never include server exception text."""

def conversion_problem(messages, extension):
    text = '\n'.join(str(message) for message in messages).lower()
    rules = [
        (('unable to access process', '进程访问权限不足', 'access denied', 'permission denied'),
         'QQ_PERMISSION_DENIED', '服务器无法访问 QQ 音乐进程', '站长需要修复服务端运行权限；你无需安装或重启软件。'),
        (('未找到 qqmusic', 'unable to find process', 'process not found', 'qq_backend_unavailable'),
         'QQ_BACKEND_UNAVAILABLE', 'QQ 音乐转换服务尚未就绪', '请稍后重试，或联系站长检查服务器上的 QQ 音乐运行状态。'),
        (('no ekey', 'empty ekey', 'cookie may be expired', 'key derivation failed', 'invalid ekey'),
         'QQ_KEY_UNAVAILABLE', '未取得此文件的有效解密密钥', '请确认文件来源与使用权限；站长需检查服务端登录状态或密钥兼容性。'),
        (('frida hook', 'script has been destroyed', 'export', 'is not a function'),
         'QQ_VERSION_INCOMPATIBLE', 'QQ 音乐客户端与解密组件不兼容', '请联系站长检查服务端客户端版本，不需要在你的电脑上部署项目。'),
        (('未找到 ffmpeg', '无法导入 qmdec', '未找到 qmdec', '未安装 frida', '缺少 ncm 依赖'),
         'SERVER_COMPONENT_MISSING', '服务器缺少必要转换组件', '请联系站长补齐组件；下载区的组件包供站长维护使用。'),
        (('md5', '样本数校验失败', '音频参数或样本数异常'),
         'AUDIO_INTEGRITY_FAILED', '音频完整性校验未通过', '请从原来源重新获取完整文件后重试，当前结果不会提供下载。'),
        (('unsupported file format', '格式不支持'),
         'FORMAT_UNSUPPORTED', '暂不支持此加密格式或文件版本', '请确认文件类型；更改扩展名不能改变实际音频格式。'),
        (('ncm',), 'NCM_INVALID', 'NCM 文件损坏、内容不完整或版本不受支持', '请重新获取完整的原始 NCM 文件后重试。'),
        (('ffmpeg', 'invalid data', 'invalid argument'),
         'AUDIO_DECODE_FAILED', '无法读取音频内容', '文件可能损坏或扩展名与实际格式不符，请重新获取原文件。'),
    ]
    for markers, code, reason, action in rules:
        if any(marker in text for marker in markers):
            return dict(code=code, reason=reason, action=action)
    return dict(code='CONVERSION_FAILED', reason='此文件转换失败',
                action='请检查文件是否完整；若仍失败，请把任务编号与文件格式提供给站长。')
