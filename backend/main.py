import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DEMO_DB_PATH", str(BASE_DIR / "data" / "demo.db"))).resolve()

CHOICE_FIELDS = [
    "Country", "Status", "Identity", "Department", "Region",
    "Hardware_Type", "Hardware_Manufacturer", "Hardware_Model", "Win_OS", "Location_Floor"
]

FIELD_TO_COL = {
    "Country": "country",
    "Status": "status",
    "Identity": "identity",
    "Department": "department",
    "Region": "region",
    "Hardware_Type": "hardware_type",
    "Hardware_Manufacturer": "hardware_manufacturer",
    "Hardware_Model": "hardware_model",
    "Win_OS": "win_os",
    "Location_Floor": "location_floor",
}

@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    role_count = conn.execute("SELECT COUNT(*) c FROM roles").fetchone()["c"]
    if role_count == 0:
        conn.executemany("INSERT INTO roles(id,name) VALUES(?,?)", [(1,"Admin"),(2,"Edit"),(3,"View")])

    user_count = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    if user_count == 0:
        conn.executemany(
            "INSERT INTO users(username,display_name,role_id) VALUES(?,?,?)",
            [
                ("ENTERPRISE\\admin", "Portfolio Admin", 1),
                ("ENTERPRISE\\editor", "Portfolio Editor", 2),
                ("ENTERPRISE\\viewer", "Portfolio Viewer", 3),
            ],
        )

    directory_count = conn.execute("SELECT COUNT(*) c FROM directory_users").fetchone()["c"]
    if directory_count == 0:
        conn.executemany(
            "INSERT INTO directory_users(username,display_name,email) VALUES(?,?,?)",
            [
                ("admin", "Portfolio Admin", "admin@example.com"),
                ("editor", "Portfolio Editor", "editor@example.com"),
                ("viewer", "Portfolio Viewer", "viewer@example.com"),
                ("alex.johnson", "Alex Johnson", "alex.johnson@example.com"),
                ("lina.khan", "Lina Khan", "lina.khan@example.com"),
            ],
        )

    item_count = conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"]
    if item_count == 0:
        conn.executemany(
            """
            INSERT INTO items(
              country,status,name_surname,identity,department,region,
              hardware_type,hardware_manufacturer,hardware_model,
              hardware_serial_number,asset_number,capitalization_date,
              user_name,old_user,windows_computer_name,win_os,
              location_floor,notes,if_deleted
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    "TR", "Assigned", "Alex Johnson", "Personnel", "IT", "IST",
                    "Laptop", "Lenovo", "ThinkPad", "SN-TR-0001", "ASSET-0001", "2024-01-15",
                    "alex.johnson", "", "TRISTMCSNTR0001", "Windows 11", "HQ Floor 1", "Demo record", 0
                ),
                (
                    "AE", "In Inventory", "Lina Khan", "Personnel", "Operations", "MEA",
                    "Desktop", "Dell", "Latitude", "SN-AE-0002", "ASSET-0002", "2023-10-02",
                    "lina.khan", "", "AEMEAWSSNAE0002", "Windows 10", "HQ Floor 2", "Demo spare", 0
                ),
            ],
        )


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS roles(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT,
                role_id INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS directory_users(
                username TEXT PRIMARY KEY,
                display_name TEXT,
                email TEXT
            );
            CREATE TABLE IF NOT EXISTS items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country TEXT,status TEXT,name_surname TEXT,identity TEXT,department TEXT,region TEXT,
                hardware_type TEXT,hardware_manufacturer TEXT,hardware_model TEXT,
                hardware_serial_number TEXT UNIQUE,asset_number TEXT,
                capitalization_date TEXT,user_name TEXT,old_user TEXT,
                windows_computer_name TEXT,win_os TEXT,location_floor TEXT,notes TEXT,
                if_deleted INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS field_params(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                field_name TEXT NOT NULL,param_name TEXT NOT NULL,is_active INTEGER,
                UNIQUE(field_name,param_name)
            );
            CREATE TABLE IF NOT EXISTS charts(
                id TEXT PRIMARY KEY,title TEXT,group_by TEXT NOT NULL,
                group_filter_value TEXT NOT NULL DEFAULT '',metric TEXT NOT NULL,
                filter_by TEXT NOT NULL,filter_value TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS audit_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,action TEXT NOT NULL,entity_type TEXT NOT NULL,
                entity_id TEXT,summary TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        _seed(conn)
        conn.commit()


app = FastAPI(title="Enterprise Inventory API (Portfolio)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        value.strip()
        for value in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if value.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event() -> None:
    init_db()


def _short_user(value: str) -> str:
    user = (value or "").strip()
    if "\\" in user:
        user = user.split("\\")[-1]
    if "@" in user:
        user = user.split("@")[0]
    return user.strip()


def _normalize_user(value: str) -> str:
    user = (value or "").strip()
    if not user:
        return ""
    if "\\" in user or "@" in user:
        return user
    domain = os.getenv("AUTH_USERNAME_DOMAIN", "ENTERPRISE").strip()
    return f"{domain}\\{user}" if domain else user


def _audit(conn: sqlite3.Connection, actor: str, action: str, entity: str, entity_id: Optional[str], summary: str) -> None:
    conn.execute(
        "INSERT INTO audit_log(actor,action,entity_type,entity_id,summary) VALUES(?,?,?,?,?)",
        (actor, action, entity, entity_id, summary),
    )


async def get_current_user(request: Request) -> Dict[str, Any]:
    header_name = os.getenv("AUTH_REMOTE_USER_HEADER", "X-Remote-User")
    username = request.headers.get(header_name) or request.headers.get("X-Remote-User")
    if not username:
        username = os.getenv("AUTH_DEMO_USER", "ENTERPRISE\\admin")

    normalized = _normalize_user(username)
    short = _short_user(normalized)

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT u.id,u.username,u.display_name,u.role_id,r.name role_name
            FROM users u JOIN roles r ON r.id=u.role_id
            WHERE LOWER(u.username)=LOWER(?)
               OR LOWER(CASE
                    WHEN INSTR(u.username,'\\')>0 THEN SUBSTR(u.username, INSTR(u.username,'\\')+1)
                    WHEN INSTR(u.username,'@')>0 THEN SUBSTR(u.username,1,INSTR(u.username,'@')-1)
                    ELSE u.username END)=LOWER(?)
            LIMIT 1
            """,
            (normalized, short),
        ).fetchone()
        if not row and os.getenv("AUTH_AUTO_PROVISION", "1") in {"1", "true", "True"}:
            role_id = int(os.getenv("AUTH_DEFAULT_ROLE_ID", "1"))
            display_name = short.replace(".", " ").replace("_", " ").title() or "Demo User"
            conn.execute(
                "INSERT OR IGNORE INTO users(username,display_name,role_id) VALUES(?,?,?)",
                (normalized, display_name, role_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT u.id,u.username,u.display_name,u.role_id,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id WHERE LOWER(u.username)=LOWER(?) LIMIT 1",
                (normalized,),
            ).fetchone()

    if not row:
        raise HTTPException(status_code=403, detail={"message": "User is not authorised."})

    return {
        "id": int(row["id"]),
        "username": row["username"],
        "display_name": row["display_name"],
        "role_id": int(row["role_id"]),
        "role_name": row["role_name"],
    }


async def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    admin_roles = {x.strip() for x in os.getenv("ADMIN_ROLE_IDS", "1").split(",") if x.strip()}
    is_admin = str(user["role_id"]) in admin_roles or str(user["role_name"]).lower() == "admin"
    if not is_admin:
        raise HTTPException(status_code=403, detail={"message": "Admin permission required."})
    return user


async def require_editor(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    is_viewer = str(user["role_name"]).lower() in {"view", "viewer"} or int(user["role_id"]) == 3
    if is_viewer:
        raise HTTPException(status_code=403, detail={"message": "Edit permission required."})
    return user


class UserCreateRequest(BaseModel):
    username: str
    display_name: Optional[str] = None
    role_id: int = Field(ge=1)


class UserPatchRequest(BaseModel):
    role_id: int = Field(ge=1)


class HardwarePayload(BaseModel):
    Name_Surname: str = Field(..., min_length=1, max_length=100)
    Hardware_Serial_Number: str = Field(..., min_length=1, max_length=80)
    Asset_Number: str = Field(..., min_length=1, max_length=80)
    Country: str = Field(..., min_length=2, max_length=8)

    Identity: Optional[str] = None
    Region: Optional[str] = None
    Win_OS: Optional[str] = None
    Hardware_Type: Optional[str] = None
    Hardware_Manufacturer: Optional[str] = None
    Hardware_Model: Optional[str] = None
    User_Name: Optional[str] = None
    Status: Optional[str] = None
    Department: Optional[str] = None
    Location_Floor: Optional[str] = None
    Capitalization_Date: Optional[Union[str, date]] = None
    Old_User: Optional[str] = None
    Notes: Optional[str] = None
    If_Deleted: Optional[int] = Field(0, ge=0, le=1)
    Windows_Computer_Name: Optional[str] = None

    @field_validator("Asset_Number", mode="before")
    def asset_to_str(cls, value):
        return str(value) if value is not None else value


class ChartPayload(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = ""
    groupBy: str
    groupFilterValue: str = ""
    metric: str
    filterBy: str = ""
    filterValue: str = ""


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


@app.get("/health")
def health():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"]
    return {"ok": True, "db": str(DB_PATH), "items": int(total)}


@app.get("/count")
def count_all(_: Dict[str, Any] = Depends(require_editor)):
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"]
    return {"total": int(total)}


@app.get("/users/me")
def users_me(user: Dict[str, Any] = Depends(get_current_user)):
    return {
        "id": user["id"],
        "username": user["username"],
        "displayName": user["display_name"],
        "roleId": user["role_id"],
        "roleName": user["role_name"],
    }


@app.get("/roles")
def roles(_: Dict[str, Any] = Depends(require_admin)):
    with get_conn() as conn:
        rows = conn.execute("SELECT id,name FROM roles ORDER BY id").fetchall()
    return [{"id": int(row["id"]), "name": row["name"]} for row in rows]


@app.get("/users")
def users(_: Dict[str, Any] = Depends(require_admin)):
    with get_conn() as conn:
        rows = conn.execute("SELECT u.id,u.username,u.display_name,u.role_id,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id ORDER BY u.username").fetchall()
    return [
        {
            "id": int(row["id"]),
            "username": row["username"],
            "displayName": row["display_name"],
            "roleId": int(row["role_id"]),
            "roleName": row["role_name"],
        }
        for row in rows
    ]


@app.post("/users", status_code=201)
def create_user(payload: UserCreateRequest, response: Response, actor: Dict[str, Any] = Depends(require_admin)):
    username = _normalize_user(payload.username)
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM users WHERE LOWER(username)=LOWER(?)", (username,)).fetchone()
        if existing:
            conn.execute("UPDATE users SET role_id=?, display_name=? WHERE id=?", (payload.role_id, payload.display_name, existing["id"]))
            response.status_code = 200
            uid = int(existing["id"])
            action = "update"
        else:
            cur = conn.execute("INSERT INTO users(username,display_name,role_id) VALUES(?,?,?)", (username, payload.display_name, payload.role_id))
            uid = int(cur.lastrowid)
            action = "create"
        _audit(conn, actor["username"], action, "user", str(uid), f"{action} user")
        conn.commit()
        row = conn.execute("SELECT u.id,u.username,u.display_name,u.role_id,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id=?", (uid,)).fetchone()
    return {"id": int(row["id"]), "username": row["username"], "displayName": row["display_name"], "roleId": int(row["role_id"]), "roleName": row["role_name"]}


@app.patch("/users/{user_id}")
def patch_user(user_id: int, payload: UserPatchRequest, actor: Dict[str, Any] = Depends(require_admin)):
    with get_conn() as conn:
        conn.execute("UPDATE users SET role_id=? WHERE id=?", (payload.role_id, user_id))
        if conn.total_changes == 0:
            raise HTTPException(status_code=404, detail={"message": "User not found."})
        _audit(conn, actor["username"], "update", "user", str(user_id), "updated user role")
        conn.commit()
        row = conn.execute("SELECT u.id,u.username,u.display_name,u.role_id,r.name role_name FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id=?", (user_id,)).fetchone()
    return {"id": int(row["id"]), "username": row["username"], "displayName": row["display_name"], "roleId": int(row["role_id"]), "roleName": row["role_name"]}


@app.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, actor: Dict[str, Any] = Depends(require_admin)):
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        if conn.total_changes == 0:
            raise HTTPException(status_code=404, detail={"message": "User not found."})
        _audit(conn, actor["username"], "delete", "user", str(user_id), "deleted user")
        conn.commit()
    return Response(status_code=204)


@app.get("/directory/search")
def directory_search(
    q: Optional[str] = Query(None, min_length=2, max_length=128),
    Prefix: Optional[str] = Query(None, min_length=2, max_length=128),
    prefix: Optional[str] = Query(None, min_length=2, max_length=128),
    _: Dict[str, Any] = Depends(require_editor),
):
    query = (q or Prefix or prefix or "").strip()
    if len(query) < 2:
        return []
    like = f"%{query.lower()}%"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT username,display_name,email FROM directory_users WHERE LOWER(username) LIKE ? OR LOWER(COALESCE(display_name,'')) LIKE ? OR LOWER(COALESCE(email,'')) LIKE ? ORDER BY username LIMIT 25",
            (like, like, like),
        ).fetchall()
    return [{"username": row["username"], "displayName": row["display_name"] or row["username"], "email": row["email"] or ""} for row in rows]


@app.get("/AutoSuggestName")
def auto_suggest(
    Prefix: Optional[str] = Query(None, min_length=2, max_length=128),
    _: Dict[str, Any] = Depends(require_editor),
):
    query = (Prefix or "").strip()
    if len(query) < 2:
        return []
    like = f"%{query.lower()}%"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT username,display_name,email FROM directory_users WHERE LOWER(username) LIKE ? OR LOWER(COALESCE(display_name,'')) LIKE ? OR LOWER(COALESCE(email,'')) LIKE ? ORDER BY username LIMIT 25",
            (like, like, like),
        ).fetchall()
    return [{"DisplayName": row["display_name"] or row["username"], "EMail": row["email"] or "", "Username": row["username"]} for row in rows]


