# v1.3 —— 等级限制解除（Issue #1）

> 回应：[issue #1「等级限制有解除吗」](https://github.com/deathbook/maimemo-v5.6.0-crack/issues/1)
> **已解除。** 无 root 独立包与 LSPosed 模块都已同步更新。

---

## 附件

| 文件 | 说明 |
|---|---|
| `maimemo_v5.6.0_cracked_standalone.apk` | 无 root 独立包，`adb install -r` 即生效（**必须先卸载官方版**，签名不同） |
| `momocrack-module.apk` | LSPosed 模块（12.7 KB），官方 APK 原封不动，需 root + LSPosed |
| `unpacked_dex.zip` / `native_libs.zip` | 脱壳 dex 与 native 库（与 v1.1 相同，未变动） |

## 这次新增：等级特权解锁

墨墨除了「单词上限」还有一套**等级特权**：每个特权带一个**要求的用户等级**，没达到就标「解锁」。
门控在 `com/maimemo/android/momo/user/level/a.java`：

```java
boolean z9 = xfb.f.h() >= levelPrivilege.getLevel();     // 用户等级 >= 特权要求等级
if (!z9) disableReasons.add(LevelPrivilege.DisableReason.LevelNotReached);   // ←「等级限制」
```

两条路线都加了同一对 hook：

| 目标 | 改成 | 说明 |
|---|---|---|
| `com.maimemo.android.momo.user.level.LevelPrivilege.a()` | `0` | 特权要求的等级清零（dex 里方法名是 `a`，jadx 重命名成了 `getLevel`） |
| `xfb.h()` | `999` | 用户等级拉满，兜住其它直接用等级比较的地方 |

两个操作数都被强制通过（`999 >= 0`），`LevelNotReached` 不会再产生，所有特权 `enable = true`。

**不需要反检测**：`inf_level` 带 `@SyncIgnored`，等级不随上报链路回传服务器；改的是本地设置值，
不写数据库、不碰 `inf_tb`。

## 真机验证（Xiaomi 23116PN5BC / Android 16 / 无 root）

```
I MoMoCrack: [OK] hook a.s()  => 2147483647（仅上报路径回落真实值）
I MoMoCrack: [OK] hook LevelPrivilege.a()  => 0（特权等级要求清零）
I MoMoCrack: [OK] hook xfb.h()  => 999（用户等级拉满）
I MoMoCrack: xfb.h() 原始用户等级 = 7（已改为 999）
I MoMoCrack: SELFTEST ok local=2147483647 reporting=5012 stealth=true origCallOk
```

* 原始等级 = **Lv.7** —— 既证明 `xfb.h()` 确实是用户等级 getter（jadx 反编译成 `return 0` 是错的），
  也说明这是在真实账号上测的。
* `SELFTEST` 仍通过：等级解锁**没有影响单词上限与上报一致性**。

## 完整能力一览

| 功能 | 独立包 | LSPosed 模块 |
|---|---|---|
| 单词上限 → 无限 | ✅ | ✅ |
| 上报仍为服务端真实值（反封号） | ✅ | ✅ |
| 欠债数 → 0 | ✅ | ✅ |
| **等级特权解锁（本次）** | ✅ | ✅ |
| 需要 root | ❌ | ✅ |
| 需要重打包/卸载官方版 | ✅ | ❌ |
| 按键延迟 | 有地板 | 接近官方 |

详细分析：<https://github.com/deathbook/maimemo-v5.6.0-crack/blob/main/docs/Issue1_Level_Unlock.md>
