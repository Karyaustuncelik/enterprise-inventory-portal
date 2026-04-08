import { useEffect, useMemo, useState } from "react";
import { api, searchDirectoryUsers } from "../api";
import CustomSelect from "./CustomSelect";
import DatePickerField from "./DatePickerField";

const EMPTY = Object.freeze({
  Country: "",
  Status: "",
  Name_Surname: "",
  Identity: "",
  Department: "",
  Region: "",
  Hardware_Type: "",
  Hardware_Manufacturer: "",
  Hardware_Model: "",
  Hardware_Serial_Number: "",
  Asset_Number: "",
  Capitalization_Date: "",
  User_Name: "",
  Old_User: "",
  Windows_Computer_Name: "",
  Win_OS: "",
  Location_Floor: "",
  Notes: "",
});

const DRAFT_STORAGE_KEY = "inventory.add_item_form_draft_v1";
const DRAFT_MAX_AGE_MS = 1000 * 60 * 60 * 4;

const REQUIRED_FIELDS = ["Country", "Hardware_Serial_Number", "Asset_Number"];

const CHOICE_FIELDS = [
  "Country",
  "Status",
  "Department",
  "Region",
  "Hardware_Type",
  "Hardware_Manufacturer",
  "Hardware_Model",
  "Identity",
  "Location_Floor",
  "Win_OS",
];

function coerceArray(payload) {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
}

function normalizeStatus(value) {
  return String(value ?? "").trim().toLowerCase();
}

function isDisposedStatus(value) {
  const normalized = normalizeStatus(value);
  return normalized.includes("disposed");
}

function resolveStatusActiveFlag(item) {
  if (!item || typeof item !== "object") return null;
  if (typeof item.is_active === "boolean") return item.is_active;
  if (typeof item.status_active === "boolean") return item.status_active;
  if (typeof item.statusActive === "boolean") return item.statusActive;
  if (typeof item.active === "boolean") return item.active;
  if (typeof item.isActive === "boolean") return item.isActive;
  if (typeof item.inactive === "boolean") return !item.inactive;
  if (typeof item.is_inactive === "boolean") return !item.is_inactive;
  const state = item.inventory_state ?? item.inventory ?? item.state ?? item.status_state;
  if (typeof state === "string") {
    const normalized = state.trim().toLowerCase();
    if (normalized === "active") return true;
    if (normalized === "inactive") return false;
  }
  return null;
}

function buildStatusActivityMap(statusItems) {
  const map = new Map();
  const list = Array.isArray(statusItems) ? statusItems : [];
  list.forEach((item) => {
    const rawValue = typeof item === "string" ? item : item?.value ?? item?.label;
    if (!rawValue) return;
    const normalized = normalizeStatus(rawValue);
    if (!normalized) return;
    const activeFlag = resolveStatusActiveFlag(item);
    if (activeFlag === null) return;
    map.set(normalized, activeFlag);
  });
  return map;
}

function resolveStatusIsActive(value, statusActivityMap) {
  const normalized = normalizeStatus(value);
  if (normalized && statusActivityMap?.has(normalized)) {
    return statusActivityMap.get(normalized);
  }
  return !isDisposedStatus(value);
}

function toDateInput(value) {
  if (!value) return "";
  const raw = String(value).trim();
  if (!raw) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
  return raw.slice(0, 10);
}

function toFormState(record) {
  if (!record) return { ...EMPTY };
  return {
    ...EMPTY,
    ...record,
    Country: record.Country ?? record.country ?? "",
    Status: record.Status ?? record.status ?? "",
    Name_Surname: record.Name_Surname ?? record.name_surname ?? "",
    Identity: record.Identity ?? record.identity ?? "",
    Department: record.Department ?? record.department ?? "",
    Region: record.Region ?? record.region ?? "",
    Hardware_Type: record.Hardware_Type ?? record.hardware_type ?? "",
    Hardware_Manufacturer: record.Hardware_Manufacturer ?? record.hardware_manufacturer ?? "",
    Hardware_Model: record.Hardware_Model ?? record.hardware_model ?? "",
    Hardware_Serial_Number: record.Hardware_Serial_Number ?? record.hardware_serial_number ?? "",
    Asset_Number: record.Asset_Number ?? record.asset_number ?? "",
    Capitalization_Date: toDateInput(record.Capitalization_Date ?? record.capitalization_date ?? ""),
    User_Name: record.User_Name ?? record.user_name ?? "",
    Old_User: record.Old_User ?? record.old_user ?? "",
    Windows_Computer_Name: record.Windows_Computer_Name ?? record.windows_computer_name ?? "",
    Win_OS: record.Win_OS ?? record.win_os ?? "",
    Location_Floor: record.Location_Floor ?? record.location_floor ?? "",
    Notes: record.Notes ?? record.notes ?? "",
  };
}

