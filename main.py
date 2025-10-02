# main.py

from fastapi import FastAPI, Query, HTTPException
from typing import Optional, Union
from pydantic import BaseModel, Field, field_validator
from database import get_conn
from datetime import date
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="IT Inventory API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PARAM_FILTERS = {
    "country": ("[Country]", "exact"),
    "status": ("[Status]", "exact"),
    "name_surname": ("[Name_Surname]", "like"),
    "identity": ("[Identity]", "exact"),
    "department": ("[Department]", "exact"),
    "region": ("[Region]", "exact"),
    "hardware_type": ("[Hardware_Type]", "exact"),
    "hardware_manufacturer": ("[Hardware_Manufacturer]", "exact"),
    "hardware_model": ("[Hardware_Model]", "exact"),
    "win_os": ("[Win_OS]", "exact"),
    "user_name": ("[User_Name]", "like"),
    "old_user": ("[Old_User]", "like"),
    "windows_computer_name": ("[Windows_Computer_Name]", "like"),
    "location_floor": ("[Location/Floor]", "like"),
    "notes": ("[Notes]", "like"),
    "hardware_serial_number": ("[Hardware_Serial_Number]", "like"),
    "asset_number": ("[Asset_Number]", "like"),
    "if_deleted": ("[If_Deleted]", "exact"),
}

COUNTRY_ALIASES = {
    "tr": "TR",
    "turkey": "TR",
    "turkiye": "TR",
    "sa": "SA",
    "ksa": "SA",
    "saudi arabia": "SA",
    "the kingdom of saudi arabia": "SA",
    "kingdom of saudi arabia": "SA",
    "suudi arabistan": "SA",
    "jo": "JO",
    "jordan": "JO",
    "jordania": "JO",
    "jordanya": "JO",
    "hashemite kingdom of jordan": "JO",
    "il": "IL",
    "israel": "IL",
    "state of israel": "IL",
    "israil": "IL",
    "ae": "AE",
    "uae": "AE",
    "u.a.e": "AE",
    "united arab emirates": "AE",
    "birlesik arap emirlikleri": "AE",
}

SEARCHABLE_COLUMNS = {
    "Country": ("[Country]", "like"),
    "Status": ("[Status]", "like"),
    "Name_Surname": ("[Name_Surname]", "like"),
    "Identity": ("[Identity]", "like"),
    "Department": ("[Department]", "like"),
    "Region": ("[Region]", "like"),
    "Hardware_Type": ("[Hardware_Type]", "like"),
    "Hardware_Manufacturer": ("[Hardware_Manufacturer]", "like"),
    "Hardware_Model": ("[Hardware_Model]", "like"),
    "Hardware_Serial_Number": ("[Hardware_Serial_Number]", "like"),
    "Asset_Number": ("[Asset_Number]", "like"),
    "Capitalization_Date": ("[Capitalization_Date]", "date_like"),
    "User_Name": ("[User_Name]", "like"),
    "Old_User": ("[Old_User]", "like"),
    "Windows_Computer_Name": ("[Windows_Computer_Name]", "like"),
    "Win_OS": ("[Win_OS]", "like"),
    "Location_Floor": ("[Location/Floor]", "like"),
    "Notes": ("[Notes]", "like"),
    "If_Deleted": ("[If_Deleted]", "exact"),
    "Age": ("[Age]", "number"),
}

SEARCHABLE_COLUMN_LOOKUP = {
    key.lower(): value for key, value in SEARCHABLE_COLUMNS.items()
}
SEARCHABLE_COLUMN_LOOKUP.update(
    {
        key.replace("_", " ").lower(): value
        for key, value in SEARCHABLE_COLUMNS.items()
    }
)

def _append_filter(clauses, params, column_sql, operator, raw_value):
    if raw_value is None:
        return

    if isinstance(raw_value, str):
        value = raw_value.strip()
    else:
        value = raw_value

    if value is None or value == "":
        return

    if operator == "exact":
        clauses.append(f"{column_sql} = ?")
        params.append(value)
    elif operator == "like":
        clauses.append(f"{column_sql} LIKE ?")
        params.append(f"%{value}%")
    elif operator == "number":
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid numeric search value.")
        clauses.append(f"{column_sql} = ?")
        params.append(numeric_value)
    elif operator == "date_gte":
        clauses.append(f"{column_sql} >= TRY_CONVERT(date, ?, 23)")
        params.append(value)
    elif operator == "date_lte":
        clauses.append(f"{column_sql} <= TRY_CONVERT(date, ?, 23)")
        params.append(value)
    elif operator == "date_like":
        clauses.append(f"CONVERT(varchar(10), {column_sql}, 23) LIKE ?")
        params.append(f"%{value}%")
    else:
        raise HTTPException(status_code=400, detail="Unsupported filter operator.")

