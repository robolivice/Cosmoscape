import gzip
import hashlib
import shutil
import sqlite3
import sys

src = sys.argv[1]
conn = sqlite3.connect(src)
conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
conn.execute("VACUUM")
conn.close()

with open(src, "rb") as f_in:
    with gzip.open("universe.db.gz", "wb", compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out)

h = hashlib.sha256()
with open("universe.db.gz", "rb") as f:
    while True:
        block = f.read(1048576)
        if not block:
            break
        h.update(block)
print("SHA256:", h.hexdigest())