function buildPayload(form, statusActivityMap) {
  const statusIsActive = resolveStatusIsActive(form.Status, statusActivityMap);
  return {
    Country: form.Country || null,
    Status: form.Status || null,
    Name_Surname: form.Name_Surname || null,
    Identity: form.Identity || null,
    Department: form.Department || null,
    Region: form.Region || null,
    Hardware_Type: form.Hardware_Type || null,
    Hardware_Manufacturer: form.Hardware_Manufacturer || null,
    Hardware_Model: form.Hardware_Model || null,
    Hardware_Serial_Number: form.Hardware_Serial_Number || null,
    Asset_Number: form.Asset_Number || null,
    Capitalization_Date: form.Capitalization_Date || null,
    User_Name: form.User_Name || null,
    Old_User: form.Old_User || null,
    Windows_Computer_Name: form.Windows_Computer_Name || null,
    Win_OS: form.Win_OS || null,
    Location_Floor: form.Location_Floor || null,
    Notes: form.Notes || null,
    If_Deleted: statusIsActive ? 0 : 1,
  };
}

function resolveRecordId(record) {
  if (!record) return null;
  const directId = record.ID ?? record.Id ?? record.id;
  if (directId !== undefined && directId !== null && directId !== "") {
    return directId;
  }
  return record.Asset_Number ?? record.asset_number ?? null;
}

function sanitizeDraftForm(form) {
  const source = form && typeof form === "object" ? form : {};
  const normalized = { ...EMPTY };
  Object.keys(EMPTY).forEach((key) => {
    const value = source[key];
    if (value === undefined || value === null) return;
    normalized[key] = String(value);
  });
  return normalized;
}

function readAddItemDraft() {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(DRAFT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const savedAt = Number(parsed?.savedAt ?? 0);
    if (!Number.isFinite(savedAt) || Date.now() - savedAt > DRAFT_MAX_AGE_MS) {
      window.sessionStorage.removeItem(DRAFT_STORAGE_KEY);
      return null;
    }
    return sanitizeDraftForm(parsed?.form);
  } catch {
    return null;
  }
}

function writeAddItemDraft(form) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      DRAFT_STORAGE_KEY,
      JSON.stringify({
        savedAt: Date.now(),
        form: sanitizeDraftForm(form),
      })
    );
  } catch {
    // ignore storage failures
  }
}

function clearAddItemDraft() {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(DRAFT_STORAGE_KEY);
  } catch {
    // ignore storage failures
  }
}

function resolveInitialFormState(initialData, mode) {
  const editing = mode === "edit" || Boolean(resolveRecordId(initialData));
  if (editing) return toFormState(initialData);
  const draft = readAddItemDraft();
  return toFormState(draft ?? initialData);
}

