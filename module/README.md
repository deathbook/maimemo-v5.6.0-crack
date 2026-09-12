# LSPosed 模块 —— 墨墨背单词 v5.6.0 单词上限解锁

```
momocrack-module.apk     12,695 B   已签名(v2/v3)
SHA256                   a6ee08583c3e6a9d10f93a71be285a1785c37fdf2001697535774b33d6d97ea7
```

**官方 APK 原封不动** —— 不重打包、不换签名、没有 `packageInfo is null`、不用卸载任何东西。
代价是设备需要 **root + LSPosed**。

---

## 为什么需要它

无 root 的 Frida 独立包（Releases 里的 `maimemo_v5.6.0_cracked_standalone.apk`）能用，但按键有明显延迟：
Frida 建 Java hook 后，被 hook 的方法与其所在类会**退出 ART 的 AOT/JIT 优化路径**，这是"在场成本"，
不是回调次数的问题（实测 `a.s()` 20 秒才 11 次，照样掉 44%）。

LSPosed 走 ART 层的 `ArtMethod` 替换，不进 JS 桥、不做全量插桩，代价低一个量级。

Android 16 上 **LSPatch 不可用**（LSPatch v0.6 的 loader 崩：`LSPlant: Failed to find GetMethodShorty`
+ `NoSuchFieldError: ActivityThread$AppBindData#compatInfo`，详见 `docs/LSPatch_Probe_Result.md`），
所以 Android 16 只有 LSPosed 这一条路。

---

## 安装

```bash
adb install -r momocrack-module.apk
```

1. 打开 **LSPosed 管理器 → 模块**，勾选 **MoMoCrack**
2. **作用域**只勾「墨墨背单词」（`com.maimemo.android.momo`）
3. **强行停止**墨墨，重新打开（勾了作用域但没生效就重启一次手机）

### 验证

模块本身不写日志（保持零开销），直接看效果：App 里「**现单词上限总量**」应变成 **2147483647**。

要看模块有没有跑起来：

```bash
adb logcat -s LSPosed:I LSPosed:E AndroidRuntime:E
```

---

## 它做了什么

```
smali/com/momowords/crack/
    MoMoHook.smali        入口（assets/xposed_init 指定）：确认包名 → 丢守护线程
    Installer.smali       轮询 com.maimemo.android.momo.a 最多 60s，探到后一次性装全部 hook
    Stealth.smali         ThreadLocal 的「上报模式」标志（按线程隔离）
    UnlimitedHook.smali   把返回值改成常数（非上报路径）
    ReportHook.smali      包住上报构造函数：进入置标志，退出清标志
```

| 目标 | 结果 |
|---|---|
| `com.maimemo.android.momo.a.s()` | `0x7FFFFFFF`（单词上限） |
| `x1d.f(boolean)` | `0x7FFFFFFF`（可用单词上限） |
| `dma.a(int,String,String)` | `0x7FFFFFFF`（本地 `inf_words_limit` 解密） |
| `gq2.c()` | `0`（欠债数） |
| `ada.b()` / `s40.m()` / `gq2.m()` | **不拦返回值**，只包一层上报模式标志 |

### 两个关键实现点

**1. 不能立刻 `findClass`。** `handleLoadPackage` 在 Application 创建之前跑，而 SecNeo 是那之后才把业务
dex 解密加载进来 —— 第一秒一定找不到类。所以 `Installer` 是个守护线程，每 400 ms 探一次，最多 150 次。

**2. 非上报路径根本不执行原实现。**

```smali
invoke-static {}, Lcom/momowords/crack/Stealth;->isReporting()Z
move-result v0
if-nez v0, :done                       # 上报中 → 什么都不做，原实现照常跑
iget v0, p0, ...->value:I
invoke-static {v0}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;
invoke-virtual {p1, v0}, ...MethodHookParam;->setResult(Ljava/lang/Object;)V   # 否则直接改返回值
```

这一点是必须的：`a.s()` 走 JNI 会去开 SQLite，**未登录 / 数据库还没建立时它会抛
`SQLiteCantOpenDatabaseException`**。如果先调原实现再看标志，异常会从 hook 里冒出去，UI 拿不到无限值。

### 反封号（上报一致性）

服务端三条聚合上报链路会带上限值。如果本地无限、上报也报 2147483647，一次请求就是破解特征。
所以 `ReportHook` 在进入这些构造函数时置「上报模式」，期间上述方法回落**服务端真实值**（实测 5012），
出栈立刻恢复无限。逐词 oplog 与备份 ZIP 保持诚实，记忆曲线同步不受影响。

---

## 构建（本机无需 Android SDK）

apktool 自带 smali 汇编器，直接吃 `smali/` 目录：

```bash
java -jar tools/apktool.jar b module -o momocrack-module.apk
java -jar tools/uber-apk-signer.jar -a momocrack-module.apk -o signed
```

`module/AndroidManifest.xml` 里的关键 meta-data：

```xml
<meta-data android:name="xposedmodule"      android:value="true" />
<meta-data android:name="xposeddescription" android:value="..." />
<meta-data android:name="xposedminversion"  android:value="93" />
```

`module/xposed_init`（构建时放到 APK 的 `assets/xposed_init`）：

```
com.momowords.crack.MoMoHook
```

---

## 已知限制

* **本模块尚未在真机运行验证。** 开发机上测试设备只有 KernelSU、没有 LSPosed，`su` 对 adb shell 也不可用，
  装不了也启用不了框架。已验证的是：apktool 编译通过、baksmali 反查确认 dex 内 5 个类齐全、
  清单 meta-data 与 `xposed_init` 正确、签名有效(v2/v3)。运行时行为需在有 LSPosed 的设备上确认。
* `ada.b()` / `s40.m()` / `gq2.m()` 用 `hookAllMethods` 按名字全hook（这三个方法的重载签名没逐个确认过）。
  包装只是置/清一个线程级标志，多包一个无害。
* `r47.getAvailableWordLimit(fb2)` 没有 hook —— `a.s()` 改成无限后它的取值来源需要实测确认；
  如果设置页显示的可用上限不对，按同一个 `UnlimitedHook` 补上即可。

---

## 等级特权解锁（Issue #1）

模块同样包含等级解锁，两个 hook：

| 目标 | 改成 |
|---|---|
| `com.maimemo.android.momo.user.level.LevelPrivilege.a()` | `0`（特权要求的等级清零） |
| `xfb.h()` | `999`（用户等级拉满） |

门控公式：`xfb.f.h() >= levelPrivilege.getLevel()` → 不满足就加
`DisableReason.LevelNotReached`。两个操作数都被强制通过后，该原因不会再产生。
细节与真机证据见 [`../docs/Issue1_Level_Unlock.md`](../docs/Issue1_Level_Unlock.md)。