@app.get("/field-parameters")
def field_parameters(_: Dict[str, Any] = Depends(require_editor)):
    with get_conn() as conn:
        fields: Dict[str, List[Dict[str, Any]]] = {}
        for field in CHOICE_FIELDS:
            rows = conn.execute("SELECT param_name,is_active FROM field_params WHERE field_name=? ORDER BY param_name", (field,)).fetchall()
            items = []
            for row in rows:
                usage = 0
                col = FIELD_TO_COL.get(field)
                if col:
                    usage = int(conn.execute(f"SELECT COUNT(*) c FROM items WHERE LOWER(TRIM(COALESCE({col},'')))=LOWER(TRIM(?))", (row["param_name"],)).fetchone()["c"])
                item = {"value": row["param_name"], "usage_count": usage, "managed": True}
                if field == "Status":
                    item["is_active"] = bool(row["is_active"]) if row["is_active"] is not None else True
                items.append(item)
            fields[field] = items
    return {"fields": fields}


@app.post("/field-parameters/{field}", status_code=201)
def create_field_parameter(field: str, payload: Dict[str, Any], actor: Dict[str, Any] = Depends(require_admin)):
    if field not in CHOICE_FIELDS:
        raise HTTPException(status_code=404, detail={"message": "Unknown field."})
    value = str(payload.get("value", "")).strip()
    if not value:
        raise HTTPException(status_code=400, detail={"message": "Value is required."})
    is_active = payload.get("isActive", payload.get("is_active"))
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO field_params(field_name,param_name,is_active) VALUES(?,?,?)",
                (field, value, None if is_active is None else (1 if bool(is_active) else 0)),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail={"message": "Value already exists."})
        _audit(conn, actor["username"], "create", "field_parameter", f"{field}:{value}", "created field parameter")
        conn.commit()
    return {"value": value, "usage_count": 0, "managed": True, "is_active": bool(is_active) if field == "Status" and is_active is not None else None}


