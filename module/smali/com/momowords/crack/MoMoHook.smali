.class public Lcom/momowords/crack/MoMoHook;
.super Ljava/lang/Object;
.implements Lde/robv/android/xposed/IXposedHookLoadPackage;
.source "MoMoHook.java"


# Xposed / LSPosed 模块入口（由 assets/xposed_init 指定）。
# 只做一件事：确认进程是墨墨，然后把装 hook 的活丢给守护线程（见 Installer 的注释）。

.method public constructor <init>()V
    .locals 0

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method


.method public handleLoadPackage(Lde/robv/android/xposed/callbacks/XC_LoadPackage$LoadPackageParam;)V
    .locals 3

    const-string v0, "com.maimemo.android.momo"

    iget-object v1, p1, Lde/robv/android/xposed/callbacks/XC_LoadPackage$LoadPackageParam;->packageName:Ljava/lang/String;

    invoke-virtual {v0, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v0

    if-nez v0, :ret

    new-instance v0, Lcom/momowords/crack/Installer;

    iget-object v1, p1, Lde/robv/android/xposed/callbacks/XC_LoadPackage$LoadPackageParam;->classLoader:Ljava/lang/ClassLoader;

    invoke-direct {v0, v1}, Lcom/momowords/crack/Installer;-><init>(Ljava/lang/ClassLoader;)V

    new-instance v1, Ljava/lang/Thread;

    const-string v2, "MoMoCrack-Install"

    invoke-direct {v1, v0, v2}, Ljava/lang/Thread;-><init>(Ljava/lang/Runnable;Ljava/lang/String;)V

    const/4 v0, 0x1

    invoke-virtual {v1, v0}, Ljava/lang/Thread;->setDaemon(Z)V

    invoke-virtual {v1}, Ljava/lang/Thread;->start()V

    :ret
    return-void
.end method
