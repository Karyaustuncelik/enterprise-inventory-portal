# main.py

from fastapi import FastAPI, Query, HTTPException
from typing import Optional, Union, List, Dict
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


def _clean_text(value, upper: bool = False):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.upper() if upper else text


def _clean_date(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_flag(value) -> int:
    if value in (1, "1", True, "true", "True"):
        return 1
    return 0


def _prepare_payload_dict(payload):
    return {
        "Country": _clean_text(getattr(payload, "Country", None), upper=True),
        "Status": _clean_text(getattr(payload, "Status", None)),
        "Name_Surname": _clean_text(getattr(payload, "Name_Surname", None)),
        "Identity": _clean_text(getattr(payload, "Identity", None)),
        "Department": _clean_text(getattr(payload, "Department", None)),
        "Region": _clean_text(getattr(payload, "Region", None)),
        "Hardware_Type": _clean_text(getattr(payload, "Hardware_Type", None)),
        "Hardware_Manufacturer": _clean_text(getattr(payload, "Hardware_Manufacturer", None)),
        "Hardware_Model": _clean_text(getattr(payload, "Hardware_Model", None)),
        "Hardware_Serial_Number": _clean_text(getattr(payload, "Hardware_Serial_Number", None)),
        "Asset_Number": _clean_text(getattr(payload, "Asset_Number", None)),
        "Capitalization_Date": _clean_date(getattr(payload, "Capitalization_Date", None)),
        "User_Name": _clean_text(getattr(payload, "User_Name", None)),
        "Old_User": _clean_text(getattr(payload, "Old_User", None)),
        "Windows_Computer_Name": _clean_text(getattr(payload, "Windows_Computer_Name", None)),
        "Win_OS": _clean_text(getattr(payload, "Win_OS", None)),
        "Location_Floor": _clean_text(getattr(payload, "Location_Floor", None)),
        "Notes": _clean_text(getattr(payload, "Notes", None)),
        "If_Deleted": _normalize_flag(getattr(payload, "If_Deleted", 0)),
    }


def _prepare_payload_params(payload):
    data = _prepare_payload_dict(payload)
    for field in REQUIRED_DB_STR_FIELDS:
        if data.get(field) is None:
            data[field] = ""
    return data, [
        data["Country"],
        data["Status"],
        data["Name_Surname"],
        data["Identity"],
        data["Department"],
        data["Region"],
        data["Hardware_Type"],
        data["Hardware_Manufacturer"],
        data["Hardware_Model"],
        data["Hardware_Serial_Number"],
        data["Asset_Number"],
        data["Capitalization_Date"],
        data["User_Name"],
        data["Old_User"],
        data["Windows_Computer_Name"],
        data["Win_OS"],
        data["Location_Floor"],
        data["Notes"],
        data["If_Deleted"],
    ]


WRITE_COLUMN_SQL = {
    "Country": "[Country]",
    "Status": "[Status]",
    "Name_Surname": "[Name_Surname]",
    "Identity": "[Identity]",
    "Department": "[Department]",
    "Region": "[Region]",
    "Hardware_Type": "[Hardware_Type]",
    "Hardware_Manufacturer": "[Hardware_Manufacturer]",
    "Hardware_Model": "[Hardware_Model]",
    "Hardware_Serial_Number": "[Hardware_Serial_Number]",
    "Asset_Number": "[Asset_Number]",
    "Capitalization_Date": "[Capitalization_Date]",
    "User_Name": "[User_Name]",
    "Old_User": "[Old_User]",
    "Windows_Computer_Name": "[Windows_Computer_Name]",
    "Win_OS": "[Win_OS]",
    "Location_Floor": "[Location/Floor]",
    "Notes": "[Notes]",
    "If_Deleted": "[If_Deleted]",
}


REQUIRED_DB_STR_FIELDS = {
    "Identity",
    "Region",
    "Hardware_Type",
    "Hardware_Manufacturer",
    "Windows_Computer_Name",
    "Win_OS",
    "User_Name",
}


def _build_exact_match_sql(cleaned):
    clauses = []
    params: List[object] = []
    for key, column_sql in WRITE_COLUMN_SQL.items():
        value = cleaned.get(key)
        if value is None:
            clauses.append(f"{column_sql} IS NULL")
        else:
            clauses.append(f"{column_sql} = ?")
            params.append(value)
    where = " AND ".join(clauses) if clauses else "1=1"
    return where, params


UPDATE_ITEM_SQL = """
UPDATE [dbo].[ITHardware]
SET
  Country = ?,
  Status = ?,
  Name_Surname = ?,
  [Identity] = ?,
  Department = ?,
  Region = ?,
  Hardware_Type = ?,
  Hardware_Manufacturer = ?,
  Hardware_Model = ?,
  Hardware_Serial_Number = ?,
  Asset_Number = ?,
  Capitalization_Date = TRY_CONVERT(date, ?, 23),
  User_Name = ?,
  Old_User = ?,
  Windows_Computer_Name = ?,
  Win_OS = ?,
  [Location/Floor] = ?,
  Notes = ?,
  If_Deleted = ?
WHERE {where_clause};
"""


PARAM_FILTERS = {
    "country": ("[Country]", "like"),
    "status": ("[Status]", "like"),
    "name_surname": ("[Name_Surname]", "like"),
    "identity": ("[Identity]", "like"),
    # Department yalnızca kod kısmına göre filtrelensin
    "department": ("[Department]", "dept_code_like"),
    "region": ("[Region]", "like"),
    "hardware_type": ("[Hardware_Type]", "like"),
    "hardware_manufacturer": ("[Hardware_Manufacturer]", "like"),
    "hardware_model": ("[Hardware_Model]", "like"),
    "win_os": ("[Win_OS]", "like"),
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
    # Global column search'ta da Department kodu baz alınsın
    "Department": ("[Department]", "dept_code_like"),
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

CHOICE_FIELDS = [
    "Country",
    "Department",
    "Hardware_Manufacturer",
    "Hardware_Model",
    "Hardware_Type",
    "Identity",
    "Location_Floor",
    "Region",
    "Status",
    "Win_OS",
]

CHOICE_FIELD_LOOKUP = {field.lower(): field for field in CHOICE_FIELDS}
FIELD_PARAM_COLUMN_SQL = {
    "Country": "[Country]",
    "Department": "[Department]",
    "Hardware_Manufacturer": "[Hardware_Manufacturer]",
    "Hardware_Model": "[Hardware_Model]",
    "Hardware_Type": "[Hardware_Type]",
    "Identity": "[Identity]",
    "Location_Floor": "[Location/Floor]",
    "Region": "[Region]",
    "Status": "[Status]",
    "Win_OS": "[Win_OS]",
}


class FieldParamItem(BaseModel):
    value: str
    usage_count: int
    managed: bool = True


class FieldParametersResponse(BaseModel):
    fields: Dict[str, List[FieldParamItem]]


class FieldParamCreate(BaseModel):
    value: str = Field(..., min_length=1, max_length=255)

    @field_validator("value")
    def normalise_value(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("Value cannot be empty.")
        return value


class FieldParamUpdate(BaseModel):
    original: str = Field(..., min_length=1, max_length=255)
    value: str = Field(..., min_length=1, max_length=255)
    update_existing: bool = True

    @field_validator("original", "value")
    def normalise_update_values(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("Value cannot be empty.")
        return value


def _ensure_choice_field(field: str) -> str:
    if not field:
        raise HTTPException(status_code=404, detail="Field name is required.")
    key = field.strip().lower()
    canonical = CHOICE_FIELD_LOOKUP.get(key)
    if not canonical:
        raise HTTPException(status_code=404, detail=f"Unsupported field '{field}'.")
    return canonical


def _normalise_param_value(value: str) -> str:
    trimmed = (value or "").strip()
    if not trimmed:
        raise HTTPException(status_code=400, detail="Value cannot be empty.")
    return trimmed


def _field_column_sql(field: str) -> str:
    try:
        return FIELD_PARAM_COLUMN_SQL[field]
    except KeyError as exc:
        raise HTTPException(status_code=500, detail=f"Missing column mapping for field '{field}'.") from exc


def _get_usage_count(conn, field: str, value: str) -> int:
    column_sql = _field_column_sql(field)
    trim_expr = f"LTRIM(RTRIM({column_sql}))"
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM [dbo].[ITHardware] WHERE {trim_expr} = ?", value)
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _fetch_field_params(conn, field: str) -> List[Dict[str, object]]:
    canonical = _ensure_choice_field(field)
    column_sql = _field_column_sql(canonical)
    managed_values: List[str] = []
    cur = conn.cursor()
    cur.execute("SELECT ParamName FROM FieldParams WHERE FieldName = ? ORDER BY ParamName ASC", canonical)
    for (raw_value,) in cur.fetchall():
        value = (raw_value or "").strip()
        if value and value not in managed_values:
            managed_values.append(value)
    trim_expr = f"LTRIM(RTRIM({column_sql}))"
    usage_counts: Dict[str, int] = {}
    cur.execute(f"SELECT {trim_expr} AS ParamValue, COUNT(*) FROM [dbo].[ITHardware] GROUP BY {trim_expr}")
    for raw_value, count in cur.fetchall():
        value = (raw_value or "").strip()
        if not value:
            continue
        usage_counts[value] = int(count)
    items: List[Dict[str, object]] = []
    seen = set()
    for value in managed_values:
        usage = usage_counts.get(value, 0)
        items.append({"value": value, "usage_count": usage, "managed": True})
        seen.add(value)
    for value, usage in usage_counts.items():
        if value not in seen:
            items.append({"value": value, "usage_count": usage, "managed": False})
    items.sort(key=lambda item: (0 if item.get("managed") else 1, item["value"].lower()))
    return items


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
        text_value = str(value)
        # Trim + upper ile sağlamlaştır
        clauses.append(f"UPPER(LTRIM(RTRIM({column_sql}))) LIKE ?")
        params.append(f"%{text_value.upper()}%")

    elif operator == "dept_code_like":
        # "HCB - Henkel Consumer Brands" -> "HCB"
        code_expr = f"""
            UPPER(LTRIM(RTRIM(
                CASE
                    WHEN CHARINDEX('-', {column_sql}) > 0
                        THEN LEFT({column_sql}, CHARINDEX('-', {column_sql}) - 1)
                    ELSE {column_sql}
                END
            )))
        """
        text_value = str(value).strip().upper()
        if not text_value:
            return
        clauses.append(f"{code_expr} LIKE ?")
        params.append(f"%{text_value}%")

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
# server ve db ayakta mı?
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

@app.get("/field-parameters", response_model=FieldParametersResponse)
def list_field_parameters():
    with get_conn() as conn:
        fields = {field: _fetch_field_params(conn, field) for field in CHOICE_FIELDS}
    return {"fields": fields}


@app.get("/field-parameters/{field}", response_model=List[FieldParamItem])
def get_field_parameters(field: str):
    canonical = _ensure_choice_field(field)
    with get_conn() as conn:
        return _fetch_field_params(conn, canonical)


@app.post("/field-parameters/{field}", response_model=FieldParamItem, status_code=201)
def create_field_parameter(field: str, payload: FieldParamCreate):
    canonical = _ensure_choice_field(field)
    value = payload.value
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM FieldParams WHERE FieldName = ? AND UPPER(LTRIM(RTRIM(ParamName))) = UPPER(?)",
            canonical,
            value,
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="This value already exists for the selected field.")
        cur.execute("INSERT INTO FieldParams (FieldName, ParamName) VALUES (?, ?)", canonical, value)
        conn.commit()
        usage_count = _get_usage_count(conn, canonical, value)
    return {"value": value, "usage_count": usage_count, "managed": True}


@app.put("/field-parameters/{field}", response_model=FieldParamItem)
def update_field_parameter(field: str, payload: FieldParamUpdate):
    canonical = _ensure_choice_field(field)
    original = payload.original
    new_value = payload.value
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT ParamName FROM FieldParams WHERE FieldName = ? AND RTRIM(LTRIM(ParamName)) = ?",
            canonical,
            original,
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="The specified value was not found.")
        stored_original = row[0]
        if new_value.lower() != original.lower():
            cur.execute(
                "SELECT 1 FROM FieldParams WHERE FieldName = ? AND UPPER(LTRIM(RTRIM(ParamName))) = UPPER(?)",
                canonical,
                new_value,
            )
            existing = cur.fetchone()
            if existing:
                raise HTTPException(status_code=409, detail="Another parameter already uses this value.")
        cur.execute(
            "UPDATE FieldParams SET ParamName = ? WHERE FieldName = ? AND ParamName = ?",
            new_value,
            canonical,
            stored_original,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Value update failed.")
        if payload.update_existing and new_value.lower() != original.lower():
            column_sql = _field_column_sql(canonical)
            trim_expr = f"LTRIM(RTRIM({column_sql}))"
            cur.execute(
                f"UPDATE [dbo].[ITHardware] SET {column_sql} = ? WHERE {trim_expr} = ?",
                new_value,
                stored_original.strip(),
            )
        conn.commit()
        usage_count = _get_usage_count(conn, canonical, new_value)
    return {"value": new_value, "usage_count": usage_count, "managed": True}


@app.delete("/field-parameters/{field}/{value}")
def delete_field_parameter(
    field: str,
    value: str,
    force: bool = Query(False),
    replacement: Optional[str] = Query(None),
):
    canonical = _ensure_choice_field(field)
    target_value = _normalise_param_value(value)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT ParamName FROM FieldParams WHERE FieldName = ? AND RTRIM(LTRIM(ParamName)) = ?",
            canonical,
            target_value,
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Value not found.")
        stored_value = row[0]
        usage_count = _get_usage_count(conn, canonical, stored_value.strip())
        applied_replacement: Optional[str] = None
        column_sql = _field_column_sql(canonical)
        trim_expr = f"LTRIM(RTRIM({column_sql}))"
        affected = 0
        if usage_count > 0:
            if replacement:
                replacement_value = _normalise_param_value(replacement)
                cur.execute(
                    "SELECT ParamName FROM FieldParams WHERE FieldName = ? AND RTRIM(LTRIM(ParamName)) = ?",
                    canonical,
                    replacement_value,
                )
                rep_row = cur.fetchone()
                if not rep_row:
                    raise HTTPException(status_code=404, detail="Replacement value is not registered.")
                applied_replacement = rep_row[0].strip()
                if applied_replacement.lower() == stored_value.strip().lower():
                    raise HTTPException(status_code=400, detail="Replacement must be different from the removed value.")
                cur.execute(
                    f"UPDATE [dbo].[ITHardware] SET {column_sql} = ? WHERE {trim_expr} = ?",
                    applied_replacement,
                    stored_value.strip(),
                )
                affected = cur.rowcount
            elif force:
                cur.execute(
                    f"UPDATE [dbo].[ITHardware] SET {column_sql} = NULL WHERE {trim_expr} = ?",
                    stored_value.strip(),
                )
                affected = cur.rowcount
            else:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": f"Cannot delete '{stored_value.strip()}' while it is used in {usage_count} records.",
                        "usage_count": usage_count,
                        "requires_replacement": True,
                    },
                )
        cur.execute(
            "DELETE FROM FieldParams WHERE FieldName = ? AND ParamName = ?",
            canonical,
            stored_value,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Deletion failed.")
        conn.commit()
    return {
        "value": stored_value.strip(),
        "removed": True,
        "affected_records": affected,
        "replacement": applied_replacement,
        "usage_before": usage_count,
    }


# -----------------------------
# Yeni kayıt oluşturma (POST)
# -----------------------------
class HardwareCreate(BaseModel):
    Name_Surname: str = Field(..., min_length=1, max_length=50)
    Hardware_Serial_Number: str = Field(..., min_length=1, max_length=50)
    Asset_Number: str = Field(..., min_length=1, max_length=50)

    Country: str = Field(..., min_length=2, max_length=2)
    Identity: Optional[str] = Field(None, max_length=10)
    Region: Optional[str] = Field(None, max_length=8)
    Win_OS: Optional[str] = Field(None, max_length=15)
    Hardware_Type: Optional[str] = Field(None, max_length=20)
    Hardware_Manufacturer: Optional[str] = Field(None, max_length=60)
    Windows_Computer_Name: Optional[str] = Field(None, max_length=100)
    User_Name: Optional[str] = Field(None, max_length=30)

    Status: Optional[str] = Field(None, max_length=30)
    Department: Optional[str] = Field(None, max_length=50)
    Hardware_Model: Optional[str] = Field(None, max_length=60)
    Location_Floor: Optional[str] = Field(None, max_length=100)
    Capitalization_Date: Optional[Union[str, date]] = Field(None, description="YYYY-MM-DD")
    Old_User: Optional[str] = None
    Notes: Optional[str] = None
    If_Deleted: Optional[int] = Field(0, ge=0, le=1)

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

@app.post("/items", status_code=201)
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

    cleaned, params = _prepare_payload_params(payload)

    with get_conn() as conn:
        cur = conn.cursor()
        try:
            # Duplicate serial check
            serial = cleaned.get("Hardware_Serial_Number")
            if serial:
                cur.execute(
                    "SELECT TOP 1 ID FROM [dbo].[ITHardware] WHERE [Hardware_Serial_Number] = ?",
                    serial,
                )
                if cur.fetchone():
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "duplicate_serial",
                            "message": "An item with this hardware serial number already exists.",
                        },
                    )

            # Exact row duplicate check
            where_sql, match_params = _build_exact_match_sql(cleaned)
            cur.execute(
                f"SELECT TOP 1 ID FROM [dbo].[ITHardware] WHERE {where_sql}",
                match_params,
            )
            if cur.fetchone():
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "duplicate_row",
                        "message": "An identical item is already registered in the inventory.",
                    },
                )

            cur.execute(sql, params)
            conn.commit()
        except HTTPException as http_err:
            conn.rollback()
            raise http_err
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail={"message": str(e)}) from e
        new_id = None
        try:
            cur.execute("SELECT SCOPE_IDENTITY()")
            row = cur.fetchone()
            if row:
                new_id = row[0]
        except Exception:
            new_id = None
    return {"ok": True, "id": new_id}


