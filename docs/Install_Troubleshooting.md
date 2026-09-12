# 安装问题排查：`解析软件包时出现问题（33） / packageInfo is null`

> 结论先行：**APK 本身没有问题。** 同一个文件 `adb install -r` 可装（两次成功）、`apksigner` v1/v2/v3 全过、
> `aapt dump badging` 正常、`unzip -t` 无损坏、结构上与官方原版逐项等价（见 §2）。
> 所以这个报错来自**手机上的安装器/系统策略**，不是包结构。

---

## 1. 按概率排序的四个真实原因

### ① 手机上还装着官方版墨墨（签名不同）—— 最可能

官方包的签名是墨墨的发布证书，我们的包是重新签名的。Android 不允许"同包名、不同签名"覆盖安装。
小米安装器在准备"是否替换已装应用"这一步会去取**已安装包的 PackageInfo**，签名不匹配时拿不到，
就抛成了 `packageInfo is null`（而不是标准的 `INSTALL_FAILED_UPDATE_INCOMPATIBLE`）。

**处理（必须做）**：先在手机上卸载官方墨墨，再装破解包。

```bash
adb uninstall com.maimemo.android.momo
adb install -r maimemo_v5.6.0_cracked_standalone.apk
```

> 注意：卸载会清掉账号登录态与本地词库。想同时保留官方版，只能走 `docs/` 里的 LSPosed 模块路线
> （官方包原封不动，模块单独安装），那条路不存在签名冲突。

### ② HyperOS「纯净模式 / 安全守护 / 应用安全检查」拦截

小米对非应用商店来源的包有额外校验，被拦时的表现就是"解析软件包时出现问题"。
关掉 **设置 → 安全 → 纯净模式 / 安全守护**，或在安装弹窗里选"继续安装/仍要安装"。

### ③ 用 `file://` 拉起系统安装器

Android 7 起禁止 `file://` 暴露给其它应用（`FileUriExposedException`），安装器拿不到可读的 URI，
解析阶段就失败 → 同样报 `packageInfo is null`。

**正确做法**：从**系统文件管理器**里点这个 APK（它走 `content://` FileProvider），或者用 `adb install`。
不要用第三方工具的"直接 file:// 安装"路径。

### ④ 文件传到手机时被截断

134 MB 走 MTP / 微信 / 网盘很容易传一半。先在手机上核对大小与 SHA256：

```bash
# 手机上（Termux 或 adb shell）：
sha256sum /sdcard/Download/maimemo_v5.6.0_cracked_standalone.apk
# 应为 e4932416c24e7fa382a3062331eecd19cd6b11e217f776f8bf6d0b4071bdfeb6
```

（另外确保空闲空间 ≥ 1.5 GB。）

---

## 2. 为什么可以断定不是包的问题

用 `scripts/apk_struct_diff.py` 把**官方原版**和**我们的重打包版**逐字段对比：

| 检查项 | 官方原版 | 我们的包 | 结论 |
|---|---|---|---|
| EOCD / 条目数 | 3422 | 3426（+4 个 `META-INF/native/`） | 正常增量 |
| Zip64 | 否 | 否 | 一致 |
| 中央目录 extra 字段 | 0 个 | 0 个 | 一致 |
| `resources.arsc` | `method=0`，data_off % 4 == 0 | `method=0`，data_off % 4 == 0 | **符合 Android 11+ 硬要求** |
| `AndroidManifest.xml` | `method=8` | `method=8` | 一致 |
| v1 (JAR) 签名 | `META-INF/_____.RSA/.SF` + `MANIFEST.MF` | `META-INF/ANDROIDD.RSA/.SF` + `MANIFEST.MF` | **都有 v1，外加 v2/v3** |
| `aapt dump badging` | OK | OK | 一致 |
| `unzip -t` | 通过 | 通过 | 一致 |

也就是说：我们的包在 ZIP 结构、资源对齐、签名方案上**不比官方包少任何一项**，`lib/` 目录更是一个字节都没动。
平台解析器会对官方包做的每一项校验，对我们的包同样通过。

---

## 3. 三种可靠安装方式（按推荐度）

### A. adb 安装（最稳，已验证）

```bash
adb uninstall com.maimemo.android.momo      # 若装过官方版或有旧签名的包
adb install -r maimemo_v5.6.0_cracked_standalone.apk
adb shell monkey -p com.maimemo.android.momo -c android.intent.category.LAUNCHER 1
adb logcat -s MoMoBoot:I MoMoCrack:I
```

### B. 手机上点按安装

1. 卸载已装的 `com.maimemo.android.momo`；
2. 关闭纯净模式 / 安全守护；
3. 把 APK 放到 `/sdcard/Download/`，用**系统文件管理器**点开；
4. 允许该文件管理器"安装未知应用"。

### C. 先校验再安装

```bash
adb shell ls -l /sdcard/Download/maimemo_v5.6.0_cracked_standalone.apk   # 应为 140677433 字节
```

---

## 4. 安装成功后如何确认破解生效

```bash
adb logcat -s MoMoBoot:I MoMoCrack:I
```

期望看到：

```
I MoMoBoot : dladdr self=/data/data/com.maimemo.android.momo/cache/momoco-host-native-.../libmomoco.so
I MoMoBoot : chain dlopen(libmomoco.so) -> 0x...
I MoMoBoot : extract ok=1 js=.../mmc.js so=.../libmmcore.so
I MoMoBoot : dlopen(gadget) -> 0x...
I MoMoCrack: [OK] hook a.s()  => 2147483647（仅上报路径回落真实值）
I MoMoCrack: [OK] hook x1d.f(boolean)  => 2147483647
I MoMoCrack: [OK] 已包装上报构造 ada.b() / s40.m() / gq2.m()
I MoMoCrack: SELFTEST ok local=2147483647 reporting=<服务端真实值> stealth=true origCallOk
```

`local=2147483647` 且 `reporting` 是真实值 → 破解生效、上报未泄露。

---

## 5. 仍未解决的话需要什么信息

1. 具体在哪个界面报错（系统安装器 / 文件管理器 / MT管理器 / adb）；
2. 报错时手机上是否装着官方版墨墨；
3. 手机上该文件的字节数与 SHA256；
4. 弹窗截图 + `adb logcat -b all -d | findstr /i "PackageInstaller PackageManager installd"`。
