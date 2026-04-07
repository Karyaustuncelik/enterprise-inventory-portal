from database import get_conn
try:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1")
    print("DB OK:", cur.fetchone())
    conn.close()
except Exception as e:
    print("DB FAIL:", repr(e))
