/*
 * libmmboot.so — MoMoWords Lesson1 「无 root 独立包」注入引导层  (v2)
 *
 * 载入路径（APK 内不触碰 lib/，只放 META-INF/native/）：
 *   BaseAppContext.<clinit>
 *     -> classLoader.getResource("META-INF/native/libmomoco.so") != null
 *     -> SQLiteLibraryLoader/SQLCipherLibraryLoader.loadFromClasspath()
 *     -> System.load(g57.k("META-INF/native/libmomoco.so"))   <-- 载入本文件
 *
 * 本文件做三件事：
 *   1) 顶替了真 libmomoco.so 的位置，所以先把真的从 native lib dir dlopen 回来，
 *      并手动调用它的 JNI_OnLoad（dlopen 不会自己调）。
 *   2) 从自身文件尾部（64 字节 footer）取出内嵌的 frida-gadget 与 crack 脚本，
 *      写到同一个临时目录下。
 *   3) 生成 gadget 配置 <dir>/libmmcore.config.so，然后 dlopen gadget。
 *      gadget 只在自己所在目录找 <stem>.config.so，所以必须先落地配置文件。
 *
 * 编译（zig 交叉编译，无需 NDK；DT_NEEDED 用 stub .so 注入）：
 *   cd patch/gadget_payload/stubs
 *   python -m ziglang cc -target aarch64-linux-android -shared -nostdlib -fno-sanitize=all \
 *       -Wl,-soname,libdl.so -o libdl.so empty.c        # 同理 libc.so / liblog.so
 *   cd ..
 *   python -m ziglang cc -target aarch64-linux-android -shared -nostdlib -fno-stack-protector \
 *       -fno-builtin -fno-sanitize=all -Wl,-soname,libmmboot.so -O0 \
 *       -Wl,--no-as-needed stubs/libdl.so stubs/libc.so stubs/liblog.so -o libmmboot.so loader.c
 *
 * 注意：所有字符串操作都带长度上限 —— 上一版的 scpy/sapp 无界循环曾把栈撑爆
 *       到映射外（SIGSEGV SEGV_MAPERR），这里的 bscpy/bsapp/derive_dir 全部带 cap。
 */
typedef unsigned char u8;
typedef unsigned int u32;
typedef unsigned long long u64;
typedef unsigned long usize;
typedef int i32;

extern void *dlopen(const char *filename, int flags);
extern void *dlsym(void *handle, const char *symbol);
extern int dladdr(const void *addr, void *info);
extern char *dlerror(void);
extern int open(const char *path, int flags, ...);
extern long read(int fd, void *buf, usize count);
extern long write(int fd, const void *buf, usize count);
extern long lseek(int fd, long offset, int whence);
extern int close(int fd);
extern int __android_log_print(int prio, const char *tag, const char *fmt, ...);

typedef struct {
    const char *dli_fname;
    void *dli_fbase;
    const char *dli_sname;
    void *dli_saddr;
} DlInfo;

#define LOG_TAG "MoMoBoot"
#define LOGI(...) __android_log_print(4, LOG_TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(5, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(6, LOG_TAG, __VA_ARGS__)

#define O_RDONLY 0
#define O_WRONLY 1
#define O_CREAT 0100
#define O_TRUNC 01000
#define SEEK_SET 0
#define SEEK_END 2
#define RTLD_NOW 2

#define MAPS_SZ (1024 * 1024)
#define PATH_SZ 1024
#define CFG_SZ 2048
#define FOOT_SZ 64
#define MAX_DIR 400

static char g_maps[MAPS_SZ];
static u8 g_iobuf[65536];
static char g_self[PATH_SZ];
static char g_dir[PATH_SZ];
static int g_entered = 0;

/* ---------- 有界字符串工具 ---------- */

static usize slen(const char *s) { usize n = 0; while (n < PATH_SZ && s[n]) n++; return n; }

static void bscpy(char *d, const char *s, usize cap) {
    usize i = 0;
    if (cap == 0) return;
    while (i + 1 < cap && s[i]) { d[i] = s[i]; i++; }
    d[i] = 0;
}

static void bsapp(char *d, const char *s, usize cap) {
    usize i = 0;
    while (i < cap && d[i]) i++;
    if (i >= cap) return;
    while (i + 1 < cap && *s) d[i++] = *s++;
    d[i] = 0;
}

