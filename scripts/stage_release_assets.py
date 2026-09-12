# -*- coding: utf-8 -*-
"""
把破解产物打成 Release 附件（GitHub 普通 git 单文件上限 100MB，
134MB 的破解 APK 只能走 Release 资源）。

产物：
    dist/maimemo_v5.6.0_cracked_standalone.apk   重打包 + 签名的破解包（可直接安装）
    dist/unpacked_dex.zip                        脱壳出来的业务 dex
    dist/native_libs.zip                         原版 / 补丁后 / 独立包 payload 的 .so
    dist/SHA256SUMS.txt                          校验清单
"""
import hashlib
import os
import shutil
import zipfile

BASE = r'C:\Users\O5-3\Documents\VibeCoding\Crack\MoMoWords'
SRC_APK = os.path.join(BASE, 'artifacts', 'maimemo_v5.6.00_900_1788339161.apk')
CRACKED_APK = os.path.join(BASE, 'build', 'standalone', 'signed',
                           'MoMoWords_L1_standalone_unsigned-aligned-debugSigned.apk')
DIST = os.path.join(BASE, 'dist')

DEXES = [
    ('analysis/unpacked/dex_0000_OK_OpenCommon_v039.dex', 'dex_0000_shell_anchor.dex'),
    ('analysis/unpacked/dex_0006_OK_OpenCommon_v037.dex', 'dex_0006_business.dex'),
    ('analysis/unpacked/dex_0007_OK_OpenCommon_v037.dex', 'dex_0007_business.dex'),
    ('analysis/unpacked/dex_0008_OK_OpenCommon_v037.dex', 'dex_0008_business.dex'),
    ('analysis/unpacked/dex_0009_OK_OpenCommon_v037.dex', 'dex_0009_business.dex'),
    ('patch/dex_0007_patched.dex', 'dex_0007_patched_a.s_returns_2147483647.dex'),
]

SO_FROM_APK = ['libDexHelper.so', 'libdexjni.so', 'libmomoco.so',
               'libmmsqlite.so', 'libmmsqlcipher.so', 'libmmftsext.so']

SO_FILES = [
    ('patch/elf/libdexjni.arm64.patched.so', 'patched/libdexjni.arm64.patched.so'),
    ('patch/elf/libmomoco.patched.so', 'patched/libmomoco.patched.so'),
    ('patch/gadget_payload/libmomoco.so', 'payload/libmomoco.so  <- 独立包=libmmboot+gadget+js'),
    ('patch/gadget_payload/libmmboot.so', 'payload/libmmboot.so'),
    ('patch/gadget_payload/stubs/libc.so', 'payload/stubs/libc.so'),
    ('patch/gadget_payload/stubs/libdl.so', 'payload/stubs/libdl.so'),
    ('patch/gadget_payload/stubs/liblog.so', 'payload/stubs/liblog.so'),
]


def sha256(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    os.makedirs(DIST, exist_ok=True)

    # 1) 破解 APK
    apk_out = os.path.join(DIST, 'maimemo_v5.6.0_cracked_standalone.apk')
    shutil.copyfile(CRACKED_APK, apk_out)
    print('[apk] %s  %.1f MB' % (os.path.basename(apk_out), os.path.getsize(apk_out) / 1048576))

    # 2) 脱壳 dex
    dex_zip = os.path.join(DIST, 'unpacked_dex.zip')
    with zipfile.ZipFile(dex_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel, arc in DEXES:
            p = os.path.join(BASE, rel.replace('/', os.sep))
            if os.path.exists(p):
                z.write(p, arc)
                print('    + %-52s %10d B' % (arc, os.path.getsize(p)))
    print('[dex] %s  %.1f MB' % (os.path.basename(dex_zip), os.path.getsize(dex_zip) / 1048576))

    # 3) native .so
    so_zip = os.path.join(DIST, 'native_libs.zip')
    tmp = os.path.join(DIST, '_tmp')
    os.makedirs(tmp, exist_ok=True)
    with zipfile.ZipFile(SRC_APK) as apk:
        for n in SO_FROM_APK:
            data = apk.read('lib/arm64-v8a/' + n)
            with open(os.path.join(tmp, n), 'wb') as f:
                f.write(data)
    with zipfile.ZipFile(so_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for n in SO_FROM_APK:
            z.write(os.path.join(tmp, n), 'original/lib/arm64-v8a/' + n)
            print('    + %-52s %10d B' % ('original/lib/arm64-v8a/' + n, os.path.getsize(os.path.join(tmp, n))))
        for rel, arc in SO_FILES:
            p = os.path.join(BASE, rel.replace('/', os.sep))
            if os.path.exists(p):
                z.write(p, arc.split('  ')[0])
                print('    + %-52s %10d B' % (arc.split('  ')[0], os.path.getsize(p)))
        z.writestr('README.txt',
                   'original/          从原版 APK 的 lib/arm64-v8a/ 解出（梆梆 SecNeo + Fort andjni）\n'
                   'patched/           我们对 libdexjni.so / libmomoco.so 做过的 ELF 补丁实验产物\n'
                   'payload/libmomoco.so  无 root 独立包真正落地的那个文件：\n'
                   '                   libmmboot.so(17512) + frida-gadget(25192176) + crack.js + 64B footer\n'
                   'payload/libmmboot.so  自解包引导层（源码见仓库 native/loader.c）\n'
                   'payload/stubs/     仅为往 DT_NEEDED 里塞 libdl/libc/liblog 名字用的空 stub\n')
    shutil.rmtree(tmp, ignore_errors=True)
    print('[so]  %s  %.1f MB' % (os.path.basename(so_zip), os.path.getsize(so_zip) / 1048576))

    # 4) 校验清单
    lines = []
    for name in ('maimemo_v5.6.0_cracked_standalone.apk', 'unpacked_dex.zip', 'native_libs.zip'):
        p = os.path.join(DIST, name)
        lines.append('%s  %s' % (sha256(p), name))
    sums = os.path.join(DIST, 'SHA256SUMS.txt')
    with open(sums, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('[sha256]')
    for l in lines:
        print('    ' + l)


if __name__ == '__main__':
    main()
