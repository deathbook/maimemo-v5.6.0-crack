.class public Lcom/momowords/crack/UnlimitedHook;
.super Lde/robv/android/xposed/XC_MethodHook;
.source "UnlimitedHook.java"


# 把目标方法的返回值改成常数（默认 0x7FFFFFFF 或 0 / false）。
# 关键：**非上报路径根本不执行原实现** —— beforeHookedMethod 里直接 setResult 就会跳过原方法。
# 这一点很重要：a.s() 走 JNI 会去开 SQLite，数据库没建立时它会抛异常，
# 如果先调原实现，异常会从 hook 里冒出去，UI 就拿不到无限值了。
#
# 上报路径（Stealth.isReporting() == true）不做任何事 → 原实现照常跑 → 上报真实值。

.field private final value:I


.method public constructor <init>(I)V
    .locals 0

    invoke-direct {p0}, Lde/robv/android/xposed/XC_MethodHook;-><init>()V

    iput p1, p0, Lcom/momowords/crack/UnlimitedHook;->value:I

    return-void
.end method


.method protected beforeHookedMethod(Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;)V
    .locals 1

    invoke-static {}, Lcom/momowords/crack/Stealth;->isReporting()Z

    move-result v0

    if-nez v0, :done

    iget v0, p0, Lcom/momowords/crack/UnlimitedHook;->value:I

    invoke-static {v0}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;

    move-result-object v0

    invoke-virtual {p1, v0}, Lde/robv/android/xposed/XC_MethodHook$MethodHookParam;->setResult(Ljava/lang/Object;)V

    :done
    return-void
.end method
