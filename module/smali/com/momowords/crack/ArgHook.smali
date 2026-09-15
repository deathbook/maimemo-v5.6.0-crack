.class public Lcom/momowords/crack/ArgHook;
.super Lde/robv/android/xposed/XC_MethodHook;
.source "ArgHook.java"


# 上报模式时把第 index 个入参替换成 value；其余情况完全不干预（原实现拿到的还是真实入参）。
#
# 用在 cq2 的构造上：s40.m() 里 new cq2(time, phd.d().a.G0(), a.s(), phd.d().a.c1())
#   第 1 个入参 = learned_voc_count  ← 改成 1
#   第 2 个入参 = max_voc_count      ← 不动，仍是 a.s() 回落的服务端真实值

.field private final index:I

.field private final value:I


.method public constructor <init>(II)V
    .locals 0

    invoke-direct {p0}, Lde/robv/android/xposed/XC_MethodHook;-><init>()V

    iput p1, p0, Lcom/momowords/crack/ArgHook;->index:I

    iput p2, p0, Lcom/momowords/crack/ArgHook;->value:I

    return-void
.end method


.method protected beforeHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .locals 3

    invoke-static {}, Lcom/momowords/crack/Stealth;->isReporting()Z

    move-result v0

    if-eqz v0, :done

    iget v0, p0, Lcom/momowords/crack/ArgHook;->value:I

    invoke-static {v0}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object v0

    iget-object v1, p1, Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;->args:[Ljava/lang/Object;

    iget v2, p0, Lcom/momowords/crack/ArgHook;->index:I

    aput-object v0, v1, v2

    :done
    return-void
.end method
