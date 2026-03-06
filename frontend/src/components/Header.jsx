import "./Header.css";
import brandMark from "../assets/brand-mark.svg";

const NAV_LINKS = [
  { id: "home", label: "Home" },
  { id: "inventory", label: "Active Inventory" },
  { id: "deleted", label: "Inactive Inventory" },
  { id: "parameters", label: "Edit Field Parameters" },
  { id: "users", label: "Users" },
  { id: "new", label: "Add new item" },
  { id: "charts", label: "Charts" },
];

export default function Header({
  active = "home",
  onNavigate,
  userName = "Guest",
  canGoBack = false,
  canGoForward = false,
  onBack,
  onForward,
  allowedNav = null,
  inventoryCountries = [],
  selectedInventoryCountries = [],
  onInventoryCountryToggle,
  onInventoryCountryClear,
}) {
  const navItems = Array.isArray(allowedNav)
    ? NAV_LINKS.filter((item) => allowedNav.includes(item.id))
    : NAV_LINKS;
  const inventoryOptions = Array.isArray(inventoryCountries) ? inventoryCountries : [];
  const selectedCountrySet = new Set(
    (Array.isArray(selectedInventoryCountries) ? selectedInventoryCountries : [])
      .map((value) => String(value))
  );
  const canShowInventoryMenu = inventoryOptions.length > 0;
  const displayName = userName?.trim() || "Guest";
  const initials =
    displayName
      .split(" ")
      .filter(Boolean)
      .map((part) => part[0]?.toUpperCase())
      .slice(0, 2)
      .join("") || "G";

  return (
    <header className="app-header">
      <div className="brand" aria-label="Enterprise">
        <img
          className="brand-logo"
          src={brandMark}
          alt="Enterprise logo"
          loading="lazy"
        />
      </div>

      <nav className="main-nav" aria-label="Primary">
        <ul>
          {navItems.map((item) => {
            const buttonClass = `nav-button${active === item.id ? " active" : ""}`;
            const hasInventoryMenu = item.id === "inventory" && canShowInventoryMenu;
            return (
              <li key={item.id} className={hasInventoryMenu ? "nav-item nav-item--dropdown" : "nav-item"}>
                <div className="nav-item-inner">
                  <button
                    type="button"
                    className={buttonClass}
                    onClick={() => onNavigate?.(item.id)}
                  >
                    {item.label}
                  </button>
                  {hasInventoryMenu ? (
                    <div className="nav-dropdown" role="menu" aria-label="Country filter">
                      <button
                        type="button"
                        className={`nav-dropdown-item${selectedCountrySet.size === 0 ? " is-selected" : ""}`}
                        onClick={() => onInventoryCountryClear?.()}
                        aria-pressed={selectedCountrySet.size === 0}
                      >
                        <span className="nav-dropdown-check" aria-hidden="true">
                          {selectedCountrySet.size === 0 ? "✓" : ""}
                        </span>
                        <span className="nav-dropdown-label">All</span>
                      </button>
                      <div className="nav-dropdown-divider" role="separator" />
                      {inventoryOptions.map((option) => {
                        const optionValue = String(option.value);
                        const isSelected = selectedCountrySet.has(optionValue);
                        return (
                          <button
                            key={optionValue}
                            type="button"
                            className={`nav-dropdown-item${isSelected ? " is-selected" : ""}`}
                            onClick={() => onInventoryCountryToggle?.(option.value)}
                            aria-pressed={isSelected}
                          >
                            <span className="nav-dropdown-check" aria-hidden="true">
                              {isSelected ? "✓" : ""}
                            </span>
                            <span className="nav-dropdown-label">{option.label ?? option.value}</span>
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
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
          <span className="user-name" title={displayName}>
            {displayName}
          </span>
        </div>
        <div className="header-history-bar" aria-label="Page history">
          <button
            type="button"
            className="header-history-button"
            onClick={onBack}
            disabled={!canGoBack}
            aria-label="Go back"
            title="Back"
          >
            {"<"}
          </button>
          <button
            type="button"
            className="header-history-button"
            onClick={onForward}
            disabled={!canGoForward}
            aria-label="Go forward"
            title="Forward"
          >
            {">"}
          </button>
        </div>
      </div>
    </header>
  );
}
