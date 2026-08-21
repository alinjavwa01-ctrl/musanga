#!/usr/bin/env python3
"""Stamp asset URLs in web/*.html with each file's modification time.

The dev server already sends no-store, but a browser that cached an asset
before that header existed will happily keep serving it. A version query makes
the URL itself change whenever the file does.

Run after editing anything under web/css or web/js.
"""

import glob
import os
import re

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
PATTERN = re.compile(r'(href|src)="(/(?:css|js)/[^"]+)"')


def stamp(match):
    attr, path = match.group(1), match.group(2)
    clean = path.split("?")[0]
    disk = os.path.join(WEB, clean.lstrip("/"))
    if not os.path.isfile(disk):
        return match.group(0)
    return '%s="%s?v=%d"' % (attr, clean, int(os.path.getmtime(disk)))


def main():
    for page in sorted(glob.glob(os.path.join(WEB, "*.html"))):
        original = open(page).read()
        updated = PATTERN.sub(stamp, original)
        if updated != original:
            open(page, "w").write(updated)
            print("  stamped %s" % os.path.basename(page))


if __name__ == "__main__":
    main()
