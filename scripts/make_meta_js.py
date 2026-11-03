# -*- coding: utf-8 -*-
"""把 data/meta/<layer>.json 转成 web/data/meta/<layer>.js（window.GA_META 挂载）。

为什么不并进 make_web.py：make_web 切片很慢，而元数据只是转格式。
两者都有各自的坑，分开跑更省事；本脚本只读 data/meta/*.json，纯改格式，可反复跑。

注意：早期 make_web.py 里用 js_assign("(window.GA_META=...)['x']") 会拼出
`window.(window.GA_META=...)['x']=...` —— 这是语法错误，整段 meta 脚本静默作废，
表现为「异写永远只有 1 种、没有出处、点不开异写」。本脚本不再用那种拼法。
"""
import glob
import json
import os
import re

SRC = "data/meta"
OUT = "web/data/meta"


def main():
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for p in sorted(glob.glob(os.path.join(SRC, "*.json"))):
        lid = os.path.splitext(os.path.basename(p))[0]
        meta = json.load(open(p, encoding="utf-8"))
        body = "window.GA_META=window.GA_META||{};\nwindow.GA_META[%s]=%s;\n" % (
            json.dumps(lid), json.dumps(meta, ensure_ascii=False, separators=(",", ":")))
        dst = os.path.join(OUT, lid + ".js")
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        total += len(body)
        print("%-12s %8.2f MB  %6d chars" % (lid, len(body.encode()) / 1048576, len(meta)))
    print("total %.2f MB" % (total / 1048576))


if __name__ == "__main__":
    main()