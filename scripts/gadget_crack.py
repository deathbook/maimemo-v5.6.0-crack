#!/usr/bin/env python3
"""
gadget_crack.py — 免 root 破解：连接 APK 内嵌 frida-gadget 并注入破解脚本

原理：
  改过的 APK 里放了 META-INF/native/libmomoco.so（= frida-gadget），
  App 自己的 BaseAppContext.<clinit> 会把它解压到 cache 并 System.load()，
  gadget 在 127.0.0.1:27042 起监听。
  gadget 默认 on_load=wait，会阻塞主线程，所以必须在 ANR 超时前连上去。

用法:
    python gadget_crack.py [--keep]
"""
import os
import subprocess
import sys
import threading
import time

import frida

SERIAL = 'b733636b'
PKG = 'com.maimemo.android.momo'
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLE = os.path.join(BASE, 'frida', 'crack.bundle.js')
LOG = os.path.join(BASE, 'logs', 'gadget_crack.log')
GADGET_PORT = 27042


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True).stdout.decode('utf-8', 'replace').strip()


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def on_message(m, d):
    if m['type'] == 'send':
        p = m.get('payload')
        if isinstance(p, dict) and 'msg' in p:
            log(f"[{p.get('level','INFO')}] {p['msg']}")
        else:
            log('[send] ' + str(p))
    elif m['type'] == 'error':
        log('[error] ' + m.get('stack', str(m)))


def main():
    keep = '--keep' in sys.argv
    with open(BUNDLE, encoding='utf-8') as f:
        code = f.read()

    log('=== gadget_crack 开始 ===')
    sh(f'adb -s {SERIAL} forward tcp:{GADGET_PORT} tcp:{GADGET_PORT}')
    sh(f'adb -s {SERIAL} shell am force-stop {PKG}')
    sh(f'adb -s {SERIAL} logcat -c')
    time.sleep(1)

    # 启动
    sh(f'adb -s {SERIAL} shell monkey -p {PKG} -c android.intent.category.LAUNCHER 1')
    log('已启动 App，立刻轮询 gadget 端口…')

    dev = None
    target_pid = None
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            d = frida.get_device_manager().add_remote_device(f'127.0.0.1:{GADGET_PORT}')
            pids = d.enumerate_processes()          # 这一步成功 = gadget 响应了
            dev = d
            target_pid = pids[0].pid if pids else 0
            log(f'gadget 已响应，进程数={len(pids)}，目标 pid={target_pid} '
                f'({pids[0].name if pids else "?"})')
            break
        except Exception as e:
            time.sleep(0.4)

    if dev is None:
        log('❌ 25 秒内没能连上 gadget（App 可能已 ANR 被杀）')
        return 1

    try:
        session = dev.attach(target_pid)
        script = session.create_script(code)
        script.on('message', on_message)
        script.load()
        log('✅ 破解脚本已注入')
    except Exception as e:
        log(f'❌ 注入失败: {e}')
        return 1

    # 给脚本时间装 hook 并解锁主线程
    time.sleep(12)

    alive = sh(f'adb -s {SERIAL} shell "ps -A -o PID,NAME | grep -i maimemo"')
    log('App 进程: ' + (alive if alive else '(已退出)'))

    if keep:
        log('保持连接中，Ctrl+C 退出…')
        try:
            while True:
                time.sleep(3)
        except KeyboardInterrupt:
            pass
    log('=== gadget_crack 结束 ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
