# -*- coding: utf-8 -*-
"""
发布 LSPosed 模块的 GitHub Release（v1.2）。

附件：momocrack-module.apk（模块本体）+ momocrack-module-src.zip（apktool 工程源码）
token 取自 ~/.config/gh/hosts.yml
"""
import http.client
import hashlib
import json
import os
import re
import ssl
import sys
import zipfile

BASE = r'C:\Users\O5-3\Documents\VibeCoding\Crack\MoMoWords'
MOD = os.path.join(BASE, 'lspatch', 'mod')
APK = os.path.join(BASE, 'lspatch', 'signedmod', 'momocrack-module-aligned-debugSigned.apk')
DIST = os.path.join(BASE, 'dist')
SRC_ZIP = os.path.join(DIST, 'momocrack-module-src.zip')

OWNER, REPO = 'deathbook', 'maimemo-v5.6.0-crack'
TAG = 'v1.2'
TITLE = 'LSPosed 模块 —— 墨墨背单词 v5.6.0 单词上限解锁（12.7 KB）'


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def get_token():
    p = os.path.join(os.path.expanduser('~'), '.config', 'gh', 'hosts.yml')
    with open(p, encoding='utf-8') as f:
        return re.search(r'oauth_token:\s*(\S+)', f.read()).group(1)


def api(method, path, token, body=None):
    c = http.client.HTTPSConnection('api.github.com', timeout=120,
                                    context=ssl.create_default_context())
    h = {'Authorization': 'token ' + token, 'User-Agent': 'dsh',
         'Accept': 'application/vnd.github+json'}
    if body is not None:
        h['Content-Type'] = 'application/json'
        h['Content-Length'] = str(len(body))
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    d = r.read()
    c.close()
    return r.status, d


def upload(path, token, fp, name):
    size = os.path.getsize(fp)
    c = http.client.HTTPSConnection('uploads.github.com', timeout=1800,
                                    context=ssl.create_default_context())
    c.putrequest('POST', path, skip_host=False, skip_accept_encoding=True)
    c.putheader('Authorization', 'token ' + token)
    c.putheader('User-Agent', 'dsh')
    c.putheader('Accept', 'application/vnd.github+json')
    c.putheader('Content-Type', 'application/octet-stream')
    c.putheader('Content-Length', str(size))
    c.endheaders()
    with open(fp, 'rb') as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            c.send(b)
    r = c.getresponse()
    d = r.read()
    c.close()
    return r.status, d


def build_src_zip():
    with zipfile.ZipFile(SRC_ZIP, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel in ('AndroidManifest.xml', 'apktool.yml', 'assets/xposed_init'):
            z.write(os.path.join(MOD, rel.replace('/', os.sep)), rel)
        sm = os.path.join(MOD, 'smali', 'com', 'momowords', 'crack')
        for n in sorted(os.listdir(sm)):
            z.write(os.path.join(sm, n), 'smali/com/momowords/crack/' + n)
    return SRC_ZIP


def main():
    if not os.path.exists(APK):
        sys.exit('模块 APK 不存在: %s' % APK)
    build_src_zip()

    apk_sha = sha256(APK)
    apk_mb = os.path.getsize(APK)
    body = """# LSPosed 模块 —— 墨墨背单词 v5.6.0

**Android 16 上唯一能解决按键延迟的路线。官方 APK 原封不动。**

## 附件

| 文件 | 大小 | 说明 |
|---|---|---|
| `momocrack-module.apk` | {apk_mb:,} B | 模块本体，已签名 (v2/v3)，无需 root 也能装，但要生效需 LSPosed |
| `momocrack-module-src.zip` | {src_mb:,} B | 源码（apktool 工程：AndroidManifest.xml + xposed_init + 5 个 smali） |

```
SHA256  momocrack-module.apk  {apk_sha}
```

## 装法

```bash
adb install -r momocrack-module.apk
```

1. LSPosed 管理器 → **模块** → 勾选 **MoMoCrack**
2. **作用域**只勾「墨墨背单词」（`com.maimemo.android.momo`）
3. **强行停止**墨墨，重新打开（勾了作用域但没生效就重启一次手机）

## 效果

| 项 | 结果 |
|---|---|
| 本地 | `a.s()` / `x1d.f(false)` → **2147483647**（无限） |
| 上报 | 仍返回**服务端真实值**（实测 5012），服务端看不到异常 |

## 为什么要单独做一个模块

Frida 的 Java hook 有"在场成本"：建 hook 后相关类会退出 ART 的 AOT/JIT 优化路径，与回调次数无关
（实测 `a.s()` 20 秒才 11 次，主线程 CPU 仍从 327 → 471 ticks/5s）。LSPosed 走 ART 层 `ArtMethod`
替换，不进 JS 桥、不做全量插桩，代价低一个量级。

**LSPatch 在 Android 16 上不可用**（v0.6 的 loader 崩在 `LSPlant: Failed to find GetMethodShorty`
与 `NoSuchFieldError: ActivityThread$AppBindData#compatInfo`），所以 Android 16 只有这一条路。

无 root 的替代方案：见 [v1.1]({rel11}) 的 `maimemo_v5.6.0_cracked_standalone.apk`
（普通安装即生效，但有性能地板；且需先卸载官方版，因为签名不同）。

## 前提与限制

* **需要 root + LSPosed**。
* **本模块尚未在真机运行验证** —— 开发机测试设备只有 KernelSU、没有 LSPosed，`su` 对 adb shell 也不可用。
  已验证：apktool 编译通过、baksmali 反查确认 dex 内 5 个类齐全、清单 meta-data 与 `xposed_init` 正确、
  签名有效。运行时行为待确认。
* 三条路线对比与实现细节：<https://github.com/deathbook/maimemo-v5.6.0-crack/blob/main/module/README.md>
""".format(apk_mb=apk_mb, src_mb=os.path.getsize(SRC_ZIP), apk_sha=apk_sha,
           rel11='https://github.com/%s/%s/releases/tag/v1.1' % (OWNER, REPO))

    token = get_token()
    payload = json.dumps({'tag_name': TAG, 'name': TITLE, 'body': body,
                          'draft': False, 'prerelease': False}).encode('utf-8')
    st, data = api('POST', '/repos/%s/%s/releases' % (OWNER, REPO), token, payload)
    print('create release -> HTTP %d' % st)
    if st not in (200, 201):
        print(data.decode('utf-8', 'replace')[:800])
        sys.exit(1)
    rel = json.loads(data.decode('utf-8'))
    print('  id=%s tag=%s url=%s' % (rel['id'], rel['tag_name'], rel['html_url']))

    for fp, name in ((APK, 'momocrack-module.apk'), (SRC_ZIP, 'momocrack-module-src.zip')):
        st, data = upload('/repos/%s/%s/releases/%s/assets?name=%s' % (OWNER, REPO, rel['id'], name),
                          token, fp, name)
        if st in (200, 201):
            a = json.loads(data.decode('utf-8'))
            print('  [OK] %-28s %7d B  state=%s' % (name, a['size'], a['state']))
        else:
            print('  [FAIL] %s HTTP %d %s' % (name, st, data.decode('utf-8', 'replace')[:200]))


if __name__ == '__main__':
    main()
