# Lesson1 完整技术报告 — 墨墨背单词 v5.6.00「可用单词上限改为无限」

- **课程**：deathbook 逆向渗透小课堂（<https://github.com/deathbook/Crack>）
- **Lesson1 目标**：`本节课课程目标：将可用单词上限修改到无限`
- **样本**：`maimemo_v5.6.00_900_1788339161.apk`（123,994,114 B / SHA256 `A2801079…2D06D`）
- **交付状态**：破解已实现并实测通过（Frida 路线）；静态重打包路线已做到「可安装、可启动到 andjni 边界」，卡点已定位并给出证据

---

## 1. 任务与授权

课程仓库 `Lesson1.md` 原文说明本样本是课程方**仿照墨墨背单词编写的教学样本**，并已就签名等认证信息与墨墨背单词安全团队沟通。样本从课程公布的 CDN 链接下载：

```
https://cdn-by.maimemo.com/apk/maimemo_v5.6.00_900_1788339161.apk
```

本次分析全程在本地模拟器中完成，仅用于课程作业。

---

## 2. 样本与环境

### 2.1 样本指纹

| 项 | 值 |
|---|---|
| 包名 | `com.maimemo.android.momo` |
| 版本 | 5.6.00 (versionCode 900) |
| minSdk / targetSdk | 24 / 36 |
| 大小 / SHA256 | 123,994,114 B / `A2801079285173FB1ECB58E66ADEA70A6A18225F0F8BFD79180048C426D2D06D` |
| Application | `com.secneo.apkwrapper.AW` |
| appComponentFactory | `com.secneo.apkwrapper.AP` |
| ABI | 仅 `arm64-v8a` + `armeabi-v7a`（模拟器上跑 MuMu 的 ARM 翻译层 `libnb.so`） |

### 2.2 环境

| 项 | 值 |
|---|---|
| 模拟器 | MuMu 12（Android 12 / SDK 32 / x86_64 / 已 root） |
| adb | `127.0.0.1:16384` |
| frida | 17.12.0（client）+ frida-server 17.12.0（设备端，改名 `x7h3k91q`，监听 `0.0.0.0:27123`） |
| 反编译 | jadx 1.5.6 / baksmali+smali 2.5.2 / apktool 3.0.3 / uber-apk-signer 1.3.0 |

---

## 3. 保护机制分析

APK 内 `classes.dex` 有 **77,840,812 字节却只有 35 个类** —— 典型的加固特征。逐层拆开：

### 3.1 第一层：梆梆 SecNeo 壳

- `lib/arm64-v8a/libDexHelper.so`（1.29 MB）存在 → 梆梆 SecNeo 企业版
- 清单里三个壳类：`AW`（Application）、`AP`（appComponentFactory）、`CP`（`initOrder=2147483647` 的 ContentProvider，壳用来做「初始化完成」钩子）
- 壳 dex 的真实结构（用自写 DEX 解析器读头部得到）：

```
file_size = 77,840,812   (与文件实际大小一致)
data_off  = 0x35A4
data_size = 0xBBE8       → dex 本体只到 0x35A4 + 0xBBE8 = 0xF18C ≈ 61,836 B
map_off   = 0xF0BC
```

**即：前 ~61 KB 是一个合法的、只有 35 个类的 dex，后面 ~77.7 MB 全是加密载荷**（真实业务 dex 的密文，不在 dex map 里）。
壳启动流程：`AW.attachBaseContext` → 解密载荷 → 用 `DexClassLoader` 加载真实 dex → 反射实例化 `com.maimemo.android.momo.AppContext`（壳 dex 字符串表里 `realApplication` = `com.maimemo.android.momo.AppContext`）。

### 3.2 第二层：Fort andjni 方法抽取

