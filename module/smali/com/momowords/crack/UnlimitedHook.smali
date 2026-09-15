.class public Lcom/momowords/crack/UnlimitedHook;
.super Lde/robv/android/xposed/XC_MethodHook;
.source "UnlimitedHook.java"


# 把目标方法的返回值改成常数。两个场景分开：
#
#   value       正常路径（本地 UI / 业务判定）返回值
#   reportValue 上报路径（Stealth.isReporting() == true）返回值
#
# reportValue 取 SENTINEL(0x7FFFFFFE) 表示「上报路径不干预」—— 直接 return，让原实现照常跑。
# 构造时按需传：
#   单词上限类   UnlimitedHook(0x7FFFFFFF, 1)     本地无限 / 上报固定 1
#   欠债数       UnlimitedHook(0, 0x7FFFFFFE)     本地 0 / 上报不干预
#   特权等级要求 UnlimitedHook(0, 0)              恒为 0（等级不上报，无需区分）
#   用户等级     UnlimitedHook(999, 999)          恒为 999
#
# 关键：**正常路径根本不执行原实现** —— beforeHookedMethod 里 setResult 就会跳过原方法。
# 这一点是必须的：a.s() 走 JNI 会去开 SQLite，数据库没建立时它会抛
# SQLiteCantOpenDatabaseException，如果先调原实现，异常会从 hook 里冒出去，UI 拿不到无限值。

.field private final value:I

.field private final reportValue:I


.method public constructor <init>(II)V
    .locals 0

    invoke-direct {p0}, Lde/robv/android/xposed/XC_MethodHook;-><init>()V

    iput p1, p0, Lcom/momowords/crack/UnlimitedHook;->value:I

    iput p2, p0, Lcom/momowords/crack/UnlimitedHook;->reportValue:I

    return-void
.end method


.method protected beforeHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .locals 2

    invoke-static {}, Lcom/momowords/crack/Stealth;->isReporting()Z

    move-result v0

    if-eqz v0, :normal

    # ---- 上报路径 ----
    iget v0, p0, Lcom/momowords/crack/UnlimitedHook;->reportValue:I

    const v1, 0x7ffffffe

    if-ne v0, v1, :set

    # reportValue == SENTINEL → 不干预，原实现照常执行
    return-void

    :normal
    iget v0, p0, Lcom/momowords/crack/UnlimitedHook;->value:I

    :set
    invoke-static {v0}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object v0

    invoke-virtual {p1, v0}, Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;->setResult(Ljava/lang/Object;)V

    return-void
.end method
