/*
 * entry_crack.js — Lesson1 破解主体（v2：加入上报一致性反检测）
 *
 * 目标 APK : 墨墨背单词 v5.6.00 (build 900)  com.maimemo.android.momo
 * 保护     : 梆梆 SecNeo 壳 + Fort andjni 方法抽取 + 反调试
 *
 * ── 第一层：破解（可用单词上限 → 无限）─────────────────────────
 *   com.maimemo.android.momo.a.s()   = 单词上限 wordsLimit（JNI 桩，默认 600）
 *   x1d.f(false)                     = 可用单词上限 = a.s() − 已学词数
 *   r47.getAvailableWordLimit()      = 可用单词上限（Compose 侧同一式子）
 *   gq2.c()                          = 欠债数 = 已学词数 − a.s()
 *   dma.a(uid, enc, email)           = 本地 inf_words_limit 解密读取
 *
 * ── 第二层：反检测（避免上报异常值被服务端判定破解 → 封号）──────
 *   App 会把上限值回传给服务器，两条链路：
 *     1) /log/study_log     ada.b() 构造 StudyLogRequest：
 *                             wordLimit          = a.s()
 *                             availableWordLimit = x1d.f(false)
 *     2) /misc/system/check s40.m(...) 构造 debt_report_data：
 *                             max_voc_count      = a.s()
 *        （gq2.m() 的债务上报同理）
 *
 *   如果本地改无限、上报也报 2147483647，而服务器清楚该账号只有 5012
 *   —— 一次请求就是"破解特征"。所以这里做「表里不一」：
 *   进入上报构造函数时置「上报模式」标志，期间 a.s()/x1d.f() 返回**真实值**，
 *   出了构造函数立刻恢复无限。UI 与本地限制判定始终是无限。
 *
 *   标志按线程隔离（Process.getCurrentThreadId），避免后台上报线程与 UI 线程互相污染。
 *
 * 打包：esbuild entry_crack.js --bundle --outfile=crack.bundle.js --format=iife --platform=neutral --target=es2020
 */
import Java from 'frida-java-bridge';

var TAG = '[MoMoCrack]';
var LIMIT = 0x7FFFFFFF;         // 2147483647 ≈ 无限
var STEALTH = true;             // true = 上报真实值（反封号）；false = 连上报也是无限（会被判定破解）
var FALLBACK_REAL = 600;        // 上报路径读不到真实值时的兜底（= App 自身默认上限，绝不泄露无限值）
var gOrigFail = '';             // 上报路径调用原实现失败的记录（用于取证：区分「真 600」与「读不到」）

/*
 * gadget 内嵌模式下 App 进程的 stdout 是 /dev/null，send() 的内容看不见，
 * 所以日志走两条路：
 *   1) __android_log_print 直接写 logcat（tag=MoMoCrack）—— 无 root 也能 adb logcat 看
 *   2) 关键节点 Toast 打到屏幕上
 * frida-server attach 路线不受影响。
 */
var alogFn = null;
try {
    var logSym = null;
    try { logSym = Process.getModuleByName('liblog.so').getExportByName('__android_log_print'); }
    catch (e1) {
        try { logSym = Module.getGlobalExportByName('__android_log_print'); }
        catch (e2) { try { logSym = Module.findGlobalExportByName('__android_log_print'); } catch (e3) { } }
    }
    if (logSym) { alogFn = new NativeFunction(logSym, 'int', ['int', 'pointer', 'pointer', 'pointer']); }
} catch (e) { }
var _alogTag = null, _alogFmt = null;
function alog(msg) {
    try {
        if (!alogFn) { return; }
        if (_alogTag === null) {
            _alogTag = Memory.allocUtf8String('MoMoCrack');
            _alogFmt = Memory.allocUtf8String('%s');
        }
        alogFn(4, _alogTag, _alogFmt, Memory.allocUtf8String(String(msg)));
    } catch (e) { }
}

var TOAST_BUDGET = 14;
function toast(msg) {
    if (TOAST_BUDGET <= 0) { return; }
    TOAST_BUDGET--;
    var text = String(msg);
    if (text.length > 88) { text = text.substring(0, 88) + '...'; }
    try {
        Java.perform(function () {
            try {
                var ActivityThread = Java.use('android.app.ActivityThread');
                var app = ActivityThread.currentApplication();
                if (app === null) { return; }
                Java.scheduleOnMainThread(function () {
                    try {
                        var Toast = Java.use('android.widget.Toast');
                        var JString = Java.use('java.lang.String');
                        Toast.makeText(app, JString.$new(text), 0).show();
                    } catch (e) { }
                });
            } catch (e) { }
        });
    } catch (e) { }
}

function log(level, msg) {
    send({ tag: TAG, level: level, msg: msg });
    alog('[' + level + '] ' + msg);
    if (level === 'OK' || level === 'AUDIT' || level === 'ERROR' || level === 'WARN') {
        toast(msg);
    }
}

/* 按线程记录「当前是否在构造上报数据」 */
var reportingTid = {};
function curTid() { return Process.getCurrentThreadId(); }
function inReporting() { return reportingTid[curTid()] === true; }