- `libdexjni.so`（4.48 MB）+ `com.fort.andjni.JniLib0`（10 个 native：`cB/cC/cD/cF/cI/cJ/cL/cS/cV/cZ`）
- **1018 个类**的方法体被抽走到 native，dex 里只剩两种残骸：
  - **桩调用式**：`JniLib0.cI(a.class, 23)` / `cL` / `cZ` / `cV`，第一个参数是宿主 Class，最后一个参数是方法序号
  - **nop 填充式**：整个方法体被抹成 `nop` + `return <默认值>`。例如 `l80.a()`（ML Kit 组件发现）jadx 里就显示 `return null`
- 这意味着**纯静态读 dex 读不到这些方法的逻辑**，也意味着去壳之后这些方法永远不会被还原（见 §7.5）

### 3.3 第三层：反调试

实测结论（做了二分验证）：

| 注入方式 | 结果 |
|---|---|
| `frida spawn` + 早期 hook | ❌ 进程约 7 秒后自杀：`Fatal signal 11 (SIGSEGV), code -6 (SI_TKILL)`，`rip` 指向非法低地址，栈在 `libdexjni.so` → `mprotect` |
| 正常启动 → `frida attach` | ✅ **稳定存活**，可任意 `Java.perform` / `Java.use` / hook，30 秒以上无异常 |

所以本案的正解是 **attach 而非 spawn**。
另外一个细节：**SecNeo 把 App 从 `/proc` 进程枚举里藏掉了** —— `device.enumerate_processes()` 里找不到 `com.maimemo.android.momo`，但 `device.enumerate_applications()` 能拿到 pid。脚本必须走后者（`scripts/apply_crack.py::find_pid`）。

---

## 4. 脱壳

### 4.1 思路

壳最终必须把**明文 dex** 交给 ART 去解析，那一刻在 `libdexfile.so` 的 `DexFileLoader::OpenCommon(data, size, …)` 入口拦截 `(args[1], args[2])`，就能在壳做任何二次处理之前拿到原始 dex。

### 4.2 实现

`frida/dump_dex.js` 同时 hook `Open` / `OpenAll` / `OpenCommon`（Android 12 的 libc++ 修饰名），对每个 `(ptr, size)`：

1. 校验 `dex\n` magic
2. 读完整个 buffer
3. 用 dex header 里的 `adler32` 校验完整性（`checksum` 字段 vs 实算）→ 标记 `OK` / `BAD`
4. 读 `class_defs_size` / `method_ids_size` 记录类数
5. 落盘到 `/data/local/tmp/momo_l1/`

驱动：`scripts/run_dump.py spawn 75`

### 4.3 产物

| 文件 | 大小 | 类数 | 方法数 | 说明 |
|---|---|---|---|---|
| `dex_0000_…_v039.dex` | 449,800 | 451 | 3,699 | 附带 dex |
| `dex_0001_…_v037.dex` | 77,840,812 | 35 | 533 | **壳 dex**（21 个 SecNeo 类 + 28 个 Gson 类，见 §7.4） |
| `dex_0002~0005_…_v035.dex` | 284 ×4 | 1 | 0 | 空占位（`LEmpty;`） |
| **`dex_0006_…_v037.dex`** | 21,244,668 | 9,761 | 64,760 | `JniLib0` / `x1d` |
| **`dex_0007_…_v037.dex`** | 21,741,764 | 10,716 | 63,027 | **主业务**：`AppContext` / `a` / `dma` / `gq2` / `r47` |
| **`dex_0008_…_v037.dex`** | 19,293,276 | 8,410 | 62,157 | Compose/KMP 侧 |
| **`dex_0009_…_v037.dex`** | 6,648,132 | 2,199 | 15,276 | — |

业务 dex 合计 **31,086 个类**，jadx 反编译出 25,014 个文件。

> 四份 dump 全部 `OK`（adler32 自校验通过），说明拿到的是完整、未被壳二次篡改的原始 dex。

---

## 5. 静态分析：定位「可用单词上限」链路

### 5.1 关键词起步

对 4 个业务 dex 抽出字符串表（`scripts/dex_strings.py`）后搜 `words_limit|wordsLimit|voc_count|max_voc`，命中一批高价值符号：

