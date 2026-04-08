import { useEffect, useRef, useState } from "react";
import "./Header.css";
import brandLogo from "../assets/brand-mark.svg";

const NAV_LINKS = [
  { id: "home", label: "Home" },
  { id: "inventory", label: "Inventory" },
  { id: "parameters", label: "Edit Field Parameters" },
  { id: "users", label: "Users" },
  { id: "new", label: "Add new item" },
  { id: "charts", label: "Charts" },
];

export default function Header({
  active = "home",
  onNavigate,
  onInventoryViewSelect,
  userName = "Guest",
  onOpenSettings,
  settingsDisabled = false,
  canGoBack = false,
  canGoForward = false,
  onBack,
  onForward,
  allowedNav = null,
  inventoryCountries = [],
  selectedInventoryCountries = [],
  onInventoryCountrySelect,
  onInventoryCountryClear,
}) {
  const navRef = useRef(null);
  const inventoryMenuRef = useRef(null);
  const [inventoryMenuOpen, setInventoryMenuOpen] = useState(false);
  const [inventorySubmenuView, setInventorySubmenuView] = useState(null);

  const allowedSet = new Set(Array.isArray(allowedNav) ? allowedNav : NAV_LINKS.map((item) => item.id));
  const inventoryEnabled = !Array.isArray(allowedNav) || allowedSet.has("inventory");
  const deletedEnabled = !Array.isArray(allowedNav) || allowedSet.has("deleted");
  const navItems = NAV_LINKS.filter((item) => {
    if (item.id === "inventory") return inventoryEnabled || deletedEnabled;
    return !Array.isArray(allowedNav) || allowedSet.has(item.id);
  });
  const inventoryOptions = Array.isArray(inventoryCountries) ? inventoryCountries : [];
  const selectedCountrySet = new Set(
    (Array.isArray(selectedInventoryCountries) ? selectedInventoryCountries : []).map((value) => String(value))
  );
  const inventoryButtonActive = active === "inventory" || active === "deleted";
  const displayName = userName?.trim() || "Guest";
  const initials =
    displayName
      .split(" ")
      .filter(Boolean)
      .map((part) => part[0]?.toUpperCase())
      .slice(0, 2)
      .join("") || "G";

  useEffect(() => {
    if (!navRef.current) return;
    const activeButton = navRef.current.querySelector(".nav-button.active");
    if (!activeButton) return;
    activeButton.scrollIntoView({
      block: "nearest",
      inline: "center",
      behavior: "smooth",
    });
  }, [active, navItems.length]);

  useEffect(() => {
    if (!inventoryMenuOpen) return undefined;
    const handlePointerDown = (event) => {
      if (inventoryMenuRef.current?.contains(event.target)) return;
      setInventoryMenuOpen(false);
      setInventorySubmenuView(null);
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [inventoryMenuOpen]);

  useEffect(() => {
    if (active !== "inventory" && active !== "deleted") {
      setInventorySubmenuView(null);
    }
  }, [active]);

  const inventorySections = [
    inventoryEnabled ? { id: "inventory", label: "Active Inventory" } : null,
    deletedEnabled ? { id: "deleted", label: "Inactive Inventory" } : null,
  ].filter(Boolean);

  const closeInventoryMenus = () => {
    setInventoryMenuOpen(false);
    setInventorySubmenuView(null);
  };

  return (
    <header className="app-header">
      <div className="brand" aria-label="Enterprise">
        <img className="brand-logo" src={brandLogo} alt="Enterprise logo" loading="lazy" />
      </div>

      <nav className="main-nav" aria-label="Primary" ref={navRef}>
        <ul>
          {navItems.map((item) => {
            if (item.id === "inventory") {
              return (
                <li
                  key={item.id}
                  ref={inventoryMenuRef}
                  className={`nav-item nav-item--inventory${inventoryMenuOpen ? " is-open" : ""}`}
                >
                  <button
                    type="button"
                    className={`nav-button${inventoryButtonActive ? " active" : ""}`}
                    aria-haspopup="menu"
                    aria-expanded={inventoryMenuOpen}
                    onClick={() => {
                      setInventoryMenuOpen((prev) => {
                        const nextOpen = !prev;
                        if (!nextOpen) setInventorySubmenuView(null);
                        return nextOpen;
                      });
                    }}
                  >
                    {item.label}
                  </button>

                  {inventoryMenuOpen ? (
                    <div className="inventory-menu-shell" role="menu" aria-label="Inventory navigation">
                      <div className="nav-dropdown nav-dropdown--primary is-open">
                        {inventorySections.map((section) => {
                          const isSectionActive = active === section.id;
                          const isSubmenuActive = inventorySubmenuView === section.id;
                          return (
                            <button
                              key={section.id}
                              type="button"
                              className={`nav-dropdown-item nav-dropdown-item--section${isSectionActive ? " is-selected" : ""}${isSubmenuActive ? " is-submenu-active" : ""}`}
                              onClick={() => {
                                if (section.id === "deleted") {
                                  onInventoryViewSelect?.("deleted");
                                  closeInventoryMenus();
                                  return;
                                }
                                onInventoryViewSelect?.("inventory");
                                setInventorySubmenuView("inventory");
                              }}
                            >
                              <span className="nav-dropdown-label">{section.label}</span>
                              <span className="nav-dropdown-arrow" aria-hidden="true">&gt;</span>
                            </button>
                          );
                        })}
                      </div>

                      {inventorySubmenuView === "inventory" ? (
                        <div className="nav-dropdown nav-dropdown--secondary is-open" aria-label="Country filter">
                          <div className="nav-submenu-title">Country filter</div>
                          <button
                            type="button"
                            className={`nav-dropdown-item${selectedCountrySet.size === 0 ? " is-selected" : ""}`}
                            onClick={() => {
                              onInventoryCountryClear?.("inventory");
                              closeInventoryMenus();
                            }}
                          >
                            <span className="nav-dropdown-check" aria-hidden="true">{selectedCountrySet.size === 0 ? "x" : ""}</span>
                            <span className="nav-dropdown-label">All countries</span>
                          </button>
                          <div className="nav-dropdown-divider" role="separator" />
                          {inventoryOptions.map((option) => {
                            const optionValue = String(option.value);
                            const isSelected = selectedCountrySet.has(optionValue);
                            return (
                              <button
                                key={`inventory:${optionValue}`}
                                type="button"
                                className={`nav-dropdown-item${isSelected ? " is-selected" : ""}`}
                                onClick={() => {
                                  onInventoryCountrySelect?.("inventory", option.value);
                                  closeInventoryMenus();
                                }}
                              >
                                <span className="nav-dropdown-check" aria-hidden="true">{isSelected ? "x" : ""}</span>
                                <span className="nav-dropdown-label">{option.label ?? option.value}</span>
                              </button>
                            );
                          })}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </li>
              );
            }

            return (
              <li key={item.id} className="nav-item">
                <button
                  type="button"
                  className={`nav-button${active === item.id ? " active" : ""}`}
                  onClick={() => onNavigate?.(item.id)}
                >
                  {item.label}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="header-right">
        <div className="user-chip" aria-label={`Signed in as ${displayName}`}>
          <span className="user-avatar" aria-hidden>
            {initials}
          </span>
          <span className="user-name">{displayName}</span>
        </div>
        <button
          type="button"
          className="header-settings-button"
          onClick={() => onOpenSettings?.()}
          disabled={settingsDisabled}
          aria-label="Open personalization settings"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path
              d="M12 8.25a3.75 3.75 0 1 0 0 7.5a3.75 3.75 0 0 0 0-7.5Zm8 3.75l-1.73-.66a6.77 6.77 0 0 0-.51-1.23l.76-1.68a.75.75 0 0 0-.15-.84l-1.95-1.95a.75.75 0 0 0-.84-.15l-1.68.76c-.39-.21-.8-.38-1.23-.51L12.75 4a.75.75 0 0 0-.75-.5h-2a.75.75 0 0 0-.75.5l-.42 1.85c-.43.13-.84.3-1.23.51l-1.68-.76a.75.75 0 0 0-.84.15L3.13 7.7a.75.75 0 0 0-.15.84l.76 1.68c-.21.39-.38.8-.51 1.23L1.38 12a.75.75 0 0 0-.5.75v2c0 .35.24.66.58.74l1.77.44c.13.43.3.84.51 1.23l-.76 1.68a.75.75 0 0 0 .15.84l1.95 1.95c.23.23.58.29.84.15l1.68-.76c.39.21.8.38 1.23.51l.42 1.85c.08.34.39.58.75.58h2c.36 0 .67-.24.75-.58l.42-1.85c.43-.13.84-.3 1.23-.51l1.68.76c.26.14.61.08.84-.15l1.95-1.95a.75.75 0 0 0 .15-.84l-.76-1.68c.21-.39.38-.8.51-1.23l1.85-.42a.75.75 0 0 0 .58-.74v-2a.75.75 0 0 0-.5-.75Z"
              fill="currentColor"
            />
          </svg>
        </button>
        <div className="header-history-bar" aria-label="Page history">
          <button
            type="button"
            className="header-history-button"
            onClick={onBack}
            disabled={!canGoBack}
            aria-label="Go back"
          >
            {"<"}
          </button>
          <button
            type="button"
            className="header-history-button"
            onClick={onForward}
            disabled={!canGoForward}
            aria-label="Go forward"
          >
            {">"}
          </button>
        </div>
      </div>
    </header>
  );
}


