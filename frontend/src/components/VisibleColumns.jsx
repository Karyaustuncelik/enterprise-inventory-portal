// src/components/VisibleColumns.jsx
import { useMemo, useState, useRef, useEffect } from "react";

export default function VisibleColumns({
  columns,
  selected,
  onChange,
  label = "Visible Columns",
  buttonClassName = "",
  renderButtonContent,
  buttonAriaLabel,
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef(null);

  const allKeys = useMemo(() => columns.map((c) => c.key), [columns]);
  const shown = useMemo(
    () =>
      columns.filter(
        (c) =>
          c.label.toLowerCase().includes(q.toLowerCase()) ||
          c.key.toLowerCase().includes(q.toLowerCase())
      ),
    [columns, q]
  );

  useEffect(() => {
    function onDocClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const allSelected = selected.length === allKeys.length;
  const caption = allSelected
    ? `All (${allKeys.length})`
    : selected.length === 0
    ? "None"
    : `${selected.length} / ${allKeys.length}`;

  const buttonLabel = buttonAriaLabel || `${label}: ${caption}`;
  const buttonContent = renderButtonContent
    ? renderButtonContent({
        caption,
        allSelected,
        selectedCount: selected.length,
        totalCount: allKeys.length,
      })
    : (
      <>
        {label}: <strong>{caption}</strong>
      </>
    );

  const toggle = (key) => {
    if (selected.includes(key)) onChange(selected.filter((k) => k !== key));
    else onChange([...selected, key]);
  };

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={buttonClassName}
        aria-label={buttonLabel}
        aria-haspopup="true"
        aria-expanded={open}
        style={
          !buttonClassName
            ? {
                padding: "10px 14px",
                border: "1px solid var(--accent)",
                borderRadius: 9999,
                background: "#ffffff",
                color: "var(--accent)",
                cursor: "pointer",
                fontSize: 14,
                fontWeight: 600,
              }
            : undefined
        }
      >
        {buttonContent}
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "110%",
            right: 0,
            zIndex: 20,
            width: 340,
            maxHeight: 520,
            overflow: "auto",
            overflowX: "hidden",
            background: "#ffffff",
            border: "1px solid #f1f1f1",
            borderRadius: 16,
            boxShadow: "0 18px 40px rgba(0, 0, 0, 0.12)",
            padding: 14,
          }}
        >
          {/* Search + Buttons */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 10 }}>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search columns…"
              className="vc-search-input"
              style={{
                gridColumn: "1 / -1",
                minWidth: 0,
                padding: "8px 10px",
                border: "1px solid #f1f1f1",
                borderRadius: 8,
                fontSize: 14,
                color: "var(--accent)",
                background: "#f1f1f1",
              }}
            />
            <button
              onClick={() => onChange(allKeys)}
              style={{
                flexShrink: 0,
                border: "1px solid #f1f1f1",
                background: "#ffffff",
                borderRadius: 8,
                padding: "8px 10px",
                fontWeight: 600,
                cursor: "pointer",
                fontSize: 13,
                color: "var(--accent)",
              }}
            >
              All
            </button>
            <button
              onClick={() => onChange([])}
              style={{
                flexShrink: 0,
                border: "1px solid #f1f1f1",
                background: "#ffffff",
                borderRadius: 8,
                padding: "8px 10px",
                fontWeight: 600,
                cursor: "pointer",
                fontSize: 13,
                color: "var(--accent)",
              }}
            >
              None
            </button>
          </div>

          {/* Column list */}
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              minHeight: 180,
              maxHeight: 400,
              overflowY: "auto",
            }}
            className="custom-scrollbar"
          >
            {shown.map((c) => (
              <li
                key={c.key}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "6px 2px",
                }}
              >
                <input
                  id={`vc-${c.key}`}
                  type="checkbox"
                  checked={selected.includes(c.key)}
                  onChange={() => toggle(c.key)}
                  style={{
                    width: 18,
                    height: 18,
                    accentColor: "var(--accent)",
                  }}
                />
                <label
                  htmlFor={`vc-${c.key}`}
                  style={{
                    cursor: "pointer",
                    fontSize: 15,
                    color: "var(--accent)",
                    fontWeight: 600,
                  }}
                >
                  {c.label}
                </label>
              </li>
            ))}
            {shown.length === 0 && (
              <li style={{ color: "var(--accent)", fontSize: 13, padding: 6 }}>
                No results
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