export default function AddItemForm({
  initialData = null,
  mode = "create",
  onCancel,
  onSaved,
}) {
  const [form, setForm] = useState(() => resolveInitialFormState(initialData, mode));
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [dialog, setDialog] = useState(null);
  const [choiceMap, setChoiceMap] = useState({});
  const [loadingChoices, setLoadingChoices] = useState(false);
  const [userDirectoryResults, setUserDirectoryResults] = useState([]);
  const [userDirectoryLoading, setUserDirectoryLoading] = useState(false);
  const [userDirectoryError, setUserDirectoryError] = useState("");
  const [userSearchActive, setUserSearchActive] = useState(false);
  const [lastDirectoryDisplayName, setLastDirectoryDisplayName] = useState("");
  const selectMenuMaxHeight = 180;
  const addItemSelectProps = {
    searchable: true,
    searchPlaceholder: "Search...",
    menuMaxHeight: selectMenuMaxHeight,
    menuDirection: "down",
  };
  const statusActivityMap = useMemo(
    () => buildStatusActivityMap(choiceMap?.Status),
    [choiceMap]
  );

  const recordId = useMemo(() => resolveRecordId(initialData), [initialData]);
  const isEditMode = mode === "edit" || Boolean(recordId);
  const usesAutopilotComputerName = useMemo(() => {
    const normalized = String(form.Hardware_Manufacturer ?? "")
      .trim()
      .replace(/\s+/g, " ")
      .toLowerCase();
    return normalized === "lenovo autopilot" || normalized === "lenovo app";
  }, [form.Hardware_Manufacturer]);
  const computerNameEnabled = useMemo(() => {
    const normalizedType = String(form.Hardware_Type ?? "").trim().toLowerCase();
    return usesAutopilotComputerName || normalizedType === "laptop" || normalizedType === "desktop";
  }, [form.Hardware_Type, usesAutopilotComputerName]);

  const setField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  useEffect(() => {
    setForm(resolveInitialFormState(initialData, mode));
    setError("");
    setNotice("");
    setDialog(null);
    setUserDirectoryResults([]);
    setUserDirectoryError("");
    setUserDirectoryLoading(false);
    setUserSearchActive(false);
    setLastDirectoryDisplayName("");
  }, [initialData, mode]);

  useEffect(() => {
    if (isEditMode) return;
    writeAddItemDraft(form);
  }, [form, isEditMode]);
   
  useEffect(() => {
    document.body.classList.add("is-add-form");
    return () => document.body.classList.remove("is-add-form");
  }, []);

  useEffect(() => {
    let active = true;
    setLoadingChoices(true);
    api
      .get("/field-parameters")
      .then((response) => {
        if (!active) return;
        const fields = response.data?.fields ?? {};
        setChoiceMap(fields);
      })
      .catch((err) => {
        if (!active) return;
        console.error("choice load error", err);
      })
      .finally(() => {
        if (active) setLoadingChoices(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const hardwareType = String(form.Hardware_Type ?? "").trim().toLowerCase();
    const manufacturer = String(form.Hardware_Manufacturer ?? "")
      .trim()
      .replace(/\s+/g, " ")
      .toLowerCase();
    const country = String(form.Country ?? "").trim();
    const region = String(form.Region ?? "").trim();
    const serial = String(form.Hardware_Serial_Number ?? "").trim();
    const suffix = hardwareType === "laptop" ? "MC" : hardwareType === "desktop" ? "WS" : "";
    const useAutopilotFormula =
      manufacturer === "lenovo autopilot" || manufacturer === "lenovo app";

    if (useAutopilotFormula) {
      if (!country || !serial) {
        if (form.Windows_Computer_Name) {
          setField("Windows_Computer_Name", "");
        }
        return;
      }
      const computedName = `${country.toUpperCase()}APP${serial.toUpperCase()}`;
      if (computedName !== form.Windows_Computer_Name) {
        setField("Windows_Computer_Name", computedName);
      }
      return;
    }

    if (!suffix) {
      if (form.Windows_Computer_Name) {
        setField("Windows_Computer_Name", "");
      }
      return;
    }

    if (!country || !region || !serial) {
      if (form.Windows_Computer_Name) {
        setField("Windows_Computer_Name", "");
      }
      return;
    }

    const computedName = `${country.toUpperCase()}${region.toUpperCase()}${suffix}${serial.toUpperCase()}`;
    if (computedName !== form.Windows_Computer_Name) {
      setField("Windows_Computer_Name", computedName);
    }
  }, [
    form.Country,
    form.Region,
    form.Hardware_Type,
    form.Hardware_Manufacturer,
    form.Hardware_Serial_Number,
    form.Windows_Computer_Name,
  ]);

  useEffect(() => {
    if (!userSearchActive) return;
    const query = String(form.User_Name ?? "").trim();
    if (query.length < 2) {
      setUserDirectoryResults([]);
      setUserDirectoryError("");
      setUserDirectoryLoading(false);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setUserDirectoryLoading(true);
      setUserDirectoryError("");
      searchDirectoryUsers(query, { signal: controller.signal })
        .then((results) => {
          setUserDirectoryResults(results);
          if (!results.length) {
            setUserDirectoryError("No matching users found. You can use the typed username.");
          }
        })
        .catch((err) => {
          if (controller.signal.aborted) return;
          console.error("/directory/search error", err);
          setUserDirectoryError("User search failed.");
        })
        .finally(() => {
          setUserDirectoryLoading(false);
        });
    }, 350);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [form.User_Name, userSearchActive]);

  const handleUserNameSelect = (result) => {
    if (!result?.username) return;
    const nextUsername = String(result.username ?? "").trim();
    const nextDisplayName = String(result.displayName ?? "").trim();
    setForm((prev) => {
      const currentName = String(prev.Name_Surname ?? "").trim();
      const shouldReplaceName =
        Boolean(nextDisplayName) &&
        (!currentName || currentName === String(lastDirectoryDisplayName ?? "").trim());
      return {
        ...prev,
        User_Name: nextUsername,
        Name_Surname: shouldReplaceName ? nextDisplayName : prev.Name_Surname,
      };
    });
    setLastDirectoryDisplayName(nextDisplayName);
    setUserDirectoryResults([]);
    setUserDirectoryError("");
    setUserSearchActive(false);
  };

  const handleUserNameChange = (event) => {
    setField("User_Name", event.target.value);
    setUserSearchActive(true);
    setUserDirectoryError("");
  };

  const handleUserNameFocus = () => {
    if (!userSearchActive) {
      setUserSearchActive(true);
    }
  };

  const handleNameSurnameChange = (event) => {
    const nextValue = event.target.value;
    setField("Name_Surname", nextValue);
    if (
      lastDirectoryDisplayName &&
      String(nextValue ?? "").trim() !== String(lastDirectoryDisplayName).trim()
    ) {
      setLastDirectoryDisplayName("");
    }
  };

  const validate = () => {
    const missing = REQUIRED_FIELDS.filter((field) => !String(form[field] ?? "").trim());
    if (!String(form.Name_Surname ?? "").trim() && !String(form.User_Name ?? "").trim()) {
      missing.push("Name_Surname or User_Name");
    }
    if (missing.length) {
      setError(`Required fields: ${missing.join(", ")}`);
      return false;
    }
    if (form.Capitalization_Date && !/^\d{4}-\d{2}-\d{2}$/.test(form.Capitalization_Date)) {
      setError("Capitalization Date must be YYYY-MM-DD");
      return false;
    }
    setError("");
    return true;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!validate()) return;
    const editingId = isEditMode ? recordId : null;
    if (isEditMode && (editingId === null || editingId === undefined || editingId === "")) {
      setError("This record does not have a database id yet.");
      return;
    }
    const encodedId =
      editingId === null || editingId === undefined ? null : encodeURIComponent(String(editingId));
    setSaving(true);
    setNotice("");
    try {
      const payload = buildPayload(form, statusActivityMap);
      const response = isEditMode
        ? await api.put(`/items/${encodedId}`, payload)
        : await api.post("/items", payload);
      if (!isEditMode) {
        clearAddItemDraft();
      }
      setNotice(isEditMode ? "Item updated." : "Item created.");
      const responseData = response?.data ?? null;
      const createdId = responseData?.id ?? editingId ?? null;
      const resolvedStatus =
        responseData?.Status ??
        responseData?.status ??
        payload.Status ??
        payload.status ??
        form.Status ??
        "";
      const statusIsActive = resolveStatusIsActive(resolvedStatus, statusActivityMap);
      onSaved?.(responseData, {
        mode: isEditMode ? "edit" : "create",
        id: createdId,
        status: resolvedStatus,
        statusIsActive,
      });
    } catch (err) {
      console.error("save error", err);
      const detail = err?.response?.data?.detail;
      const status = err?.response?.status;
      if (status === 409) {
        const code = typeof detail === "object" ? detail?.code : null;
        const friendly =
          code === "duplicate_serial"
            ? "An item with this hardware serial number already exists."
            : "An identical item is already registered in the inventory.";
        setDialog({
          title: "Item already exists",
          message: friendly,
          navigateHome: true,
        });
        setError("");
        setNotice("");
        return;
      } else {
        const message =
          (typeof detail === "string" ? detail : detail?.message) ??
          err?.response?.data?.message ??
          err?.message ??
          "Save failed.";
        setError(message);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDialogClose = () => {
    const shouldNavigateHome = dialog?.navigateHome;
    setDialog(null);
    if (shouldNavigateHome) {
      onCancel?.();
    }
  };

  const handleClearAll = () => {
    setForm({ ...EMPTY });
    setError("");
    setNotice("");
    setDialog(null);
    setUserDirectoryResults([]);
    setUserDirectoryError("");
    setUserDirectoryLoading(false);
    setUserSearchActive(false);
    clearAddItemDraft();
  };

  const normalizedChoiceMap = useMemo(() => {
    const result = {};
    CHOICE_FIELDS.forEach((field) => {
      const rawList = Array.isArray(choiceMap?.[field]) ? choiceMap[field] : [];
      const seen = new Set();
      const values = [];
      rawList.forEach((item) => {
        const rawValue = typeof item === "string" ? item : item?.value;
        if (rawValue === undefined || rawValue === null) return;
        const trimmed = String(rawValue).trim();
        if (!trimmed || seen.has(trimmed)) return;
        seen.add(trimmed);
        values.push(trimmed);
      });
      const current = form[field];
      if (current && !seen.has(current)) {
        values.unshift(current);
      }
      result[field] = values;
    });
    return result;
  }, [choiceMap, form]);

  return (
    <form className="add-form" onSubmit={handleSubmit}>
      {dialog ? (
        <div className="form-dialog-backdrop" role="dialog" aria-modal="true">
          <div className="form-dialog-card">
            <h3>{dialog.title ?? "Notice"}</h3>
            <p>{dialog.message}</p>
            <button type="button" className="ghost-button primary" onClick={handleDialogClose}>
              Cancel
            </button>
          </div>
        </div>
      ) : null}
      {error ? <div className="form-error" role="alert">{error}</div> : null}
      {notice ? <div className="form-notice" role="status">{notice}</div> : null}

      <div className="add-grid add-grid--dense">
        <div className="fg">
          <label htmlFor="Status">Status</label>
          {normalizedChoiceMap.Status?.length ? (
            <CustomSelect
              id="Status"
              options={normalizedChoiceMap.Status.map((value) => ({ value, label: value }))}
              value={form.Status || ""}
              onChange={(nextValue) => setField("Status", nextValue)}
              placeholder="Select status"
              disabled={loadingChoices && !form.Status}
              {...addItemSelectProps}
            />
          ) : (
            <input
              id="Status"
              value={form.Status}
              onChange={(event) => setField("Status", event.target.value)}
              placeholder="In Use / Spare / ..."
              maxLength={30}
            />
          )}
        </div>

        <div className="fg">
          <label htmlFor="Old_User">Old User</label>
          <input
            id="Old_User"
            value={form.Old_User}
            onChange={(event) => setField("Old_User", event.target.value)}
          />
        </div>

        <div className="fg">
          <label htmlFor="Hardware_Type">Hardware Type</label>
          {normalizedChoiceMap.Hardware_Type?.length ? (
            <CustomSelect
              id="Hardware_Type"
              options={normalizedChoiceMap.Hardware_Type.map((value) => ({ value, label: value }))}
              value={form.Hardware_Type || ""}
              onChange={(nextValue) => setField("Hardware_Type", nextValue)}
              placeholder="Select hardware type"
              disabled={loadingChoices && !form.Hardware_Type}
              {...addItemSelectProps}
            />
          ) : (
            <input
              id="Hardware_Type"
              value={form.Hardware_Type}
              onChange={(event) => setField("Hardware_Type", event.target.value)}
              placeholder="Laptop..."
              maxLength={20}
            />
          )}
        </div>

        <div className="fg required">
          <label htmlFor="Hardware_Serial_Number">Hardware Serial Number *</label>
          <input
            id="Hardware_Serial_Number"
            value={form.Hardware_Serial_Number}
            onChange={(event) => setField("Hardware_Serial_Number", event.target.value)}
            maxLength={50}
            required
          />
        </div>

        <div className="fg">
          <label htmlFor="Identity">Identity</label>
          {normalizedChoiceMap.Identity?.length ? (
            <CustomSelect
              id="Identity"
              options={normalizedChoiceMap.Identity.map((value) => ({ value, label: value }))}
              value={form.Identity || ""}
              onChange={(nextValue) => setField("Identity", nextValue)}
              placeholder="Select identity"
              disabled={loadingChoices && !form.Identity}
              {...addItemSelectProps}
            />
          ) : (
            <input
              id="Identity"
              value={form.Identity}
              onChange={(event) => setField("Identity", event.target.value)}
              placeholder="Personel/Intern..."
              maxLength={10}
            />
          )}
        </div>

        <div className="fg">
          <label htmlFor="Hardware_Manufacturer">Hardware Manufacturer</label>
          {normalizedChoiceMap.Hardware_Manufacturer?.length ? (
            <CustomSelect
              id="Hardware_Manufacturer"
              options={normalizedChoiceMap.Hardware_Manufacturer.map((value) => ({ value, label: value }))}
              value={form.Hardware_Manufacturer || ""}
              onChange={(nextValue) => setField("Hardware_Manufacturer", nextValue)}
              placeholder="Select manufacturer"
              disabled={loadingChoices && !form.Hardware_Manufacturer}
              {...addItemSelectProps}
            />
          ) : (
            <input
              id="Hardware_Manufacturer"
              value={form.Hardware_Manufacturer}
              onChange={(event) => setField("Hardware_Manufacturer", event.target.value)}
              placeholder="HP / Lenovo"
              maxLength={60}
            />
          )}
        </div>

        <div className="fg required">
          <label htmlFor="Asset_Number">Asset Number *</label>
          <input
            id="Asset_Number"
            value={form.Asset_Number}
            onChange={(event) => setField("Asset_Number", event.target.value)}
            maxLength={50}
            required
          />
        </div>

        <div className="fg required">
          <label htmlFor="Country">Country *</label>
          {normalizedChoiceMap.Country?.length ? (
            <CustomSelect
              id="Country"
              options={normalizedChoiceMap.Country.map((value) => ({ value, label: value }))}
              value={form.Country || ""}
              onChange={(nextValue) => setField("Country", nextValue)}
              placeholder="Select country"
              disabled={loadingChoices && !form.Country}
              {...addItemSelectProps}
            />
          ) : (
            <input
              id="Country"
              value={form.Country}
              onChange={(event) => setField("Country", event.target.value.toUpperCase())}
              placeholder="TR / AE / SA ..."
              maxLength={2}
              required
            />
          )}
        </div>

        <div className="fg">
          <label htmlFor="Hardware_Model">Hardware Model</label>
          {normalizedChoiceMap.Hardware_Model?.length ? (
            <CustomSelect
              id="Hardware_Model"
              options={normalizedChoiceMap.Hardware_Model.map((value) => ({ value, label: value }))}
              value={form.Hardware_Model || ""}
              onChange={(nextValue) => setField("Hardware_Model", nextValue)}
              placeholder="Select model"
              disabled={loadingChoices && !form.Hardware_Model}
              {...addItemSelectProps}
            />
          ) : (
            <input
              id="Hardware_Model"
              value={form.Hardware_Model}
              onChange={(event) => setField("Hardware_Model", event.target.value)}
              maxLength={60}
            />
          )}
        </div>

        <div className="fg">
          <label htmlFor="Capitalization_Date">Capitalization Date</label>
          <DatePickerField
            id="Capitalization_Date"
            value={form.Capitalization_Date}
            onChange={(nextValue) => setField("Capitalization_Date", nextValue)}
          />
        </div>

        <div className="fg">
          <label htmlFor="Region">Region</label>
          {normalizedChoiceMap.Region?.length ? (
            <CustomSelect
              id="Region"
              options={normalizedChoiceMap.Region.map((value) => ({ value, label: value }))}
              value={form.Region || ""}
              onChange={(nextValue) => setField("Region", nextValue)}
              placeholder="Select region"
              disabled={loadingChoices && !form.Region}
              {...addItemSelectProps}
            />
          ) : (
            <input
              id="Region"
              value={form.Region}
              onChange={(event) => setField("Region", event.target.value)}
              placeholder="IST"
              maxLength={8}
            />
          )}
        </div>

        <div className="fg">
          <label htmlFor="Windows_Computer_Name">Windows Computer Name</label>
          <input
            id="Windows_Computer_Name"
            value={form.Windows_Computer_Name}
            readOnly
            disabled={!computerNameEnabled}
            placeholder={computerNameEnabled ? "" : "Select Laptop/Desktop to auto-fill"}
            maxLength={100}
          />
        </div>

        <div className="fg">
          <label htmlFor="Name_Surname">Name &amp; Surname</label>
          <input
            id="Name_Surname"
            value={form.Name_Surname}
            onChange={handleNameSurnameChange}
            maxLength={50}
            placeholder="Auto-fills from selected user"
          />
        </div>

        <div className="fg">
          <label htmlFor="Location_Floor">Location / Floor</label>
          {normalizedChoiceMap.Location_Floor?.length ? (
            <CustomSelect
              id="Location_Floor"
              options={normalizedChoiceMap.Location_Floor.map((value) => ({ value, label: value }))}
              value={form.Location_Floor || ""}
              onChange={(nextValue) => setField("Location_Floor", nextValue)}
              placeholder="Select location"
              disabled={loadingChoices && !form.Location_Floor}
              {...addItemSelectProps}
            />
          ) : (
            <input
              id="Location_Floor"
              value={form.Location_Floor}
              onChange={(event) => setField("Location_Floor", event.target.value)}
              maxLength={100}
            />
          )}
        </div>

        <div className="fg">
          <label htmlFor="Win_OS">Windows OS</label>
          {normalizedChoiceMap.Win_OS?.length ? (
            <CustomSelect
              id="Win_OS"
              options={normalizedChoiceMap.Win_OS.map((value) => ({ value, label: value }))}
              value={form.Win_OS || ""}
              onChange={(nextValue) => setField("Win_OS", nextValue)}
              placeholder="Select Windows OS"
              disabled={loadingChoices && !form.Win_OS}
              {...addItemSelectProps}
            />
          ) : (
            <input
              id="Win_OS"
              value={form.Win_OS}
              onChange={(event) => setField("Win_OS", event.target.value)}
              maxLength={15}
            />
          )}
        </div>

        <div className="fg">
          <label htmlFor="User_Name">User Name</label>
          <div className="directory-input">
            <input
              id="User_Name"
              value={form.User_Name}
              onChange={handleUserNameChange}
              onFocus={handleUserNameFocus}
              maxLength={30}
              placeholder="Type a name or DOMAIN\\username"
              autoComplete="off"
            />
            {userDirectoryLoading ? <span className="directory-hint">Searching...</span> : null}
            {userDirectoryError && !userDirectoryResults.length ? (
              <span className="directory-hint directory-hint--error">{userDirectoryError}</span>
            ) : null}
            {userDirectoryResults.length ? (
              <ul className="directory-suggestions custom-scrollbar" role="listbox">
                {userDirectoryResults.map((result) => (
                  <li
                    key={result.id}
                    className="directory-suggestion"
                    onMouseDown={() => handleUserNameSelect(result)}
                    role="option"
                  >
                    <span className="directory-suggestion-name">{result.displayName || result.username}</span>
                    <span className="directory-suggestion-meta">{result.username}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </div>

        <div className="fg">
          <label htmlFor="Department">Department</label>
          {normalizedChoiceMap.Department?.length ? (
            <CustomSelect
              id="Department"
              options={normalizedChoiceMap.Department.map((value) => ({ value, label: value }))}
              value={form.Department || ""}
              onChange={(nextValue) => setField("Department", nextValue)}
              placeholder="Select department"
              disabled={loadingChoices && !form.Department}
              {...addItemSelectProps}
            />
          ) : (
            <input
              id="Department"
              value={form.Department}
              onChange={(event) => setField("Department", event.target.value)}
              placeholder="DX/HR..."
              maxLength={50}
            />
          )}
        </div>

        <div className="fg">
          <label htmlFor="Notes">Notes</label>
          <textarea
            id="Notes"
            value={form.Notes}
            onChange={(event) => setField("Notes", event.target.value)}
            rows={3}
            maxLength={255}
          />
        </div>
      </div>

      <div className="add-form-footer">
        {!isEditMode ? (
          <button
            type="button"
            className="ghost-button"
            onClick={handleClearAll}
            disabled={saving}
          >
            Clear all
          </button>
        ) : null}
        <button
          type="button"
          className="ghost-button"
          onClick={onCancel}
          disabled={saving}
        >
          Cancel
        </button>
        <button type="submit" className="ghost-button primary" disabled={saving}>
          {saving ? (isEditMode ? "Saving..." : "Creating...") : isEditMode ? "Save changes" : "Create item"}
        </button>
      </div>
    </form>
  );
}
