.class public Lcom/momowords/crack/StudyLogHook;
.super Lde/robv/android/xposed/XC_MethodHook;
.source "StudyLogHook.java"


# 包住 ada.b()（构造 /log/study_log 的 StudyLogRequest）：
#   进入 → 开启上报模式（期间 a.s()/x1d.f()/dma.a() 回落服务端真实值）
#   退出 → 关掉上报模式，并把结果里的「已学词数」改成 learned
#
# 为什么要改字段：ada.b() 里是
#       req.wordLimit          = a.s();            ← 上限，保持真实值
#       req.lsrCount           = phd.d().a.W0();   ← 已学（@wl9("total_learned_voc_count")）
#       req.availableWordLimit = x1d.f(false);
# W0() 挂在一个 r05 接口实现上，静态拿不到具体类，所以在结果对象上直接改字段更稳。

.field private final learned:I


.method public constructor <init>(I)V
    .locals 0

    invoke-direct {p0}, Lde/robv/android/xposed/XC_MethodHook;-><init>()V

    iput p1, p0, Lcom/momowords/crack/StudyLogHook;->learned:I

    return-void
.end method


.method protected beforeHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .locals 0

    invoke-static {}, Lcom/momowords/crack/Stealth;->enter()V

    return-void
.end method


.method protected afterHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .locals 4

    invoke-static {}, Lcom/momowords/crack/Stealth;->exit()V

    :try_start
    iget-object v0, p1, Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;->result:Ljava/lang/Object;

    if-nez v0, :done

    invoke-virtual {v0}, Ljava/lang/Object;->getClass()Ljava/lang/Class;

    move-result-object v1

    const-string v2, "lsrCount"

    invoke-static {v1, v2}, Lde/robv/android/xposed/XposedHelpers;->findField(Ljava/lang/Class;Ljava/lang/String;)Ljava/lang/reflect/Field;

    move-result-object v1

    iget v2, p0, Lcom/momowords/crack/StudyLogHook;->learned:I

    invoke-static {v2}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object v2

    invoke-virtual {v1, v0, v2}, Ljava/lang/reflect/Field;->set(Ljava/lang/Object;Ljava/lang/Object;)V
    :try_end
    .catch Ljava/lang/Throwable; {:try_start .. :try_end} :caught

    :done
    return-void

    :caught
    move-exception v0

    return-void
.end method
