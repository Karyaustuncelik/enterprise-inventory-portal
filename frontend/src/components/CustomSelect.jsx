import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

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

function splitSearchTerms(value = "") {
  return normalizeSearchText(value)
    .split(/\s+/)
    .filter(Boolean);
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
  const openFrameRef = useRef(0);
  const selected = useMemo(() => options.find((opt) => String(opt.value) === String(value)), [options, value]);
  const normalizedQuery = useMemo(() => normalizeSearchText(searchQuery), [searchQuery]);
  const visibleOptions = useMemo(() => {
    if (!searchable || !normalizedQuery) return options;
    const queryTerms = splitSearchTerms(normalizedQuery);
    if (!queryTerms.length) return options;
    return options.filter((option) => {
      const normalizedLabel = normalizeSearchText(option?.label ?? option?.value ?? "");
      const normalizedValue = normalizeSearchText(option?.value ?? "");
      const combined = `${normalizedLabel} ${normalizedValue}`.trim();
      return queryTerms.every((term) => combined.includes(term));
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
    if (!ref.current || typeof window === "undefined") return;
    const rect = ref.current.getBoundingClientRect();
    const viewportPadding = 8;
    const menuGap = 6;
    const spaceBelow = Math.max(0, window.innerHeight - rect.bottom - viewportPadding - menuGap);
    const spaceAbove = Math.max(0, rect.top - viewportPadding - menuGap);
    let openUpwards = menuDirection === "up";

    if (menuDirection === "auto") {
      if (spaceBelow >= menuMaxHeight) {
        openUpwards = false;
      } else if (spaceAbove >= menuMaxHeight) {
        openUpwards = true;
      } else {
        openUpwards = spaceAbove > spaceBelow;
      }
    } else if (menuDirection !== "down") {
      openUpwards = spaceAbove > spaceBelow;
    }

    const preferredSpace = openUpwards ? spaceAbove : spaceBelow;
    const alternateSpace = openUpwards ? spaceBelow : spaceAbove;
    if (preferredSpace < 96 && alternateSpace > preferredSpace) {
      openUpwards = !openUpwards;
    }

    const availableSpace = openUpwards ? spaceAbove : spaceBelow;
    const resolvedSpace =
      menuDirection === "auto"
        ? Math.max(availableSpace, Math.max(spaceAbove, spaceBelow))
        : availableSpace;
    const maxHeight = Math.min(menuMaxHeight, Math.max(resolvedSpace, 0));
    setMenuStyle({
      position: "absolute",
      left: 0,
      right: 0,
      top: openUpwards ? "auto" : `calc(100% + ${menuGap}px)`,
      bottom: openUpwards ? `calc(100% + ${menuGap}px)` : "auto",
      maxHeight,
      zIndex: 1000,
    });
  }, [menuDirection, menuMaxHeight]);

  const ensureTriggerVisibility = useCallback(() => {
    if (!ref.current || typeof window === "undefined") return false;
    const rect = ref.current.getBoundingClientRect();
    const viewportPadding = 12;
    const spaceBelow = window.innerHeight - rect.bottom - viewportPadding;
    const spaceAbove = rect.top - viewportPadding;
    const preferredMenuSpace = Math.min(menuMaxHeight, 180);
    const needsDownwardSpace = menuDirection === "down" && spaceBelow < preferredMenuSpace;
    const needsUpwardSpace = menuDirection === "up" && spaceAbove < preferredMenuSpace;
    const isFullyVisible =
      rect.top >= viewportPadding &&
      rect.bottom <= window.innerHeight - viewportPadding &&
      rect.left >= viewportPadding &&
      rect.right <= window.innerWidth - viewportPadding;

    if (isFullyVisible && !needsDownwardSpace && !needsUpwardSpace) return false;
    ref.current.scrollIntoView({
      block: needsDownwardSpace || needsUpwardSpace ? "center" : "nearest",
      inline: "nearest",
      behavior: "auto",
    });
    return true;
  }, [menuDirection, menuMaxHeight]);

  const handleOpen = useCallback(() => {
    if (disabled) return;
    const openMenu = () => {
      updateMenuPosition();
      setOpen(true);
    };

    if (!ensureTriggerVisibility()) {
      openMenu();
      return;
    }

    if (openFrameRef.current) {
      cancelAnimationFrame(openFrameRef.current);
    }
    openFrameRef.current = requestAnimationFrame(() => {
      openFrameRef.current = 0;
      openMenu();
    });
  }, [disabled, ensureTriggerVisibility, updateMenuPosition]);

  useLayoutEffect(() => {
    if (!open) return;
    updateMenuPosition();
    const handleResize = () => updateMenuPosition();
    const handleScroll = (event) => {
      const target = event.target;
      if (ref.current && target instanceof Node && ref.current.contains(target)) {
        updateMenuPosition();
        return;
      }
      setOpen(false);
    };
    window.addEventListener("resize", handleResize);
    window.addEventListener("scroll", handleScroll, true);
    return () => {
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [open, updateMenuPosition, visibleOptions.length, searchQuery]);

  useEffect(() => {
    return () => {
      if (openFrameRef.current) {
        cancelAnimationFrame(openFrameRef.current);
      }
    };
  }, []);

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
      handleOpen();
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
        onClick={() => {
          if (open) {
            setOpen(false);
            return;
          }
          handleOpen();
        }}
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

