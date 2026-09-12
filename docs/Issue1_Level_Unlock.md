# Issue #1：等级限制解除

> Issue：<https://github.com/deathbook/maimemo-v5.6.0-crack/issues/1> ——「等级限制有解除吗」
> 结论：**已解除**，两条交付路线都已更新（无 root 独立包 + LSPosed 模块）。

---

## 1. 等级限制在哪

墨墨背单词除了「单词上限」，还有一套**用户等级特权**系统：每个特权有一个**要求的用户等级**，
没达到就不给用，UI 上标「解锁」。

相关资源串：

```
level_detail                        "等级详情"
user_info_card_level                "等级"
next_user_level_privilege_unlock    "解锁"
privilege_name_exceed_limit         "%s数量已达上限"
```

数据模型：

| 位置 | 含义 |
|---|---|
| `UserInfo.level` ← `inf_level`（`@SyncIgnored`） | 用户等级（**不上传服务器**） |
| `UserInfo.levelBuff` ← `inf_level_buff` | 等级加成 |
| `defpackage.xfb`（`f` 是单例） | 本地设置：`user_level` / `user_last_level` / `user_level_buff` / `level_buff_config` |
| `defpackage.qfb` = `UserLevelPrivilege` | `level` / `conditionText` / `privilegeText` / `privileges` |
| `LevelPrivilege` | `code` / `name` / `description` / `limits` / `links` / `prompts` / `level` / `enable` / `disableReasons` |
| `LevelPrivilege.DisableReason` | `LevelNotReached` / `InDebt` |
| `defpackage.h46` = `LevelConfig` | `id` / `userLevelPrivileges` / `updatedTime` |

`LevelPrivilege.level` 是从服务端下发的 `limits` 里 `field == "user.level"` 那条解析出来的
（见 `LevelPrivilege.w()`），也就是**这个特权要求的用户等级**。

## 2. 门控代码

`com/maimemo/android/momo/user/level/a.java`（生成特权列表的地方）：

```java
for (LevelPrivilege levelPrivilege2 : arrayList2) {
    boolean z9 = xfb.f.h() >= levelPrivilege2.getLevel();     // ← 等级判定
    ...
    if (z9 && z3) {
        levelPrivilege2.u(true);      // enable = true
        levelPrivilege2.t(null);      // disableReasons = null
    } else {
        levelPrivilege2.u(false);     // enable = false
        q76 q76VarF = hv1.f();
        if (!z9) q76VarF.add(LevelPrivilege.DisableReason.LevelNotReached);   // ←「等级限制」
        if (!z3) q76VarF.add(LevelPrivilege.DisableReason.InDebt);
        levelPrivilege2.t(hv1.c(q76VarF));
    }
}
```

* `xfb.f.h()` = 用户等级
* `levelPrivilege2.getLevel()` = 该特权要求的等级（dex 里的方法名其实是 **`a()`**，jadx 重命名成了 `getLevel`）
* `z3` 是欠债相关（`gq2.h()`），我们的 `gq2.c() = 0` + 单词上限无限后它天然为 false → `z3 = true`

所以只要让 **`999 >= 0`** 恒成立，就不会再有 `LevelNotReached`，所有特权 `enable = true`。

## 3. 怎么解的

两条路线都加了同一对 hook：

| 目标 | 改成 | 作用 |
|---|---|---|
| `com.maimemo.android.momo.user.level.LevelPrivilege.a()` | `0` | 特权要求的等级清零 → 判定必然通过 |
| `xfb.h()` | `999` | 用户等级拉满（兜住其它直接用等级做比较的地方） |

**故意的取舍**：没有去 hook `LevelPrivilege.u(boolean)` / `t(...)` 那两个 setter 强制 enable，
因为那只骗过列表里的显示，管不住别处独立做的等级判断；直接改「等级」这个输入更彻底。

**不需要反检测**：`inf_level` 带 `@SyncIgnored`，等级不会随上报链路回传服务器；
而且改的是本地设置值（`xfb` 的 `user_level`），不写数据库、不写 `inf_tb`。

## 4. 真机证据

Xiaomi 23116PN5BC / Android 16 / 无 root，安装更新后的独立包：

```
I MoMoCrack: [OK] hook a.s()  => 2147483647（仅上报路径回落真实值）
I MoMoCrack: [OK] hook LevelPrivilege.a()  => 0（特权等级要求清零）
I MoMoCrack: [OK] hook xfb.h()  => 999（用户等级拉满）
I MoMoCrack: xfb.h() 原始用户等级 = 7（已改为 999）
I MoMoCrack: SELFTEST ok local=2147483647 reporting=5012 stealth=true origCallOk
```

* `xfb.h()` 原始值 = **7**：既证明这个 getter 确实是用户等级（jadx 反编译成 `return 0` 是错的），
  也说明原账号是 Lv.7。
* `SELFTEST` 仍通过：等级解锁**没有影响单词上限与上报一致性**。

## 5. 复现

```bash
# 无 root 独立包（Releases）
adb install -r maimemo_v5.6.0_cracked_standalone.apk
adb logcat -s MoMoBoot:I MoMoCrack:I

# LSPosed 模块（module/）
adb install -r momocrack-module.apk   # 然后在 LSPosed 里勾选 + 勾作用域 + 强停重启
```
