#!/usr/bin/env python3
"""
patch_dex_return.py — 在 DEX 字节层面把某个「无参返回 int」的方法体改成 `return <常量>`

为什么不用 baksmali/smali 全量重汇编：
    本 APK 有 3 万+ 类、1018 个类的方法体被 Fort andjni 抽取到 native。
    全量重汇编会改变 dex 结构（类索引/方法索引顺序），风险高、且前人已踩坑。
    本工具只改目标方法 code_item 里的 insns，其余字节保持完全一致，最小侵入。

用法:
    python patch_dex_return.py <in.dex> <out.dex> <class_descriptor> <method_name> <int_value>

例:
    python patch_dex_return.py dex_0007.dex dex_0007.patched.dex \\
        Lcom/maimemo/android/momo/a; s 2147483647
"""
import hashlib
import struct
import sys
import zlib

NO_INDEX = 0xFFFFFFFF


def uleb128(buf, off):
    result = 0
    shift = 0
    while True:
        b = buf[off]
        off += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, off


def read_uleb_keep(buf, off):
    """返回 (value, new_off, raw_bytes)"""
    start = off
    v, off = uleb128(buf, off)
    return v, off, buf[start:off]


class Dex:
    def __init__(self, data):
        self.d = bytearray(data)
        if self.d[:4] != b'dex\n':
            raise ValueError('not a dex')
        (self.string_ids_size, self.string_ids_off,
         self.type_ids_size, self.type_ids_off,
         self.proto_ids_size, self.proto_ids_off,
         self.field_ids_size, self.field_ids_off,
         self.method_ids_size, self.method_ids_off,
         self.class_defs_size, self.class_defs_off) = struct.unpack_from('<12I', self.d, 0x38)

    # ---- 基础表读取 ----
    def string(self, idx):
        if idx == NO_INDEX:
            return None
        off = struct.unpack_from('<I', self.d, self.string_ids_off + idx * 4)[0]
        _, p = uleb128(self.d, off)
        end = self.d.index(b'\x00', p)
        return self.d[p:end].decode('utf-8', 'replace')

    def type_desc(self, idx):
        if idx == NO_INDEX:
            return None
        sidx = struct.unpack_from('<I', self.d, self.type_ids_off + idx * 4)[0]
        return self.string(sidx)

    def method(self, idx):
        """-> (class_desc, name, (return_type, [params]))"""
        cidx, pidx, nidx = struct.unpack_from('<HHI', self.d, self.method_ids_off + idx * 8)
        sidx, ret, par_off = struct.unpack_from('<III', self.d, self.proto_ids_off + pidx * 12)
        params = []
        if par_off:
            n = struct.unpack_from('<I', self.d, par_off)[0]
            for i in range(n):
                t = struct.unpack_from('<H', self.d, par_off + 4 + i * 2)[0]
                params.append(self.type_desc(t))
        return self.type_desc(cidx), self.string(nidx), (self.type_desc(ret), params)

    # ---- class_data ----
    def find_class_def(self, desc):
        for i in range(self.class_defs_size):
            base = self.class_defs_off + i * 32
            cidx = struct.unpack_from('<I', self.d, base)[0]
            if self.type_desc(cidx) == desc:
                return base
        return None

    def class_methods(self, class_def_off):
        """-> list of (method_idx, access_flags, code_off)"""
        cd_off = struct.unpack_from('<I', self.d, class_def_off + 24)[0]
        if cd_off == 0:
            return []
        p = cd_off
        sf, p = uleb128(self.d, p)
        inf, p = uleb128(self.d, p)
        dm, p = uleb128(self.d, p)
        vm, p = uleb128(self.d, p)
        # 跳过字段
        for _ in range(sf + inf):
            _, p = uleb128(self.d, p)  # field_idx_diff
            _, p = uleb128(self.d, p)  # access_flags
        out = []
        midx = 0
        for _ in range(dm + vm):
            diff, p = uleb128(self.d, p)
            af, p = uleb128(self.d, p)
            code_off, p = uleb128(self.d, p)
            midx = diff if midx == 0 else midx + diff
            out.append((midx, af, code_off))
        return out

    # ---- 写回 ----
    def write_code(self, code_off, insns):
        """把新的指令序列写进 code_item（保持 insns_size 不变，尾部补 nop）"""
        regs, ins, outs, tries, dbg_off, insns_size = struct.unpack_from('<HHHHII', self.d, code_off)
        if tries != 0:
            raise RuntimeError(f'code_item @0x{code_off:x} 含 try/catch，拒绝字节级改写')
        if len(insns) > insns_size:
            raise RuntimeError(f'新指令需要 {len(insns)} code unit，原方法只有 {insns_size}，放不下')
        base = code_off + 16
        for i, u in enumerate(insns):
            struct.pack_into('<H', self.d, base + i * 2, u)
        for i in range(len(insns), insns_size):
            struct.pack_into('<H', self.d, base + i * 2, 0x0000)  # nop
        return regs, insns_size, len(insns)

    def fix_checksum_and_signature(self):
        # signature = SHA-1(offset 32 .. EOF)
        sig = hashlib.sha1(bytes(self.d[32:])).digest()
        self.d[12:32] = sig
        # checksum = adler32(offset 12 .. EOF)
        chk = zlib.adler32(bytes(self.d[12:])) & 0xFFFFFFFF
        struct.pack_into('<I', self.d, 8, chk)
        return chk, sig.hex()


