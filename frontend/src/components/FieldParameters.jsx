import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import LoadingLogo from "./LoadingLogo";

const CHOICE_FIELDS = [
  { id: "Country", label: "Country" },
  { id: "Department", label: "Department" },
  { id: "Hardware_Manufacturer", label: "Hardware Manufacturer" },
  { id: "Hardware_Model", label: "Hardware Model" },
  { id: "Hardware_Type", label: "Hardware Type" },
  { id: "Identity", label: "Identity" },
  { id: "Location_Floor", label: "Location / Floor" },
  { id: "Region", label: "Region" },
  { id: "Status", label: "Status" },
  { id: "Win_OS", label: "Windows OS" },
];

const DEFAULT_FIELD = CHOICE_FIELDS[0].id;
const STATUS_FIELD_ID = "Status";

function resolveErrorMessage(error) {
  if (!error) return "Unexpected error occurred.";
  const { response, message } = error;
  if (response?.data?.detail) {
    const detail = response.data.detail;
    if (typeof detail === "string") return detail;
    if (detail?.message) return detail.message;
  }
  return message || "Unexpected error occurred.";
}

function formatUsage(count) {
  if (count === 0) return "No records";
  if (count === 1) return "1 record";
  return `${count.toLocaleString()} records`;
}

function normalizeStatusValue(value) {
  return String(value ?? "").trim().toLowerCase();
}