@app.put("/field-parameters/{field}")
@app.patch("/field-parameters/{field}")
def update_field_parameter(field: str, payload: Dict[str, Any], actor: Dict[str, Any] = Depends(require_admin)):
    if field not in CHOICE_FIELDS:
        raise HTTPException(status_code=404, detail={"message": "Unknown field."})
    original = str(payload.get("original", "")).strip()
    value = str(payload.get("value", "")).strip()
    update_existing = bool(payload.get("updateExisting", payload.get("update_existing", False)))
    is_active = payload.get("isActive", payload.get("is_active"))
    if not original or not value:
        raise HTTPException(status_code=400, detail={"message": "Values are required."})
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM field_params WHERE field_name=? AND LOWER(param_name)=LOWER(?)", (field, original)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Original value not found."})
        conn.execute("UPDATE field_params SET param_name=?, is_active=? WHERE id=?", (value, None if is_active is None else (1 if bool(is_active) else 0), row["id"]))
        if update_existing:
            col = FIELD_TO_COL.get(field)
            if col:
                conn.execute(f"UPDATE items SET {col}=? WHERE LOWER(TRIM(COALESCE({col},'')))=LOWER(TRIM(?))", (value, original))
        _audit(conn, actor["username"], "update", "field_parameter", f"{field}:{original}", "updated field parameter")
        conn.commit()
    return {"value": value, "usage_count": 0, "managed": True, "is_active": bool(is_active) if field == "Status" and is_active is not None else None}


