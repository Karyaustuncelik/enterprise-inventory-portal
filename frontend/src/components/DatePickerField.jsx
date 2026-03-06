import { useEffect, useMemo, useRef, useState } from "react";

function resolveUserLocale() {
  if (typeof navigator === "undefined") return undefined;
  if (Array.isArray(navigator.languages) && navigator.languages.length) return navigator.languages;
  return navigator.language || undefined;
}

function buildMonthNames(locale) {
  const formatter = new Intl.DateTimeFormat(locale, { month: "long" });
  return Array.from({ length: 12 }, (_, index) =>
    formatter.format(new Date(2020, index, 1))
  );
}

function buildWeekdayLabels(locale) {
  const formatter = new Intl.DateTimeFormat(locale, { weekday: "short" });
  const base = new Date(2021, 7, 1);
  return Array.from({ length: 7 }, (_, index) =>
    formatter.format(new Date(base.getFullYear(), base.getMonth(), base.getDate() + index))
  );
}

function parseISODate(value) {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const [, year, month, day] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

function formatISODate(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDisplay(value, formatter) {
  const date = parseISODate(value);
  if (!date) return "";
  return formatter.format(date);
}

function buildCalendar(year, month) {
  const firstOfMonth = new Date(year, month, 1);
  const firstWeekday = firstOfMonth.getDay();
  let cursor = 1 - firstWeekday;
  const weeks = [];
  for (let row = 0; row < 6; row += 1) {
    const week = [];
    for (let col = 0; col < 7; col += 1) {
      const date = new Date(year, month, cursor);
      week.push({
        date,
        iso: formatISODate(date),
        inMonth: date.getMonth() === month,
      });
      cursor += 1;
    }
    weeks.push(week);
  }
  return weeks;
}

export default function DatePickerField({
  id,
  value,
  onChange,
  placeholder = "Select date",
  disabled = false,
}) {
  const locale = useMemo(() => resolveUserLocale(), []);
  const displayFormatter = useMemo(
    () => new Intl.DateTimeFormat(locale, { year: "numeric", month: "2-digit", day: "2-digit" }),
    [locale]
  );
  const monthNames = useMemo(() => buildMonthNames(locale), [locale]);
  const weekdayLabels = useMemo(() => buildWeekdayLabels(locale), [locale]);
  const today = useMemo(() => new Date(), []);
  const selectedDate = useMemo(() => parseISODate(value), [value]);
  const [viewYear, setViewYear] = useState(selectedDate?.getFullYear() ?? today.getFullYear());
  const [viewMonth, setViewMonth] = useState(selectedDate?.getMonth() ?? today.getMonth());
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    if (!selectedDate) return;
    setViewYear(selectedDate.getFullYear());
    setViewMonth(selectedDate.getMonth());
  }, [selectedDate]);

  useEffect(() => {
    function handleClick(event) {
      if (!wrapperRef.current || wrapperRef.current.contains(event.target)) return;
      setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const calendar = useMemo(() => buildCalendar(viewYear, viewMonth), [viewYear, viewMonth]);

  const handleSelect = (iso) => {
    if (disabled) return;
    setOpen(false);
    onChange?.(iso);
  };

  const handleClear = () => {
    if (disabled) return;
    onChange?.("");
    setOpen(false);
  };

  const handleToday = () => {
    if (disabled) return;
    const iso = formatISODate(today);
    setViewYear(today.getFullYear());
    setViewMonth(today.getMonth());
    onChange?.(iso);
    setOpen(false);
  };

  const goPreviousMonth = () => {
    if (disabled) return;
    if (viewMonth === 0) {
      setViewMonth(11);
      setViewYear((prev) => prev - 1);
    } else {
      setViewMonth((prev) => prev - 1);
    }
  };

  const goNextMonth = () => {
    if (disabled) return;
    if (viewMonth === 11) {
      setViewMonth(0);
      setViewYear((prev) => prev + 1);
    } else {
      setViewMonth((prev) => prev + 1);
    }
  };

  const displayValue = formatDisplay(value, displayFormatter);

  return (
    <div
      className={`date-picker-field ${disabled ? "is-disabled" : ""}`}
      ref={wrapperRef}
    >
      <input
        id={id}
        className="date-picker-input"
        value={displayValue}
        readOnly
        disabled={disabled}
        placeholder={placeholder}
        onClick={() => !disabled && setOpen(true)}
        onFocus={() => !disabled && setOpen(true)}
      />
      <button
        type="button"
        className="date-picker-toggle"
        onClick={() => !disabled && setOpen((prev) => !prev)}
        aria-label="Toggle calendar"
        disabled={disabled}
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <rect x="3" y="5" width="18" height="16" rx="4" stroke="currentColor" strokeWidth="1.4" />
          <path d="M8 3V7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          <path d="M16 3V7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          <path d="M3 11H21" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      </button>
      {open && !disabled ? (
        <div className="date-picker-popover" role="dialog" aria-modal="true">
          <div className="date-picker-header">
            <button type="button" onClick={goPreviousMonth} aria-label="Previous month">
              {"<"}
            </button>
            <span>{`${monthNames[viewMonth]} ${viewYear}`}</span>
            <button type="button" onClick={goNextMonth} aria-label="Next month">
              {">"}
            </button>
          </div>
          <div className="date-picker-weekdays">
            {weekdayLabels.map((day, index) => (
              <span key={`${index}-${day}`}>{day}</span>
            ))}
          </div>
          <div className="date-picker-grid">
            {calendar.flat().map((cell) => {
              const isSelected = value && cell.iso === value;
              const isToday =
                cell.date.getFullYear() === today.getFullYear() &&
                cell.date.getMonth() === today.getMonth() &&
                cell.date.getDate() === today.getDate();
              return (
                <button
                  type="button"
                  key={cell.iso}
                  className={[
                    "date-picker-day",
                    cell.inMonth ? "is-current" : "is-muted",
                    isSelected ? "is-selected" : "",
                    isToday ? "is-today" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onClick={() => handleSelect(cell.iso)}
                >
                  {cell.date.getDate()}
                </button>
              );
            })}
          </div>
          <div className="date-picker-footer">
            <button type="button" onClick={handleClear}>
              Clear
            </button>
            <button type="button" onClick={handleToday}>
              Today
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