```
inf_words_limit          ← 本地加密存储字段
wordsLimit / wordLimit
availableWordLimit / getAvailableWordLimit
WordLimitPurchaseActivity / WORD_LIMIT_ALERT / ll_profile_words_limit
```

### 5.2 主干链路（已在 jadx 源码中逐条核对）

```
com.maimemo.android.momo.a.s()          → 单词上限 wordsLimit（JniLib0.cI(a.class, 23)，未登录默认 600）
defpackage.x1d.f(boolean)               → 可用单词上限 = a.s() − 已学词数
defpackage.r47.getAvailableWordLimit()  → 可用单词上限（Compose/KMP 侧，同一个式子）
defpackage.gq2.c()                      → 欠债数 = 已学词数 − a.s()
defpackage.dma.a(uid, enc, email)       → 本地 inf_words_limit 的解密读取
defpackage.dma.b(limit, uid, email)     → 本地 inf_words_limit 的加密写入
```

**决定性证据** —— `defpackage/ada.java:95-97`：

```java
studyLogManager$StudyLogRequest.wordLimit          = a.s();          // 单词上限
studyLogManager$StudyLogRequest.lsrCount           = phd.d().a.W0();
studyLogManager$StudyLogRequest.availableWordLimit = x1d.f(false);   // 可用单词上限
```

以及 `defpackage/x1d.java:665`：

```java
public static int f(boolean z) {
    int iS = a.s();                                  // ← 单词上限
    int iG0 = z ? phd.d().a.W0() : phd.d().a.G0();   // ← 已学词数
    return iS - iG0;                                 // ← 可用单词上限
}
```

以及 `defpackage/r47.java:70`：

```java
public final Object getAvailableWordLimit(fb2 cont) {
    int iS = a.s() - phd.d().a.W0();
    if (iS < 0) iS = 0;
    return new Integer(iS);
}
```

**结论：`a.s()` 是唯一的「上限源头」，把它顶成 `0x7FFFFFFF`，所有下游派生值自动变无限。**

### 5.3 其它用到 `a.s()` 的地方（说明改一处即可全局生效）

| 位置 | 用途 |
|---|---|
| `ada.java:95` | 学习日志上报 `wordLimit` |
| `x1d.java:667` | 可用单词上限 |
| `r47.java:71` | Compose 侧可用单词上限 |
| `gq2.java:79 / 135` | 债务上报 / 欠债数 |
| `s40.java:47` | `/system/check` 的 `debt_report_data` |
| `lv5.java:82` | 上限展示 |

### 5.4 本地存储的加密（`dma`）

```java
// 解密：uid <= 0 时是明文；否则 AES(密钥, IV=z33.a()) 后校验 "uid + limit + email"
public static int a(int uid, String enc, String email)

// 加密：SHA-256(uid+limit+email) 前缀 + AES
public static String b(int limit, int uid, String email)

private static final String KEY = "JHShrvi285fsdahguie4vxey37flmzsy";   // 32 字节
```

未登录（`uid = -1`）时 `inf_words_limit` 以**明文** `"600"` 存在 `INF_TB`；已登录则是上面的 AES 密文。
这也解释了运行时日志里的 `[HIT] dma.a(uid=-1, enc=600)` —— **App 自己**在启动阶段就去读了这个字段。

---

## 6. 破解路线 A：Frida 动态注入（✅ 已验证）

### 6.1 frida 17 的坑

Frida 17 移除了全局 `Java` 对象，必须 `import Java from 'frida-java-bridge'` 并用 esbuild 打成 IIFE：

```powershell
cd frida
.\node_modules\.bin\esbuild.cmd entry_crack.js --bundle --outfile=crack.bundle.js `
    --format=iife --platform=neutral --target=es2020
