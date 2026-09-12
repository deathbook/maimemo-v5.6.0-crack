# 性能问题：按键延迟的实测与结论

> 现象：破解包在 App 内按键/滑动有明显延迟。原始观测（Redmi Note 13 Pro / Android 16）：
> `Janky frames: 147 (2.80%)`、`Janky frames (legacy): 1721 (32.76%)`、`99th percentile: 450ms`。
> 同机对比：**空脚本版（只加载 gadget、不装 hook）约 327 ticks / 5s，带 hook 版约 471 ticks / 5s**。

---

## 1. 根因

不是某个 hook 被高频调用。原始计数（约 20 秒内）：

```
a.s()  11 次      x1d.f()  3 次      dma.a()  3 次
r47.getAvailableWordLimit()  0 次    gq2.c()  0 次     gq2.h()  118 次
```

调用次数这么低却掉了 44% 的性能，原因是 **Frida 建立 Java hook 后，被 hook 的方法与其所在类会退出
ART 的 AOT/JIT 优化路径**，并且相关调用要过 Frida 的 JS 桥。这是"在场成本"，不是"调用成本"。

---

## 2. 这一版做的减负（v3 脚本）

| 改动 | 依据 |
|---|---|
| Toast 默认全关（`ENABLE_TOAST=false`） | Toast 要在主线程 inflate + 跨进程发通知，本身就是 UI 抖动源 |
| 去掉 `send()` | script 交互模式下 gadget 只把它打到 stdout（= /dev/null），纯浪费一次 JSON 序列化 |
| **不再 hook `gq2.h()`** | 它是唯一的热点（20s/118 次）。而 `a.s()` 改成无限后欠债数天然为负，`h()` 自己就返回 false |
| 上报字段审计默认关闭（`AUDIT_REPORTS=false`） | 每次上报都要过 JS 桥读 2 个字段 |
| INFO 级日志默认不进 logcat | 降噪；日志本身也要过 JS 桥 + `__android_log_print` |

hook 数量从 9 个降到 8 个（其中热路径 hook 从 1 个降到 0 个）。

---

## 3. 实测（小米 23116PN5BC / Android 16，`scripts/bench_app.py`）

测量方法：`am start -W` 取冷启动；读 `/proc/<pid>/task/<pid>/stat` 的 `utime+stime` 取主线程 tick 增量；
`--interact` 模式在测量窗口内用 50 次 `input swipe` 制造 UI 负载。

| 版本 | 冷启动 | 主线程 ticks / 20s（空闲） | 主线程 ticks / 20s（50 次滑动） |
|---|---:|---:|---:|
| v2（已发布的初版） | 1318 ms | 801 | 未测 |
| **v3（本次精简）** | 1310 ms | 887 | 1608 |

**诚实结论：空闲状态两者没有可测差异（差异在噪声内）。** v2 的带负载对照尚未补齐，
所以本文档**不声称**精简带来了提升 —— 它只是把"白付的成本"去掉了。

---

## 4. 结论：Frida 路线有性能地板

只要还走 Frida gadget，就存在"在场成本"。把脚本减到只剩 `a.s()` 一个 hook 也仍然是 Frida。
要做到接近官方版的跟手程度，必须换 hook 机制：

| 方案 | 性能 | 是否需要重打包 | 是否需要 root |
|---|---|---|---|
| Frida gadget（当前，无 root 独立包） | 有地板 | 是（改 `META-INF/native/`） | **否** |
| **LSPosed 模块**（官方包不动） | 接近官方 | **否** | 是（需 LSPosed） |
| LSPatch 本地模式（模块内嵌） | 接近官方 | 是（改 Manifest + 加 dex） | 否 |

LSPosed/LSPatch 走的是 ART 层的 `ArtMethod` 替换，不进 JS 桥、不做全量插桩，所以代价低一个量级。

---

## 5. 复现

```bash
python scripts/bench_app.py <序列号> --wait 20 --interact
```

脚本会输出冷启动耗时、主线程/全进程 tick 增量，以及当次 `MoMoBoot` / `MoMoCrack` 日志。