@app.put("/field-parameters/{field}/{value}")
@app.patch("/field-parameters/{field}/{value}")
def update_field_parameter_by_path(field: str, value: str, payload: Dict[str, Any], actor: Dict[str, Any] = Depends(require_admin)):
    merged = {
        "original": payload.get("original") or value,
        "value": payload.get("value") or value,
        "updateExisting": payload.get("updateExisting", payload.get("update_existing", False)),
        "isActive": payload.get("isActive", payload.get("is_active")),
    }
    return update_field_parameter(field, merged, actor)


@app.delete("/field-parameters/{field}/{value}")
def delete_field_parameter(field: str, value: str, actor: Dict[str, Any] = Depends(require_admin)):
    if field not in CHOICE_FIELDS:
        raise HTTPException(status_code=404, detail={"message": "Unknown field."})
    with get_conn() as conn:
        row = conn.execute("SELECT id,param_name FROM field_params WHERE field_name=? AND LOWER(param_name)=LOWER(?)", (field, value)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Value not found."})
        conn.execute("DELETE FROM field_params WHERE id=?", (row["id"],))
        _audit(conn, actor["username"], "delete", "field_parameter", f"{field}:{row['param_name']}", "deleted field parameter")
        conn.commit()
    return {"value": row["param_name"], "removed": True}


def _item_values(payload: HardwarePayload):
    cap_date = payload.Capitalization_Date
    cap_text = str(cap_date)[:10] if cap_date else None
    return (
        payload.Country, payload.Status, payload.Name_Surname, payload.Identity, payload.Department, payload.Region,
        payload.Hardware_Type, payload.Hardware_Manufacturer, payload.Hardware_Model,
        payload.Hardware_Serial_Number, payload.Asset_Number, cap_text,
        payload.User_Name, payload.Old_User, payload.Windows_Computer_Name, payload.Win_OS,
        payload.Location_Floor, payload.Notes, int(payload.If_Deleted or 0),
    )


@app.post("/items", status_code=201)
def create_item(payload: HardwarePayload, actor: Dict[str, Any] = Depends(require_editor)):
    with get_conn() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO items(
                  country,status,name_surname,identity,department,region,
                  hardware_type,hardware_manufacturer,hardware_model,
                  hardware_serial_number,asset_number,capitalization_date,
                  user_name,old_user,windows_computer_name,win_os,
                  location_floor,notes,if_deleted
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                _item_values(payload),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail={"code": "duplicate_serial", "message": "Serial number already exists."})
        iid = int(cur.lastrowid)
        _audit(conn, actor["username"], "create", "item", str(iid), "created inventory item")
        conn.commit()
    return {"ok": True, "id": iid}


@app.put("/items/{item_ref}")
def update_item(item_ref: str, payload: HardwarePayload, actor: Dict[str, Any] = Depends(require_editor)):
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM items WHERE id=? OR asset_number=? LIMIT 1", (item_ref, item_ref)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Item not found."})
        iid = int(row["id"])
        conn.execute(
            """
            UPDATE items SET
              country=?,status=?,name_surname=?,identity=?,department=?,region=?,
              hardware_type=?,hardware_manufacturer=?,hardware_model=?,
              hardware_serial_number=?,asset_number=?,capitalization_date=?,
              user_name=?,old_user=?,windows_computer_name=?,win_os=?,
              location_floor=?,notes=?,if_deleted=?
            WHERE id=?
            """,
            (*_item_values(payload), iid),
        )
        _audit(conn, actor["username"], "update", "item", str(iid), "updated inventory item")
        conn.commit()
    return {"ok": True, "updated": 1, "id": iid}