def build_const_return(reg, value):
    """生成 `const vREG, value` + `return vREG` 的 code unit 列表"""
    if not (-0x80000000 <= value <= 0x7FFFFFFF):
        raise ValueError('值超出 32 位 int')
    out = []
    if -8 <= value <= 7:
        # const/4 vA, #+B   : opcode 0x12, A(4bit) B(4bit)
        out.append(0x12 | ((value & 0xF) << 12) | (reg << 8))
    elif -32768 <= value <= 32767:
        # const/16 vAA, #+BBBB : opcode 0x13
        out.append(0x13 | (reg << 8))
        out.append(value & 0xFFFF)
    else:
        # const vAA, #+BBBBBBBB : opcode 0x14
        out.append(0x14 | (reg << 8))
        out.append(value & 0xFFFF)
        out.append((value >> 16) & 0xFFFF)
    # return vAA : opcode 0x0F
    out.append(0x0F | (reg << 8))
    return out


def main():
    if len(sys.argv) != 6:
        print(__doc__)
        return 2
    src, dst, desc, mname, value = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])

    with open(src, 'rb') as f:
        raw = f.read()
    dex = Dex(raw)
    print(f'[i] {src}: {dex.class_defs_size} classes, {dex.method_ids_size} methods')

    cdo = dex.find_class_def(desc)
    if cdo is None:
        print(f'[!] 未找到类 {desc}')
        return 1
    print(f'[i] 类 {desc} @ class_def 0x{cdo:x}')

    hit = None
    for midx, af, code_off in dex.class_methods(cdo):
        c, n, (ret, params) = dex.method(midx)
        if n == mname:
            print(f'    method {c}->{n}() ret={ret} params={params} code_off=0x{code_off:x}')
            if ret == 'I' and not params and code_off:
                hit = (midx, code_off)
    if hit is None:
        print(f'[!] 未找到可改写的 {mname}()I（无参、非 abstract/native）')
        return 1

    midx, code_off = hit
    print(f'[i] 目标: method_idx={midx} @ code_item 0x{code_off:x}')
    before = bytes(dex.d[code_off + 16: code_off + 16 + 16])
    print(f'[i] 原始 insns 前 16 字节: {before.hex(" ")}')

    insns = build_const_return(0, value)
    regs, insns_size, used = dex.write_code(code_off, insns)
    print(f'[i] 写入 {used} code unit (原 {insns_size}, registers_size={regs}), 值={value}')

    after = bytes(dex.d[code_off + 16: code_off + 16 + 16])
    print(f'[i] 改写后 insns 前 16 字节: {after.hex(" ")}')

    chk, sig = dex.fix_checksum_and_signature()
    print(f'[i] checksum=0x{chk:08x} signature={sig[:16]}...')

    with open(dst, 'wb') as f:
        f.write(bytes(dex.d))
    print(f'[OK] 已写出 {dst}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
