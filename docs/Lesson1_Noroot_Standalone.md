# Lesson1 进阶：无 root 独立包（standalone APK）

> 目标：不依赖 frida-server / root / LSPosed，**普通安装即可生效**的破解包。
> 产物：`MoMoWords/build/standalone/signed/MoMoWords_L1_standalone_unsigned-aligned-debugSigned.apk`
> 设备验证：Xiaomi 23116PN5BC (Android 16, arm64) —— 普通 `adb install` 安装，无 su、无 frida-server。

---

## 1. 为什么不能走常规思路

| 思路 | 结果 | 证据 |
|---|---|---|
| 改 `lib/arm64-v8a/*.so`（加/改任何文件） | 进程自毁 `SIGSEGV SEGV_MAPERR, fault addr 0xa98` | 变体 P / F 实测 |
| 往 `lib/` 里加新文件（哪怕不碰原 so） | 同上，自毁 | 变体 F：0 处 so 修改，仅新增 3 个文件 |
| 去壳后重打包（`classes.dex` 换成真 dex） | `Fort andjni` 方法体是 nop 桩，运行即 NPE | `l80.a()` 返回 null |
| `frida-gadget` 直接当 `META-INF/native/libmomoco.so` | gadget 能加载、能监听 27042，但 **卡启动页** | 变体 C2：`on_load` 默认 `wait`，无配置文件无法改成 `resume` |

**壳的完整性校验只覆盖 `lib/`；`META-INF/native/` 是安全区。**

## 2. 注入点：`BaseAppContext.<clinit>`

```java
static {
    ClassLoader cl = BaseAppContext.class.getClassLoader();
    if (cl != null && cl.getResource("META-INF/native/" + System.mapLibraryName("momoco")) != null) {
        if (Boolean.getBoolean("momo.hostNativeClasspathLoaded")) return;
        SQLiteLibraryLoader.loadFromClasspath();      // 需要 META-INF/native/libmmsqlite.so
        SQLCipherLibraryLoader.loadFromClasspath();   // 需要 META-INF/native/libmmsqlcipher.so
        System.load(g57.k("META-INF/native/libmomoco.so").getAbsolutePath());  // ← 载入我们控制的 so
        ...
        return;
    }
    System.loadLibrary("momoco");        // 原版走这里，从 lib/ 加载
    System.loadLibrary("mmsqlite");
    System.loadLibrary("mmsqlcipher");
}
```

`g57.k()`（`defpackage/g57.java:508`）把资源解到
`/data/user/0/<pkg>/cache/momoco-host-native-<随机>/libmomoco.so` 然后 `System.load`。

好处：**APK 里不动 `lib/` 一个字节，却能执行任意 arm64 原生代码。**
代价：真 `libmomoco.so` 不再被加载 → 必须由我们链式加载回来。

## 3. 卡住的地方：gadget 找不到配置文件

frida-gadget 的配置查找逻辑（`lib/gadget/gadget.vala: load_config`）：

```
config_path = <gadget 所在目录>/<去掉扩展名的文件名>.config
若不存在 → 把最后一个 '.' 改成 ".config.so" → <目录>/<stem>.config.so
```

即 gadget 在 `<临时目录>/libmomoco.so` 时，只认 `<临时目录>/libmomoco.config.so`。
而 `g57.k()` **只写一个文件**，`File.createTempFile` 生成的目录名又是随机的 ——
配置文件没法预置，gadget 就永远落到默认值（`listen` + `on_load: wait`）→ 卡启动页。

## 4. 最终方案：自解包引导层 `libmmboot.so`

```
META-INF/native/libmomoco.so  = libmmboot.so(17KB) + frida-gadget(25MB) + crack.js(487KB) + 64B footer
```

`JNI_OnLoad`（`patch/gadget_payload/loader.c`）依次做四件事：

1. **拿到自己的路径** —— `dladdr(&JNI_OnLoad)`，得到 `<临时目录>/libmomoco.so`。
   （不能用 `/proc/self/maps` 做主力：maps 可达 1MB 以上，截断后字段解析会失控。）
2. **链式加载真 `libmomoco.so`** —— `dlopen("libmomoco.so")`（我们的 so 用
   `DT_SONAME=libmmboot.so`，不会和自己撞名），再手动 `dlsym(h,"JNI_OnLoad")` 调一次。
