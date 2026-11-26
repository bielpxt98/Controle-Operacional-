# -*- coding: utf-8 -*-
"""
Banco Espelho Local (SQLite) para contingência offline do Controle Operacional.
Garante que o sistema continue lendo e salvando coletas mesmo se o Supabase cair,
pausar ou atingir limites de cota.
"""

import os
import json
import time
import sqlite3
import threading
import requests
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MIRROR_DB_PATH = os.path.join(BASE_DIR, "coletas_mirror.db")
_db_lock = threading.Lock()


def _get_conn():
    conn = sqlite3.connect(MIRROR_DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def init_mirror_db():
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS deliveries_mirror (
                    id INTEGER PRIMARY KEY,
                    data TEXT,
                    delivery TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT,
                    pending_sync INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mirror_data ON deliveries_mirror(data)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mirror_delivery ON deliveries_mirror(delivery)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mirror_pending ON deliveries_mirror(pending_sync)")
            conn.commit()
        finally:
            conn.close()


init_mirror_db()


def mirror_sync_all(rows):
    """Sincroniza em lote os registros do Supabase para o espelho local sem sobrescrever pendências offline."""
    if not isinstance(rows, list) or not rows:
        return
    now_iso = datetime.utcnow().isoformat()
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute("SELECT id FROM deliveries_mirror WHERE pending_sync != 0")
            pending_ids = {row[0] for row in cur.fetchall()}

            for r in rows:
                rid = r.get("id")
                if not rid or rid in pending_ids:
                    continue
                conn.execute(
                    """
                    INSERT INTO deliveries_mirror (id, data, delivery, payload_json, updated_at, pending_sync)
                    VALUES (?, ?, ?, ?, ?, 0)
                    ON CONFLICT(id) DO UPDATE SET
                        data = excluded.data,
                        delivery = excluded.delivery,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at,
                        pending_sync = 0
                    """,
                    (
                        int(rid),
                        str(r.get("data") or "").strip(),
                        str(r.get("delivery") or "").strip(),
                        json.dumps(r, ensure_ascii=False),
                        now_iso,
                    ),
                )
            conn.commit()
        except Exception as e:
            print(f"[SQLITE-MIRROR] Erro em mirror_sync_all: {e}")
        finally:
            conn.close()


def mirror_upsert_rows(rows, pending=0):
    """Insere ou atualiza registros no espelho local. Se pending=1, marca para sincronizar depois."""
    if not isinstance(rows, list) or not rows:
        return []
    now_iso = datetime.utcnow().isoformat()
    saved = []
    with _db_lock:
        conn = _get_conn()
        try:
            for r in rows:
                rid = r.get("id")
                if not rid:
                    # Gera ID negativo temporário para registros criados offline
                    rid = -int(time.time() * 1000)
                    time.sleep(0.002)
                    r = {**r, "id": rid}
                else:
                    rid = int(rid)
                conn.execute(
                    """
                    INSERT INTO deliveries_mirror (id, data, delivery, payload_json, updated_at, pending_sync)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        data = excluded.data,
                        delivery = excluded.delivery,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at,
                        pending_sync = excluded.pending_sync
                    """,
                    (
                        rid,
                        str(r.get("data") or "").strip(),
                        str(r.get("delivery") or "").strip(),
                        json.dumps(r, ensure_ascii=False),
                        now_iso,
                        int(pending),
                    ),
                )
                saved.append(r)
            conn.commit()
        except Exception as e:
            print(f"[SQLITE-MIRROR] Erro em mirror_upsert_rows: {e}")
        finally:
            conn.close()
    return saved


def mirror_delete_row(rec_id, pending=0):
    try:
        rid = int(rec_id)
    except Exception:
        return
    with _db_lock:
        conn = _get_conn()
        try:
            if pending == 0 or rid < 0:
                conn.execute("DELETE FROM deliveries_mirror WHERE id = ?", (rid,))
            else:
                conn.execute("UPDATE deliveries_mirror SET pending_sync = -1 WHERE id = ?", (rid,))
            conn.commit()
        finally:
            conn.close()


def mirror_get_all():
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "SELECT payload_json FROM deliveries_mirror WHERE pending_sync != -1 ORDER BY id DESC"
            )
            return [json.loads(row[0]) for row in cur.fetchall()]
        except Exception as e:
            print(f"[SQLITE-MIRROR] Erro em mirror_get_all: {e}")
            return []
        finally:
            conn.close()


def mirror_get_by_dates(variants):
    if not variants:
        return []
    placeholders = ",".join(["?"] * len(variants))
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                f"SELECT payload_json FROM deliveries_mirror WHERE pending_sync != -1 AND data IN ({placeholders}) ORDER BY id ASC",
                tuple(variants),
            )
            return [json.loads(row[0]) for row in cur.fetchall()]
        except Exception as e:
            print(f"[SQLITE-MIRROR] Erro em mirror_get_by_dates: {e}")
            return []
        finally:
            conn.close()


def mirror_pending_count():
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute("SELECT COUNT(*) FROM deliveries_mirror WHERE pending_sync != 0")
            return cur.fetchone()[0]
        except Exception:
            return 0
        finally:
            conn.close()


def flush_pending_to_supabase(supabase_url, headers):
    """Tenta reenviar alterações feitas offline quando o Supabase volta ao ar."""
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute("SELECT id, payload_json, pending_sync FROM deliveries_mirror WHERE pending_sync != 0")
            pending_rows = cur.fetchall()
        finally:
            conn.close()

    if not pending_rows:
        return 0

    synced = 0
    for rid, payload_str, p_status in pending_rows:
        try:
            payload = json.loads(payload_str)
            if p_status == -1:
                if rid > 0:
                    res = requests.delete(f"{supabase_url.rstrip('/')}/rest/v1/deliveries?id=eq.{rid}", headers=headers, timeout=8)
                    if res.status_code in [200, 204]:
                        mirror_delete_row(rid, pending=0)
                        synced += 1
                else:
                    mirror_delete_row(rid, pending=0)
                    synced += 1
            elif p_status == 1:
                clean_payload = {k: v for k, v in payload.items() if k != "id" and not str(k).startswith("_")}
                if rid > 0:
                    res = requests.patch(
                        f"{supabase_url.rstrip('/')}/rest/v1/deliveries?id=eq.{rid}",
                        headers=headers,
                        json=clean_payload,
                        timeout=8,
                    )
                    if res.status_code in [200, 204]:
                        mirror_upsert_rows([payload], pending=0)
                        synced += 1
                else:
                    res = requests.post(
                        f"{supabase_url.rstrip('/')}/rest/v1/deliveries",
                        headers={**headers, "Prefer": "return=representation"},
                        json=clean_payload,
                        timeout=8,
                    )
                    if res.status_code in [200, 201] and res.json():
                        new_row = res.json()[0]
                        mirror_delete_row(rid, pending=0)
                        mirror_upsert_rows([new_row], pending=0)
                        synced += 1
        except Exception:
            break
    return synced