function enterReporting() { reportingTid[curTid()] = true; }
function exitReporting() { delete reportingTid[curTid()]; }

function use(name) {
    var attempts = [name];
    if (name.indexOf('.') < 0) { attempts.push('defpackage.' + name); }
    for (var i = 0; i < attempts.length; i++) {
        try { return Java.use(attempts[i]); } catch (e) { /* next */ }
    }
    log('WARN', 'Java.use("' + name + '") 失败');
    return null;
}

function call(label, fn) {
    try { return String(fn()); } catch (e) { return '<err: ' + e + '>'; }
}

/* 包装一个「构造上报数据」的方法：调用原实现期间开启上报模式 */
function wrapReportBuilder(cls, method, label, inspect) {
    if (!cls) { return; }
    try {
        var orig = cls[method];
        cls[method].implementation = function () {
            enterReporting();
            var ret;
            try {
                ret = orig.apply(this, arguments);
            } finally {
                exitReporting();
            }
            // 审计：把即将上传的字段打出来，证明没有泄露无限值
            if (inspect) {
                try { inspect(ret); } catch (e) { log('WARN', label + ' 审计失败: ' + e); }
            }
            return ret;
        };
        log('OK', '已包装上报构造 ' + label + '（期间返回真实值）');
    } catch (e) {
        log('WARN', '包装 ' + label + ' 失败: ' + e);
    }
}

/*
 * boot()：既支持 frida attach（类已加载），也支持 frida-gadget 内嵌
 *         （gadget 在 Application.attachBaseContext 就被载入，那时壳还没把
 *          业务 dex 解密加载，Java.use 会失败 —— 所以轮询等待）。
 */
