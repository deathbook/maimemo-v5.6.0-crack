/*
 * dump_dex.js — Lesson1 (maimemo v5.6.00) 脱壳
 *
 * 原理：梆梆 SecNeo 壳把真实 dex 加密存放在 APK 的 classes.dex 中，
 *       运行时在内存里解密，然后交给 ART 的 DexFileLoader::OpenCommon 解析。
 *       在 OpenCommon 入口拦截 (data_ptr, size)，即可拿到「壳篡改前」的原始 dex。
 *
 * Hook 目标：libdexfile.so (Android 12 x86_64, libc++ 名字修饰)
 * 输出目录  ：/data/local/tmp/momo_l1/
 */
'use strict';

var TAG = '[DumpDex]';
var OUT_DIR = '/data/local/tmp/momo_l1';
var seen = {};
var nDumped = 0, nFailed = 0, nNonDex = 0;
var HOOK_MODE = (typeof MODE !== 'undefined') ? MODE : 'early';

function log(level, msg) {
    console.log(new Date().toISOString() + ' ' + TAG + '[' + level + '] ' + msg);
}

function adler32(u8, from) {
    var a = 1, b = 0;
    for (var i = from; i < u8.length; i++) {
        a = (a + u8[i]) % 65521;
        b = (b + a) % 65521;
    }
    return (((b << 16) | a) >>> 0);
}

function ensureDir(path) {
    var mkdir = new NativeFunction(Module.getGlobalExportByName('mkdir'), 'int', ['pointer', 'int']);
    var mk = Memory.allocUtf8String(path);
    var r = mkdir(mk, 0x1ff /* 0777 */);
    log('INFO', 'mkdir(' + path + ') -> ' + r);
}

function tryDump(ptr, size, tag) {
    try {
        if (ptr.isNull()) { return; }
        var key = ptr.toString() + ':' + size;
        if (seen[key]) { return; }
        seen[key] = true;

        if (size < 0x70 || size > 400 * 1024 * 1024) {
            log('DEBUG', 'skip bad size=' + size + ' at ' + ptr + ' tag=' + tag);
            return;
        }
        var head = new Uint8Array(ptr.readByteArray(8));
        var ms = String.fromCharCode(head[0], head[1], head[2], head[3]);
        if (ms !== 'dex\n') {
            nNonDex++;
            var hv = [];
            for (var i = 0; i < 8; i++) { hv.push(('0' + head[i].toString(16)).slice(-2)); }
            log('WARN', 'non-dex tag=' + tag + ' size=' + size + ' at ' + ptr + ' head=' + hv.join(' '));
            return;
        }
        var data = ptr.readByteArray(size);
        var u8 = new Uint8Array(data);

        // 版本号（dex\n037\0 -> "037"）
        var ver = String.fromCharCode(u8[4], u8[5], u8[6]);

        // 校验 adler32（头部 12..end）
        var exp = ((u8[8]) | (u8[9] << 8) | (u8[10] << 16) | (u8[11] << 24)) >>> 0;
        var act = adler32(u8, 12);
        var ok = (exp === act);

        // 类数量（header: class_defs_size @ 0x60）
        var nClass = ((u8[0x60]) | (u8[0x61] << 8) | (u8[0x62] << 16) | (u8[0x63] << 24)) >>> 0;
        var nMethod = ((u8[0x58]) | (u8[0x59] << 8) | (u8[0x5a] << 16) | (u8[0x5b] << 24)) >>> 0;

        var name = OUT_DIR + '/dex_' + ('0000' + nDumped).slice(-4) + '_' + (ok ? 'OK' : 'BAD') +
                   '_' + tag + '_v' + ver + '.dex';
        var f = new File(name, 'wb');
        f.write(data);
        f.close();
        nDumped++;
        log('INFO', (ok ? 'OK  ' : 'BAD ') + name + ' size=' + size +
            ' classes=' + nClass + ' methods=' + nMethod + ' ver=' + ver + ' at=' + ptr);
    } catch (e) {
        nFailed++;
        log('ERROR', 'dump failed at ' + ptr + ' tag=' + tag + ' err=' + e);
    }
}

function install() {
    var m = null;
    try { m = Process.getModuleByName('libdexfile.so'); }
    catch (e) {
        log('WARN', 'libdexfile.so not loaded yet, retry in 100ms');
        setTimeout(install, 100);
        return;
    }
    log('INFO', 'libdexfile.so base=' + m.base + ' size=' + m.size);

    // Android 12 (API 32) libc++ 修饰名
    var syms = {
        Open: '_ZNK3art13DexFileLoader4OpenEPKhmRKNSt3__112basic_stringIcNS3_11char_traitsIcEENS3_9allocatorIcEEEEjPKNS_10OatDexFileEbbPS9_NS3_10unique_ptrINS_16DexFileContainerENS3_14default_deleteISH_EEEE',
        OpenAll: '_ZNK3art13DexFileLoader7OpenAllEPKhmRKNSt3__112basic_stringIcNS3_11char_traitsIcEENS3_9allocatorIcEEEEbbPNS_22DexFileLoaderErrorCodeEPS9_PNS3_6vectorINS3_10unique_ptrIKNS_7DexFileENS3_14default_deleteISI_EEEENS7_ISL_EEEE',
        OpenCommon: '_ZN3art13DexFileLoader10OpenCommonEPKhmS2_mRKNSt3__112basic_stringIcNS3_11char_traitsIcEENS3_9allocatorIcEEEEjPKNS_10OatDexFileEbbPS9_NS3_10unique_ptrINS_16DexFileContainerENS3_14default_deleteISH_EEEEPNS0_12VerifyResultE'
    };

    var hooked = 0;
    Object.keys(syms).forEach(function (k) {
        var a = null;
        try { a = m.findExportByName(syms[k]); } catch (e) { a = null; }
        if (!a) { log('WARN', 'symbol not found: ' + k); return; }
        Interceptor.attach(a, {
            onEnter: function (args) {
                try { tryDump(args[1], parseInt(args[2].toString(), 16), k); }
                catch (e) { log('ERROR', 'onEnter ' + k + ' err=' + e); }
            }
        });
        hooked++;
        log('INFO', 'hooked ' + k + ' @ ' + a);
    });
    log('INFO', 'install done, hooks=' + hooked);
}

function summary() {
    log('INFO', 'SUMMARY dumped=' + nDumped + ' failed=' + nFailed + ' nonDex=' + nNonDex);
}

setImmediate(function () {
    ensureDir(OUT_DIR);
    install();
    // 定期输出进度，便于日志观察
    var iv = setInterval(summary, 5000);
    // 60 秒后自动解绑，避免长期挂载影响 App
    setTimeout(function () { clearInterval(iv); summary(); log('INFO', 'auto-detach timer fired'); }, 90000);
});
