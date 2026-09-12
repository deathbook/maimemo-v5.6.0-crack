# -*- coding: utf-8 -*-
"""
构建 MoMoWords Lesson1「无 root 独立包」。

思路（不触碰 APK 的 lib/ —— 壳会校验 lib/ 目录，加/改任何文件都会自毁）：
  1) META-INF/native/libmomoco.so   = 自制引导层 libmmboot.so + 内嵌 frida-gadget + JS
     BaseAppContext.<clinit> 检测到该 classpath 资源存在时，会把它解到临时目录并 System.load()。
  2) 引导层在 JNI_OnLoad 里：
       a. dlopen("libmomoco.so") 把被顶替的真身链式加载回来并调用其 JNI_OnLoad
       b. 从自身文件尾部 footer 取出内嵌 gadget / 脚本，写入同一临时目录
       c. 生成 <dir>/libmmcore.config.so（gadget 只认自己所在目录的 <stem>.config.so）
       d. dlopen(<dir>/libmmcore.so) —— gadget 以 script 交互模式跑我们的 crack 脚本
  3) META-INF/native/ 下同时放真的 libmmsqlite / libmmsqlcipher / libmmftsext
     （BaseAppContext 走 classpath 分支时这两个 loader 也需要它们）
"""
import os
import struct
import zipfile

BASE = r'C:\Users\O5-3\Documents\VibeCoding\Crack\MoMoWords'
SRC_APK = os.path.join(BASE, 'artifacts', 'maimemo_v5.6.00_900_1788339161.apk')
LOADER = os.path.join(BASE, 'patch', 'gadget_payload', 'libmmboot.so')
GADGET = os.path.join(BASE, 'artifacts', 'gadget', 'frida-gadget-17.12.0-android-arm64.so')
SCRIPT = os.path.join(BASE, 'frida', 'gadget.bundle.js')
PAYLOAD = os.path.join(BASE, 'patch', 'gadget_payload', 'libmomoco.so')
OUTDIR = os.path.join(BASE, 'build', 'standalone')
OUT_APK = os.path.join(OUTDIR, 'MoMoWords_L1_standalone_unsigned.apk')


def build_payload():
    lb = open(LOADER, 'rb').read()
    gb = open(GADGET, 'rb').read()
    jb = open(SCRIPT, 'rb').read()
    blob = bytearray(lb)
    goff = len(blob)
    blob += gb
    joff = len(blob)
    blob += jb
    foot = bytearray(64)
    foot[0:4] = b'MMPK'
    struct.pack_into('<I', foot, 4, 1, )
    struct.pack_into('<Q', foot, 8, goff)
    struct.pack_into('<Q', foot, 16, len(gb))
    struct.pack_into('<Q', foot, 24, joff)
    struct.pack_into('<Q', foot, 32, len(jb))
    foot[40:44] = b'KPMN'
    blob += foot
    os.makedirs(os.path.dirname(PAYLOAD), exist_ok=True)
    with open(PAYLOAD, 'wb') as f:
        f.write(bytes(blob))
    print('[payload] %s = %d B  (loader %d + gadget %d + js %d + footer 64)'
          % (os.path.basename(PAYLOAD), len(blob), len(lb), len(gb), len(jb)))
    return len(blob)


def drop_entry(name):
    u = name.upper()
    return (u == 'META-INF/MANIFEST.MF' or u.endswith('.SF') or u.endswith('.RSA')
            or u.endswith('.DSA') or u.endswith('.EC'))


def build_apk():
    os.makedirs(OUTDIR, exist_ok=True)
    with zipfile.ZipFile(SRC_APK) as z:
        add = {
            'META-INF/native/libmomoco.so': open(PAYLOAD, 'rb').read(),
            'META-INF/native/libmmsqlite.so': z.read('lib/arm64-v8a/libmmsqlite.so'),
            'META-INF/native/libmmsqlcipher.so': z.read('lib/arm64-v8a/libmmsqlcipher.so'),
            'META-INF/native/libmmftsext.so': z.read('lib/arm64-v8a/libmmftsext.so'),
        }
        kept = 0
        with zipfile.ZipFile(OUT_APK, 'w', zipfile.ZIP_DEFLATED) as out:
            for info in z.infolist():
                if drop_entry(info.filename):
                    continue
                data = z.read(info.filename)
                ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                ni.compress_type = info.compress_type
                ni.external_attr = info.external_attr
                ni.internal_attr = info.internal_attr
                ni.create_system = info.create_system
                out.writestr(ni, data, compress_type=info.compress_type,
                             compresslevel=6 if info.compress_type == zipfile.ZIP_DEFLATED else None)
                kept += 1
            for name, data in add.items():
                ni = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
                ni.compress_type = zipfile.ZIP_DEFLATED
                ni.external_attr = 0o644 << 16
                out.writestr(ni, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
    size = os.path.getsize(OUT_APK)
    print('[apk] %s' % OUT_APK)
    print('[apk] %d B  (kept %d entries + %d new)' % (size, kept, len(add)))
    return OUT_APK


def verify():
    with zipfile.ZipFile(OUT_APK) as z:
        n = z.namelist()
        print('[verify] entries = %d' % len(n))
        for k in ('META-INF/native/libmomoco.so', 'META-INF/native/libmmsqlite.so',
                  'META-INF/native/libmmsqlcipher.so', 'lib/arm64-v8a/libmomoco.so',
                  'lib/arm64-v8a/libDexHelper.so', 'classes.dex', 'resources.arsc'):
            i = z.getinfo(k)
            print('   %-42s %10d  method=%d' % (k, i.file_size, i.compress_type))
        d = z.read('META-INF/native/libmomoco.so')
        assert d[:4] == b'\x7fELF', 'payload not ELF'
        assert d[-64:-60] == b'MMPK', 'payload footer magic missing'
        goff, glen, joff, jlen = struct.unpack('<QQQQ', d[-56:-24])
        assert d[goff:goff + 4] == b'\x7fELF', 'gadget blob not ELF'
        assert b'Java.perform' in d[joff:joff + jlen], 'js blob bad'
        print('[verify] footer ok  gadget@%d(%d) js@%d(%d)' % (goff, glen, joff, jlen))


if __name__ == '__main__':
    build_payload()
    build_apk()
    verify()
    print('[done]')