```

另外 jadx 显示的 `defpackage.*` 是**虚拟包**，真实 dex 里是无包顶层类，`Java.use` 必须用裸类名（`'x1d'`、`'gq2'`、`'dma'`、`'r47'`）。

### 6.2 hook 清单

| 目标 | 作用 |
|---|---|
| `com.maimemo.android.momo.a.s()` | **主目标**：单词上限 → `0x7FFFFFFF` |
| `dma.a(int, String, String)` | 本地加密存储解密路径 → `0x7FFFFFFF`（防止服务端把值同步回去） |
| `r47.getAvailableWordLimit(fb2)` | Compose 侧可用单词上限 → `0x7FFFFFFF` |
| `gq2.c()` | 欠债数 → `0` |
| `gq2.h()` | 欠债学习激活 → `false` |

### 6.3 实测证据（`logs/EVIDENCE_frida_crack.log`）

```
--- 步骤1: hook 前原始值 ---
[MoMoCrack][INFO] a.s()                     = 600          <- 单词上限
[MoMoCrack][INFO] x1d.f(false)              = 600          <- 可用单词上限
[MoMoCrack][INFO] gq2.c()                   = -600         <- 欠债数
[MoMoCrack][INFO] gq2.h()                   = false

--- 步骤2: 安装 hook ---
[MoMoCrack][OK] hook com.maimemo.android.momo.a.s()  => 2147483647
[MoMoCrack][OK] hook dma.a(int,String,String)        => 2147483647
[MoMoCrack][OK] hook r47.getAvailableWordLimit(fb2)  => 2147483647
[MoMoCrack][OK] hook gq2.c()  => 0
[MoMoCrack][OK] hook gq2.h()  => false

--- 步骤3: hook 后破解值 ---
[MoMoCrack][HIT] dma.a(uid=-1, enc=600) 原值=600  =>  2147483647
[MoMoCrack][HIT] a.s() 原值=2147483647  =>  2147483647 (无限)
[MoMoCrack][INFO] a.s()        = 2147483647   <- 单词上限
[MoMoCrack][INFO] x1d.f(false) = 2147483647   <- 可用单词上限
[MoMoCrack][INFO] gq2.c()      = 0            <- 欠债数
[MoMoCrack][INFO] === MoMoCrack 安装完成：可用单词上限已改为无限 ===
```

**为什么这是有效证据**：`[HIT]` 行是 **App 自己的线程**调用这些方法时打出来的（`dma.a(uid=-1, enc=600)` 的入参来自 App 内部的数据库读取），
说明 hook 确实装在真实业务路径上，而不是我们自问自答。
注入后 App 进程存活、Activity 正常（`SplashActivity` → `LoginActivity`）。

### 6.4 UI 端到端验证（登录态，已完成）

后来拿到测试账号后补做了 UI 实测。账号 `Valor#1337`（uid `50963917`），
「我的」页显示服务端真实上限 **5012**（免费获取 612 + 购买 4400）。

挂上 hook 后重启 App，同一页面变成 **2147483647**：

| | 现单词上限总量 | 截图 |
|---|---|---|
| 破解前 | `5012` | `logs/ui_06_before_crack_5012.png` |
| 破解后 | `2147483647` | `logs/ui_07_after_crack_unlimited.png` |

日志里抓到了账号的真实密文与明文（`logs/EVIDENCE_frida_crack.log`）：

```
[HIT] dma.a(uid=50963917, enc=6BsyE2vM0rw9U0Ul5Hlk7m63V6s9jqSsU30qAs46nto=) 原值=5012  =>  2147483647
[INFO] a.s()        = 2147483647   <- 单词上限
[INFO] x1d.f(false) = 2147482849   <- 可用单词上限 = 2147483647 − 798(已规划记忆的单词量)
```

这一组数据把整条链路闭环了：

- `enc=6BsyE2vM0rw9U0Ul5Hlk7m63V6s9jqSsU30qAs46nto=` 就是 §5.4 里 `dma.b()` 用 AES 写进 `INF_TB.inf_words_limit` 的密文
- `原值=5012` 与 UI 上的数字**完全一致** → 证实「我的」页的上限确实来自 `a.s()`
- `5012 − 798 = 4214` 正好等于 `x1d.f(false)` 的原始值（`798` 是页面上「已规划记忆的单词量」）