function boot(attempt) {
  Java.perform(function () {
    // readiness 探测绝不能有副作用：
    // a.s() 会去开 SQLite 数据库，若在主线程上每 500ms 调一次，
    // 会和 App 自身的 DB 初始化抢锁 → 启动页卡死。
    // 所以这里只判断「类能不能拿到」，拿到就装 hook（各步各自 try/catch）。
    var probe = null;
    try { probe = Java.use('com.maimemo.android.momo.a'); } catch (e) { probe = null; }
    if (!probe) {
        if (attempt === 0 || attempt % 20 === 0) {
            log('INFO', '等待业务 dex 加载…第 ' + attempt + ' 次');
        }
        setTimeout(function () { boot(attempt + 1); }, 400);
        return;
    }

    log('INFO', '=== MoMoCrack v2 启动 (maimemo v5.6.00) ===');
    log('INFO', 'arch=' + Process.arch + ' frida=' + Frida.version + ' stealth=' + STEALTH);

    var A = use('com.maimemo.android.momo.a');
    var X1D = use('x1d');
    var GQ2 = use('gq2');
    var DMA = use('dma');
    var R47 = use('r47');
    var ADA = use('ada');
    var S40 = use('s40');

    // ---------- 1. 原始值：故意推迟到步骤3 ----------
    // 启动早期从 Frida 线程调 a.s()/x1d.f() 会去开 SQLite，和 App 自身的 DB 初始化抢锁
    // → 启动页卡死。所以先装 hook，真实值留到步骤 3 用「上报模式」读。
    var realLimit = -1, realAvail = -1;
    log('INFO', '--- 步骤1: 跳过启动期原始值读取（避免 DB 抢锁，改在步骤3读） ---');

    // ---------- 2. 安装 hook ----------
    log('INFO', '--- 步骤2: 安装 hook ---');

    // 2.1 主目标：单词上限
    // 关键：非上报路径**绝不能**先调 origS。a.s() 走 JNI → 会去开 SQLite，
    // 数据库还没建立时它会抛 SQLiteCantOpenDatabaseException —— 如果先调它，
    // 异常会从 hook 里冒出去，UI 拿不到 2147483647（登录前/启动早期就是这种状态）。
    if (A) {
        var origS = A.s;
        var lastRealLimit = -1;
        A.s.implementation = function () {
            if (STEALTH && inReporting()) {
                try { lastRealLimit = origS.call(this); } catch (e) { gOrigFail = 'a.s:' + e; }
                // 读不到真实值时退回 App 自己的默认上限，绝不把 2147483647 报上去
                return lastRealLimit >= 0 ? lastRealLimit : FALLBACK_REAL;
            }
            return LIMIT;
        };
        log('OK', 'hook a.s()  => ' + LIMIT + (STEALTH ? '（仅上报路径回落真实值）' : ''));
    }

    // 2.2 本地加密存储解密（dma.a 只有 (int,String,String) 这一个 a 重载）
    if (DMA) {
        var origDmaA = DMA.a;
        var lastRealDma = -1;
        DMA.a.implementation = function (uid, enc, email) {
            if (STEALTH && inReporting()) {
                try { lastRealDma = origDmaA.call(this, uid, enc, email); } catch (e) { }
                return lastRealDma >= 0 ? lastRealDma : FALLBACK_REAL;
            }
            return LIMIT;
        };
        log('OK', 'hook dma.a(int,String,String)  => ' + LIMIT + '（仅上报路径回落真实值）');
    }

    // 2.3 可用单词上限
    if (X1D) {
        var origX1DF = X1D.f;
        var lastRealAvail = -1;
        X1D.f.implementation = function (z) {
            if (STEALTH && inReporting()) {
                try { lastRealAvail = origX1DF.call(this, z); } catch (e) { }
                return lastRealAvail >= 0 ? lastRealAvail : FALLBACK_REAL;
            }
            return LIMIT;
        };
        log('OK', 'hook x1d.f(boolean)  => ' + LIMIT + '（仅上报路径回落真实值）');
    }

    // 2.4 Compose 侧可用上限
    if (R47) {
        try {
            var IntBox = Java.use('java.lang.Integer');
            var origR47 = R47.getAvailableWordLimit;
            R47.getAvailableWordLimit.implementation = function (cont) {
                if (STEALTH && inReporting()) { return origR47.call(this, cont); }
                return IntBox.valueOf(LIMIT);
            };
            log('OK', 'hook r47.getAvailableWordLimit(fb2)  => ' + LIMIT);
        } catch (e) { log('WARN', 'r47 hook 失败: ' + e); }
    }

    // 2.5 欠债
    if (GQ2) {
        try {
            var origGq2C = GQ2.c;
            GQ2.c.implementation = function () {
                if (STEALTH && inReporting()) { return origGq2C.call(this); }
                return 0;
            };
            log('OK', 'hook gq2.c()  => 0');
        } catch (e) { log('WARN', 'gq2.c hook 失败: ' + e); }
        try {
            GQ2.h.implementation = function () { return false; };
            log('OK', 'hook gq2.h()  => false');
        } catch (e) { log('WARN', 'gq2.h hook 失败: ' + e); }
    }

    // 2.6 【反检测】上报构造函数 —— 期间返回真实值
    wrapReportBuilder(ADA, 'b', 'ada.b()  [/log/study_log 的 StudyLogRequest]', function (req) {
        if (!req) { return; }
        try {
            var wl = req.wordLimit.value;
            var aw = req.availableWordLimit.value;
            var flag = (wl >= LIMIT || aw >= LIMIT) ? '❌ 泄露!!' : '✅ 正常';
            log('AUDIT', '/log/study_log 将上报 wordLimit=' + wl + ' availableWordLimit=' + aw + '  ' + flag);
        } catch (e) { log('AUDIT', 'StudyLogRequest 字段读取失败: ' + e); }
    });
    wrapReportBuilder(S40, 'm', 's40.m()  [/misc/system/check 的 debt_report_data]');
    wrapReportBuilder(GQ2, 'm', 'gq2.m()  [债务上报]');

    // ---------- 3. 复核（延迟 20s：等 App 自己的 DB 初始化完成后再读真实值）----------
    setTimeout(function () {
        Java.perform(function () {
            log('INFO', '--- 步骤3: hook 后复核 ---');
            if (A) { log('INFO', 'a.s()        = ' + call('a.s', function () { return A.s(); }) + '   <- 本地：无限'); }
            if (X1D) { log('INFO', 'x1d.f(false) = ' + call('x1d.f', function () { return X1D.f(false); }) + '   <- 本地：无限'); }
            try {
                enterReporting();
                try { realLimit = A ? A.s() : -1; } catch (e) { }
                try { realAvail = X1D ? X1D.f(false) : -1; } catch (e) { }
                exitReporting();
                log('INFO', '上报模式读到的真实值: 单词上限=' + realLimit + ' 可用上限=' + realAvail);
            } catch (e) { log('WARN', '真实值读取失败: ' + e); }
            log('INFO', '复核后本地 a.s() = ' + call('a.s', function () { return A.s(); }));
            log('INFO', '=== 安装完成：本地无限 + 上报真实值（反封号） ===');
            alog('SELFTEST ok local=' + LIMIT + ' reporting=' + realLimit + ' stealth=' + STEALTH
                 + (gOrigFail ? (' origCallFailed=' + gOrigFail) : ' origCallOk'));
            toast('MoMoCrack OK  本地上限=' + LIMIT + '  上报真实值=' + realLimit);
        });
    }, 20000);

    // ---------- 4. 自检接口（供 apply_crack.py --selftest 调用）----------
    rpc.exports = {
        /* 验证「上报模式」确实会切回真实值 */
        stealthtest: function () {
            var out = {};
            try {
                out.local = A ? A.s() : null;                 // 本地读：应为无限
                enterReporting();
                out.reporting = A ? A.s() : null;             // 上报中读：应为真实值
                exitReporting();
                out.after = A ? A.s() : null;                 // 恢复后：应为无限
                out.realLimit = realLimit;
                out.realAvail = realAvail;
                out.limit = LIMIT;
                out.ok = (out.local === LIMIT || out.local >= LIMIT) &&
                         (out.reporting === realLimit) &&
                         (out.after === LIMIT || out.after >= LIMIT);
            } catch (e) {
                out.error = String(e);
                out.ok = false;
            }
            return out;
        }
    };
  });
}

boot(0);