def _normalise_country_code(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        key = value.strip().lower()
        if not key:
            return None
        return COUNTRY_ALIASES.get(key, value.strip().upper())
    return str(value).strip().upper()

# -----------------------------
# server ve db ayakta m?
# -----------------------------
@app.get("/health")
def health():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT @@SERVERNAME, DB_NAME()")
        server, db = cur.fetchone()
    return {"ok": True, "server": server, "db": db}

@app.get("/count")
def count_all():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM [dbo].[ITHardware]")
        total = cur.fetchone()[0]
    return {"total": total}

# -----------------------------
# Yeni kay?t olu?turma (POST)
# -----------------------------
class HardwareCreate(BaseModel):
    Country: str = Field(..., min_length=2, max_length=2)
    Name_Surname: str = Field(..., max_length=50)
    Identity: str = Field(..., max_length=10)
    Region: str = Field(..., max_length=8)
    Win_OS: str = Field(..., max_length=15)
    Hardware_Type: str = Field(..., max_length=20)
    Hardware_Manufacturer: str = Field(..., max_length=60)
    Windows_Computer_Name: str = Field(..., max_length=100)
    User_Name: str = Field(..., max_length=30)
    Hardware_Serial_Number: str = Field(..., max_length=50)
    Asset_Number: str = Field(..., max_length=50)

    Status: Optional[str] = Field(None, max_length=30)
    Department: Optional[str] = Field(None, max_length=50)
    Hardware_Model: Optional[str] = Field(None, max_length=60)
    Location_Floor: Optional[str] = Field(None, max_length=100)
    Capitalization_Date: Optional[Union[str, date]] = Field(None, description="YYYY-MM-DD")
    Old_User: Optional[str] = None
    Notes: Optional[str] = None

    # INSERT edilemeyen/computed gibi davranan alan
    Age: Optional[float] = Field(None, ge=0)

    @field_validator("Asset_Number", mode="before")
    def coerce_asset_to_str(cls, v):
        return str(v) if v is not None else v

    @field_validator("Capitalization_Date", mode="before")
    def coerce_date_to_iso(cls, v):
        try:
            if isinstance(v, date):
                return v.isoformat()
        except Exception:
            pass
        return v

@app.post("/items")
def create_item(payload: HardwareCreate):
    sql = """
    INSERT INTO [dbo].[ITHardware] (
        Country, Status, Name_Surname, [Identity], Department, Region,
        Hardware_Type, Hardware_Manufacturer, Hardware_Model,
        Hardware_Serial_Number, Asset_Number,
        Capitalization_Date, User_Name, Old_User,
        Windows_Computer_Name, Win_OS, [Location/Floor], Notes,
        If_Deleted
    )
    VALUES (
        ?, ?, ?, ?, ?, ?,
        ?, ?, ?,
        ?, ?,
        TRY_CONVERT(date, ?, 23), ?, ?,
        ?, ?, ?, ?,
        ?
    );
    """

    params = [
        payload.Country, payload.Status, payload.Name_Surname, payload.Identity,
        payload.Department, payload.Region,
        payload.Hardware_Type, payload.Hardware_Manufacturer, payload.Hardware_Model,
        payload.Hardware_Serial_Number, payload.Asset_Number,
        payload.Capitalization_Date, payload.User_Name, payload.Old_User,
        payload.Windows_Computer_Name, payload.Win_OS, payload.Location_Floor, payload.Notes,
        0  # If_Deleted = false
    ]

    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            conn.commit()
            try:
                cur.execute("SELECT SCOPE_IDENTITY()")
                new_id = cur.fetchone()[0]
            except Exception:
                new_id = None
            return {"ok": True, "id": new_id}
        except Exception as e:
            return {"ok": False, "error": str(e), "params": params}

# -------------------------------------------
# ?lke baz?nda spare oranlar?
# -------------------------------------------
@app.get("/spare_ratios")
def spare_ratios():
    sql = """
    SELECT
        Country,
        COUNT(*) AS total,
        SUM(CASE WHEN Status = 'In Inventory' THEN 1 ELSE 0 END) AS spare
    FROM [dbo].[ITHardware]
    GROUP BY Country
    ORDER BY Country;
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        rows = []
        for country, total, spare in cur.fetchall():
            total = total or 0
            spare = spare or 0
            ratio = (spare / total) if total > 0 else 0
            rows.append({
                "country": country,
                "total": total,
                "spare": spare,
                "ratio": ratio,
                "ratio_pct": round(ratio * 100, 2)
            })
    return {"items": rows, "count": len(rows)}

# -------------------------------------------
# Filtreli listeleme (paging + toplam)
# -------------------------------------------
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
    cap_from: Optional[str] = None,
    cap_to: Optional[str] = None,
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    column: Optional[str] = None,
    search: Optional[str] = None,
):
    if age_min > age_max:
        raise HTTPException(status_code=400, detail="age_min cannot be greater than age_max.")

    normalised_country = _normalise_country_code(country)

    filter_values = {
        "country": normalised_country,
        "status": status,
        "name_surname": name_surname,
        "identity": identity,
        "department": department,
        "region": region,
        "hardware_type": hardware_type,
        "hardware_manufacturer": hardware_manufacturer,
        "hardware_model": hardware_model,
        "win_os": win_os,
        "user_name": user_name,
        "old_user": old_user,
        "windows_computer_name": windows_computer_name,
        "location_floor": location_floor,
        "notes": notes,
        "hardware_serial_number": hardware_serial_number,
        "asset_number": asset_number,
        "if_deleted": if_deleted,
    }

    where_clauses = ["([Age] IS NULL OR TRY_CONVERT(float, NULLIF(LTRIM(RTRIM(CAST([Age] AS nvarchar(64)))), '')) BETWEEN ? AND ?)"]
    params = [age_min, age_max]

    def add_filter(column_sql: str, operator: str, raw_value):
        _append_filter(where_clauses, params, column_sql, operator, raw_value)

    add_filter("[Capitalization_Date]", "date_gte", cap_from)
    add_filter("[Capitalization_Date]", "date_lte", cap_to)

    for key, (column_sql, operator) in PARAM_FILTERS.items():
        add_filter(column_sql, operator, filter_values.get(key))

    search_key = (column or "").strip().lower()
    search_value = (search or "").strip()
    if search_value and search_key:
        lookup_key = search_key
        search_column_info = SEARCHABLE_COLUMN_LOOKUP.get(lookup_key)
        if not search_column_info:
            search_column_info = SEARCHABLE_COLUMN_LOOKUP.get(lookup_key.replace("_", " "))
        if search_column_info:
            column_sql, operator = search_column_info
            _append_filter(where_clauses, params, column_sql, operator, search_value)

    where_sql = " AND ".join(["1=1", *where_clauses])

    select_sql = f"""
        SELECT
          Country,
          Status,
          Name_Surname,
          [Identity],
          Department,
          Region,
          Hardware_Type,
          Hardware_Manufacturer,
          Hardware_Model,
          Hardware_Serial_Number,
          Asset_Number,
          Capitalization_Date,
          Age,
          User_Name,
          Old_User,
          Windows_Computer_Name,
          Win_OS,
          [Location/Floor] AS Location_Floor,
          Notes,
          [If_Deleted] AS If_Deleted
        FROM [dbo].[ITHardware]
        WHERE {where_sql}
        ORDER BY
          Capitalization_Date DESC,
          Country ASC,
          Name_Surname ASC
        OFFSET CAST(? AS INT) ROWS FETCH NEXT CAST(? AS INT) ROWS ONLY;
        """

    count_sql = f"""
    SELECT COUNT(*)
    FROM [dbo].[ITHardware]
    WHERE {where_sql};
    """

    base_params = list(params)
    count_params = base_params.copy()
    page_params = base_params + [int(offset), int(limit)]

    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(count_sql, count_params)
            total_count = cur.fetchone()[0]

            cur.execute(select_sql, page_params)
            cols = [c[0] for c in cur.description]
            data = [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": str(e),
                    "where": where_sql,
                    "params": base_params,
                    "search": {"column": column, "search": search_value},
                    "offset": offset,
                    "limit": limit,
                },
            ) from e

    return {
        "items": data,
        "page_count": len(data),
        "total_count": total_count,
        "limit": int(limit),
        "offset": int(offset),
        "count": total_count,
    }

