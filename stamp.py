#!/usr/bin/env python3
"""Stamp asset URLs in web/*.html with a hash of each file's contents.

The dev server sends no-store, but a browser that cached an asset before that
header existed will happily keep serving it, and in production the assets are
cached for a year. A version query makes the URL itself change whenever the
file changes.

The stamp is a content hash rather than a timestamp so it is reproducible: a
fresh git checkout produces the same URLs, which lets CI check that the
committed HTML matches the committed assets.

Run after editing anything under web/css or web/js.
"""

import glob
import hashlib
import os
import re

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
PATTERN = re.compile(r'(href|src)="(/(?:css|js)/[^"]+)"')
STAMP_LENGTH = 10


def digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()[:STAMP_LENGTH]


def stamp(match):
    attr, path = match.group(1), match.group(2)
    clean = path.split("?")[0]
    disk = os.path.join(WEB, clean.lstrip("/"))
    if not os.path.isfile(disk):
        return match.group(0)
    return '%s="%s?v=%s"' % (attr, clean, digest(disk))


def main():
    changed = []
    for page in sorted(glob.glob(os.path.join(WEB, "*.html"))):
        original = open(page).read()
        updated = PATTERN.sub(stamp, original)
        if updated != original:
            open(page, "w").write(updated)
            changed.append(os.path.basename(page))
    for name in changed:
        print("  stamped %s" % name)
    if not changed:
        print("  asset stamps already current")


if __name__ == "__main__":
    main()
