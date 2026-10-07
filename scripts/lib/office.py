"""在受限环境里调用 LibreOffice —— 唯一一处。

默认用户 profile 在沙箱／受限 HOME 下会锁住或不可写，`soffice` 在**启动阶段**就抛
`DeploymentException`（`libc++abi: terminating due to uncaught exception of type
com::sun::star::deployment::DeploymentException`），与要转的文件无关。2026-10-07 实测：
本 Skill 自己的 `.doc` 转换用例因此长期红着，而三个调用点里只有一个显式给了临时 profile。

所以每次运行都显式 `-env:UserInstallation=<临时目录>`。写成一处，三个调用点共用：
`prepare_source_material.py`（.doc → docx）、`template/extract_template_pack.py`
（PPTX → PDF → PNG）、`test/test_source_assets.py`。
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def soffice_binary():
    """找到可用的 LibreOffice；找不到返回 None（调用方决定报什么错）。"""
    return shutil.which('soffice') or shutil.which('libreoffice')


def soffice_argv(args=None):
    """完整 argv：二进制 + 本次运行的临时 profile + 调用方参数。找不到二进制返回 None。"""
    binary = soffice_binary()
    if not binary:
        return None
    profile = Path(tempfile.gettempdir()) / f'lo_profile_{os.getpid()}'
    profile.mkdir(parents=True, exist_ok=True)
    return [binary, f'-env:UserInstallation={profile.as_uri()}'] + list(args or [])


def run_soffice(args, **kwargs):
    argv = soffice_argv(args)
    if argv is None:
        raise FileNotFoundError('soffice 未安装：转 .doc／渲染 PPTX 需要 LibreOffice')
    return subprocess.run(argv, **kwargs)
