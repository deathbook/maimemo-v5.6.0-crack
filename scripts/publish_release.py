# -*- coding: utf-8 -*-
"""
创建 GitHub Release 并上传二进制产物（流式上传，能扛 134MB 的 APK）。

用法：python scripts/publish_release.py
token 取自 ~/.config/gh/hosts.yml（本机已有，不写入任何文件）
"""
import http.client
import json
import os
import re
import ssl
import sys

BASE = r'C:\Users\O5-3\Documents\VibeCoding\Crack\MoMoWords'
DIST = os.path.join(BASE, 'dist')
OWNER = 'deathbook'
REPO = 'maimemo-v5.6.0-crack'
TAG = 'v1.0'
TITLE = '墨墨背单词 v5.6.0 破解产物（APK / 脱壳 dex / native so）'

ASSETS = [
    'maimemo_v5.6.0_cracked_standalone.apk',
    'unpacked_dex.zip',
    'native_libs.zip',
    'SHA256SUMS.txt',
]


def get_token():
    p = os.path.join(os.path.expanduser('~'), '.config', 'gh', 'hosts.yml')
    with open(p, encoding='utf-8') as f:
        m = re.search(r'oauth_token:\s*(\S+)', f.read())
    if not m:
        sys.exit('未找到 gh oauth_token')
    return m.group(1)


def api(method, path, token, body=None):
    conn = http.client.HTTPSConnection('api.github.com', timeout=120,
                                       context=ssl.create_default_context())
    headers = {'Authorization': 'token ' + token, 'User-Agent': 'dsh',
               'Accept': 'application/vnd.github+json'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
        headers['Content-Length'] = str(len(body))
    conn.request(method, path, body=body, headers=headers)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, data


def upload(path, token, filepath, name):
    size = os.path.getsize(filepath)
    conn = http.client.HTTPSConnection('uploads.github.com', timeout=7200,
                                       context=ssl.create_default_context())
    conn.putrequest('POST', path, skip_host=False, skip_accept_encoding=True)
    conn.putheader('Authorization', 'token ' + token)
    conn.putheader('User-Agent', 'dsh')
    conn.putheader('Accept', 'application/vnd.github+json')
    conn.putheader('Content-Type', 'application/octet-stream')
    conn.putheader('Content-Length', str(size))
    conn.endheaders()
    sent = 0
    with open(filepath, 'rb') as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            conn.send(b)
            sent += len(b)
            if sent % (16 << 20) < (1 << 20):
                print('      ... %d / %d MB' % (sent >> 20, size >> 20), flush=True)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, data


def main():
    token = get_token()

    with open(os.path.join(DIST, 'RELEASE_BODY.md'), encoding='utf-8') as f:
        body = f.read()

    payload = json.dumps({'tag_name': TAG, 'name': TITLE, 'body': body,
                          'draft': False, 'prerelease': False}).encode('utf-8')
    st, data = api('POST', '/repos/%s/%s/releases' % (OWNER, REPO), token, payload)
    print('create release -> HTTP %d' % st)
    if st not in (200, 201):
        print(data.decode('utf-8', 'replace')[:800])
        sys.exit(1)
    rel = json.loads(data.decode('utf-8'))
    rid = rel['id']
    print('  id=%s  tag=%s  url=%s' % (rid, rel['tag_name'], rel['html_url']))

    ok = True
    for name in ASSETS:
        fp = os.path.join(DIST, name)
        if not os.path.exists(fp):
            print('  [skip] %s 不存在' % name)
            continue
        mb = os.path.getsize(fp) / 1048576.0
        print('  [upload] %-46s %7.2f MB' % (name, mb), flush=True)
        st, data = upload('/repos/%s/%s/releases/%s/assets?name=%s' % (OWNER, REPO, rid, name),
                          token, fp, name)
        if st in (200, 201):
            a = json.loads(data.decode('utf-8'))
            print('      OK  size=%.2f MB  state=%s' % (a['size'] / 1048576.0, a['state']))
        else:
            ok = False
            print('      FAIL HTTP %d: %s' % (st, data.decode('utf-8', 'replace')[:300]))

    print('结果: %s' % ('全部上传成功' if ok else '有失败项'))


if __name__ == '__main__':
    main()
