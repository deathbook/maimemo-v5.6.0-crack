# -*- coding: utf-8 -*-
"""对比原版 APK 与重打包 APK 的 ZIP 结构，定位「设备安装器解析失败」的结构性差异。"""
import os
import struct

PATHS = {
    'ORIG 官方原版': r'C:\Users\O5-3\Documents\VibeCoding\Crack\MoMoWords\artifacts\maimemo_v5.6.00_900_1788339161.apk',
    'OURS 重打包版': r'C:\Users\O5-3\Documents\VibeCoding\Crack\MoMoWords\dist\maimemo_v5.6.0_cracked_standalone.apk',
}


def probe(tag, p):
    print('=' * 24, tag, '%.1f MB' % (os.path.getsize(p) / 1048576.0))
    with open(p, 'rb') as f:
        f.seek(-22, 2)
        eocd = f.read(22)
        sig, disk, cddisk, n_disk, n_tot, cdsize, cdoff, clen = struct.unpack('<IHHHHIIH', eocd)
        print('  EOCD=%s  entries=%d  cdsize=%d  comment=%d' % (hex(sig), n_tot, cdsize, clen))
        f.seek(-22 - 20, 2)
        z64 = struct.unpack('<I', f.read(4))[0]
        print('  zip64 locator = %s' % ('YES' if z64 == 0x07064b50 else 'no'))
        f.seek(cdoff)
        cd = f.read(cdsize)

    off, total, extras, systems, internals = 0, 0, 0, set(), set()
    meta_root = []
    interesting = {}
    while off < len(cd) - 4 and cd[off:off + 4] == b'PK\x01\x02':
        (_sig, vs, vn, fl, m, t, d, crc, cs, us, nl, el, cl, ds, ia, ea, lho) = \
            struct.unpack('<IHHHHHHIIIHHHHHII', cd[off:off + 46])
        name = cd[off + 46:off + 46 + nl].decode('utf-8', 'replace')
        total += 1
        if el:
            extras += 1
        systems.add(vs >> 8)
        internals.add(ia)
        if name.startswith('META-INF/') and name.count('/') == 1:
            meta_root.append(name)
        if name in ('AndroidManifest.xml', 'resources.arsc', 'classes.dex',
                    'META-INF/native/libmomoco.so', 'lib/arm64-v8a/libmomoco.so'):
            interesting[name] = (m, cs, us, el, lho)
        off += 46 + nl + el + cl

    print('  条目=%d  带extra字段=%d  version_made_by_hi(OS)=%s  internal_attr=%s'
          % (total, extras, systems, internals))
    print('  META-INF/ 根下的条目: %s' % (sorted(meta_root) or '（无）'))
    for k, (m, cs, us, el, lho) in sorted(interesting.items()):
        print('    %-34s method=%d  csize=%-10d usize=%-10d extra=%-3d localhdr_off=%d'
              % (k, m, cs, us, el, lho))
    # resources.arsc 是否 4 字节对齐（Android 11+ 硬要求）
    z = __import__('zipfile').ZipFile(p)
    info = z.getinfo('resources.arsc')
    with open(p, 'rb') as f:
        f.seek(info.header_offset + 26)
        nl, el = struct.unpack('<HH', f.read(4))
        data_off = info.header_offset + 30 + nl + el
    print('  resources.arsc: method=%d  data_off=0x%X  %%4=%d  %s'
          % (info.compress_type, data_off, data_off % 4,
             'OK' if info.compress_type == 0 and data_off % 4 == 0 else '!! 不合规'))
    mf = z.getinfo('AndroidManifest.xml')
    with open(p, 'rb') as f:
        f.seek(mf.header_offset + 26)
        nl, el = struct.unpack('<HH', f.read(4))
        doff = mf.header_offset + 30 + nl + el
    print('  AndroidManifest.xml: method=%d data_off=0x%X' % (mf.compress_type, doff))


for t, p in PATHS.items():
    probe(t, p)