@app.delete("/items/{item_ref}")
def delete_item(item_ref: str, actor: Dict[str, Any] = Depends(require_editor)):
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM items WHERE id=? OR asset_number=? LIMIT 1", (item_ref, item_ref)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Item not found."})
        iid = int(row["id"])
        conn.execute("DELETE FROM items WHERE id=?", (iid,))
        _audit(conn, actor["username"], "delete", "item", str(iid), "deleted inventory item")
        conn.commit()
    return {"ok": True, "deleted": 1}


@app.get("/rows")
def rows(
    country: Optional[str] = None,
    status: Optional[str] = None,
    name_surname: Optional[str] = None,
    identity: Optional[str] = None,
    department: Optional[str] = None,
    region: Optional[str] = None,
    hardware_type: Optional[str] = None,
    hardware_manufacturer: Optional[str] = None,
    hardware_model: Optional[str] = None,
    win_os: Optional[str] = None,
    user_name: Optional[str] = None,
    old_user: Optional[str] = None,
    windows_computer_name: Optional[str] = None,
    location_floor: Optional[str] = None,
    notes: Optional[str] = None,
    hardware_serial_number: Optional[str] = None,
    asset_number: Optional[str] = None,
    if_deleted: Optional[int] = Query(0, ge=0, le=1),
    age_min: float = Query(0, ge=0),
    age_max: float = Query(1000, ge=0),
    capitalization_date_from: Optional[str] = None,
    capitalization_date_to: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000000),
    offset: int = Query(0, ge=0),
    _: Dict[str, Any] = Depends(require_editor),
):
    filters = []
    params: List[Any] = []

    def like(col: str, val: Optional[str]):
        if val and val.strip():
            filters.append(f"LOWER(COALESCE({col},'')) LIKE ?")
            params.append(f"%{val.strip().lower()}%")

    like("country", country)
    like("status", status)
    like("name_surname", name_surname)
    like("identity", identity)
    like("department", department)
    like("region", region)
    like("hardware_type", hardware_type)
    like("hardware_manufacturer", hardware_manufacturer)
    like("hardware_model", hardware_model)
    like("win_os", win_os)
    like("user_name", user_name)
    like("old_user", old_user)
    like("windows_computer_name", windows_computer_name)
    like("location_floor", location_floor)
    like("notes", notes)
    like("hardware_serial_number", hardware_serial_number)
    like("asset_number", asset_number)

    if if_deleted is not None:
        filters.append("if_deleted = ?")
        params.append(int(if_deleted))

    age_expr = "(julianday('now') - julianday(capitalization_date)) / 365.25"
    filters.append(f"COALESCE({age_expr},0) >= ?")
    params.append(age_min)
    filters.append(f"COALESCE({age_expr},0) <= ?")
    params.append(age_max)

    if capitalization_date_from:
        filters.append("date(capitalization_date) >= date(?)")
        params.append(capitalization_date_from)
    if capitalization_date_to:
        filters.append("date(capitalization_date) <= date(?)")
        params.append(capitalization_date_to)

    where_sql = "WHERE " + " AND ".join(filters) if filters else ""

    sql = f"""
    SELECT
      id ID,
      country Country,
      status Status,
      name_surname Name_Surname,
      identity Identity,
      department Department,
      region Region,
      hardware_type Hardware_Type,
      hardware_manufacturer Hardware_Manufacturer,
      hardware_model Hardware_Model,
      hardware_serial_number Hardware_Serial_Number,
      asset_number Asset_Number,
      capitalization_date Capitalization_Date,
      user_name User_Name,
      old_user Old_User,
      windows_computer_name Windows_Computer_Name,
      win_os Win_OS,
      location_floor Location_Floor,
      notes Notes,
      if_deleted If_Deleted,
      ROUND({age_expr}, 1) Age
    FROM items
    {where_sql}
    ORDER BY id DESC
    LIMIT ? OFFSET ?
    """

    with get_conn() as conn:
        rows = conn.execute(sql, (*params, limit, offset)).fetchall()
        total = conn.execute(f"SELECT COUNT(*) c FROM items {where_sql}", tuple(params)).fetchone()["c"]
    return {"items": [dict(row) for row in rows], "count": int(total)}


