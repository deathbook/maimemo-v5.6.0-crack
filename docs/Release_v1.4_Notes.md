# v1.4 —— 上报值改为固定 1

> 承接 [issue #1](https://github.com/deathbook/maimemo-v5.6.0-crack/issues/1) 的后续调整。

---

## 变更

上报路径的单词上限返回值从**服务端真实值**（实测 5012）改成**固定 `1`**。

| | 本地路径 | 上报路径 |
|---|---|---|
| v1.3 及以前 | `2147483647` | 服务端真实值（5012） |
| **v1.4** | `2147483647` | **`1`** |

涉及 `a.s()` / `x1d.f(boolean)` / `dma.a(int,String,String)` 三个 hook；
`gq2.c()`（欠债数）语义不变。

**两条路线同步更新**：

* Frida 独立包：新增开关 `REPORT_REAL = false` + `REPORT_VALUE = 1`（改回旧行为只需把 `REPORT_REAL` 置 `true`）
* LSPosed 模块：`UnlimitedHook` 改为 `(value, reportValue)` 双参数，`reportValue = 0x7FFFFFFE` 作哨兵表示"上报不干预"

## 真机验证

```
I MoMoCrack: [OK] hook a.s()  => 2147483647（上报路径固定返回 1）
I MoMoCrack: [OK] hook x1d.f(boolean)  => 2147483647（上报路径固定返回 1）
I MoMoCrack: [OK] hook LevelPrivilege.a()  => 0（特权等级要求清零）
I MoMoCrack: [OK] hook xfb.h()  => 999（用户等级拉满）
I MoMoCrack: xfb.h() 原始用户等级 = 7（已改为 999）
I MoMoCrack: SELFTEST ok local=2147483647 reporting=1 stealth=true origCallOk
```

## 附件

| 文件 | 说明 |
|---|---|
| `maimemo_v5.6.0_cracked_standalone.apk` | 无 root 独立包（先卸载官方版，签名不同） |
| `momocrack-module.apk` | LSPosed 模块，官方 APK 原封不动 |
| `unpacked_dex.zip` / `native_libs.zip` | 脱壳 dex 与 native 库 |

## ⚠️ 风险提示

这一改动**削弱了原来的反检测设计**：服务端知道该账号上限是 5012，客户端上报 `1` 属于
"报了服务端已知不对的数"，本身就是异常信号；且 `learned_voc_count` 仍是真实的 5012，
会出现"已学 5012 > 上限 1"的矛盾。旧方案（上报真实值）在这些维度上更安全。

要切回：Frida 侧 `REPORT_REAL = true`；模块侧把三个 hook 的 `reportValue` 传 `0x7FFFFFFE`。

细节见 `docs/Report_Value_Change.md`。
