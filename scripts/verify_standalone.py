# -*- coding: utf-8 -*-
"""
无 root 独立包 —— 一键真机验证。

做四件事：装包 → 清 logcat → 冷启 → 抓 logcat 里的 MoMoBoot/MoMoCrack 证据并断言。
不需要 root、不需要 frida-server。

用法：
    python scripts/verify_standalone.py [设备序列号] [--out logs/standalone_verify.log]
"""
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APK = os.path.join(BASE, 'build', 'standalone', 'signed',
                   'MoMoWords_L1_standalone_unsigned-aligned-debugSigned.apk')
PKG = 'com.maimemo.android.momo'
LIMIT = '2147483647'


def adb(*args, serial=None, timeout=180):
    cmd = ['adb']
    if serial:
        cmd += ['-s', serial]
    cmd += list(args)
    p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


def main():
    serial = None
    out_path = os.path.join(BASE, 'logs', 'standalone_verify.log')
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == '--out':
            out_path = argv[i + 1]
            i += 2
        else:
            serial = argv[i]
            i += 1

    if not os.path.exists(APK):
        sys.exit('APK 不存在: %s\n先跑 python scripts/build_standalone.py 并用 uber-apk-signer 签名' % APK)

    log = []

    def say(s):
        print(s)
        log.append(s)

    say('[1/5] 安装 %s' % os.path.basename(APK))
    rc, out, err = adb('install', '-r', '-d', APK, serial=serial, timeout=900)
    say('      ' + (out.strip().splitlines() or [''])[-1])
    if 'Success' not in out:
        say('      stderr: ' + err.strip()[:400])
        sys.exit(1)

    say('[2/5] 清空 logcat 并冷启动')
    adb('logcat', '-c', serial=serial)
    adb('shell', 'am', 'force-stop', PKG, serial=serial)
    adb('shell', 'monkey', '-p', PKG, '-c', 'android.intent.category.LAUNCHER', '1', serial=serial)
    say('      等待 45s 让 gadget 装 hook、App 走过启动页 …')
    time.sleep(45)

    rc, pid, _ = adb('shell', 'pidof', PKG, serial=serial)
    pid = pid.strip()
    say('      进程 pid = %s' % (pid or '(空!)'))

    say('[3/5] 抓取日志')
    rc, dump, _ = adb('logcat', '-d', '-s', 'MoMoBoot:I', 'MoMoCrack:I', serial=serial, timeout=300)
    for line in dump.splitlines():
        if 'MoMoBoot' in line or 'MoMoCrack' in line:
            say('      ' + line.strip())

    say('[4/5] 断言')
    checks = [
        ('loader 通过 dladdr 定位自身', r'MoMoBoot: dladdr self=/data/.*/libmomoco\.so'),
        ('真 libmomoco.so 已链式加载', r'MoMoBoot: chain dlopen\(libmomoco\.so\) -> 0x'),
        ('真 libmomoco 的 JNI_OnLoad 已调用', r'MoMoBoot: real libmomoco JNI_OnLoad=0x'),
        ('gadget + 脚本已释放到同目录', r'MoMoBoot: extract ok=1 js=.*mmc\.js so=.*libmmcore\.so'),
        ('frida-gadget 已 dlopen（无监听/无 attach）', r'MoMoBoot: dlopen\(gadget\) -> 0x'),
        ('hook a.s()', r'MoMoCrack: \[OK\] hook a\.s\(\)'),
        ('hook x1d.f(boolean)', r'MoMoCrack: \[OK\] hook x1d\.f\(boolean\)'),
        ('hook dma.a(int,String,String)', r'MoMoCrack: \[OK\] hook dma\.a\(int,String,String\)'),
        ('hook r47.getAvailableWordLimit', r'MoMoCrack: \[OK\] hook r47\.getAvailableWordLimit'),
        ('wrap ada.b()  (/log/study_log)', r'MoMoCrack: \[OK\] 已包装上报构造 ada\.b\(\)'),
        ('wrap s40.m()  (/misc/system/check)', r'MoMoCrack: \[OK\] 已包装上报构造 s40\.m\(\)'),
        ('wrap gq2.m()  (债务上报)', r'MoMoCrack: \[OK\] 已包装上报构造 gq2\.m\(\)'),
        ('本地可用上限 = 2147483647', r'MoMoCrack: \[INFO\] x1d\.f\(false\) = ' + LIMIT),
        ('自检 local=2147483647 且上报路径读到真实值',
         r'SELFTEST ok local=' + LIMIT + r' reporting=\d+ stealth=true origCallOk'),
    ]
    ok = True
    for name, pat in checks:
        hit = re.search(pat, dump) is not None
        say('      [%s] %s' % ('PASS' if hit else 'FAIL', name))
        ok = ok and hit

    leak = re.search(r'SELFTEST ok local=' + LIMIT + r' reporting=' + LIMIT, dump)
    if leak:
        say('      [FAIL] 上报路径泄露了无限值（反封号失效）')
        ok = False
    else:
        say('      [PASS] 上报路径没有泄露无限值')

    alive = bool(pid)
    say('      [%s] 进程存活（无壳自毁 / 无崩溃）' % ('PASS' if alive else 'FAIL'))
    ok = ok and alive

    rc, crash, _ = adb('logcat', '-d', serial=serial, timeout=300)
    seg = [l for l in crash.splitlines() if 'Fatal signal' in l and PKG.split('.')[-1] in l]
    say('      [%s] 无 Fatal signal' % ('PASS' if not seg else 'FAIL'))
    ok = ok and not seg

    say('[5/5] 结果: %s' % ('全部通过 ✅' if ok else '存在失败项 ❌'))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log) + '\n')
    print('证据已写入 %s' % out_path)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