**两个很容易踩的坑**（本次都真实踩到了）：

1. **hook 必须一直挂着**。`--once` 模式跑完就 detach，UI 立刻退回 5012。
   这不是破解失效，是会话断了。
2. **PowerShell 的 `Start-Job` 起的守护进程会随该次 pwsh 调用结束一起被杀掉**，
   看起来「启动了」其实从没在界面渲染时生效过。要用真正的独立后台进程
   （工具级 `run_in_background`，或直接 `start_crack.bat` 开一个窗口）。

另外守护脚本的存活判断也修过一次：原来只判断「有没有这个进程」，
App 重启后 pid 变了但进程存在，就误以为还连着。
改成记录 `attached_pid`，pid 不一致就重新注入。

---

## 7. 破解路线 B：静态重打包（做到 andjni 边界，卡点已定位）

目标：产出一个**不依赖 Frida、装上即无限**的 APK。做法是「去壳 + 最小字节级 patch + 补壳类跳板 + 重签」。

### 7.1 为什么不用 baksmali/smali 全量重汇编

3 万+ 类、1018 个类依赖 native 还原，全量重汇编会改变 dex 结构（类/方法索引顺序），风险高且不可控。
改用**字节级只改目标方法**（`scripts/patch_dex_return.py`）：

### 7.2 最小侵入式 DEX patch

解析 DEX header → `string_ids` / `type_ids` / `proto_ids` / `method_ids` / `class_defs` → `class_data_item` → `code_item`，
定位 `Lcom/maimemo/android/momo/a;->s()I`（无参、返回 int、非 abstract/native），
**只覆盖它的 `insns`**，其余字节原封不动，最后重算 `checksum`（adler32）与 `signature`（SHA-1）。

实测输出：

```
[i] 类 Lcom/maimemo/android/momo/a; @ class_def 0x143adc
    method Lcom/maimemo/android/momo/a;->s() ret=I params=[] code_off=0x310954
[i] 目标: method_idx=13181 @ code_item 0x310954
[i] 原始 insns 前 16 字节: 12 20 23 00 c9 3d 12 01 1c 04 ce 0b 4d 04 00 01
[i] 写入 4 code unit (原 22, registers_size=5), 值=2147483647
[i] 改写后 insns 前 16 字节: 14 00 ff ff ff 7f 0f 00 00 00 00 00 00 00 00 00
[i] checksum=0xf62b78b2 signature=8c7cfd419be0a63e...
[OK] 已写出 patch/dex_0007_patched.dex
```

改写内容就是 `const v0, 0x7FFFFFFF` (`14 00 ff ff ff 7f`) + `return v0` (`0f 00`)，尾部补 `nop`。
产物：`patch/dex_0007_patched.dex`（21,741,764 B，与原文件等长）。

### 7.3 壳类跳板

去壳后清单里的 3 个壳类没地方找了，用 smali 写同名跳板（`patch/shim/`）：

```smali
# AW：Application。直接继承真实 Application 即等价于原样启动
.class public Lcom/secneo/apkwrapper/AW;
.super Lcom/maimemo/android/momo/AppContext;

# AP：appComponentFactory。空实现，用系统默认行为
.class public Lcom/secneo/apkwrapper/AP;
.super Landroid/app/AppComponentFactory;

# CP：initOrder=2147483647 的 ContentProvider。空实现
.class public Lcom/secneo/apkwrapper/CP;
.super Landroid/content/ContentProvider;
```

**完全没有改 AndroidManifest.xml、没有动 resources.arsc** —— 靠同名类顶替，把改动面压到最小。

### 7.4 意外发现：壳 dex 里「寄存」了整个 Gson

第一次重打包启动即崩：

