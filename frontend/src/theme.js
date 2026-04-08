const THEME_STORAGE_PREFIX = "enterprise.theme.v1";

export const DEFAULT_THEME_ID = "brand-red";

export const THEME_PALETTES = [
  { id: "brand-red", name: "Brand Red", accent: "#e1000f" },
  { id: "cobalt-blue", name: "Cobalt Blue", accent: "#145ce6" },
  { id: "deep-ocean", name: "Deep Ocean", accent: "#0a6d8f" },
  { id: "royal-purple", name: "Royal Purple", accent: "#6b3fd6" },
  { id: "berry-magenta", name: "Berry Magenta", accent: "#b03078" },
  { id: "emerald-green", name: "Emerald Green", accent: "#118a4f" },
  { id: "pine-green", name: "Pine Green", accent: "#2f6d45" },
  { id: "teal-wave", name: "Teal Wave", accent: "#0d8c8c" },
  { id: "amber-gold", name: "Amber Gold", accent: "#9a5d00" },
  { id: "copper-orange", name: "Copper Orange", accent: "#b25520" },
  { id: "plum-violet", name: "Plum Violet", accent: "#7d3f98" },
  { id: "slate-blue", name: "Slate Blue", accent: "#4866a8" },
];

const THEME_LOOKUP = new Map(THEME_PALETTES.map((palette) => [palette.id, palette]));

function hexToRgbTriplet(hex) {
  const normalized = String(hex || "").replace("#", "").trim();
  if (!/^[0-9a-f]{6}$/i.test(normalized)) return "225, 0, 15";
  const value = normalized.toLowerCase();
  const red = Number.parseInt(value.slice(0, 2), 16);
  const green = Number.parseInt(value.slice(2, 4), 16);
  const blue = Number.parseInt(value.slice(4, 6), 16);
  return `${red}, ${green}, ${blue}`;
}

function themeStorageKey(username) {
  const normalized = String(username || "").trim().toLowerCase();
  return `${THEME_STORAGE_PREFIX}:${normalized}`;
}

export function normalizeThemeId(value) {
  const candidate = String(value || "").trim().toLowerCase();
  return THEME_LOOKUP.has(candidate) ? candidate : DEFAULT_THEME_ID;
}

export function getThemePalette(value) {
  return THEME_LOOKUP.get(normalizeThemeId(value)) ?? THEME_LOOKUP.get(DEFAULT_THEME_ID);
}

export function applyThemePalette(value) {
  if (typeof document === "undefined") return getThemePalette(value);
  const palette = getThemePalette(value);
  const root = document.documentElement;
  root.style.setProperty("--accent", palette.accent);
  root.style.setProperty("--accent-rgb", hexToRgbTriplet(palette.accent));
  const themeMeta = document.querySelector('meta[name="theme-color"]');
  if (themeMeta) themeMeta.setAttribute("content", palette.accent);
  return palette;
}

export function readCachedThemeId(username) {
  if (typeof window === "undefined" || !username) return "";
  try {
    return normalizeThemeId(window.localStorage.getItem(themeStorageKey(username)));
  } catch (error) {
    return "";
  }
}

export function writeCachedThemeId(username, value) {
  if (typeof window === "undefined" || !username) return;
  try {
    window.localStorage.setItem(themeStorageKey(username), normalizeThemeId(value));
  } catch (error) {
    // Ignore storage write failures.
  }
}

