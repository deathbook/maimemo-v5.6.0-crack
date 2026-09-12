.class public Lcom/momowords/crack/Stealth;
.super Ljava/lang/Object;
.source "Stealth.java"


# 按线程记录「当前是否在构造上报数据」。
# 用 ThreadLocal 存 Boolean.TRUE（自动装箱命中缓存），所以下面可以用引用比较。
.field private static final REPORTING:Ljava/lang/ThreadLocal;


.method static constructor <clinit>()V
    .locals 1

    new-instance v0, Ljava/lang/ThreadLocal;

    invoke-direct {v0}, Ljava/lang/ThreadLocal;-><init>()V

    sput-object v0, Lcom/momowords/crack/Stealth;->REPORTING:Ljava/lang/ThreadLocal;

    return-void
.end method


.method public constructor <init>()V
    .locals 0

    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method


.method public static enter()V
    .locals 2

    sget-object v0, Lcom/momowords/crack/Stealth;->REPORTING:Ljava/lang/ThreadLocal;

    sget-object v1, Ljava/lang/Boolean;->TRUE:Ljava/lang/Boolean;

    invoke-virtual {v0, v1}, Ljava/lang/ThreadLocal;->set(Ljava/lang/Object;)V

    return-void
.end method


.method public static exit()V
    .locals 1

    sget-object v0, Lcom/momowords/crack/Stealth;->REPORTING:Ljava/lang/ThreadLocal;

    invoke-virtual {v0}, Ljava/lang/ThreadLocal;->remove()V

    return-void
.end method


.method public static isReporting()Z
    .locals 2

    sget-object v0, Lcom/momowords/crack/Stealth;->REPORTING:Ljava/lang/ThreadLocal;

    invoke-virtual {v0}, Ljava/lang/ThreadLocal;->get()Ljava/lang/Object;

    move-result-object v0

    sget-object v1, Ljava/lang/Boolean;->TRUE:Ljava/lang/Boolean;

    if-ne v0, v1, :not_reporting

    const/4 v0, 0x1

    return v0

    :not_reporting
    const/4 v0, 0x0

    return v0
.end method
