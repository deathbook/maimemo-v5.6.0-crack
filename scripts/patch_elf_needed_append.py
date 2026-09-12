#!/usr/bin/env python3
"""
patch_elf_needed_append.py — 用「文件末尾追加 + 扩展最后一个 PT_LOAD」的方式注入 DT_NEEDED

适用场景：库内部被塞满（.dynamic 无空槽、.dynstr 无空位、也无大块零区），
          但 ELF 允许我们在文件尾部追加数据，并把**最后一个 PT_LOAD 段**的
          p_filesz / p_memsz 扩大，从而让追加的数据成为「已映射内存」，
          可以被 DT_STRTAB 指向。

做法：
  1. 在文件末尾（按 16 对齐）追加一份新的 .dynstr：原表 + 新库名；
  2. 扩展覆盖该区域的 PT_LOAD 的 p_filesz / p_memsz；
  3. DT_STRTAB 指向新位置，DT_STRSZ 调大；
  4. DT_NEEDED：优先用 .dynamic 里的空槽；没有空槽就扩展 PT_DYNAMIC 的 p_memsz
     （前提是动态段后面有零填充）。
  5. 同步 .dynstr 节头（bionic 的 get_string 会做边界检查）。

用法:
    python patch_elf_needed_append.py <in.so> <out.so> <needed_name>
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patch_elf_needed import ELF, DT_NEEDED, DT_STRTAB, DT_STRSZ, DT_NULL, PT_LOAD, PT_DYNAMIC  # noqa: E402


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    src, dst, name = sys.argv[1], sys.argv[2], sys.argv[3]
    raw = name.encode() + b'\0'

    elf = ELF(open(src, 'rb').read())
    seg, ents = elf.dynamic()
    strtab = strsz = None
    for _, t, v in ents:
        if t == DT_STRTAB:
            strtab = v
        if t == DT_STRSZ:
            strsz = v
    if strtab is None or strsz is None:
        print('[!] 找不到 DT_STRTAB / DT_STRSZ')
        return 1

    soff = elf.v2o(strtab)
    old_str = bytes(elf.d[soff:soff + strsz])
    dyn_null = ents[-1][0]
    dyn_end = seg['off'] + seg['memsz']
    free_slots = (dyn_end - dyn_null) // elf.dyn_sz - 1

    print(f'[i] {os.path.basename(src)}  ELF{"64" if elf.is64 else "32"}  {len(elf.d):,} B')
    print(f'    .dynstr @ {soff:#x} ({strsz} B)   DT_NULL @ {dyn_null:#x}  段内空槽={free_slots}')

    # 追加位置：文件尾 16 对齐
    append_at = (len(elf.d) + 15) // 16 * 16
    pad = append_at - len(elf.d)
    new_str_off = append_at
    new_str_end = new_str_off + strsz + len(raw)

    # 找最后一个 LOAD 段（按 vaddr 排序），把追加区并进去
    loads = [s for s in elf.segs if s['type'] == PT_LOAD]
    loads.sort(key=lambda s: s['vaddr'])
    last = loads[-1]
    last_file_end = last['off'] + last['filesz']
    last_v_end = last['vaddr'] + last['filesz']

    print(f'    最后一个 LOAD: off={last["off"]:#x} filesz={last["filesz"]:#x} vaddr={last["vaddr"]:#x}')
    print(f'      其文件结束 {last_file_end:#x}，文件实际 {len(elf.d):#x}，尾部非段区 {len(elf.d)-last_file_end} B')
    print(f'    追加 .dynstr 到 {new_str_off:#x}（+{pad}B 对齐），长度 {strsz+len(raw)} B')

    # 追加区必须能映射到 last LOAD 的连续 vaddr 上：
    # 追加偏移 - last.off 必须 < 新的 filesz，且 vaddr 连续
    new_filesz = (new_str_end - last['off'] + 0xFFF) & ~0xFFF
    new_memsz = max(last['memsz'], new_filesz)
    new_str_vaddr = last['vaddr'] + (new_str_off - last['off'])
    print(f'    扩 LOAD: filesz {last["filesz"]:#x} -> {new_filesz:#x}, memsz -> {new_memsz:#x}')
    print(f'    新 .dynstr vaddr = {new_str_vaddr:#x}')

    # ---- 改写 ----
    elf.d.extend(b'\0' * (new_filesz - (len(elf.d) - last['off'])))
    elf.d[new_str_off:new_str_off + strsz] = old_str
    elf.d[new_str_off + strsz:new_str_end] = raw
    new_name_index = strsz

    # 扩最后一个 LOAD 的 filesz/memsz
    for idx in range(elf.e_phnum):
        poff = elf.e_phoff + idx * elf.e_phentsize
        f = struct.unpack_from(elf.ent_fmt, elf.d, poff)
        if f[0] == PT_LOAD and f[2] == last['off'] if elf.is64 else False:
            pass
    # 直接按 off/vaddr 定位
    for idx in range(elf.e_phnum):
        poff = elf.e_phoff + idx * elf.e_phentsize
        f = struct.unpack_from(elf.ent_fmt, elf.d, poff)
        if f[0] != PT_LOAD:
            continue
        if elf.is64:
            off, va = f[2], f[3]
        else:
            off, va = f[1], f[2]
        if off == last['off'] and va == last['vaddr']:
            if elf.is64:
                struct.pack_into('<Q', elf.d, poff + 32, new_filesz)   # p_filesz
                struct.pack_into('<Q', elf.d, poff + 40, new_memsz)    # p_memsz
            else:
                struct.pack_into('<I', elf.d, poff + 16, new_filesz)
                struct.pack_into('<I', elf.d, poff + 20, new_memsz)
            print(f'    [OK] PT_LOAD#{idx} 已扩展')
            break

    # 更新 DT_STRTAB / DT_STRSZ
    for p, t, _ in ents:
        if t == DT_STRTAB:
            elf.set_dyn(p, DT_STRTAB, new_str_vaddr)
        if t == DT_STRSZ:
            elf.set_dyn(p, DT_STRSZ, strsz + len(raw))

    # DT_NEEDED：有空槽就用，没有就扩动态段
    if free_slots >= 1:
        elf.set_dyn(dyn_null, DT_NEEDED, new_name_index)
        elf.set_dyn(dyn_null + elf.dyn_sz, DT_NULL, 0)
        print(f'    DT_NEEDED({name}) -> 用段内空槽 @ {dyn_null:#x}')
    else:
        # 动态段后必须是零填充才能扩
        tail = bytes(elf.d[dyn_end:dyn_end + elf.dyn_sz * 2])
        if tail.strip(b'\0') != b'':
            print('[!] 动态段后非零填充，无法扩展，放弃')
            return 1
        for idx in range(elf.e_phnum):
            poff = elf.e_phoff + idx * elf.e_phentsize
            f = struct.unpack_from(elf.ent_fmt, elf.d, poff)
            if f[0] != PT_DYNAMIC:
                continue
            if elf.is64:
                struct.pack_into('<Q', elf.d, poff + 40, seg['memsz'] + elf.dyn_sz * 2)
            else:
                struct.pack_into('<I', elf.d, poff + 20, seg['memsz'] + elf.dyn_sz * 2)
            break
        elf.set_dyn(dyn_null, DT_NEEDED, new_name_index)
        elf.set_dyn(dyn_null + elf.dyn_sz, DT_NULL, 0)
        print(f'    DT_NEEDED({name}) -> 扩展动态段后写入 @ {dyn_null:#x}')

    # .dynstr 节头（若存在）
    for sh in elf.section_headers():
        if sh['type'] == 3 and sh['sh_offset'] == soff:
            elf.set_section_size(sh, strsz + len(raw))
            ooff = sh['off_in_file'] + (24 if elf.is64 else 16)
            if elf.is64:
                struct.pack_into('<Q', elf.d, ooff, new_str_off)
            else:
                struct.pack_into('<I', elf.d, ooff, new_str_off)
            print(f'    .dynstr 节头 -> offset={new_str_off:#x} size={strsz+len(raw):#x}')
            break

    open(dst, 'wb').write(bytes(elf.d))
    print(f'[OK] {dst}  ({os.path.getsize(dst):,} B, 原 {os.path.getsize(src):,} B)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
