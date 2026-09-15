# 上报调整：已学词数 → 1（上限保持服务端真实值）

> 本文档修正了 v1.4 的错误实现。v1.4 误把**上限**改成了 1；正确需求是
> **「已学」上报成 1，上限不动、仍用服务端真实值**。已在 v1.5 修正。

## 需求

| 字段 | 上报值 |
|---|---|
| 单词上限（`wordLimit` / `max_voc_count`） | **服务端真实值**（实测 5012），不动 |
| 可用单词上限（`availableWordLimit`） | 真实值，不动 |
| **已学词数（`total_learned_voc_count` / `learned_voc_count`）** | **`1`** |

本地路径（UI / 业务判定）一切照旧：上限 `2147483647`（无限），已学词数是真实值。

## 两条上报通道

### 通道 1：`/misc/system/check` → `debt_report_data`

```java
// defpackage/s40.java:47
cq2 cq2Var = new cq2(aza.q(), phd.d().a.G0(), a.s(), phd.d().a.c1());
//                  ↑time    ↑learned_voc_count  ↑max_voc_count  ↑day_new_limit
```

**做法**：hook `cq2` 的构造函数，**只改第 2 个入参**（index 1）。上限入参原样透传，
而它在 `inReporting()` 期间由 `a.s()` 回落成服务端真实值。

### 通道 2：`/log/study_log` → `StudyLogRequest`

```java
// defpackage/ada.java:95-97
studyLogManager$StudyLogRequest.wordLimit          = a.s();            // 上限，真实值
studyLogManager$StudyLogRequest.lsrCount           = phd.d().a.W0();   // ← 已学
studyLogManager$StudyLogRequest.availableWordLimit = x1d.f(false);
```

**做法**：`ada.b()` 原本已经被 `wrapReportBuilder` 包住（负责开关上报模式），
现在多传一个 `fixup`，在原实现返回后把结果对象的 `lsrCount` 字段改成 1。
（`lsrCount` 是 dex 里的真实字段名，`@wl9("total_learned_voc_count")`，jadx 没有重命名它。）

> 为什么不在 `W0()` / `G0()` 上做文章：这两个方法挂在 `dda` 内部的 `r05` **接口代理**上
> （`dda.a` 声明类型是接口），静态拿不到具体实现类；在结果对象上改字段更稳。

## 两条路线的实现

### Frida 独立包（`frida/entry_crack.js`）

```js
var REPORT_LEARNED = 1;   // 上报路径的「已学词数」固定值（上限不动）

// 通道1：cq2 构造函数的第 2 个入参
var cq2Ctor = Java.use('cq2').$init.overload('java.util.Date', 'int', 'int', 'int');
cq2Ctor.implementation = function (time, learned, maxVoc, dayNewLimit) {
    var use = (STEALTH && inReporting()) ? REPORT_LEARNED : learned;
    return this.$init(time, use, maxVoc, dayNewLimit);   // maxVoc 原样透传
};

// 通道2：ada.b() 包装的 fixup
req.lsrCount.value = REPORT_LEARNED;
```

上限相关的三个 hook（`a.s()` / `x1d.f()` / `dma.a()`）**恢复成 v1.3 的语义**：
上报路径回落服务端真实值，本地返回 2147483647。

### LSPosed 模块

| 类 | 作用 |
|---|---|
| `ArgHook(index, value)` | 上报模式时把第 index 个入参替换成 value（新增） |
| `StudyLogHook(learned)` | 包 `ada.b()`：进入置上报标志、退出清标志并改写结果里的 `lsrCount`（新增） |
| `UnlimitedHook(value, reportValue)` | `reportValue = 0x7FFFFFFE` 表示「上报路径不干预」 |

调用点：

```
a.s() / x1d.f() / dma.a()   UnlimitedHook(0x7FFFFFFF, 0x7FFFFFFE)   # 上报不干预 → 真实值
gq2.c()                     UnlimitedHook(0, 0x7FFFFFFE)
cq2.<init>(Date,int,int,int) ArgHook(1, 1)                          # 已学 → 1
ada.b()                     StudyLogHook(1)                         # 已学 → 1
LevelPrivilege.a()          UnlimitedHook(0, 0)
xfb.h()                     UnlimitedHook(999, 999)
```

## 真机验证

Xiaomi 23116PN5BC / Android 16 / 无 root：

```
I MoMoCrack: [OK] hook a.s()  => 2147483647（上报路径回落服务端真实值）
I MoMoCrack: [OK] hook x1d.f(boolean)  => 2147483647（上报路径回落服务端真实值）
I MoMoCrack: [OK] hook dma.a(int,String,String)  => 2147483647（上报路径回落服务端真实值）
I MoMoCrack: [OK] hook cq2(Date,int,int,int)  => 上报时 learned_voc_count=1
I MoMoCrack: cq2 原始 learned_voc_count = 798（上报改为 1，上限保持 5012）
I MoMoCrack: SELFTEST ok local=2147483647 reporting=5012 stealth=true origCallOk
```

* `cq2 原始 learned_voc_count = 798` —— 真实已学 **798**，真实上限 **5012**；
  上报时已学改成 1，上限 5012 原样带上。
* `SELFTEST ... reporting=5012` —— 上限的上报值仍是服务端真实值（v1.4 的错误已修正）。

> 通道 2（`ada.b()` 的 `lsrCount`）需要真实的学词行为触发上报才会打日志；
> 字段名已从 dex 确认（`lsrCount`，无重命名），逻辑与通道 1 对称。

## 副作用提示

上报 `learned=1` 而 `max_voc_count=5012` 时，服务端会看到一个
「只有 1 个已学词、却买了 5012 上限」的账号画像。这是这次改动的预期效果，
但它与账号的历史学习记录不一致，是否需要配合其它字段一起改由使用者判断。
