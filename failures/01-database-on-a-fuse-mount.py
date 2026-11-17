#!/usr/bin/env python3
"""Failure 1: a cloud-drive mount zeroed a file, twice in one day.

In-place rewrites of a file on a FUSE-mounted cloud drive left it at zero bytes. SQLite on that
kind of mount is worse: its locking is advisory at best there, so the database corrupts.

Real here: connect() in bin/lanes and its fs_type() parsing, exactly as the runner calls them.
Simulated: the mount. A reader's machine has no cloud drive mounted, so this script hands
fs_type() a mount table in which a temp folder is a fuse.rclone mount. It reproduces the
condition the guardrail checks for (a database path on a FUSE mount), not the zeroed file.

Guardrail: connect() in bin/lanes refuses a database on a FUSE or network mount (NETWORK_FS).
Guarding test: tests/test_lint.py, Database.test_knows_a_fuse_mount_from_a_local_disk (the
mount parsing). tests/test_failures.py runs this script, which covers the refusal itself.
"""
import atexit
import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile
from importlib.machinery import SourceFileLoader

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.dont_write_bytecode = True


def load_lanes():
    loader = SourceFileLoader("lanes_core", os.path.join(ROOT, "bin", "lanes"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("lanes_core", loader))
    loader.exec_module(mod)
    return mod


def main():
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="failure-01-"))
    atexit.register(shutil.rmtree, tmp, True)
    drive, local = os.path.join(tmp, "drive"), os.path.join(tmp, "local")
    os.makedirs(drive), os.makedirs(local)
    os.environ.pop("LANES_ALLOW_ANY_FS", None)

    core = load_lanes()
    mounts = f"/dev/sda1 / ext4 rw 0 0\nremote: {drive} fuse.rclone rw 0 0\nserver:/x {tmp}/nfs nfs4 rw 0 0\n"
    real_fs_type = core.fs_type
    core.fs_type = lambda path, m=None: real_fs_type(path, mounts if m is None else m)
    print(f"setup: {drive} is a fuse.rclone mount in the mount table this script hands to fs_type()")

    # Without the guardrail: nothing in SQLite knows or cares what is under the file.
    plain = os.path.join(drive, "plain.db")
    sqlite3.connect(plain).execute("create table t (x)").connection.close()
    print(f"without the guardrail: sqlite3.connect() opened {plain} on the mount without a word")
    os.remove(plain)

    held = True
    for path in (os.path.join(drive, "lanes.db"), os.path.join(tmp, "nfs", "lanes.db")):
        os.environ["LANES_DB"] = path
        try:
            core.connect().close()
            print(f"FAIL: connect() opened {path}, which is on a {real_fs_type(path, mounts)} mount")
            held = False
        except SystemExit as e:
            print(f"guardrail: connect() refused: {e}")
            if os.path.exists(path):
                print(f"FAIL: the refusal came after {path} was created")
                held = False

    os.environ["LANES_DB"] = os.path.join(local, "lanes.db")
    try:
        core.connect().close()
        print(f"control: connect() opened {os.environ['LANES_DB']} on local disk (ext4), as it should")
    except SystemExit as e:
        print(f"FAIL: connect() refused local disk too: {e}")
        held = False

    print("HELD: the database will not open on a FUSE or network mount" if held else
          "BROKEN: connect() opened a database on a mount it should refuse")
    return 0 if held else 1


if __name__ == "__main__":
    sys.exit(main())
