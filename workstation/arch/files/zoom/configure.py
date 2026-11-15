#!/usr/bin/env python3
"""Idempotent, comment-preserving Citrix module.ini integration."""
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time


def configure(text):
    lines = text.splitlines()
    drivers = [i for i, line in enumerate(lines) if re.match(r'^\s*VirtualDriver\s*=', line, re.I)]
    if len(drivers) != 1:
        raise ValueError('Expected exactly one Citrix VirtualDriver list; refusing ambiguous config')
    index = drivers[0]
    key, value = lines[index].split('=', 1)
    entries = [entry.strip() for entry in value.split(',') if entry.strip() and entry.strip().lower() != 'zoommedia']
    lines[index] = key + '=' + ','.join(entries + ['ZoomMedia'])
    end = next((i for i in range(index + 1, len(lines)) if re.match(r'^\s*\[', lines[i])), len(lines))
    start = next((i for i in range(index - 1, -1, -1) if re.match(r'^\s*\[', lines[i])), -1)
    switches = [i for i in range(start + 1, end) if re.match(r'^\s*ZoomMedia\s*=', lines[i], re.I)]
    if len(switches) > 1:
        raise ValueError('Duplicate ZoomMedia switch')
    if switches:
        lines[switches[0]] = 'ZoomMedia=On'
    else:
        lines.insert(index + 1, 'ZoomMedia=On')
    sections = [i for i, line in enumerate(lines) if re.match(r'^\s*\[ZoomMedia\]\s*$', line, re.I)]
    if len(sections) > 1:
        raise ValueError('Duplicate ZoomMedia section')
    if sections:
        start = sections[0]
        end = next((i for i in range(start + 1, len(lines)) if re.match(r'^\s*\[', lines[i])), len(lines))
        driver = [i for i in range(start + 1, end) if re.match(r'^\s*DriverName\s*=', lines[i], re.I)]
        if len(driver) > 1:
            raise ValueError('Duplicate ZoomMedia driver')
        if driver:
            lines[driver[0]] = 'DriverName=ZoomMedia.so'
        else:
            lines.insert(start + 1, 'DriverName=ZoomMedia.so')
    else:
        lines += ['', '[ZoomMedia]', 'DriverName=ZoomMedia.so']
    return ('\r\n' if '\r\n' in text else '\n').join(lines) + ('\r\n' if '\r\n' in text else '\n')


def main():
    path = Path(sys.argv[1]).resolve(strict=True)
    with path.open(newline='') as stream:
        original = stream.read()
    result = configure(original)
    changed = original != result
    if changed:
        info = path.stat()
        shutil.copy2(path, str(path) + f'.porthpean-{time.time_ns()}.bak')
        fd, temporary = tempfile.mkstemp(prefix='.zoom-module-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', newline='') as stream:
                stream.write(result)
                os.fchmod(stream.fileno(), info.st_mode & 0o777)
                os.fchown(stream.fileno(), info.st_uid, info.st_gid)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    print(json.dumps({'changed': changed}))


if __name__ == '__main__':
    main()
