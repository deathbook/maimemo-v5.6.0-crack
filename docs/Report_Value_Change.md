# 上报值调整：真实值 → 固定 1

## 改了什么

原设计（v1.0 ~ v1.3）的「表里不一」是：进入上报构造函数时，`a.s()` / `x1d.f()` / `dma.a()` **回落服务端真实值**
（实测 5012），出栈恢复无限。现在改成**上报路径固定返回 1**。

| | 本地路径 | 上报路径（`ada.b()` / `s40.m()` / `gq2.m()` 内部） |
|---|---|---|
| 改之前 | `2147483647` | 服务端真实值（5012） |
| **改之后** | `2147483647` | **`1`** |

涉及的三个 hook：`com.maimemo.android.momo.a.s()`、`x1d.f(boolean)`、`dma.a(int,String,String)`。
`gq2.c()`（欠债数）**保持原语义**：本地上报都为 0 / 上报路径不干预。

## 两条路线怎么实现的

**Frida 独立包**（`frida/entry_crack.js`）

```js
var REPORT_REAL  = false;   // true = 回落真实值
var REPORT_VALUE = 1;       // 上报路径返回的固定值

A.s.implementation = function () {
    if (STEALTH && inReporting()) {
        if (!REPORT_REAL) { return REPORT_VALUE; }
        ...
    }
    return LIMIT;
};
```

`REPORT_REAL` 保留着，想切回旧行为改一个布尔即可。

**LSPosed 模块**（`UnlimitedHook.smali`）改成携带两个参数：

```
UnlimitedHook(value, reportValue)
    reportValue == 0x7FFFFFFE (SENTINEL) → 上报路径不干预，原实现照常跑
```

调用点：

| 目标 | 构造参数 | 语义 |
|---|---|---|
| `a.s()` / `x1d.f()` / `dma.a()` | `(0x7FFFFFFF, 1)` | 本地无限 / 上报 1 |
| `gq2.c()` | `(0, 0x7FFFFFFE)` | 本地 0 / 上报不干预 |
| `LevelPrivilege.a()` | `(0, 0)` | 恒为 0 |
| `xfb.h()` | `(999, 999)` | 恒为 999 |

## 真机验证

Xiaomi 23116PN5BC / Android 16 / 无 root：

```
I MoMoCrack: [OK] hook a.s()  => 2147483647（上报路径固定返回 1）
I MoMoCrack: [OK] hook dma.a(int,String,String)  => 2147483647（上报路径固定返回 1）
I MoMoCrack: [OK] hook x1d.f(boolean)  => 2147483647（上报路径固定返回 1）
I MoMoCrack: [OK] hook LevelPrivilege.a()  => 0（特权等级要求清零）
I MoMoCrack: [OK] hook xfb.h()  => 999（用户等级拉满）
I MoMoCrack: xfb.h() 原始用户等级 = 7（已改为 999）
I MoMoCrack: SELFTEST ok local=2147483647 reporting=1 stealth=true origCallOk
```

`reporting=1` —— 上报路径确实不再返回 5012；本地仍是 2147483647；等级解锁不受影响。

## 需要知道的风险（诚实说明）

这一改动**削弱了原本的反检测逻辑**：

* 服务端自己知道这个账号的上限是 5012。客户端上报 `wordLimit = 1`、`availableWordLimit = 1`、
  `max_voc_count = 1`，与账号真实状态不符 —— **「报了一个服务端已知不对的数」本身就是异常信号**，
  严格说比上报真实值更容易被风控标记。
* 旧方案（上报真实值）的逻辑是：上报链路完全不泄露破解痕迹，服务端看到的一切都正常。
* 如果目的是"让服务端以为这是个小号/新号"，那 1 这个值还需要配合其它字段（`learned_voc_count`
  仍是真实的 5012，会出现"已学 5012 > 上限 1"的明显矛盾）才能自洽。

想切回旧行为：Frida 侧把 `REPORT_REAL` 改成 `true`；模块侧把三个 hook 的 `reportValue` 换成
`0x7FFFFFFE`（哨兵）即可。