@app.get("/spare_ratios")
def spare_ratios(_: Dict[str, Any] = Depends(require_editor)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT COALESCE(country,'N/A') country, COUNT(*) total, SUM(CASE WHEN LOWER(COALESCE(status,''))='in inventory' THEN 1 ELSE 0 END) spare FROM items GROUP BY COALESCE(country,'N/A') ORDER BY country"
        ).fetchall()
    payload = []
    for row in rows:
        total = int(row["total"] or 0)
        spare = int(row["spare"] or 0)
        ratio = (spare / total) if total else 0
        payload.append({"country": row["country"], "total": total, "spare": spare, "ratio": ratio, "ratio_pct": round(ratio * 100, 2)})
    return {"items": payload, "count": len(payload)}


@app.get("/charts")
def get_charts(_: Dict[str, Any] = Depends(require_editor)):
    with get_conn() as conn:
        rows = conn.execute("SELECT id,title,group_by,group_filter_value,metric,filter_by,filter_value FROM charts ORDER BY created_at,id").fetchall()
    return [{"id": row["id"], "title": row["title"] or "", "groupBy": row["group_by"], "groupFilterValue": row["group_filter_value"] or "", "metric": row["metric"], "filterBy": row["filter_by"], "filterValue": row["filter_value"]} for row in rows]


