# 墨墨背单词 v5.6.0 破解 —— Lesson1 作业

> 课程仓库：[deathbook/Crack](https://github.com/deathbook/Crack)
> 课程目标（Lesson1.md 原文）：**「将可用单词上限修改到无限」**
> 样本：`maimemo_v5.6.00_900_1788339161.apk`（`com.maimemo.android.momo`，123,994,114 B，SHA256 `A2801079…D2D06D`）

> ⚠️ **仅供逆向工程学习与研究**。本仓库**不包含**任何原版 APK、脱壳 dex 或重打包产物，
> 只放分析过程、脚本与报告。请勿用于商业用途或实际绕过付费。

---

## 一、结论（TL;DR）

| 项 | 结果 |
|---|---|
| 目标函数 | `com.maimemo.android.momo.a.s()` → 单词上限 `wordsLimit`（JNI，默认 600） |
| 本地效果 | `a.s()` / `x1d.f(false)` / `r47.getAvailableWordLimit()` **= 2147483647（无限）** |
| 上报效果 | 上报路径仍返回**服务端真实值（5012）**，服务端看不到任何异常 |
| 交付形态 | ① root + frida-server 注入　② **无 root 独立包**（普通安装即生效，内含 frida-gadget） |
| 真机验证 | Xiaomi 23116PN5BC / Android 16 / arm64，无 root、无 frida-server |

---

## 二、目标保护分析

| 层 | 组件 | 说明 |
|---|---|---|
| 壳 | 梆梆 SecNeo | `libDexHelper.so` + 77 MB 的 `classes.dex`（**只有 35 个类**，真正内容是其后的加密载荷） |
| 方法抽取 | Fort `andjni` | `libdexjni.so` 里 1018 个类的函数体是 nop 桩，业务逻辑搬进了 native |
| 反调试 | — | `frida spawn` 会 `SIGSEGV SI_TKILL` 自毁；SecNeo 还会把自己从 `/proc` 枚举里隐藏 |

**脱壳**：hook `libdexfile.so` 的 `DexFileLoader::OpenCommon`，落盘得到 4 个业务 dex
（31,086 个类，jadx 出 25,014 个文件）。

**关键发现**：壳的完整性校验**只覆盖 `lib/` 目录** —— 往 `lib/arm64-v8a/` 加**任何一个文件**
（哪怕一个字节都不改）都会触发自毁：

```
Fatal signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0xa98
```

但 `META-INF/native/` 下的增删改**完全放行** —— 这是后面无 root 方案的地基。

---

## 三、破解链路

```
a.s()                    = JniLib0.cI(a.class, 23)     单词上限
x1d.f(boolean)           = a.s() − 已学词数            可用单词上限
r47.getAvailableWordLimit(fb2)                          Compose 侧同一式子
gq2.c() / gq2.h()                                       欠债数 / 欠债开关
dma.a(int,String,String) 解密本地 inf_tb.inf_words_limit（uid<=0 时是明文）
```

---

## 四、无 root 独立包（本仓库的重点）

### 4.1 注入点

`BaseAppContext.<clinit>` 发现 classpath 里存在 `META-INF/native/libmomoco.so` 时，
会把它解到 `/data/user/0/<pkg>/cache/momoco-host-native-<随机>/libmomoco.so` 再 `System.load()`。
**APK 里一个字节都不动 `lib/`，却能执行任意 arm64 原生代码。**

### 4.2 卡点：frida-gadget 找不到配置文件

gadget 只认「自己所在目录 / `<stem>.config.so`」（`gadget.vala: load_config`），
而那个临时目录名随机、`g57.k()` 又只写一个文件 —— 配置无法预置，
gadget 回落到默认值（`listen` + `on_load: wait`）→ **卡死在启动页**。

### 4.3 方案：自解包引导层 `libmmboot.so`

```
META-INF/native/libmomoco.so = libmmboot.so(17KB) + frida-gadget(25MB) + crack.js(487KB) + 64B footer
```

`JNI_OnLoad` 里：

1. `dladdr(&JNI_OnLoad)` 定位自身路径；
2. `dlopen("libmomoco.so")` 把被顶替的真身链式加载回来，并手动调它的 `JNI_OnLoad`；
3. 读自身文件尾部的 64 字节 footer，把内嵌的 gadget / 脚本释放到**同一个临时目录**；
4. 写 `<临时目录>/libmmcore.config.so`（`{"interaction":{"type":"script","path":"…/mmc.js"}}`），
   然后 `dlopen` gadget —— **不监听端口、不等 attach，冷启动即生效**。

源码：[`native/loader.c`](native/loader.c)（zig 交叉编译，本机无需 NDK）

### 4.4 踩过的坑

| 现象 | 原因 | 修法 |
|---|---|---|
| `dlopen failed: cannot locate symbol "dlopen"` | `-nostdlib` 产出的 so 没有 `DT_NEEDED` | 用 stub `.so` 注入 `NEEDED libdl/libc/liblog` |
| `SIGSEGV SEGV_MAPERR`（栈被 `//////` 覆盖） | 无界 `scpy/sapp` 在 `/proc/self/maps` 截断时冲爆栈 | 全部换成带 cap 的版本 |
| `-O1/-O2` 编出来的 so 缺 `write` 与字符串常量 | zig 优化档下的 DCE 行为 | 改用 `-O0 -fno-sanitize=all` |
| `zig cc -lc` 报 `unable to provide libc` | 驱动特判 `-lc` | 把 stub `.so` 当输入文件传给 linker |
| 注释里写 `/proc/*/cmdline` | `*/` 提前结束块注释 | 改写措辞 |

---

## 五、反封号：上报一致性（「表里不一」）

服务端有两条聚合上报链路会带上限值：

| 链路 | 构造函数 | 字段 |
|---|---|---|
| `/log/study_log` | `ada.b()` | `wordLimit` / `availableWordLimit` |
| `/misc/system/check` | `s40.m()` | `debt_report_data.max_voc_count` |
| 债务上报 | `gq2.m()` | 同上 |

如果本地无限、上报也报 2147483647，而服务端清楚该账号只有 5012 —— 一次请求就是破解特征。

做法：包装这三个构造函数，进入时置**线程级**「上报模式」标志，期间
`a.s()/x1d.f()/dma.a()` 返回**真实值**，出栈立刻恢复无限。
逐词的 `/api/v1/study/oplog` 与备份 ZIP 保持诚实，记忆曲线同步不受影响。

**还有一个必须避开的坑**：hook 里**不能先调原实现**。

```js
// ✗ 错：a.s() 走 JNI 会开 SQLite，未登录/DB 未建立时抛异常，异常直接从 hook 冒出去
var real = origS.call(this);
return inReporting() ? real : LIMIT;

// ✓ 对：非上报路径根本不碰原实现；读不到真实值时退回 App 自己的默认值 600
if (STEALTH && inReporting()) {
    try { lastRealLimit = origS.call(this); } catch (e) { }
    return lastRealLimit >= 0 ? lastRealLimit : FALLBACK_REAL;
}
return LIMIT;
```

---

## 六、复现

```powershell
# 1) 脱壳（需 root + frida-server）
python scripts/apply_crack.py --once 30          # attach 注入破解
python -c "import frida"                          # 脱壳见 frida/dump_dex.js

# 2) 本地 dex 补丁路线（root）
python scripts/patch_dex_return.py               # a.s() -> const v0, 0x7fffffff

# 3) 无 root 独立包
python -m pip install ziglang
cd native && python -m ziglang cc -target aarch64-linux-android -shared -nostdlib `
  -fno-stack-protector -fno-builtin -fno-sanitize=all -Wl,-soname,libmmboot.so -O0 `
  -Wl,--no-as-needed <stub>/libdl.so <stub>/libc.so <stub>/liblog.so -o ../libmmboot.so loader.c
python scripts/build_standalone.py               # 组装 payload + 重打包 APK + 自校验
java -jar tools/uber-apk-signer.jar -a build/standalone/MoMoWords_L1_standalone_unsigned.apk -o signed
python scripts/verify_standalone.py <设备序列号>   # 一键真机断言 + 落证据

adb logcat -s MoMoBoot:I MoMoCrack:I             # 运行期日志（脚本经 __android_log_print 写 logcat）
```

---

## 七、真机证据

```
I MoMoBoot : dladdr self=/data/data/com.maimemo.android.momo/cache/momoco-host-native-…/libmomoco.so
I MoMoBoot : chain dlopen(libmomoco.so) -> 0xc748…   real libmomoco JNI_OnLoad=0x6e8351d458
I MoMoBoot : extract ok=1 js=…/mmc.js so=…/libmmcore.so
I MoMoBoot : dlopen(gadget) -> 0x1f97…               # 无监听端口、无 attach
I MoMoCrack: [OK] hook a.s()  => 2147483647（仅上报路径回落真实值）
I MoMoCrack: [OK] hook x1d.f(boolean)  => 2147483647
I MoMoCrack: [OK] 已包装上报构造 ada.b() / s40.m() / gq2.m()
I MoMoCrack: [INFO] x1d.f(false) = 2147483647
I MoMoCrack: [INFO] 上报模式读到的真实值: 单词上限=5012 可用上限=5012
I MoMoCrack: SELFTEST ok local=2147483647 reporting=5012 stealth=true origCallOk
```

**本地 2147483647，上报 5012** —— 破解生效且未泄露。进程存活，无壳自毁、无崩溃。

---

## 八、目录

```
docs/     Lesson1_Writeup.md              完整技术报告（保护分析 / 脱壳 / 链路 / 验证）
          Lesson1_Noroot_Standalone.md    无 root 独立包专题（注入点 / 配置难题 / 踩坑）
native/   loader.c                        自解包引导层（arm64）
frida/    entry_crack.js                  破解 + 反封号脚本
          dump_dex.js                     OpenCommon 脱壳
scripts/  build_standalone.py             一键构建独立包
          verify_standalone.py            一键真机验证 + 证据落盘
          apply_crack.py                  frida-server attach 注入
          patch_dex_return.py             dex 方法体字节级补丁
          patch_elf_needed_append.py      ELF DT_NEEDED 注入（追加式 .dynstr）
          gadget_crack.py                 gadget 转发 + 注入
evidence/ EVIDENCE_frida_crack.log        破解运行日志
          selftest_stealth.log            反封号自检
```

---

## 九、已知限制

* 独立包只内嵌 **arm64-v8a** 的 gadget（`META-INF/native/libmomoco.so` 只能有一个文件，
  无法同时满足两种 ABI）；32 位设备需要单独打一份 v7a 包。
* Android 16 起 `System.load` 可写的 cache 文件会打警告 `Attempt to load writable file`，
  未来版本若改为抛错，这条注入路径需要更换落点。
* 每次冷启会往 App cache 写 25 MB 的 gadget（约 200 ms）。
