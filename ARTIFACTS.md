# 墨墨背单词 v5.6.0 破解 —— 二进制产物

> 逆向工程课程（deathbook/Crack Lesson1）作业附件，**仅供教学与评审**。
> 样本来源：`https://cdn-by.maimemo.com/apk/maimemo_v5.6.00_900_1788339161.apk`
> （`com.maimemo.android.momo`，123,994,114 B，SHA256 `A2801079285173FB1ECB58E66ADEA70A6A18225F0F8BFD79180048C426D2D06D`）

---

## 1. `maimemo_v5.6.0_cracked_standalone.apk` （134 MB）

**重打包并签名的破解包，普通安装即生效**（无需 root、无需 frida-server、无需 LSPosed）。

* 基于原版 APK 重打包：**没有改动 `lib/` 里任何一个字节**（壳会校验该目录，改了就自毁）
* 注入点：`META-INF/native/libmomoco.so` = `libmmboot.so`(17 KB) + `frida-gadget`(25 MB) + `crack.js`，
  由 `BaseAppContext.<clinit>` 的 classpath 分支解到 App cache 目录后 `System.load()`
* 签名：Android Debug（SHA256 `1e08a903aef9c3a721510b64ec764d01d3d094eb954161b62544ea8f187b5953`）
* 安装：`adb install -r maimemo_v5.6.0_cracked_standalone.apk`
* 运行日志：`adb logcat -s MoMoBoot:I MoMoCrack:I`

**效果**：本地 `a.s()` / `x1d.f(false)` / `r47.getAvailableWordLimit()` = `2147483647`（无限）；
上报给服务器的仍是服务端真实值（实测 `5012`），服务端看不到异常。

---

## 2. `unpacked_dex.zip` （14 MB）

从内存里 dump 出来的业务 dex（hook `libdexfile.so` 的 `DexFileLoader::OpenCommon`）：

| 文件 | 大小 | 说明 |
|---|---|---|
| `dex_0000_shell_anchor.dex` | 449,800 B | 壳自身的锚点 dex |
| `dex_0006_business.dex` | 21,244,668 B | 业务 dex |
| `dex_0007_business.dex` | 21,741,764 B | 业务 dex（含 `com.maimemo.android.momo.a`） |
| `dex_0008_business.dex` | 19,293,276 B | 业务 dex |
| `dex_0009_business.dex` | 6,648,132 B | 业务 dex（含 `BaseAppContext` / SQLite loader） |
| `dex_0007_patched_a.s_returns_2147483647.dex` | 21,741,764 B | **手工字节级补丁后的 dex**：`a.s()` 改为 `const v0, 0x7fffffff; return v0` |

合计 31,086 个类，jadx 可出 25,014 个源文件。

---

## 3. `native_libs.zip` （16 MB）

```
original/lib/arm64-v8a/     从原版 APK 解出
    libDexHelper.so         1,299,802 B   梆梆 SecNeo 壳
    libdexjni.so            4,483,997 B   Fort andjni 方法抽取（1018 个类的函数体是 nop 桩）
    libmomoco.so               42,240 B   被独立包顶替的那个
    libmmsqlite.so          2,051,144 B
    libmmsqlcipher.so       2,211,696 B
    libmmftsext.so            341,592 B
patched/
    libdexjni.arm64.patched.so  4,483,997 B   我们的 ELF 补丁实验产物
    libmomoco.patched.so           43,656 B   DT_NEEDED 注入后的 libmomoco
payload/
    libmomoco.so           25,697,416 B   独立包真正落地的文件（libmmboot + gadget + js + footer）
    libmmboot.so               17,512 B   自解包引导层（源码 native/loader.c）
    stubs/lib{c,dl,log}.so      2,8xx B    仅用于往 DT_NEEDED 塞名字的空 stub
```

---

## 4. 校验

```
e4932416c24e7fa382a3062331eecd19cd6b11e217f776f8bf6d0b4071bdfeb6  maimemo_v5.6.0_cracked_standalone.apk
7f8651c800392895d34fc91da6b0476d429e23351752c4cd9b211b0743df1c7e  unpacked_dex.zip
86fcbb4ba59b752de5d8d76075dde026f56112274b4accb6c1b3c9f1f65bbf20  native_libs.zip
```

---

## 5. 复现

```powershell
python scripts/build_standalone.py          # 组装 payload + 重打包（需要 zig：pip install ziglang）
java -jar tools/uber-apk-signer.jar -a build/standalone/*_unsigned.apk -o signed
python scripts/verify_standalone.py <序列号>  # 一键真机断言
```

完整分析见仓库 `docs/Lesson1_Writeup.md` 与 `docs/Lesson1_Noroot_Standalone.md`。