static void derive_dir(const char *path, char *dir, usize cap) {
    usize n = 0, i, k;
    while (n < PATH_SZ && path[n]) n++;
    i = n;
    while (i > 0 && path[i - 1] != '/') i--;
    if (i > 0) i--;
    if (i >= cap) i = cap - 1;
    for (k = 0; k < i; k++) dir[k] = path[k];
    dir[i] = 0;
}

/* ---------- /proc/self/maps 兜底 ---------- */

static int load_maps(void) {
    int fd = open("/proc/self/maps", O_RDONLY, 0);
    long total = 0, n;
    if (fd < 0) return -1;
    while (total < MAPS_SZ - 1) {
        n = read(fd, g_maps + total, (usize)(MAPS_SZ - 1 - total));
        if (n <= 0) break;
        total += n;
    }
    close(fd);
    g_maps[total] = 0;
    return 0;
}

static char *skip_fields(char *r, int f) {
    int i = 0;
    while (*r && i < f) {
        while (*r == ' ') r++;
        while (*r && *r != ' ') r++;
        i++;
    }
    while (*r == ' ') r++;
    return r;
}

/* 找映射路径里含 needle 的条目所在目录（用于定位 app 的 native lib dir） */
static int dir_of_loaded(const char *needle, char *out, usize cap) {
    char *p = g_maps;
    while (*p) {
        char *eol = p;
        char save;
        while (*eol && *eol != '\n') eol++;
        save = *eol;
        *eol = 0;
        {
            char *r = skip_fields(p, 4);
            if (*r == '/') {
                char *m = r;
                int found = 0;
                while (*m) {
                    const char *a = needle;
                    char *b = m;
                    while (*a && *a == *b) { a++; b++; }
                    if (!*a) { found = 1; break; }
                    m++;
                }
                if (found) {
                    derive_dir(r, out, cap);
                    *eol = save;
                    return out[0] ? 0 : -1;
                }
            }
        }
        *eol = save;
        p = save ? eol + 1 : eol;
    }
    return -1;
}

/* ---------- 文件写入 ---------- */

static int wr(const char *path, const u8 *data, usize len) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    usize off = 0;
    if (fd < 0) { LOGE("open(w) %s failed", path); return -1; }
    while (off < len) {
        long n = write(fd, data + off, len - off);
        if (n <= 0) { close(fd); LOGE("write %s failed", path); return -2; }
        off += (usize)n;
    }
    close(fd);
    return 0;
}