@app.post("/charts", status_code=201)
def create_chart(payload: ChartPayload, actor: Dict[str, Any] = Depends(require_editor)):
    metric = (payload.metric or "").strip().lower()
    if metric not in {"count", "ratio"}:
        raise HTTPException(status_code=400, detail={"message": "metric must be count or ratio"})
    cid = payload.id or str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO charts(id,title,group_by,group_filter_value,metric,filter_by,filter_value) VALUES(?,?,?,?,?,?,?)",
            (cid, payload.title or "", payload.groupBy, payload.groupFilterValue or "", metric, payload.filterBy or "", payload.filterValue or ""),
        )
        _audit(conn, actor["username"], "create", "chart", cid, "created chart")
        conn.commit()
    return {"id": cid, "title": payload.title or "", "groupBy": payload.groupBy, "groupFilterValue": payload.groupFilterValue or "", "metric": metric, "filterBy": payload.filterBy or "", "filterValue": payload.filterValue or ""}


@app.put("/charts/{chart_id}")
def update_chart(chart_id: str, payload: ChartPayload, actor: Dict[str, Any] = Depends(require_editor)):
    metric = (payload.metric or "").strip().lower()
    if metric not in {"count", "ratio"}:
        raise HTTPException(status_code=400, detail={"message": "metric must be count or ratio"})
    with get_conn() as conn:
        conn.execute(
            "UPDATE charts SET title=?, group_by=?, group_filter_value=?, metric=?, filter_by=?, filter_value=? WHERE id=?",
            (payload.title or "", payload.groupBy, payload.groupFilterValue or "", metric, payload.filterBy or "", payload.filterValue or "", chart_id),
        )
        if conn.total_changes == 0:
            raise HTTPException(status_code=404, detail={"message": "Chart not found."})
        _audit(conn, actor["username"], "update", "chart", chart_id, "updated chart")
        conn.commit()
    return {"id": chart_id, "title": payload.title or "", "groupBy": payload.groupBy, "groupFilterValue": payload.groupFilterValue or "", "metric": metric, "filterBy": payload.filterBy or "", "filterValue": payload.filterValue or ""}


@app.delete("/charts/{chart_id}", status_code=204)
def delete_chart(chart_id: str, actor: Dict[str, Any] = Depends(require_editor)):
    with get_conn() as conn:
        conn.execute("DELETE FROM charts WHERE id=?", (chart_id,))
        if conn.total_changes == 0:
            raise HTTPException(status_code=404, detail={"message": "Chart not found."})
        _audit(conn, actor["username"], "delete", "chart", chart_id, "deleted chart")
        conn.commit()
    return Response(status_code=204)


@app.get("/audit-trail")
def audit_trail(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), _: Dict[str, Any] = Depends(require_admin)):
    with get_conn() as conn:
        rows = conn.execute("SELECT id,actor,action,entity_type,entity_id,summary,created_at FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return {"items": [dict(row) for row in rows], "count": len(rows)}


@app.post("/chat")
def chat(payload: ChatRequest, _: Dict[str, Any] = Depends(require_editor)):
    return {"answer": "Demo chat endpoint is active in portfolio mode.", "data": {"question": payload.question}}

