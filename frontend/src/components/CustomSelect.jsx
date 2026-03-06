import { useCallback, useEffect, useMemo, useRef, useState } from "react";

function normalizeSearchText(value = "") {
  return String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[\u0131\u0130]/g, "i")
    .replace(/[\u00e7\u00c7]/g, "c")
    .replace(/[\u011f\u011e]/g, "g")
    .replace(/[\u00f6\u00d6]/g, "o")
    .replace(/[\u015f\u015e]/g, "s")
    .replace(/[\u00fc\u00dc]/g, "u")
    .toLowerCase()
    .trim();
}

export default function CustomSelect({
  id,
  options = [],
  value = "",
  onChange,
  onOpenChange,
  placeholder = "Select...",
  disabled = false,
  className = "",
  menuMaxHeight = 280,
  searchable = false,
  searchPlaceholder = "Search...",
  menuDirection = "auto",
}) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const [menuStyle, setMenuStyle] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const ref = useRef(null);
  const selected = useMemo(() => options.find((opt) => String(opt.value) === String(value)), [options, value]);
  const normalizedQuery = useMemo(() => normalizeSearchText(searchQuery), [searchQuery]);
  const visibleOptions = useMemo(() => {
    if (!searchable || !normalizedQuery) return options;
    return options.filter((option) => {
      const normalizedLabel = normalizeSearchText(option?.label ?? option?.value ?? "");
      const normalizedValue = normalizeSearchText(option?.value ?? "");
      return normalizedLabel.startsWith(normalizedQuery) || normalizedValue.startsWith(normalizedQuery);
    });
  }, [options, searchable, normalizedQuery]);
  const menuId = id ? `${id}-menu` : undefined;

  useEffect(() => {
    function handleClickOutside(event) {
      if (ref.current && !ref.current.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (!open) {
      setHighlight(-1);
      setMenuStyle(null);
      setSearchQuery("");
      return;
    }
    const idx = visibleOptions.findIndex((opt) => String(opt.value) === String(selected?.value ?? ""));
    if (idx >= 0) {
      setHighlight(idx);
    } else {
      setHighlight(visibleOptions.length ? 0 : -1);
    }
  }, [open, selected, visibleOptions]);

  useEffect(() => {
    onOpenChange?.(open);
  }, [open, onOpenChange]);

  const updateMenuPosition = useCallback(() => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const viewportPadding = 8;
    const width = rect.width || 200;
    const left = Math.min(rect.left, Math.max(8, window.innerWidth - width - 8));
    const spaceBelow = window.innerHeight - rect.bottom - viewportPadding;
    const spaceAbove = rect.top - viewportPadding;
    const openUpwards =
      menuDirection === "up"
        ? true
        : menuDirection === "down"
        ? false
        : spaceBelow < menuMaxHeight && spaceAbove > spaceBelow;
    const availableSpace = openUpwards ? spaceAbove : spaceBelow;
    const minimumAutoHeight = Math.min(120, menuMaxHeight);
    const maxHeight =
      menuDirection === "auto"
        ? Math.min(menuMaxHeight, Math.max(minimumAutoHeight, availableSpace))
        : menuMaxHeight;
    const top = openUpwards
      ? Math.max(viewportPadding, rect.top - maxHeight - 6)
      : rect.bottom + 6;
    setMenuStyle({
      position: "fixed",
      top,
      left,
      width,
      maxHeight,
      zIndex: 1000,
    });
  }, [menuDirection, menuMaxHeight]);

  useEffect(() => {
    if (!open) return;
    updateMenuPosition();
    const handleScroll = () => updateMenuPosition();
    window.addEventListener("resize", handleScroll);
    window.addEventListener("scroll", handleScroll, true);
    return () => {
      window.removeEventListener("resize", handleScroll);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [open, updateMenuPosition, visibleOptions.length, searchQuery]);

  const handleSelect = (option) => {
    onChange?.(option.value);
    setOpen(false);
  };

  const moveHighlight = useCallback((step) => {
    setHighlight((prev) => {
      const total = visibleOptions.length;
      if (!total) return -1;
      if (prev < 0 || prev >= total) return step > 0 ? 0 : total - 1;
      const next = prev + step;
      if (next >= total) return 0;
      if (next < 0) return total - 1;
      return next;
    });
  }, [visibleOptions.length]);

  const handleKeyDown = (event) => {
    if (!open && (event.key === "Enter" || event.key === " " || event.key === "ArrowDown")) {
      event.preventDefault();
      setOpen(true);
      return;
    }
    if (!open) return;
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveHighlight(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      moveHighlight(-1);
    } else if (event.key === "Enter" && highlight >= 0 && highlight < visibleOptions.length) {
      event.preventDefault();
      handleSelect(visibleOptions[highlight]);
    }
  };

  const handleSearchKeyDown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveHighlight(1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      moveHighlight(-1);
      return;
    }
    if (event.key === "Enter" && highlight >= 0 && highlight < visibleOptions.length) {
      event.preventDefault();
      handleSelect(visibleOptions[highlight]);
    }
  };

  return (
    <div className={`custom-select ${className}`} ref={ref}>
      <button
        type="button"
        id={id}
        className="custom-select-trigger"
        onClick={() => !disabled && setOpen((o) => !o)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
      >
        <span className={`custom-select-value${selected ? "" : " is-placeholder"}`}>
          {selected ? selected.label : placeholder}
        </span>
        <span className="custom-select-caret" aria-hidden="true">
          <svg viewBox="0 0 12 7" aria-hidden="true" focusable="false">
            <path
              d="M1 1l5 5 5-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
            />
          </svg>
        </span>
      </button>
      {open ? (
        <div
          className="custom-select-menu custom-scrollbar"
          style={menuStyle ?? { maxHeight: menuMaxHeight }}
          id={menuId}
          role="listbox"
        >
          {searchable ? (
            <div className="custom-select-search" role="presentation">
              <input
                type="text"
                className="custom-select-search-input"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                onKeyDown={handleSearchKeyDown}
                placeholder={searchPlaceholder}
                autoFocus
                autoComplete="off"
              />
            </div>
          ) : null}
          {visibleOptions.length ? visibleOptions.map((option, index) => {
            const isSelected = selected && option.value === selected.value;
            const isActive = index === highlight;
            return (
              <button
                key={option.value}
                type="button"
                className={`custom-select-option${isSelected ? " is-selected" : ""}${isActive ? " is-active" : ""}`}
                onMouseEnter={() => setHighlight(index)}
                onClick={() => handleSelect(option)}
                role="option"
                aria-selected={isSelected}
              >
                {option.label}
              </button>
            );
          }) : (
            <div className="custom-select-menu-status" role="status" aria-live="polite">
              No matches
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