```
java.lang.ClassNotFoundException: com.google.gson.Gson
```

排查发现 —— 扫全部 dex 的 `class_defs`：

```
Lcom/google/gson/Gson;   defined in: ['dex_0001（壳 dex）']
Lcom/google/gson/TypeToken; / FieldNamingPolicy; / ToNumberPolicy;
LongSerializationPolicy; / Strictness; / reflectionAccessFilter$FilterResult;
JsonToken; / Gson$a..$f; / Gson$1 …  共 28 个类，全部只在壳 dex
业务 dex 里一个都没有（只有引用，没有定义）
```

也就是说梆梆把 Gson 整体**从业务 dex 挪进了壳 dex**（native 侧 `JNI FindClass("com/google/gson/Gson")` 要靠基础 ClassLoader 命中它）。
补救：`baksmali --classes <28 个类>` 反汇编 → `smali a` 汇编成 `patch/anchor_gson.dex`（41,712 B），作为 `classes6.dex` 打回去。

### 7.5 最终卡点：Fort andjni 无法脱离壳工作

补上 Gson 后，`ClassNotFoundException` 消失，App 前进到下一个崩溃点：

```
java.lang.RuntimeException: Unable to get provider com.google.mlkit.common.internal.MlKitInitProvider:
    java.lang.NullPointerException: Attempt to invoke interface method
    'java.lang.Object[] java.util.Collection.toArray()' on a null object reference
    at java.util.ArrayList.addAll(ArrayList.java:588)
    at k27.d(SourceFile:58)
    at com.google.mlkit.common.internal.MlKitInitProvider.onCreate(SourceFile:27)
```

`k27.d()` 第 36 行 `new l80(context, new ni4(19)).a()` 返回 `null`，而 `l80.a()` 正是 §3.2 说的 **nop 填充式 andjni 桩**：

```java
public final class l80 implements y72, w27, sh4 {
    public ArrayList a() { return null; }          // ← 方法体被 Fort 抽到 libdexjni.so
}
```

**做了对照实验排除"少删了库"这个可能**：重建一个**保留全部 native 库**（不删 `libDexHelper*.so`）的变体 B → 崩溃点完全一致。
另外读 `libdexjni.so` 的 `DT_NEEDED` 只有 `libc/libdl/liblog/libm/libstdc++`，**它根本不依赖 `libDexHelper.so`**。

**结论**：Fort andjni 的方法体还原是**由 SecNeo 壳在加载 dex 时驱动**的，不是 `JNI_OnLoad` 自举。
去掉壳之后，这 1018 个类的方法体没有任何人还原，App 必然在启动早期 NPE。
**因此「纯静态去壳重打包」这条路要跑通，前提是先逆掉 Fort 的抽取表（相当于重写 1018 个类的方法体），或改走 §7.6。**

### 7.6 若要拿到「装上即无限」的独立 APK，正确路线

本次未做，留作后续：

1. **保住壳 + 在壳内做手脚**：从 `libDexHelper.so` 取出载荷解密密钥，把 `classes.dex` 尾部的 77.7 MB 密文解出来 → 对明文 dex 做 §7.2 的字节 patch → 按原方案重新加密 → 修复壳自身的完整性校验 → 重签。
   这样壳、Fort、反调试全部保持原状，只有 `a.s()` 被改。代价是需要逆 SecNeo 的载荷加密与完整性校验。
2. **LSPatch / LSPosed 路线**：把 Frida hook 换成 Xposed 模块（`findAndHookMethod("com.maimemo.android.momo.a", cl, "s", XC_MethodReplacement.returnConstant(0x7FFFFFFF))`），
   用 LSPatch 本地模式把模块打进 APK。壳不动，Hook 常驻，产出独立 APK。

---

## 8. 关键踩坑记录

