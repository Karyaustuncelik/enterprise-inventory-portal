import { useEffect } from "react";
import { THEME_PALETTES, getThemePalette } from "../theme";
import "./ThemeSettingsDialog.css";

export default function ThemeSettingsDialog({
  open = false,
  value = "",
  saving = false,
  error = "",
  onClose,
  onChange,
  onSave,
}) {
  const selectedPalette = getThemePalette(value);

  useEffect(() => {
    if (!open) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === "Escape" && !saving) onClose?.();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose, saving]);

  if (!open) return null;

  return (
    <div className="theme-dialog-backdrop" role="presentation" onClick={() => !saving && onClose?.()}>
      <div
        className="theme-dialog-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="theme-dialog-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="theme-dialog-header">
          <div>
            <span className="theme-dialog-eyebrow">Personalization</span>
            <h3 id="theme-dialog-title">Choose your accent color</h3>
          </div>
          <button
            type="button"
            className="theme-dialog-close"
            onClick={() => onClose?.()}
            disabled={saving}
            aria-label="Close theme settings"
          >
            x
          </button>
        </div>

        <p className="theme-dialog-copy">
          The selected color is saved to your user profile and will stay active when you open the app again.
        </p>

        <div className="theme-dialog-grid">
          {THEME_PALETTES.map((palette) => {
            const isActive = palette.id === selectedPalette.id;
            return (
              <button
                key={palette.id}
                type="button"
                className={`theme-option${isActive ? " is-active" : ""}`}
                onClick={() => onChange?.(palette.id)}
                aria-pressed={isActive}
              >
                <span
                  className="theme-option-swatch"
                  aria-hidden="true"
                  style={{ backgroundColor: palette.accent }}
                />
                <span className="theme-option-name">{palette.name}</span>
              </button>
            );
          })}
        </div>

        {error ? <div className="theme-dialog-error" role="alert">{error}</div> : null}

        <div className="theme-dialog-actions">
          <button type="button" className="ghost-button" onClick={() => onClose?.()} disabled={saving}>
            Cancel
          </button>
          <button type="button" className="ghost-button primary" onClick={() => onSave?.()} disabled={saving}>
            {saving ? "Saving..." : "Save theme"}
          </button>
        </div>
      </div>
    </div>
  );
}
