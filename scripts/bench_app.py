# -*- coding: utf-8 -*-
"""
对已安装的墨墨破解包做可复现的性能采样：
  1) 冷启动耗时（am start -W 的 TotalTime）
  2) 启动后 N 秒内 主线程 / 全进程 的 CPU tick 增量（jiffies，读 /proc/<pid>/stat）
  3) MoMoCrack 自检行

用法：python scripts/bench_app.py [设备序列号] [--wait 20] [--install <apk>]
"""
import os
import re
import subprocess
import sys
import time

PKG = 'com.maimemo.android.momo'
ACT = PKG + '/com.maimemo.android.momo.ui.SplashActivity'
SERIAL = None


def adb(*args, timeout=300):
    cmd = ['adb'] + (['-s', SERIAL] if SERIAL else []) + list(args)
    p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return p.stdout.decode('utf-8', 'replace')


def pid_of():
    out = adb('shell', 'pidof', PKG).strip()
    return out.split()[0] if out else None


def ticks(pid, per_thread=False):
    """返回 (utime, stime) ticks 之和；读不到返回 None。"""
    for _ in range(4):
        if per_thread:
            ls = adb('shell', 'ls', '/proc/%s/task' % pid).split()
            if not ls:
                time.sleep(0.3); continue
            tot_u = tot_s = 0
            bad = False
            for t in ls:
                st = adb('shell', 'cat', '/proc/%s/task/%s/stat' % (pid, t))
                if ')' not in st:
                    bad = True; break
                f = st[st.rindex(')') + 2:].split()
                if len(f) <= 12:
                    bad = True; break
                tot_u += int(f[11]); tot_s += int(f[12])
            if not bad:
                return tot_u, tot_s
        else:
            st = adb('shell', 'cat', '/proc/%s/task/%s/stat' % (pid, pid))
            if ')' in st:
                f = st[st.rindex(')') + 2:].split()
                if len(f) > 12:
                    return int(f[11]), int(f[12])
        time.sleep(0.3)
    return None


def main():
    global SERIAL
    wait = 20
    apk = None
    interact = False
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == '--wait':
            wait = int(argv[i + 1]); i += 2
        elif argv[i] == '--install':
            apk = argv[i + 1]; i += 2
        elif argv[i] == '--interact':
            interact = True; i += 1
        else:
            SERIAL = argv[i]; i += 1

    if apk:
        print('[install] %s' % os.path.basename(apk))
        print('   ' + adb('install', '-r', '-d', apk, timeout=1200).strip().splitlines()[-1])

    adb('logcat', '-c')
    adb('shell', 'am', 'force-stop', PKG)
    time.sleep(1)

    out = adb('shell', 'am', 'start', '-W', '-n', ACT)
    m = re.search(r'TotalTime:\s*(\d+)', out)
    total_ms = int(m.group(1)) if m else -1
    print('[cold start] TotalTime = %s ms' % (total_ms if total_ms >= 0 else 'n/a'))

    pid = None
    for _ in range(20):
        pid = pid_of()
        if pid:
            break
        time.sleep(0.5)
    if not pid:
        print('  进程没起来！')
        print(adb('logcat', '-d', '-s', 'MoMoBoot:I', 'MoMoCrack:I'))
        sys.exit(1)
    print('[pid] %s' % pid)

    mu0 = ticks(pid); pu0 = ticks(pid, per_thread=True)
    mu0 = mu0 or (0, 0); pu0 = pu0 or (0, 0)
    mu0, ms0 = mu0
    pu0, ps0 = pu0
    if interact:
        # 用滑动列表当负载发生器：任何内容区的滑动都会驱动 Compose 重组 + 主线程绘制
        n = max(1, int(wait / 0.4))
        print('[load] %d 次滑动（模拟连续操作底部导航/列表）' % n)
        for k in range(n):
            if k % 2 == 0:
                adb('shell', 'input', 'swipe', '720', '1900', '720', '1000', '110')
            else:
                adb('shell', 'input', 'swipe', '720', '1000', '720', '1900', '110')
    else:
        print('[load] 无操作（空闲基线）')
    time.sleep(wait)
    pid2 = pid_of() or pid
    mu1 = ticks(pid2) or (0, 0)
    pu1 = ticks(pid2, per_thread=True) or (0, 0)
    mu1, ms1 = mu1
    pu1, ps1 = pu1

    print('[cpu] 窗口 %ds（screen 状态会影响绝对值，A/B 要在同一状态下测）' % wait)
    print('   主线程   : %d ticks  (u %d / s %d)' % ((mu1 - mu0) + (ms1 - ms0), mu1 - mu0, ms1 - ms0))
    print('   全进程   : %d ticks  (u %d / s %d)' % ((pu1 - pu0) + (ps1 - ps0), pu1 - pu0, ps1 - ps0))

    print('[logcat]')
    for line in adb('logcat', '-d', '-s', 'MoMoBoot:I', 'MoMoCrack:I').splitlines():
        if 'MoMoBoot' in line or 'MoMoCrack' in line:
            print('   ' + line.strip())


if __name__ == '__main__':
    main()
