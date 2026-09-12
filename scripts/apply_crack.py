#!/usr/bin/env python3
"""
apply_crack.py — 对已运行的墨墨背单词注入破解 hook

模式:
    python apply_crack.py               # 默认：常驻守护（推荐）
                                        #   注入后保持 session，进程被杀/重启会自动重新注入
    python apply_crack.py --once 20     # 单次：注入后等 20 秒即 detach（用于取证/对照输出）

前置:
    - 模拟器/设备已 root，frida-server 在 0.0.0.0:27123 监听
    - adb forward tcp:27123 tcp:27123
    - App 已正常启动（★ 不要用 frida spawn：SecNeo 的 ptrace 反调试会让进程自杀）

日志: MoMoWords/logs/apply_crack.log
"""
import json
import os
import sys
import time

import frida

DEVICE = '127.0.0.1:27123'
PKG = 'com.maimemo.android.momo'
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(BASE, 'logs', 'apply_crack.log')
BUNDLE = os.path.join(BASE, 'frida', 'crack.bundle.js')


def log(msg, level='INFO'):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{level}] {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def on_message(message, data):
    if message['type'] == 'send':
        p = message['payload']
        if isinstance(p, dict) and 'msg' in p:
            log(f"{p.get('tag','')}[{p.get('level','INFO')}] {p['msg']}", 'SCRIPT')
        else:
            log('[script] ' + json.dumps(p, ensure_ascii=False), 'SEND')
    elif message['type'] == 'error':
        log('[script-error] ' + message.get('stack', str(message)), 'ERROR')
    else:
        log('[msg] ' + json.dumps(message, ensure_ascii=False), 'RAW')


def on_log(level, text):
    """兜底：万一脚本里还有裸 console.log，也接进日志文件。"""
    log(text, f'SCRIPT:{level}')


def find_pid(dev):
    """SecNeo 把 App 从 /proc 枚举里藏掉了，必须用 enumerate_applications。"""
    for a in dev.enumerate_applications():
        if a.identifier == PKG:
            return a.pid
    return None


def inject(dev, code, killed):
    """注入一次；返回 session（失败返回 None）"""
    pid = find_pid(dev)
    if not pid:
        return None
    session = dev.attach(pid)
    script = session.create_script(code)
    script.on('message', on_message)
    try:
        script.set_log_handler(on_log)
    except Exception as e:
        log(f'set_log_handler 不可用: {e}', 'WARN')
    script.on('destroyed', lambda: killed.set())
    script.load()
    log(f'crack.bundle.js 已注入 pid={pid}')
    return session


def main():
    args = sys.argv[1:]
    once = '--once' in args
    wait = 20.0
    if once:
        i = args.index('--once')
        if len(args) > i + 1:
            try:
                wait = float(args[i + 1])
            except ValueError:
                pass

    log(f'=== apply_crack 开始 (mode={"once" if once else "daemon"}) ===')

    dev = frida.get_device_manager().add_remote_device(DEVICE)
    with open(BUNDLE, encoding='utf-8') as f:
        code = f.read()

    if once:
        session = inject(dev, code, __import__('threading').Event())
        if session is None:
            log('App 未运行，先用 monkey 启动它', 'ERROR')
            return 1
        time.sleep(wait)
        try:
            session.detach()
        except Exception as e:
            log(f'detach: {e}', 'WARN')
        log('=== apply_crack 结束 ===')
        return 0

    # ---- 常驻守护模式 ----
    import threading
    log('守护模式：Ctrl+C 退出；进程被杀/重启会自动重新注入')
    session = None
    attached_pid = None

    while True:
        try:
            cur = find_pid(dev)

            # App 不在了
            if cur is None:
                if session is not None:
                    log('App 已退出，等待重新启动…', 'WARN')
                    try:
                        session.detach()
                    except Exception:
                        pass
                    session, attached_pid = None, None
                time.sleep(3)
                continue

            # ★ pid 变了（App 重启过），旧 session 已失效，必须重新注入
            if session is not None and cur != attached_pid:
                log(f'检测到进程重启 (pid {attached_pid} -> {cur})，重新注入', 'WARN')
                try:
                    session.detach()
                except Exception:
                    pass
                session, attached_pid = None, None

            if session is None:
                killed = threading.Event()
                try:
                    session = inject(dev, code, killed)
                except Exception as e:
                    log(f'注入失败({e})，3 秒后重试', 'WARN')
                    session, attached_pid = None, None
                    time.sleep(3)
                    continue
                if session is None:
                    time.sleep(3)
                    continue
                attached_pid = cur
                log(f'hook 已生效 (pid={attached_pid})')

            time.sleep(3)
        except KeyboardInterrupt:
            log('收到 Ctrl+C，退出')
            break
        except Exception as e:
            log(f'守护循环异常: {e}', 'WARN')
            session, attached_pid = None, None
            time.sleep(3)

    try:
        if session:
            session.detach()
    except Exception:
        pass
    log('=== apply_crack 结束 ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
