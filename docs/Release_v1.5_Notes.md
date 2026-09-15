# v1.5 —— 已学词数上报为 1（上限保持真实值）

> **修正 v1.4 的错误实现。** v1.4 误把**单词上限**改成了 1 —— 正确需求是
> **「已学词数」上报成 1，上限不动、仍用服务端真实值**。v1.4 已作废删除。

---

## 改了什么

| 字段 | 本地路径 | 上报路径 |
|---|---|---|
| 单词上限 `wordLimit` / `max_voc_count` | `2147483647` | **服务端真实值（5012）** ← 与 v1.3 一致 |
| 可用单词上限 `availableWordLimit` | `2147483647` | 真实值 |
| **已学词数 `total_learned_voc_count` / `learned_voc_count`** | 真实值 | **`1`** ← 本次新增 |

## 两条通道怎么改的

**通道 1 `/misc/system/check`（`debt_report_data`）**

```java
// defpackage/s40.java:47
new cq2(aza.q(), phd.d().a.G0(), a.s(), phd.d().a.c1())
//              ↑learned_voc_count  ↑max_voc_count
```

hook `cq2(Date,int,int,int)` 构造函数，**只替换第 2 个入参**；上限入参原样透传
（上报期间 `a.s()` 回落成真实值 5012）。

**通道 2 `/log/study_log`（`StudyLogRequest`）**

`ada.b()` 的包装里加 fixup：原实现返回后把 `req.lsrCount` 改成 1。
（`lsrCount` 是 dex 真实字段名，`@wl9("total_learned_voc_count")`。）

> 不在 `W0()` / `G0()` 上 hook 的原因：它们挂在 `dda` 内部的 `r05` **接口代理**上，
> 静态拿不到具体实现类。

## 真机验证

```
I MoMoCrack: [OK] hook a.s()  => 2147483647（上报路径回落服务端真实值）
I MoMoCrack: [OK] hook cq2(Date,int,int,int)  => 上报时 learned_voc_count=1
I MoMoCrack: cq2 原始 learned_voc_count = 798（上报改为 1，上限保持 5012）
I MoMoCrack: SELFTEST ok local=2147483647 reporting=5012 stealth=true origCallOk
```

真实已学 798 / 真实上限 5012：上报时已学 → 1，上限 5012 原样带上，本地仍是无限。

## 附件

| 文件 | 说明 |
|---|---|
| `maimemo_v5.6.0_cracked_standalone.apk` | 无 root 独立包（先卸载官方版，签名不同） |
| `momocrack-module.apk` | LSPosed 模块，官方 APK 原封不动 |
| `unpacked_dex.zip` / `native_libs.zip` | 脱壳 dex 与 native 库 |

细节与实现对照见 `docs/Report_Value_Change.md`。
