"""A process-owned SQLite GPU lease shared by core and optional workers.

There is no time-only lease expiry: a long inference must never overlap another
model. A dead owner or a reused PID is the only automatic recovery condition.
"""
import os
import sqlite3
import time
import uuid
from pathlib import Path
from ..job_queue import process_birth
from .download import Canceled


class GPULease:
    def __init__(self, root, purpose, canceled=lambda:False, waiting=lambda:None):
        self.path=Path(root)/'gpu.sqlite3';self.path.parent.mkdir(parents=True,exist_ok=True)
        self.purpose=purpose;self.canceled=canceled;self.waiting=waiting
        self.token=uuid.uuid4().hex
        self.pid=int(Path('/proc/self/stat').read_text().split()[0]) if os.name!='nt' else os.getpid()
        self.birth=process_birth(self.pid,visible=True)
        if self.birth is None:raise RuntimeError('Identitas proses tidak dapat diperiksa untuk antrean GPU')
        with self.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS lease(id INTEGER PRIMARY KEY CHECK(id=1),token TEXT,pid INTEGER,birth TEXT,purpose TEXT,started REAL)')

    def connect(self):return sqlite3.connect(self.path,timeout=10)

    def __enter__(self):
        announced=False
        while True:
            if self.canceled():raise Canceled('Proses dibatalkan sebelum GPU tersedia')
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row=db.execute('SELECT token,pid,birth FROM lease WHERE id=1').fetchone()
                if row and str(process_birth(row[1],visible=True))==row[2]:
                    pass
                else:
                    db.execute('DELETE FROM lease')
                    db.execute('INSERT INTO lease VALUES(1,?,?,?,?,?)',(self.token,self.pid,str(self.birth),self.purpose,time.time()))
                    return self
            if not announced:self.waiting();announced=True
            time.sleep(.15)

    def __exit__(self,*exc):
        with self.connect() as db:db.execute('DELETE FROM lease WHERE id=1 AND token=?',(self.token,))


def owner(root):
    path=Path(root)/'gpu.sqlite3'
    if not path.exists():return None
    try:
        with sqlite3.connect(path,timeout=10) as db:
            row=db.execute('SELECT pid,birth,purpose,started FROM lease WHERE id=1').fetchone()
    except sqlite3.OperationalError:return None
    return dict(pid=row[0],purpose=row[2],started=row[3],alive=str(process_birth(row[0],visible=True))==row[1]) if row else None