3. **自解包** —— 读自身文件尾部 64 字节 footer（magic `MMPK` + 两个 `(offset,length)`），
   把内嵌的 gadget 和脚本写到**同一个临时目录**：`libmmcore.so` / `mmc.js`。
4. **生成配置并拉起 gadget** —— 写 `<临时目录>/libmmcore.config.so`：
   ```json
   {"interaction":{"type":"script","path":"<临时目录>/mmc.js"}}
   ```
   然后 `dlopen("<临时目录>/libmmcore.so")`。gadget 就在自己目录里找到了配置，
   以 `script` 交互模式跑我们的破解脚本（**不监听端口，不等待 attach**）。

`META-INF/native/` 同时放真的 `libmmsqlite.so` / `libmmsqlcipher.so` / `libmmftsext.so`
（走 classpath 分支时这两个 loader 是必需的，缺了直接 `UnsatisfiedLinkError`）。

## 5. 交叉编译（本机没有 NDK）

用 PyPI 上的 zig 直接产出 Android arm64 ELF：

```powershell
python -m pip install ziglang
cd MoMoWords/patch/gadget_payload
# 1) 造 stub so，只为往 DT_NEEDED 里塞名字（zig 会把 -lc 当成"要提供 libc"，所以用文件形式传）
cd stubs; foreach($n in 'libdl','libc','liblog'){ python -m ziglang cc -target aarch64-linux-android -shared -nostdlib -fno-sanitize=all "-Wl,-soname,$n.so" -o "$n.so" empty.c }; cd ..
# 2) 编引导层
python -m ziglang cc -target aarch64-linux-android -shared -nostdlib -fno-stack-protector `
  -fno-builtin -fno-sanitize=all "-Wl,-soname,libmmboot.so" -O0 `
  "-Wl,--no-as-needed" stubs/libdl.so stubs/libc.so stubs/liblog.so -o libmmboot.so loader.c
```

打包：`python MoMoWords/scripts/build_standalone.py`（内置 payload → 重打包 APK → 自校验）。
签名：`java -jar tools/uber-apk-signer.jar -a <unsigned.apk> -o signed`（zipalign + v2/v3 签名）。

### 踩过的坑

| 现象 | 原因 | 修法 |
|---|---|---|
| `dlopen failed: cannot locate symbol "dlopen"` | `-nostdlib` 产出的 so 没有 `DT_NEEDED`，bionic 不认全局符号 | 用 stub so 注入 `NEEDED libdl.so/libc.so/liblog.so` |
| `SIGSEGV SEGV_MAPERR @ 0x7fe3a91000`（栈被 `//////` 覆盖） | 无界 `scpy/sapp` 在 maps 解析异常时冲爆栈 | 全部换成带 cap 的 `bscpy/bsapp/derive_dir` |
| `-O1/-O2` 编出来的 so 缺 `write`/字符串常量 | zig 在优化档下的诡异 DCE（最小复现无法重现） | 用 `-O0 -fno-sanitize=all`（14KB，无所谓） |
| `zig cc -lc` 报 `unable to provide libc for target` | zig 驱动特判 `-lc` | 直接把 stub `.so` 当输入文件传给 linker |
| 注释里写 `/proc/*/cmdline` | `*/` 提前结束块注释，编译报 `unknown type name 'cmdline'` | 改写成别的话 |

## 6. 破解与反封号逻辑（`frida/entry_crack.js`）

hook 列表与 root 版完全一致，**只是加载方式换成了内嵌 gadget**：

```
a.s()                      -> 2147483647      （单词上限）
x1d.f(boolean)             -> 2147483647      （可用单词上限）
r47.getAvailableWordLimit  -> 2147483647      （Compose 侧）
gq2.c() / gq2.h()          -> 0 / false       （欠债）
dma.a(int,String,String)   -> 2147483647      （本地 inf_words_limit 解密）
```

反封号「表里不一」：包装 `ada.b()`（`/log/study_log`）、`s40.m()`（`/misc/system/check`）、
`gq2.m()`（债务上报）三个**上报构造函数**，进入时置线程级 `reportingTid` 标志，
期间 `a.s()/x1d.f()/dma.a()` 返回**服务端真实值**，出栈立刻恢复无限。
本地 UI/限制判定始终无限，上报给服务器的仍是 5012 —— 服务端看不到任何异常值。