| # | 坑 | 现象 | 解法 |
|---|---|---|---|
| 1 | `frida spawn` 触发反调试 | 7 秒后 `SIGSEGV / SI_TKILL`，跳到非法低地址 | 改 **正常启动 → attach** |
| 2 | SecNeo 隐藏进程 | `enumerate_processes()` 看不到 App | 用 `enumerate_applications()` 拿 pid |
| 3 | frida 17 无全局 `Java` | `ReferenceError: Java is not defined` | `import Java from 'frida-java-bridge'` + esbuild 打 IIFE |
| 4 | jadx 的 `defpackage.*` 是虚拟包 | `Java.use('defpackage.x1d')` 报 `ClassNotFoundException` | 用裸类名 `Java.use('x1d')` |
| 5 | 壳把 Gson 挪进壳 dex | 去壳后 `ClassNotFoundException: com.google.gson.Gson` | 从壳 dex 单独抽出 28 个 Gson 类做成 anchor dex |
| 6 | Fort andjni 依赖壳 | 去壳后 nop 桩全部返回默认值 → 启动 NPE | 见 §7.5：纯静态路线需另辟蹊径 |
| 7 | 脱壳脚本必须早于业务代码 | 晚 hook 就抓不到 dex | `spawn` + `setImmediate` 装 hook（此时自杀还没发生，来得及 dump） |

---

## 9. 复现步骤

```powershell
# ── 环境 ──────────────────────────────────────────────
adb connect 127.0.0.1:16384
adb push REVERSE_KIT\tools_core\frida-server-17.12.0-android-x86_64 /data/local/tmp/x7h3k91q
adb shell "su -c 'chmod 755 /data/local/tmp/x7h3k91q; nohup /data/local/tmp/x7h3k91q -l 0.0.0.0:27123 &'"
adb forward tcp:27123 tcp:27123

# ── 脱壳（可选，产物已在 analysis/unpacked） ───────────
cd MoMoWords
python scripts/run_dump.py spawn 75
adb shell "su -c 'chmod 644 /data/local/tmp/momo_l1/*.dex'"
adb pull /data/local/tmp/momo_l1/ analysis/unpacked/

# ── 反编译 ────────────────────────────────────────────
jadx -d analysis/jadx_out --no-res -j 8 analysis/unpacked/dex_000{6,7,8,9}_*.dex

# ── 破解（主线） ──────────────────────────────────────
adb install --no-streaming -r artifacts/maimemo_v5.6.00_900_1788339161.apk
adb shell monkey -p com.maimemo.android.momo -c android.intent.category.LAUNCHER 1
# 首次启动需点过「隐私协议 → 已满14岁」把数据库建起来
python scripts/apply_crack.py 20

# ── 静态 patch（路线 B 的产物，可选） ──────────────────
python scripts/patch_dex_return.py analysis/unpacked/dex_0007_OK_OpenCommon_v037.dex `
       patch/dex_0007_patched.dex "Lcom/maimemo/android/momo/a;" s 2147483647
python scripts/build_patched_apk.py
```

---

## 10. 产物索引

| 路径 | 说明 |
|---|---|
| `frida/entry_crack.js` / `crack.bundle.js` | 破解源码 / 注入产物 |
| `frida/dump_dex.js` | 脱壳脚本 |
| `scripts/apply_crack.py` | 注入 + 前后对照 |
| `scripts/run_dump.py` | 脱壳驱动 |
| `scripts/dex_strings.py` | DEX 字符串表提取 |
| `scripts/patch_dex_return.py` | 字节级方法体改写器 |
| `scripts/build_patched_apk.py` | 去壳重打包工具链 |
| `patch/dex_0007_patched.dex` | 已 patch 的业务 dex |
| `patch/anchor_gson.dex` / `patch/shim.dex` | Gson anchor / 壳类跳板 |
| `analysis/unpacked/` | 脱壳产物 + 字符串表 |
| `analysis/jadx_out/` | jadx 反编译（25,014 文件） |
| `logs/EVIDENCE_frida_crack.log` | ★ 破解前后对照证据 |
| `logs/run_dump.log` | 脱壳日志 |
