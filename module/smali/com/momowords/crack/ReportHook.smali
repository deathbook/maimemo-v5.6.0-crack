.class public Lcom/momowords/crack/ReportHook;
.super Lde/robv/android/xposed/XC_MethodHook;
.source "ReportHook.java"


# 包住「构造上报数据」的方法：进入时开启上报模式，退出时关掉。
# 期间 a.s() / x1d.f() / dma.a() 返回服务端真实值，于是上报出去的不是 2147483647。
#
# 按线程隔离（Stealth 内部用 ThreadLocal），所以后台同步线程与 UI 线程互不污染。
# afterHookedMethod 在方法抛异常时同样会被调用，标志不会漏清。


.method public constructor <init>()V
    .locals 0

    invoke-direct {p0}, Lde/robv/android/xposed/XC_MethodHook;-><init>()V

    return-void
.end method


.method protected beforeHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .locals 0

    invoke-static {}, Lcom/momowords/crack/Stealth;->enter()V

    return-void
.end method


.method protected afterHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .locals 0

    invoke-static {}, Lcom/momowords/crack/Stealth;->exit()V

    return-void
.end method