function isDisposedStatus(value) {
  const normalized = normalizeStatusValue(value);
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

function resolveStatusIsActive(item) {
  const value = typeof item === "string" ? item : item?.value ?? "";
  const explicit = resolveStatusActiveFlag(item);
  if (explicit !== null) return explicit;
  if (isDisposedStatus(value)) return false;
  return true;
}

export default function FieldParameters({ canEdit = true }) {
  const [fieldMap, setFieldMap] = useState({});
  const [activeField, setActiveField] = useState(DEFAULT_FIELD);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(false);

  const [newValue, setNewValue] = useState("");
  const [editingSource, setEditingSource] = useState(null);
  const [editingValue, setEditingValue] = useState("");
  const [editApply, setEditApply] = useState(true);

  const [deletePrompt, setDeletePrompt] = useState(null);
  const [deleteReplacement, setDeleteReplacement] = useState("");
  const [newStatusActive, setNewStatusActive] = useState(true);
  const isReadOnly = !canEdit;

  const fieldItems = useMemo(() => fieldMap[activeField] ?? [], [fieldMap, activeField]);
  const managedItems = useMemo(() => fieldItems.filter((item) => item.managed), [fieldItems]);
  const orphanItems = useMemo(() => fieldItems.filter((item) => !item.managed), [fieldItems]);
  const isStatusField = activeField === STATUS_FIELD_ID;

  useEffect(() => {
    const timer = notice ? setTimeout(() => setNotice(""), 5000) : null;
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [notice]);

  useEffect(() => {
    setError("");
    setNotice("");
    setEditingSource(null);
    setDeletePrompt(null);
    setDeleteReplacement("");
    setNewStatusActive(true);
  }, [activeField]);

  useEffect(() => {
    async function bootstrap() {
      setLoading(true);
      try {
        const response = await api.get("/field-parameters");
        const fields = response.data?.fields ?? {};
        setFieldMap(fields);
      } catch (err) {
        setError(resolveErrorMessage(err));
      } finally {
        setLoading(false);
      }
    }
    bootstrap();
  }, []);

  const refreshField = async (fieldId) => {
    const target = fieldId ?? activeField;
    const response = await api.get(`/field-parameters/${encodeURIComponent(target)}`);
    setFieldMap((prev) => ({ ...prev, [target]: response.data ?? [] }));
  };

  const handleAdd = async (event) => {
    event.preventDefault();
    if (!canEdit) return;
    const value = newValue.trim();
    if (!value) {
      setError("Please enter a value before adding.");
      return;
    }
    const exists = fieldItems.some((item) => item.value.toLowerCase() === value.toLowerCase());
    if (exists) {
      setError("This value is already on the list.");
      return;
    }
    setPending(true);
    setError("");
    try {
      const payload = { value };
      if (isStatusField) payload.is_active = newStatusActive;
      await api.post(`/field-parameters/${encodeURIComponent(activeField)}`, payload);
      await refreshField(activeField);
      setNewValue("");
      setNotice(`Added "${value}" to ${activeField}.`);
    } catch (err) {
      setError(resolveErrorMessage(err));
    } finally {
      setPending(false);
    }
  };

  const handleStartEdit = (item) => {
    if (!canEdit) return;
    setEditingSource(item.value);
    setEditingValue(item.value);
    setEditApply(true);
    setError("");
  };

  const handleCancelEdit = () => {
    setEditingSource(null);
    setEditingValue("");
  };

  const handleSaveEdit = async () => {
    if (!canEdit) return;
    const value = editingValue.trim();
    if (!editingSource) return;
    if (!value) {
      setError("Please provide a value.");
      return;
    }
    if (value.toLowerCase() === editingSource.toLowerCase()) {
      setNotice("No changes were made.");
      setEditingSource(null);
      return;
    }
    const exists = fieldItems.some(
      (item) => item.managed && item.value.toLowerCase() === value.toLowerCase()
    );
    if (exists) {
      setError("Another parameter already uses this value.");
      return;
    }
    setPending(true);
    setError("");
    try {
      const payload = {
        original: editingSource,
        value,
        update_existing: editApply,
      };
      if (isStatusField) {
        const matchedItem = fieldItems.find(
          (item) =>
            typeof item?.value === "string" &&
            item.value.toLowerCase() === editingSource.toLowerCase()
        );
        if (matchedItem) {
          payload.is_active = resolveStatusIsActive(matchedItem);
        }
      }
      await api.put(`/field-parameters/${encodeURIComponent(activeField)}`, payload);
      await refreshField(activeField);
      setNotice(`Renamed "${editingSource}" to "${value}".`);
      setEditingSource(null);
      setEditingValue("");
    } catch (err) {
      setError(resolveErrorMessage(err));
    } finally {
      setPending(false);
    }
  };

  const handleStatusStateChange = async (item, nextActive) => {
    if (!isStatusField || pending || !item?.managed || !canEdit) return;
    const value = item.value;
    if (!value) return;
    setPending(true);
    setError("");
    try {
      await api.put(`/field-parameters/${encodeURIComponent(activeField)}`, {
        original: value,
        value,
        is_active: nextActive,
      });
      await refreshField(activeField);
      setNotice(`Marked "${value}" as ${nextActive ? "active" : "inactive"}.`);
    } catch (err) {
      setError(resolveErrorMessage(err));
    } finally {
      setPending(false);
    }
  };

  const adoptOrphan = async (value) => {
    if (!canEdit) return;
    setPending(true);
    setError("");
    try {
      await api.post(`/field-parameters/${encodeURIComponent(activeField)}`, { value });
      await refreshField(activeField);
      setNotice(`Added existing data value "${value}" to ${activeField}.`);
    } catch (err) {
      setError(resolveErrorMessage(err));
    } finally {
      setPending(false);
    }
  };

  const performDelete = async ({ value, replacement, force }) => {
    const params = {};
    if (replacement) params.replacement = replacement;
    if (force) params.force = true;
    await api.delete(`/field-parameters/${encodeURIComponent(activeField)}/${encodeURIComponent(value)}`, {
      params,
    });
  };

  const handleDeleteClick = async (item) => {
    if (!item.managed || pending || !canEdit) return;
    setError("");
    if (item.usage_count > 0) {
      setDeletePrompt({ value: item.value, usageCount: item.usage_count });
      setDeleteReplacement("");
      return;
    }
    if (!window.confirm(`Remove "${item.value}" from ${activeField}?`)) return;
    setPending(true);
    try {
      await performDelete({ value: item.value });
      await refreshField(activeField);
      setNotice(`Removed "${item.value}" from ${activeField}.`);
    } catch (err) {
      setError(resolveErrorMessage(err));
    } finally {
      setPending(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!canEdit) return;
    if (!deletePrompt) return;
    if (deletePrompt.usageCount > 0 && !deleteReplacement) {
      setError("Select a replacement or choose to clear the value.");
      return;
    }
    setPending(true);
    setError("");
    try {
      if (deletePrompt.usageCount > 0) {
        if (deleteReplacement === "__clear__") {
          await performDelete({ value: deletePrompt.value, force: true });
          setNotice(`Removed "${deletePrompt.value}" and cleared the value in existing records.`);
        } else {
          await performDelete({ value: deletePrompt.value, replacement: deleteReplacement });
          setNotice(`Replaced "${deletePrompt.value}" with "${deleteReplacement}" in existing records.`);
        }
      } else {
        await performDelete({ value: deletePrompt.value });
        setNotice(`Removed "${deletePrompt.value}" from ${activeField}.`);
      }
      await refreshField(activeField);
      setDeletePrompt(null);
      setDeleteReplacement("");
    } catch (err) {
      setError(resolveErrorMessage(err));
    } finally {
      setPending(false);
    }
  };

  const cancelDelete = () => {
    setDeletePrompt(null);
    setDeleteReplacement("");
  };

  if (loading) {
    return (
      <section className="field-parameters-section">
        <div className="field-parameters-loading">
          <LoadingLogo label="Loading field parameters" size={112} />
        </div>
      </section>
    );
  }

  const activeMeta = CHOICE_FIELDS.find((item) => item.id === activeField) ?? CHOICE_FIELDS[0];
  const replacementOptions = deletePrompt
    ? managedItems.filter((item) => item.value !== deletePrompt.value)
    : [];

  return (
    <section className="field-parameters-section">
      <div className="field-parameters-layout">
        <aside className="field-parameters-sidebar" aria-label="Choice fields">
          <h2>Choice fields</h2>
          <ul className="field-parameters-field-list">
            {CHOICE_FIELDS.map((field) => {
              const isActive = field.id === activeField;
              const buttonClass = isActive
                ? "field-parameters-field-button active"
                : "field-parameters-field-button";
              const itemCount = (fieldMap[field.id] ?? []).filter((item) => item.managed).length;
              return (
                <li key={field.id}>
                  <button
                    type="button"
                    className={buttonClass}
                    onClick={() => setActiveField(field.id)}
                  >
                    <span className="field-parameters-field-label">{field.label}</span>
                    <span className="field-parameters-field-count">{itemCount}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>

        <div className="field-parameters-panel">
          <header className="field-parameters-header">
            <div>
              <h1>{activeMeta.label}</h1>
              <p>{isReadOnly ? "View" : "Manage"} the selectable values for {activeMeta.label.toLowerCase()}.</p>
            </div>
          </header>

          {error ? <div className="field-parameters-error" role="alert">{error}</div> : null}
          {notice ? <div className="field-parameters-notice">{notice}</div> : null}

          <form className="field-parameters-add" onSubmit={handleAdd}>
            <label htmlFor="new-param-value">Add new value</label>
            <div className="field-parameters-add-controls">
              <input
                id="new-param-value"
                type="text"
                value={newValue}
                disabled={pending || isReadOnly}
                placeholder="Enter a new value"
                onChange={(event) => setNewValue(event.target.value)}
              />
              <button type="submit" className="ghost-button" disabled={pending || isReadOnly}>
                Add
              </button>
            </div>
            {isStatusField ? (
              <div className="field-param-status-add" role="group" aria-label="Inventory tab">
                <span className="field-param-status-label">Inventory tab</span>
                <div className="field-param-status-toggle">
                  <button
                    type="button"
                    className={`field-param-status-button${newStatusActive ? " is-active" : ""}`}
                    onClick={() => setNewStatusActive(true)}
                    disabled={pending || isReadOnly || newStatusActive}
                    aria-pressed={newStatusActive}
                  >
                    Active
                  </button>
                  <button
                    type="button"
                    className={`field-param-status-button${!newStatusActive ? " is-active" : ""}`}
                    onClick={() => setNewStatusActive(false)}
                    disabled={pending || isReadOnly || !newStatusActive}
                    aria-pressed={!newStatusActive}
                  >
                    Inactive
                  </button>
                </div>
              </div>
            ) : null}
          </form>

          {fieldItems.length === 0 ? (
            <div className="field-parameters-empty">No values registered yet.</div>
          ) : (
            <div className="field-parameters-table" role="list">
              {managedItems.map((item) => {
                const isEditing = editingSource === item.value;
                const statusIsActive = isStatusField ? resolveStatusIsActive(item) : null;
                return (
                  <div key={item.value} className="field-param-row" role="listitem">
                    <div className="field-param-main">
                      {isEditing ? (
                        <input
                          type="text"
                          value={editingValue}
                          disabled={pending || isReadOnly}
                          onChange={(event) => setEditingValue(event.target.value)}
                          className="field-param-edit-input"
                        />
                      ) : (
                        <span className="field-param-value">{item.value}</span>
                      )}
                      <span className="field-param-usage">{formatUsage(item.usage_count)}</span>
                    </div>
                    <div className="field-param-actions">
                      {isEditing ? (
                        <>
                          <label className="field-param-checkbox">
                            <input
                              type="checkbox"
                              checked={editApply}
                              onChange={(event) => setEditApply(event.target.checked)}
                              disabled={isReadOnly}
                            />
                            <span>Update existing records</span>
                          </label>
                          <div className="field-param-action-buttons">
                            <button type="button" className="ghost-button" disabled={pending || isReadOnly} onClick={handleSaveEdit}>
                              Save
                            </button>
                            <button type="button" className="ghost-button" disabled={pending || isReadOnly} onClick={handleCancelEdit}>
                              Cancel
                            </button>
                          </div>
                        </>
                      ) : (
                        <>
                          {isStatusField ? (
                            <div
                              className="field-param-status-toggle"
                              role="group"
                              aria-label={`Inventory status for ${item.value}`}
                            >
                              <button
                                type="button"
                                className={`field-param-status-button${statusIsActive ? " is-active" : ""}`}
                                disabled={pending || isReadOnly || statusIsActive}
                                aria-pressed={Boolean(statusIsActive)}
                                onClick={() => handleStatusStateChange(item, true)}
                              >
                                Active
                              </button>
                              <button
                                type="button"
                                className={`field-param-status-button${!statusIsActive ? " is-active" : ""}`}
                                disabled={pending || isReadOnly || !statusIsActive}
                                aria-pressed={!statusIsActive}
                                onClick={() => handleStatusStateChange(item, false)}
                              >
                                Inactive
                              </button>
                            </div>
                          ) : null}
                          <div className="field-param-action-buttons">
                            <button
                              type="button"
                              className="ghost-button"
                              disabled={pending || isReadOnly}
                              onClick={() => handleStartEdit(item)}
                            >
                              Rename
                            </button>
                            <button
                              type="button"
                              className="ghost-button danger"
                              disabled={pending || isReadOnly}
                              onClick={() => handleDeleteClick(item)}
                            >
                              Remove
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}

              {orphanItems.length ? (
                <div className="field-param-orphans">
                  <h3>Values detected in data but not in the allowed list</h3>
                  <ul>
                    {orphanItems.map((item) => (
                      <li key={item.value}>
                        <span className="field-param-value">{item.value}</span>
                        <span className="field-param-usage">{formatUsage(item.usage_count)}</span>
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={pending || isReadOnly}
                          onClick={() => adoptOrphan(item.value)}
                        >
                          Add to options
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}

          {deletePrompt ? (
            <div className="field-param-delete-panel" role="alertdialog" aria-live="assertive">
              <div className="field-param-delete-body">
                <h3>Remove "{deletePrompt.value}"?</h3>
                <p>
                  This value is used in {deletePrompt.usageCount.toLocaleString()} record
                  {deletePrompt.usageCount === 1 ? "" : "s"}. Choose how to handle those records.
                </p>
                <label className="field-param-delete-label" htmlFor="delete-replacement-select">
                  Replacement action
                </label>
                <select
                  id="delete-replacement-select"
                  value={deleteReplacement}
                  onChange={(event) => setDeleteReplacement(event.target.value)}
                  disabled={pending || isReadOnly}
                >
                  <option value="">Select an action...</option>
                  {replacementOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      Replace with {option.value}
                    </option>
                  ))}
                  <option value="__clear__">Clear the value in existing records</option>
                </select>

                <div className="field-param-delete-actions">
                  <button type="button" className="ghost-button danger" disabled={pending || isReadOnly} onClick={handleConfirmDelete}>
                    Confirm removal
                  </button>
                  <button type="button" className="ghost-button" disabled={pending || isReadOnly} onClick={cancelDelete}>
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