static int copy_range(int fd, u64 off, u64 len, const char *dst) {
    int out;
    u64 done = 0;
    if (!len) return -1;
    out = open(dst, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (out < 0) { LOGE("open(w) %s failed", dst); return -1; }
    while (done < len) {
        u64 left = len - done;
        u32 chunk = (u32)(left > (u64)sizeof(g_iobuf) ? (u64)sizeof(g_iobuf) : left);
        long n, w;
        if (lseek(fd, (long)(off + done), SEEK_SET) < 0) { close(out); return -2; }
        n = read(fd, g_iobuf, chunk);
        if (n <= 0) { close(out); LOGE("read self @%llu failed", off + done); return -3; }
        w = write(out, g_iobuf, (usize)n);
        if (w != n) { close(out); LOGE("write %s short", dst); return -4; }
        done += (u64)n;
    }
    close(out);
    return 0;
}

static void chain_load_real_momoco(void *vm, void *reserved) {
    void *h = dlopen("libmomoco.so", RTLD_NOW);
    LOGI("chain dlopen(libmomoco.so) -> %p", h);
    if (h == 0 && g_maps[0]) {
        char ld[PATH_SZ];
        char p2[PATH_SZ];
        ld[0] = 0;
        if (dir_of_loaded("/libdexjni.so", ld, sizeof(ld)) == 0) {
            bscpy(p2, ld, sizeof(p2));
            bsapp(p2, "/libmomoco.so", sizeof(p2));
            h = dlopen(p2, RTLD_NOW);
            LOGI("chain dlopen(%s) -> %p", p2, h);
        } else {
            LOGW("native lib dir not found in maps");
        }
    }
    if (h != 0) {
        typedef i32 (*onload_t)(void *, void *);
        onload_t f = (onload_t)dlsym(h, "JNI_OnLoad");
        LOGI("real libmomoco JNI_OnLoad=%p", (void *)f);
        if (f != 0) f(vm, reserved);
    }
}

i32 JNI_OnLoad(void *vm, void *reserved) {
    DlInfo info;
    if (g_entered) return 0x00010006;   /* 防递归 */
    g_entered = 1;

    g_self[0] = 0;
    g_dir[0] = 0;

    /* 1) 自己的完整路径：优先 dladdr */
    if (dladdr((const void *)(void *)&JNI_OnLoad, &info) != 0 && info.dli_fname != 0) {
        bscpy(g_self, info.dli_fname, sizeof(g_self));
        LOGI("dladdr self=%s", g_self);
    } else {
        LOGW("dladdr failed, falling back to maps");
        if (load_maps() == 0) {
            char *p = g_maps;
            while (*p && g_self[0] == 0) {
                char *eol = p;
                char save;
                while (*eol && *eol != '\n') eol++;
                save = *eol;
                *eol = 0;
                {
                    char *r = skip_fields(p, 4);
                    if (*r == '/') {
                        const char *needle = "/libmomoco.so";
                        char *m = r;
                        while (*m) {
                            const char *a = needle;
                            char *b = m;
                            while (*a && *a == *b) { a++; b++; }
                            if (!*a && b[0] == 0) { bscpy(g_self, r, sizeof(g_self)); break; }
                            m++;
                        }
                    }
                }
                *eol = save;
                p = save ? eol + 1 : eol;
            }
        }
        LOGI("maps self=%s", g_self);
    }

    if (g_self[0] == '/') derive_dir(g_self, g_dir, sizeof(g_dir));
    LOGI("dir=%s (len=%lu)", g_dir, (unsigned long)slen(g_dir));

    /* 2) 把真 libmomoco.so 链式加载回来 */
    chain_load_real_momoco(vm, reserved);

    /* 3) 自解包 + 引导 frida-gadget */
    if (g_dir[0] == '/' && slen(g_dir) < MAX_DIR) {
        int fd = open(g_self, O_RDONLY, 0);
        if (fd < 0) {
            LOGE("open(self) failed: %s", g_self);
        } else {
            u8 foot[FOOT_SZ];
            if (lseek(fd, -(long)FOOT_SZ, SEEK_END) < 0 ||
                read(fd, foot, FOOT_SZ) != (long)FOOT_SZ ||
                foot[0] != 'M' || foot[1] != 'M' || foot[2] != 'P' || foot[3] != 'K') {
                LOGE("footer magic missing");
            } else {
                u64 goff = *(u64 *)(foot + 8), glen = *(u64 *)(foot + 16);
                u64 joff = *(u64 *)(foot + 24), jlen = *(u64 *)(foot + 32);
                char jsp[PATH_SZ], gsp[PATH_SZ], cfp[PATH_SZ], cfg[CFG_SZ];
                int ok;
                LOGI("payload gadget=%llu+%llu js=%llu+%llu", goff, glen, joff, jlen);
                bscpy(jsp, g_dir, sizeof(jsp)); bsapp(jsp, "/mmc.js", sizeof(jsp));
                bscpy(gsp, g_dir, sizeof(gsp)); bsapp(gsp, "/libmmcore.so", sizeof(gsp));
                bscpy(cfp, g_dir, sizeof(cfp)); bsapp(cfp, "/libmmcore.config.so", sizeof(cfp));
                ok = (jlen && copy_range(fd, joff, jlen, jsp) == 0) &&
                     (glen && copy_range(fd, goff, glen, gsp) == 0);
                LOGI("extract ok=%d js=%s so=%s", ok, jsp, gsp);
                if (ok) {
                    bscpy(cfg, "{\"interaction\":{\"type\":\"script\",\"path\":\"", sizeof(cfg));
                    bsapp(cfg, jsp, sizeof(cfg));
                    bsapp(cfg, "\"}}", sizeof(cfg));
                    if (wr(cfp, (const u8 *)cfg, slen(cfg)) == 0) {
                        void *gh = dlopen(gsp, RTLD_NOW);
                        LOGI("dlopen(gadget) -> %p", gh);
                        if (gh == 0) {
                            char *e = dlerror();
                            LOGE("gadget dlopen failed: %s", e ? e : "(null)");
                        }
                    }
                }
            }
            close(fd);
        }
    } else {
        LOGE("bad dir, skip bootstrap");
    }

    return 0x00010006;
}
