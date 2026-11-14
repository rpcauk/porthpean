#!/usr/bin/env python3
"""Keep noninteractive installer commands behind a whiptail gauge.

The child gets a PTY for output (so pacman emits real progress), but inherits
stdin directly. Password pipes are never echoed to the PTY or recorded.
"""
import argparse
import errno
import fcntl
import os
import re
import selectors
import signal
import struct
import subprocess
import termios
import time

ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)')
PACKAGE = re.compile(r'\(\s*(\d+)\s*/\s*(\d+)\)\s+(installing|upgrading|reinstalling|downgrading|removing)\s+(\S+)')
PERCENT = re.compile(r'(\d{1,3})%')


def clean(line):
    return ''.join(c for c in ANSI.sub('', line) if c.isprintable() or c == '\t').strip()


def progress(line, stage):
    line = clean(line)
    percent = PERCENT.search(line)
    package = PACKAGE.search(line)
    if package:
        index, total, action, name = package.groups()
        return min(int(percent[1]), 100) if percent else 0, f'{stage}\n{action.capitalize()} {name} ({index}/{total})'
    if percent:
        label = line.split('[', 1)[0].strip()
        return min(int(percent[1]), 100), f'{stage}\n{label[:160]}'
    return None, f'{stage}\n{line[:180]}' if line else stage


def frame(percent, message):
    # Never allow command output to terminate/inject the whiptail gauge protocol.
    message = '\n'.join(row for row in message.splitlines() if row.strip() != 'XXX')
    return f'XXX\n{max(0, min(percent, 100))}\n{message}\nXXX\n'.encode()


def run_command(command, stage, log_path, *, terminal=None, stdin=None, gauge_command=None):
    owned_terminal = terminal is None
    if terminal is None:
        terminal = open('/dev/tty', 'wb', buffering=0)
    gauge_command = gauge_command or ['whiptail', '--title', 'Porthpean installation', '--gauge', stage, '12', '78', '0']
    descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.fchmod(descriptor, 0o600)
    master, slave = os.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
    gauge = None
    child = None
    started = time.monotonic()
    percent = 0
    message = stage
    pending = ''
    last_update = 0.0
    last_frame = None
    last_package = None
    selector = selectors.DefaultSelector()

    def emit(done=False):
        nonlocal last_update, last_frame
        elapsed = int(time.monotonic() - started)
        value = 100 if done else percent
        text = (stage + '\nComplete' if done else message) + f'\nElapsed {elapsed // 60:02d}:{elapsed % 60:02d}'
        payload = frame(value, text)
        if payload != last_frame:
            try:
                gauge.stdin.write(payload)
                gauge.stdin.flush()
            except (BrokenPipeError, OSError):
                # Do not interrupt a package transaction because the display closed.
                pass
            last_frame = payload
        last_update = time.monotonic()

    def consume(line, log):
        nonlocal percent, message, last_package
        line = clean(line)
        if not line:
            return
        log.write(line + '\n')
        value, message = progress(line, stage)
        percent = 0 if value is None else value
        package = PACKAGE.search(line)
        if package and package.groups() != last_package:
            last_package = package.groups()
            emit()

    try:
        with os.fdopen(descriptor, 'a', encoding='utf-8', buffering=1) as log:
            log.write(f'\n=== {stage} ===\n')
            gauge = subprocess.Popen(gauge_command, stdin=subprocess.PIPE, stdout=terminal, stderr=terminal)
            env = dict(os.environ, LC_ALL='C', TERM='xterm', COLUMNS='100', LINES='30')
            # argv is passed directly, never converted into shell text.
            child = subprocess.Popen(command, stdin=stdin, stdout=slave, stderr=slave, env=env, start_new_session=True)
            os.close(slave)
            slave = -1
            selector.register(master, selectors.EVENT_READ)
            emit()
            eof = False
            while not eof:
                for key, _ in selector.select(timeout=0.2):
                    try:
                        data = os.read(key.fd, 65536)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        data = b''
                    if not data:
                        eof = True
                        break
                    pending += data.decode('utf-8', errors='replace').replace('\r', '\n')
                    while '\n' in pending:
                        line, pending = pending.split('\n', 1)
                        consume(line, log)
                        if time.monotonic() - last_update >= 0.08:
                            emit()
                if time.monotonic() - last_update >= 0.5:
                    emit()
            if pending:
                consume(pending, log)
            status = child.wait()
            log.write(f'=== Exit status: {status} ===\n')
            if status == 0:
                emit(done=True)
            return status if status >= 0 else 128 - status
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        if gauge is not None:
            try:
                gauge.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            try:
                gauge.wait(timeout=3)
            except subprocess.TimeoutExpired:
                gauge.terminate()
                gauge.wait()
        selector.close()
        os.close(master)
        if slave >= 0:
            os.close(slave)
        if owned_terminal:
            terminal.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', required=True)
    parser.add_argument('--log', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('command required')
    return run_command(command, args.stage, args.log)


if __name__ == '__main__':
    raise SystemExit(main())