@app.put("/items/{item_ref}")
def update_item(item_ref: str, payload: HardwareCreate):
    cleaned, params = _prepare_payload_params(payload)
    reference = _clean_text(item_ref)
    if not reference:
        raise HTTPException(status_code=400, detail="Invalid item reference.")
    with get_conn() as conn:
        cur = conn.cursor()
        updated = 0
        candidate_id: Optional[int] = None
        try:
            candidate_id = int(reference)
        except (TypeError, ValueError):
            candidate_id = None
        try:
            if candidate_id is not None:
                serial = cleaned.get("Hardware_Serial_Number")
                if serial:
                    cur.execute(
                        "SELECT ID FROM [dbo].[ITHardware] WHERE [Hardware_Serial_Number] = ? AND [ID] <> ?",
                        serial,
                        candidate_id,
                    )
                    if cur.fetchone():
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "code": "duplicate_serial",
                                "message": "An item with this hardware serial number already exists.",
                            },
                        )
                cur.execute(
                    UPDATE_ITEM_SQL.format(where_clause="[ID] = ?"),
                    [*params, candidate_id],
                )
                updated = cur.rowcount
            if updated == 0:
                serial = cleaned.get("Hardware_Serial_Number")
                if serial:
                    cur.execute(
                        "SELECT ID FROM [dbo].[ITHardware] WHERE [Hardware_Serial_Number] = ? AND [Asset_Number] <> ?",
                        serial,
                        reference,
                    )
                    if cur.fetchone():
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "code": "duplicate_serial",
                                "message": "An item with this hardware serial number already exists.",
                            },
                        )
                cur.execute(
                    UPDATE_ITEM_SQL.format(where_clause="[Asset_Number] = ?"),
                    [*params, reference],
                )
                updated = cur.rowcount
            if updated == 0:
                conn.rollback()
                raise HTTPException(status_code=404, detail="Item not found.")
            conn.commit()
        except HTTPException as http_err:
            conn.rollback()
            raise http_err
        except Exception as exc:
            conn.rollback()
            raise HTTPException(status_code=500, detail={"message": str(exc)}) from exc
    resolved = candidate_id if (candidate_id is not None and updated) else reference
    return {"ok": True, "updated": updated, "id": resolved}


@app.delete("/items/{item_ref}")
def delete_item(item_ref: str):
    reference = _clean_text(item_ref)
    if not reference:
        raise HTTPException(status_code=400, detail="Invalid item reference.")
    with get_conn() as conn:
        cur = conn.cursor()
        deleted = 0
        candidate_id: Optional[int] = None
        try:
            candidate_id = int(reference)
        except (TypeError, ValueError):
            candidate_id = None
        try:
            if candidate_id is not None:
                cur.execute("DELETE FROM [dbo].[ITHardware] WHERE [ID] = ?", candidate_id)
                deleted = cur.rowcount
            if deleted == 0:
                cur.execute("DELETE FROM [dbo].[ITHardware] WHERE [Asset_Number] = ?", reference)
                deleted = cur.rowcount
            if deleted == 0:
                conn.rollback()
                raise HTTPException(status_code=404, detail="Item not found.")
            conn.commit()
        except HTTPException:
            raise
        except Exception as exc:
            conn.rollback()
            raise HTTPException(status_code=500, detail={"message": str(exc)}) from exc
    return {"ok": True, "deleted": deleted}

# -------------------------------------------
# Ülke bazında spare oranları
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