启动期安全策略：**不在启动早期读真实值**（会去开 SQLite，和 App 自己的 DB 初始化抢锁），
推迟到 20s 后再用「上报模式」读一次。

### 一个必须避开的坑：hook 里不能先调原实现

最初的写法是

```js
A.s.implementation = function () {
    var real = origS.call(this);          // ← 错的
    return inReporting() ? real : LIMIT;
};
```

`a.s()` 走 JNI，会去开 SQLite；**未登录 / 数据库还没建立时会抛
`SQLiteCantOpenDatabaseException`**，异常直接从 hook 冒出去 —— UI 拿不到 2147483647。
正确写法是「非上报路径根本不碰原实现」：

```js
A.s.implementation = function () {
    if (STEALTH && inReporting()) {
        try { lastRealLimit = origS.call(this); } catch (e) { gOrigFail = 'a.s:' + e; }
        return lastRealLimit >= 0 ? lastRealLimit : FALLBACK_REAL;   // 兜底 600，绝不泄露无限值
    }
    return LIMIT;
};
```

`dma.a` / `x1d.f` 同样处理。修复前 `a.s()` 在无 DB 时报异常，修复后同一状态下返回
`2147483647`，日志里 `origCallOk` 表示上报路径读到了真实值。

日志：App 进程 stdout 是 /dev/null，所以脚本通过 `__android_log_print`
直接写 logcat（tag `MoMoCrack`），无需 root 即可 `adb logcat -s MoMoCrack:I` 观察。

## 7. 真机证据（Xiaomi 23116PN5BC / Android 16 / 无 root / 无 frida-server）

```
I MoMoBoot : dladdr self=/data/data/com.maimemo.android.momo/cache/momoco-host-native-.../libmomoco.so
I MoMoBoot : chain dlopen(libmomoco.so) -> 0xc748...      # 真 libmomoco 已链式加载
I MoMoBoot : real libmomoco JNI_OnLoad=0x6e8351d458
I MoMoBoot : payload gadget=17512+25192176 js=25209688+487051
I MoMoBoot : extract ok=1 js=.../mmc.js so=.../libmmcore.so
I MoMoBoot : dlopen(gadget) -> 0x1f97...                  # gadget 起来了
I MoMoCrack: [OK] hook a.s()  => 2147483647（上报时返回真实值）
I MoMoCrack: [OK] hook x1d.f(boolean)  => 2147483647
I MoMoCrack: [OK] 已包装上报构造 ada.b()  [/log/study_log 的 StudyLogRequest]
I MoMoCrack: [OK] 已包装上报构造 s40.m()  [/misc/system/check 的 debt_report_data]
I MoMoCrack: [OK] 已包装上报构造 gq2.m()  [债务上报]
I MoMoCrack: [INFO] x1d.f(false) = 2147483647   <- 本地：无限
I MoMoCrack: [INFO] 上报模式读到的真实值: 单词上限=5012 可用上限=5012   <- 服务端真实值
I MoMoCrack: [INFO] 复核后本地 a.s() = 2147483647
I MoMoCrack: SELFTEST ok local=2147483647 reporting=5012 stealth=true origCallOk
```

**关键结论：本地 2147483647（无限），上报路径 5012（服务端真实值）—— 破解生效且未泄露。**
进程存活、无 `Fatal signal`、无壳自毁，App 正常走到登录/主界面。

## 8. 边界与已知限制

* 只内嵌了 **arm64-v8a** 的 gadget（APK 仍含 armeabi-v7a 的 `lib/`，32 位设备上
  `META-INF/native/libmomoco.so` 会加载失败）。如需 32 位，用同样流程再嵌一份 arm gadget。
* Android 16 起 `System.load` 一个**可写的** cache 文件会打警告
  `Attempt to load writable file`（当前仅警告）。未来版本若改为抛错，这条注入路径需要换落点。
* 首次启动会往 App cache 目录写 25MB 的 gadget（约 200ms），每次冷启动都做一次。
* 未做「上报 cap」处理：目前上报的是服务端真实值，所以不存在泄露；
  若想连真实值也不上报，可在 `ada.b()` 包装里把 `wordLimit` 夹到 `learned_voc_count + N`。
