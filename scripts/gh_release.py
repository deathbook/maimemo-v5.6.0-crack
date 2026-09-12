# -*- coding: utf-8 -*-
"""
通用 GitHub Release 发布器（建 release + 流式上传附件，能扛 134MB）。

用法：
  python scripts/gh_release.py --tag v1.3 --title "..." --body-file dist/RELEASE_v1.3.md \
      --assets dist/maimemo_v5.6.0_cracked_standalone.apk dist/momocrack-module.apk

token 取自 ~/.config/gh/hosts.yml（不写入任何文件）
"""
import argparse
import http.client
import hashlib
import json
import os
import re
import ssl
import sys

OWNER, REPO = 'deathbook', 'maimemo-v5.6.0-crack'


def get_token():
    p = os.path.join(os.path.expanduser('~'), '.config', 'gh', 'hosts.yml')
    with open(p, encoding='utf-8') as f:
        m = re.search(r'oauth_token:\s*(\S+)', f.read())
    if not m:
        sys.exit('未找到 gh oauth_token')
    return m.group(1)


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


def upload(path, token, fp):
    size = os.path.getsize(fp)
    c = http.client.HTTPSConnection('uploads.github.com', timeout=3600,
                                    context=ssl.create_default_context())
    c.putrequest('POST', path, skip_host=False, skip_accept_encoding=True)
    c.putheader('Authorization', 'token ' + token)
    c.putheader('User-Agent', 'dsh')
    c.putheader('Accept', 'application/vnd.github+json')
    c.putheader('Content-Type', 'application/octet-stream')
    c.putheader('Content-Length', str(size))
    c.endheaders()
    sent = 0
    with open(fp, 'rb') as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            c.send(b)
            sent += len(b)
            if sent % (32 << 20) < (1 << 20):
                print('      ... %d/%d MB' % (sent >> 20, size >> 20), flush=True)
    r = c.getresponse()
    d = r.read()
    c.close()
    return r.status, d


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', required=True)
    ap.add_argument('--title', required=True)
    ap.add_argument('--body-file', required=True)
    ap.add_argument('--assets', nargs='*', default=[])
    a = ap.parse_args()

    with open(a.body_file, encoding='utf-8') as f:
        body = f.read()

    print('[sha256]')
    for p in a.assets:
        print('  %s  %s' % (sha256(p), os.path.basename(p)))

    token = get_token()
    payload = json.dumps({'tag_name': a.tag, 'name': a.title, 'body': body,
                          'draft': False, 'prerelease': False}).encode('utf-8')
    st, data = api('POST', '/repos/%s/%s/releases' % (OWNER, REPO), token, payload)
    print('[create release] HTTP %d' % st)
    if st not in (200, 201):
        print(data.decode('utf-8', 'replace')[:800])
        sys.exit(1)
    rel = json.loads(data.decode('utf-8'))
    print('  id=%s tag=%s %s' % (rel['id'], rel['tag_name'], rel['html_url']))

    ok = True
    for p in a.assets:
        name = os.path.basename(p)
        print('  [upload] %-46s %8.2f MB' % (name, os.path.getsize(p) / 1048576.0), flush=True)
        st, data = upload('/repos/%s/%s/releases/%s/assets?name=%s' % (OWNER, REPO, rel['id'], name),
                          token, p)
        if st in (200, 201):
            j = json.loads(data.decode('utf-8'))
            print('      OK size=%.2f MB state=%s' % (j['size'] / 1048576.0, j['state']))
        else:
            ok = False
            print('      FAIL HTTP %d: %s' % (st, data.decode('utf-8', 'replace')[:300]))
    print('结果: %s' % ('全部上传成功' if ok else '有失败项'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
