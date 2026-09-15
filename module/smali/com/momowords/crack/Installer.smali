.class public Lcom/momowords/crack/Installer;
.super Ljava/lang/Object;
.implements Ljava/lang/Runnable;
.source "Installer.java"


# 装 hook 的时机问题：
#   handleLoadPackage 在 Application 创建之前就跑，而梆梆 SecNeo 是**那时之后**才把业务 dex
#   解密加载进来的 —— 所以第一秒 findClass 一定失败。
# 做法：丢一个守护线程，每 400ms 探一次 com.maimemo.android.momo.a，最多探 150 次（约 60s），
#   探到了再一次性装全部 hook。

.field private final loader:Ljava/lang/ClassLoader;


.method public constructor <init>(Ljava/lang/ClassLoader;)V
    .locals 0

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    iput-object p1, p0, Lcom/momowords/crack/Installer;->loader:Ljava/lang/ClassLoader;

    return-void
.end method


.method private install()V
    .locals 8

    iget-object v7, p0, Lcom/momowords/crack/Installer;->loader:Ljava/lang/ClassLoader;

    :try_start
    # ---- 1) com.maimemo.android.momo.a.s()  ->  0x7FFFFFFF（单词上限）----
    new-instance v0, Lcom/momowords/crack/UnlimitedHook;

    const v1, 0x7fffffff

    const v2, 0x7ffffffe

    invoke-direct {v0, v1, v2}, Lcom/momowords/crack/UnlimitedHook;-><init>(II)V

    const/4 v1, 0x1

    new-array v1, v1, [Ljava/lang/Object;

    const/4 v2, 0x0

    aput-object v0, v1, v2

    const-string v2, "com.maimemo.android.momo.a"

    const-string v3, "s"

    invoke-static {v2, v7, v3, v1}, Lde/robv/android/xposed/XposedHelpers;->findAndHookMethod(Ljava/lang/String;Ljava/lang/ClassLoader;Ljava/lang/String;[Ljava/lang/Object;)Lde/robv/android/xposed/XC_MethodHook$Unhook;

    # ---- 2) dma.a(int, String, String)  ->  0x7FFFFFFF（本地 inf_words_limit 解密）----
    new-instance v0, Lcom/momowords/crack/UnlimitedHook;

    const v1, 0x7fffffff

    const v2, 0x7ffffffe

    invoke-direct {v0, v1, v2}, Lcom/momowords/crack/UnlimitedHook;-><init>(II)V

    const/4 v1, 0x4

    new-array v1, v1, [Ljava/lang/Object;

    const/4 v2, 0x0

    sget-object v3, Ljava/lang/Integer;->TYPE:Ljava/lang/Class;

    aput-object v3, v1, v2

    const/4 v2, 0x1

    const-class v3, Ljava/lang/String;

    aput-object v3, v1, v2

    const/4 v2, 0x2

    const-class v3, Ljava/lang/String;

    aput-object v3, v1, v2

    const/4 v2, 0x3

    aput-object v0, v1, v2

    const-string v2, "dma"

    const-string v3, "a"

    invoke-static {v2, v7, v3, v1}, Lde/robv/android/xposed/XposedHelpers;->findAndHookMethod(Ljava/lang/String;Ljava/lang/ClassLoader;Ljava/lang/String;[Ljava/lang/Object;)Lde/robv/android/xposed/XC_MethodHook$Unhook;

    # ---- 3) x1d.f(boolean)  ->  0x7FFFFFFF（可用单词上限）----
    new-instance v0, Lcom/momowords/crack/UnlimitedHook;

    const v1, 0x7fffffff

    const v2, 0x7ffffffe

    invoke-direct {v0, v1, v2}, Lcom/momowords/crack/UnlimitedHook;-><init>(II)V

    const/4 v1, 0x2

    new-array v1, v1, [Ljava/lang/Object;

    const/4 v2, 0x0

    sget-object v3, Ljava/lang/Boolean;->TYPE:Ljava/lang/Class;

    aput-object v3, v1, v2

    const/4 v2, 0x1

    aput-object v0, v1, v2

    const-string v2, "x1d"

    const-string v3, "f"

    invoke-static {v2, v7, v3, v1}, Lde/robv/android/xposed/XposedHelpers;->findAndHookMethod(Ljava/lang/String;Ljava/lang/ClassLoader;Ljava/lang/String;[Ljava/lang/Object;)Lde/robv/android/xposed/XC_MethodHook$Unhook;

    # ---- 4) gq2.c()  ->  0（欠债数）；上报路径不干预，让原实现跑 ----
    new-instance v0, Lcom/momowords/crack/UnlimitedHook;

    const/4 v1, 0x0

    const v2, 0x7ffffffe

    invoke-direct {v0, v1, v2}, Lcom/momowords/crack/UnlimitedHook;-><init>(II)V

    const/4 v1, 0x1

    new-array v1, v1, [Ljava/lang/Object;

    const/4 v2, 0x0

    aput-object v0, v1, v2

    const-string v2, "gq2"

    const-string v3, "c"

    invoke-static {v2, v7, v3, v1}, Lde/robv/android/xposed/XposedHelpers;->findAndHookMethod(Ljava/lang/String;Ljava/lang/ClassLoader;Ljava/lang/String;[Ljava/lang/Object;)Lde/robv/android/xposed/XC_MethodHook$Unhook;

    # ---- 5) 上报「已学词数」-> 1：cq2 构造函数的第 2 个入参 ----
    #   s40.m() 里 new cq2(time, phd.d().a.G0(), a.s(), phd.d().a.c1())
    #     入参0 = learned_voc_count  ← 改成 1
    #     入参1 = max_voc_count      ← 不动，仍是 a.s() 回落的真实值
    new-instance v0, Lcom/momowords/crack/ArgHook;

    const/4 v1, 0x1

    const/4 v2, 0x1

    invoke-direct {v0, v1, v2}, Lcom/momowords/crack/ArgHook;-><init>(II)V

    const/4 v1, 0x5

    new-array v1, v1, [Ljava/lang/Object;

    const/4 v2, 0x0

    const-class v3, Ljava/util/Date;

    aput-object v3, v1, v2

    const/4 v2, 0x1

    sget-object v3, Ljava/lang/Integer;->TYPE:Ljava/lang/Class;

    aput-object v3, v1, v2

    const/4 v2, 0x2

    sget-object v3, Ljava/lang/Integer;->TYPE:Ljava/lang/Class;

    aput-object v3, v1, v2

    const/4 v2, 0x3

    sget-object v3, Ljava/lang/Integer;->TYPE:Ljava/lang/Class;

    aput-object v3, v1, v2

    const/4 v2, 0x4

    aput-object v0, v1, v2

    const-string v2, "cq2"

    const-string v3, "<init>"

    invoke-static {v2, v7, v3, v1}, Lde/robv/android/xposed/XposedHelpers;->findAndHookMethod(Ljava/lang/String;Ljava/lang/ClassLoader;Ljava/lang/String;[Ljava/lang/Object;)Lde/robv/android/xposed/XC_MethodHook$Unhook;

    # ---- 6) 等级特权解锁：特权要求的等级 -> 0 ----
    #   门控在 com.maimemo.android.momo.user.level.a：
    #       boolean z9 = xfb.f.h() >= levelPrivilege.getLevel();
    #       if (!z9) disableReasons.add(DisableReason.LevelNotReached);   // ←「等级限制」
    #   注意等级 getter 在 dex 里叫 a()（jadx 把它重命名成了 getLevel）
    new-instance v0, Lcom/momowords/crack/UnlimitedHook;

    const/4 v1, 0x0

    const/4 v2, 0x0

    invoke-direct {v0, v1, v2}, Lcom/momowords/crack/UnlimitedHook;-><init>(II)V

    const/4 v1, 0x1

    new-array v1, v1, [Ljava/lang/Object;

    const/4 v2, 0x0

    aput-object v0, v1, v2

    const-string v2, "com.maimemo.android.momo.user.level.LevelPrivilege"

    const-string v3, "a"

    invoke-static {v2, v7, v3, v1}, Lde/robv/android/xposed/XposedHelpers;->findAndHookMethod(Ljava/lang/String;Ljava/lang/ClassLoader;Ljava/lang/String;[Ljava/lang/Object;)Lde/robv/android/xposed/XC_MethodHook$Unhook;

    # ---- 6) 用户等级拉满（999），双保险 ----
    new-instance v0, Lcom/momowords/crack/UnlimitedHook;

    const/16 v1, 0x3e7

    const/16 v2, 0x3e7

    invoke-direct {v0, v1, v2}, Lcom/momowords/crack/UnlimitedHook;-><init>(II)V

    const/4 v1, 0x1

    new-array v1, v1, [Ljava/lang/Object;

    const/4 v2, 0x0

    aput-object v0, v1, v2

    const-string v2, "xfb"

    const-string v3, "h"

    invoke-static {v2, v7, v3, v1}, Lde/robv/android/xposed/XposedHelpers;->findAndHookMethod(Ljava/lang/String;Ljava/lang/ClassLoader;Ljava/lang/String;[Ljava/lang/Object;)Lde/robv/android/xposed/XC_MethodHook$Unhook;

    # ---- 7) 上报构造函数：ada.b() / s40.m() / gq2.m() ----
    # 用 hookAllMethods 而不是 findAndHookMethod —— 这三个方法的重载签名我们没逐个确认过，
    # 按名字全hook 更稳，而包装只是置/清一个线程级标志，多包一个无害。
    const-string v1, "ada"

    invoke-static {v1, v7}, Lde/robv/android/xposed/XposedHelpers;->findClassIfExists(Ljava/lang/String;Ljava/lang/ClassLoader;)Ljava/lang/Class;

    move-result-object v1

    if-eqz v1, :skip_ada

    const-string v2, "b"

    new-instance v3, Lcom/momowords/crack/StudyLogHook;

    const/4 v4, 0x1

    invoke-direct {v3, v4}, Lcom/momowords/crack/StudyLogHook;-><init>(I)V

    invoke-static {v1, v2, v3}, Lde/robv/android/xposed/XposedBridge;->hookAllMethods(Ljava/lang/Class;Ljava/lang/String;Lde/robv/android/xposed/XC_MethodHook;)Ljava/util/Set;

    :skip_ada
    const-string v1, "s40"

    invoke-static {v1, v7}, Lde/robv/android/xposed/XposedHelpers;->findClassIfExists(Ljava/lang/String;Ljava/lang/ClassLoader;)Ljava/lang/Class;

    move-result-object v1

    if-eqz v1, :skip_s40

    const-string v2, "m"

    new-instance v3, Lcom/momowords/crack/ReportHook;

    invoke-direct {v3}, Lcom/momowords/crack/ReportHook;-><init>()V

    invoke-static {v1, v2, v3}, Lde/robv/android/xposed/XposedBridge;->hookAllMethods(Ljava/lang/Class;Ljava/lang/String;Lde/robv/android/xposed/XC_MethodHook;)Ljava/util/Set;

    :skip_s40
    const-string v1, "gq2"

    invoke-static {v1, v7}, Lde/robv/android/xposed/XposedHelpers;->findClassIfExists(Ljava/lang/String;Ljava/lang/ClassLoader;)Ljava/lang/Class;

    move-result-object v1

    if-eqz v1, :skip_gq2m

    const-string v2, "m"

    new-instance v3, Lcom/momowords/crack/ReportHook;

    invoke-direct {v3}, Lcom/momowords/crack/ReportHook;-><init>()V

    invoke-static {v1, v2, v3}, Lde/robv/android/xposed/XposedBridge;->hookAllMethods(Ljava/lang/Class;Ljava/lang/String;Lde/robv/android/xposed/XC_MethodHook;)Ljava/util/Set;

    :skip_gq2m
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :caught

    return-void

    :caught
    move-exception v0

    return-void
.end method


.method public run()V
    .locals 4

    const/4 v0, 0x0

    :loop
    const/16 v1, 0x96

    if-lt v0, v1, :giveup

    const-string v1, "com.maimemo.android.momo.a"

    iget-object v2, p0, Lcom/momowords/crack/Installer;->loader:Ljava/lang/ClassLoader;

    invoke-static {v1, v2}, Lde/robv/android/xposed/XposedHelpers;->findClassIfExists(Ljava/lang/String;Ljava/lang/ClassLoader;)Ljava/lang/Class;

    move-result-object v1

    if-eqz v1, :ready

    add-int/lit8 v0, v0, 0x1

    const-wide/16 v1, 0x190

    :try_start
    invoke-static {v1, v2}, Ljava/lang/Thread;->sleep(J)V
    :try_end
    .catch Ljava/lang/InterruptedException; {:try_start .. :try_end} :caught

    goto :loop

    :caught
    move-exception v1

    goto :loop

    :ready
    invoke-direct {p0}, Lcom/momowords/crack/Installer;->install()V

    :giveup
    return-void
.end method
