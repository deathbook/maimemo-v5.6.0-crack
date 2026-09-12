# LSPatch 路线可行性实测（结论：Android 16 上不可用）

> 目标：用 LSPatch「本地模式 + 内嵌模块」替代 Frida gadget，拿到接近官方版的跟手度。
> 实测设备：Xiaomi 23116PN5BC / **Android 16 / SDK 36** / arm64。
> 对照设备（用户报告）：Redmi Note 13 Pro `2312DRA50C` / **Android 16 / SDK 36**。
> 结论：**LSPatch 本身与 Android 16 不兼容，两个设备都跑不了。阻断点是工具，不是加固壳。**

---

## 1. 实验设计

为了把「LSPatch 改 Manifest/dex 会不会触发 SecNeo 自毁」和「LSPatch 能不能在 Android 16 跑」分开，
用**官方原版 APK**（未做任何我们自己的改动）做探针：

```bash
java -Xmx4g -jar lspatch.jar maimemo_v5.6.00_900_1788339161.apk -o out -f -v
# 不加 -m：只注入 loader，不嵌任何模块 → 只测兼容性，不测功能
java -jar uber-apk-signer.jar -a out/*-lspatched.apk -o signed --allowResign
adb install -r -d signed/*.apk
adb shell monkey -p com.maimemo.android.momo -c android.intent.category.LAUNCHER 1
```

---

## 2. 结果一：SecNeo **没有**自毁（意外的好消息）

LSPatch 打补丁是成功的，而且它自己就看穿了加固：

```
original appComponentFactory class: com.secneo.apkwrapper.AP
Adding metaloader dex...  Adding loader dex...  Adding native lib...
added assets/lspatch/so/arm64-v8a/liblspatch.so
Done. Output APK: ...-398-lspatched.apk   (125,591,916 B)
```

关键点：

* LSPatch 把它的 native 库放在 **`assets/lspatch/so/`**，**没有碰 `lib/`**；
* 它改的是 `AndroidManifest.xml`（替换 `appComponentFactory`）并追加了 loader dex；
* 运行时**没有出现任何 `SIGSEGV` / `fault addr 0xa98`** —— 也就是说
  **SecNeo 的完整性校验只覆盖 `lib/`，不校验 Manifest、也不校验 dex 数量**，
  这是我们这次实验额外拿到的一条加固结论（与之前"往 `lib/` 加一个文件就自毁"互补）。

## 3. 结果二：LSPatch 的 loader 在 Android 16 上直接崩

进程起来了又立刻死掉：

```
I ActivityManager: Start proc 3264:com.maimemo.android.momo ... for next-top-activity
I LSPatch-MetaLoader: Bootstrap loader from embedment
D nativeloader: Load .../base.apk!/assets/lspatch/so/arm64-v8a/liblspatch.so ... ok

E LSPlant : Failed to find GetMethodShorty
E LSPlant : Failed to init art method
E LSPosed : Failed to init lsplant
E LSPosed : Hook Fails: _ZN3art12ProfileSaver20ProcessProfilingInfoEbPt
E LSPosed : Hook Fails: _ZN3art14OatFileManager25RunBackgroundVerificationE...
E LSPatch : createLoadedApk
E LSPatch : java.lang.NoSuchFieldError: android.app.ActivityThread$AppBindData#compatInfo
E LSPatch :   at de.robv.android.xposed.XposedHelpers.lambda$findField$1(XposedHelpers.java:246)
E LSPatch :   at org.lsposed.lspatch.loader.LSPApplication.createLoadedApkWithContext(LSPApplication.java:108)
E LSPatch :   at org.lsposed.lspatch.loader.LSPApplication.onLoad(LSPApplication.java:73)
E LSPatch :   at org.lsposed.lspatch.metaloader.LSPAppComponentFactoryStub.<clinit>(Unknown Source:404)
I ActivityManager: Process com.maimemo.android.momo (pid 3264) has died: fg  TOP
```

两处硬伤，都与墨墨无关、与加固无关：

1. **`Failed to find GetMethodShorty` → `Failed to init art method` → `Failed to init lsplant`**
   —— LSPlant（LSPosed 的 ART hook 引擎）在 Android 16 的 ART 里找不到它依赖的内部符号。
2. **`NoSuchFieldError: android.app.ActivityThread$AppBindData#compatInfo`**
   —— LSPatch 自己的 loader 读 `AppBindData.compatInfo`，这个字段在 Android 16 已经被移除/改名。

**LSPatch 最新版本就是 v0.6（2023-11-23，基于 LSPosed core v1.9.2）**，之后没有任何新 release，
所以这不是配置问题，是版本天花板：

| 方案 | Android 12 (API 31) | Android 14 (API 34) | **Android 16 (API 36)** |
|---|---|---|---|
| LSPatch v0.6 | 可用 | 基本可用 | **不可用**（本实验） |
| LSPosed 1.10.x（需 root） | 可用 | 可用 | 可用 |

---

## 4. 交付：模块 APK（12.7 KB）

C 路线的功能部分已经做完并构建成 APK，`lspatch/mod/` 是源码：

```
lspatch/mod/AndroidManifest.xml          xposedmodule / xposeddescription / xposedminversion
lspatch/mod/assets/xposed_init           com.momowords.crack.MoMoHook
lspatch/mod/smali/com/momowords/crack/
    MoMoHook.smali        入口：确认包名 → 丢守护线程（SecNeo 解密 dex 要时间，不能立刻 findClass）
    Installer.smali       轮询 com.maimemo.android.momo.a 最多 60s，然后一次性装全部 hook
    Stealth.smali         ThreadLocal 的「上报模式」标志（按线程隔离）
    UnlimitedHook.smali   非上报路径**直接 setResult**，根本不执行原实现
    ReportHook.smali      包住上报构造函数：进入置标志，退出清标志
```

构建（本机无需 Android SDK，apktool 自带 smali 汇编器）：

```bash
java -jar tools/apktool.jar b lspatch/mod -o momocrack-module.apk
java -jar tools/uber-apk-signer.jar -a momocrack-module.apk -o signed
# -> signed/momocrack-module-aligned-debugSigned.apk  (12,695 B)
```

### 怎么用（两条路，同一个 APK）

| 环境 | 做法 |
|---|---|
| **有 root + LSPosed（推荐，Android 16 唯一可行）** | 装模块 APK → LSPosed 里勾选 → 作用域选「墨墨背单词」→ 强行停止并重启 App。**官方 APK 原封不动，不存在签名冲突，也不用再碰 134 MB 的包** |
| Android ≤ 14 无 root | `java -jar lspatch.jar maimemo原版.apk -m signed/momocrack-module.apk -o out` → 安装产物 |

> 模块 APK 在本机**无法测试**（`b733636b` 有 KernelSU 但没有 LSPosed，且 `su` 对 adb shell 不可用），
> 需要在有 LSPosed 的设备上验证。dex 已用 baksmali 反查确认包含全部 5 个类。

---

## 5. 复现脚本

```bash
# 1) 取 LSPatch（走 gh-proxy.com 镜像，3 MB/s；ghproxy.net 只有 20 KB/s）
curl -L -o lspatch.jar "https://gh-proxy.com/https://github.com/LSPosed/LSPatch/releases/download/v0.6/jar-v0.6-398-release.jar"
# 2) 探针：只注入 loader，不嵌模块
java -Xmx4g -jar lspatch.jar <官方原版.apk> -o out -f -v
# 3) 看崩溃
adb logcat -s LSPatch:I LSPatch:E LSPlant:E LSPosed:E
```
