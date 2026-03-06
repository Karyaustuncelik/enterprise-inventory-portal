import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import MiddleEastMap from "./components/MiddleEastMap";
import Header from "./components/Header";
import VisibleColumns from "./components/VisibleColumns";
import FieldParameters from "./components/FieldParameters";
import UsersPage from "./components/UsersPage";
import CustomSelect from "./components/CustomSelect";
import SpareCoverageChart from "./components/SpareCoverageChart";
import ChartsDashboard from "./components/ChartsDashboard";
import LoadingLogo from "./components/LoadingLogo";
import * as XLSX from "xlsx";
import "./App.css";
import AddItemForm from "./components/AddItemForm";

const MAP_COUNTRIES = [
  { id: "TR", name: "Turkey" },
  { id: "SA", name: "Saudi Arabia" },
  { id: "JO", name: "Jordan" },
  { id: "IL", name: "Israel" },
  { id: "AE", name: "United Arab Emirates" },
];

const COUNTRY_ALIASES = {
  uae: "ae",
  "u.a.e": "ae",
  ksa: "sa",
  "saudi arabia": "sa",
  "kingdom of saudi arabia": "sa",
  "the kingdom of saudi arabia": "sa",
  turkiye: "tr",
  "turkey": "tr",
  "united arab emirates": "ae",
  "birlesik arap emirlikleri": "ae",
};

const NAV_LABELS = {
  home: "Home",
  charts: "Charts",
  inventory: "Active Inventory",
  deleted: "Inactive Inventory",
  parameters: "Edit Field Parameters",
  users: "Users",
  new: "Add new item"
};

const TABLE_COLUMNS = [
  { key: "Country", label: "Country", accessors: ["Country", "country"] },
  { key: "Status", label: "Status", accessors: ["Status", "status"] },
  { key: "Name_Surname", label: "Name Surname", accessors: ["Name_Surname", "name_surname", "Name", "name", "FullName", "fullName"] },
  { key: "Identity", label: "ID", accessors: ["Identity", "identity", "ID", "id"] },
  { key: "Department", label: "Dept", accessors: ["Department", "department"] },
  { key: "Region", label: "Reg", accessors: ["Region", "region"] },
  { key: "Hardware_Type", label: "Type", accessors: ["Hardware_Type", "hardware_type", "HardwareType"] },
  { key: "Hardware_Manufacturer", label: "Manufacturer", accessors: ["Hardware_Manufacturer", "hardware_manufacturer", "Manufacturer", "manufacturer"] },
  { key: "Hardware_Model", label: "Model", accessors: ["Hardware_Model", "hardware_model", "Model", "model"] },
  { key: "Hardware_Serial_Number", label: "Serial No", accessors: ["Hardware_Serial_Number", "hardware_serial_number", "Serial", "serial"] },
  { key: "Asset_Number", label: "Asset ID", accessors: ["Asset_Number", "asset_number", "AssetNo", "assetNo"] },
  { key: "Capitalization_Date", label: "Cap. Date", accessors: ["Capitalization_Date", "capitalization_date", "CapitalizationDate"] },
  { key: "User_Name", label: "User Name", accessors: ["User_Name", "user_name", "Username", "username"] },
  { key: "Old_User", label: "Old User", accessors: ["Old_User", "old_user"] },
  { key: "Windows_Computer_Name", label: "HN", accessors: ["Windows_Computer_Name", "windows_computer_name", "ComputerName", "computer_name"] },
  { key: "Win_OS", label: "Win OS", accessors: ["Win_OS", "win_os", "WindowsVersion", "windows_version"] },
  { key: "Location_Floor", label: "Location", accessors: ["Location_Floor", "location_floor", "Location", "location", "Location/Floor"] },
  { key: "Notes", label: "Notes", accessors: ["Notes", "notes", "Remark", "remark"] },
  { key: "If_Deleted", label: "If Deleted", accessors: ["If_Deleted", "if_deleted", "Deleted", "deleted"] },
  { key: "Age", label: "Age", accessors: ["Age", "age"] },
];

const CHOICE_COLUMNS = [
  "Country",
  "Department",
  "Hardware_Manufacturer",
  "Hardware_Model",
  "Hardware_Type",
  "Identity",
  "Location_Floor",
  "Region",
  "Status",
  "Win_OS",
];

const CHOICE_COLUMN_SET = new Set(CHOICE_COLUMNS);

const COLUMN_PARAM_MAP = {
  Country: "country",
  Status: "status",
  Name_Surname: "name_surname",
  Identity: "identity",
  Department: "department",
  Region: "region",
  Hardware_Type: "hardware_type",
  Hardware_Manufacturer: "hardware_manufacturer",
  Hardware_Model: "hardware_model",
  Hardware_Serial_Number: "hardware_serial_number",
  Asset_Number: "asset_number",
  User_Name: "user_name",
  Old_User: "old_user",
  Windows_Computer_Name: "windows_computer_name",
  Win_OS: "win_os",
  Location_Floor: "location_floor",
  Notes: "notes",
  If_Deleted: "if_deleted",
};

const COLUMN_LOOKUP = TABLE_COLUMNS.reduce((acc, column) => {
  acc[column.key] = column;
  return acc;
}, {});

const DISPLAY_COLUMN_KEYS = [
  "Country",
  "Status",
  "Hardware_Type",
  "Hardware_Manufacturer",
  "Hardware_Model",
  "Hardware_Serial_Number",
  "Asset_Number",
  "Capitalization_Date",
  "Age",
  "Name_Surname",
  "User_Name",
  "Windows_Computer_Name",
  "Department",
  "Region",
  "Location_Floor",
  "Old_User",
  "Notes",
];

const DEFAULT_SEARCH_COLUMN = "Name_Surname";
const DEFAULT_LIMIT = 100;
const UNBOUNDED_LIMIT = 1000000;

const DATE_FILTER_COLUMN = "Capitalization_Date";
const DATE_RANGE_FILTER_ID = "capitalization-date-range";
const DATE_PARAM_FROM = "capitalization_date_from";
const DATE_PARAM_TO = "capitalization_date_to";
const DEFAULT_DATE_FILTER = { mode: "all", from: "", to: "" };
const DATE_FILTER_OPTIONS = [
  { value: "all", label: "All dates" },
  { value: "range", label: "Between" },
  { value: "on_or_after", label: "From date" },
  { value: "on_or_before", label: "Until date" },
];
const AGE_SORT_OPTIONS = [
  { value: "none", label: "None" },
  { value: "asc", label: "Asc" },
  { value: "desc", label: "Desc" },
];
const AGE_SORT_CHOICES = AGE_SORT_OPTIONS.filter((option) => option.value !== "none");
const AGE_SORT_MENU_KEY = "age-sort";

function createDefaultDateFilter() {
  return { ...DEFAULT_DATE_FILTER };
}

const YEAR_ONLY_REGEX = /^\d{4}$/;
const YEAR_MONTH_REGEX = /^\d{4}-(0[1-9]|1[0-2])$/;
const YEAR_MONTH_DAY_REGEX = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

const userLocale = (() => {
  if (typeof navigator === "undefined") return undefined;
  if (Array.isArray(navigator.languages) && navigator.languages.length) return navigator.languages;
  return navigator.language || undefined;
})();

const dateLabelFormatter = new Intl.DateTimeFormat(userLocale, {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const DATE_PART_ORDER = (() => {
  if (typeof dateLabelFormatter.formatToParts !== "function") {
    return ["month", "day", "year"];
  }
  const sampleParts = dateLabelFormatter.formatToParts(new Date(1999, 10, 22));
  const order = sampleParts
    .map((part) => part.type)
    .filter((type) => type !== "literal");
  return order.length ? order : ["month", "day", "year"];
})();

function parseDisplayDate(value) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
  if (value === undefined || value === null) return null;
  const str = String(value).trim();
  if (!str) return null;
  const match = str.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) {
    const [, year, month, day] = match;
    const date = new Date(Number(year), Number(month) - 1, Number(day));
    if (!Number.isNaN(date.getTime())) return date;
  }
  const numericMatch = str.match(/^(\d{1,4})[./-](\d{1,2})[./-](\d{1,4})$/);
  if (numericMatch) {
    const [, part1, part2, part3] = numericMatch;
    let year = "";
    let month = "";
    let day = "";
    if (part1.length === 4) {
      year = part1;
      month = part2;
      day = part3;
    } else {
      year = part3;
      const first = DATE_PART_ORDER[0];
      const second = DATE_PART_ORDER[1];
      if (first === "day" && second === "month") {
        day = part1;
        month = part2;
      } else {
        month = part1;
        day = part2;
      }
    }
    const normalizedYear = Number(year.length === 2 ? `20${year}` : year);
    const normalizedMonth = Number(month);
    const normalizedDay = Number(day);
    const candidate = new Date(normalizedYear, normalizedMonth - 1, normalizedDay);
    if (!Number.isNaN(candidate.getTime())) return candidate;
  }
  const parsed = new Date(str);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
}

function formatDateForDisplay(value) {
  const parsed = parseDisplayDate(value);
  if (!parsed) return "";
  return dateLabelFormatter.format(parsed);
}

function normalizeDateInput(value, boundary = "start") {
  if (!value) return "";
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (YEAR_ONLY_REGEX.test(trimmed)) {
    return boundary === "end" ? `${trimmed}-12-31` : `${trimmed}-01-01`;
  }
  if (YEAR_MONTH_REGEX.test(trimmed)) {
    const [year, month] = trimmed.split("-");
    const monthNumber = Number(month);
    const lastDay = new Date(Number(year), monthNumber, 0).getDate();
    return boundary === "end"
      ? `${year}-${month}-${String(lastDay).padStart(2, "0")}`
      : `${year}-${month}-01`;
  }
  if (YEAR_MONTH_DAY_REGEX.test(trimmed)) {
    return trimmed;
  }
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString().slice(0, 10);
}

function normalizeRowDate(value) {
  if (value === undefined || value === null) return "";
  const str = String(value).trim();
  if (!str) return "";
  const match = str.match(/^(\d{4}-\d{2}-\d{2})/);
  if (match) return match[1];
  return normalizeDateInput(str, "start");
}
// Türkçe karakterleri katlayıp (fold) sadeleştirir: "yağmür" -> "yagmur"
function foldTr(str = "") {
  return String(str)
    .normalize("NFD")               // aksanları ayır
    .replace(/[\u0300-\u036f]/g, "")// birikmiş aksanları sil
    // Türkçe özel harfleri güvenli eşdeğere çevir
    .replace(/ç/gi, "c")
    .replace(/ğ/gi, "g")
    .replace(/[ıİ]/g, "i")
    .replace(/ö/gi, "o")
    .replace(/ş/gi, "s")
    .replace(/ü/gi, "u")
    .toLowerCase()
    .trim();
}

const DISPOSED_STATUS_TOKEN = "disposed";

function isDisposedStatus(value) {
  const normalized = foldTr(value);
  return normalized.includes(DISPOSED_STATUS_TOKEN);
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

function normalizeStatusKey(value) {
  return foldTr(value);
}

function buildStatusActivityMap(items) {
  const map = new Map();
  const list = Array.isArray(items) ? items : [];
  list.forEach((item) => {
    const rawValue = typeof item === "string" ? item : item?.value ?? item?.label;
    if (!rawValue) return;
    const normalized = normalizeStatusKey(rawValue);
    if (!normalized) return;
    const activeFlag = resolveStatusActiveFlag(item);
    if (activeFlag === null) return;
    map.set(normalized, activeFlag);
  });
  return map;
}

function resolveStatusIsActive(value, statusActivityMap) {
  const normalized = normalizeStatusKey(value);
  if (normalized && statusActivityMap?.has(normalized)) {
    return statusActivityMap.get(normalized);
  }
  return !isDisposedStatus(value);
}

const CURRENT_USER_ENDPOINTS = ["/users/me"];

function normalizeRoleName(value) {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (!normalized) return "";
  if (normalized.includes("admin")) return "admin";
  if (normalized === "view" || normalized === "viewer") return "viewer";
  if (normalized.includes("view") || normalized.includes("read")) return "viewer";
  if (normalized.includes("editor")) return "editor";
  return normalized;
}

function normalizeCurrentUser(payload) {
  if (!payload || typeof payload !== "object") return null;
  const source = payload.user ?? payload.currentUser ?? payload;
  if (!source || typeof source !== "object") return null;
  const username =
    source.username ??
    source.userName ??
    source.samAccountName ??
    source.user ??
    "";
  const displayName =
    source.displayName ??
    source.fullName ??
    source.name ??
    "";
  const roleName =
    source.roleName ??
    source.RoleName ??
    source.role?.name ??
    source.role ??
    "";
  const roleIdRaw =
    source.roleId ??
    source.RoleId ??
    source.role?.id ??
    source.role_id ??
    null;
  const roleId = roleIdRaw === null || roleIdRaw === undefined ? null : Number(roleIdRaw);
  if (!username && !displayName && !roleName && roleId === null) return null;
  return {
    username: String(username || "").trim(),
    displayName: String(displayName || "").trim(),
    roleName: String(roleName || "").trim(),
    roleId: Number.isNaN(roleId) ? null : roleId,
  };
}

function resolveCurrentUserRole(user) {
  if (!user) return "";
  const byName = normalizeRoleName(user.roleName ?? user.role);
  const rawRoleId = user.roleId ?? user.RoleId ?? user.role_id ?? user.role?.id;
  const roleId = Number.isFinite(Number(rawRoleId)) ? Number(rawRoleId) : null;
  if (roleId === 1 || byName === "admin") return "admin";
  if (roleId === 3 || byName === "viewer") return "viewer";
  if (roleId !== null || byName) return "editor";
  return "";
}

function resolvePermissions(user) {
  const role = resolveCurrentUserRole(user) || "viewer";
  const canEditInventory = role === "admin" || role === "editor";
  const canEditCharts = role === "admin" || role === "editor";
  const canManageParameters = role === "admin";
  const canManageUsers = role === "admin";
  return {
    role,
    canEditInventory,
    canEditCharts,
    canManageParameters,
    canManageUsers,
  };
}

function resolveRowIsActive(row, statusActivityMap) {
  const deletedColumn = COLUMN_LOOKUP.If_Deleted;
  if (deletedColumn) {
    const rawDeleted = getColumnValue(row, deletedColumn);
    if (rawDeleted !== undefined && rawDeleted !== null && rawDeleted !== "") {
      if (typeof rawDeleted === "boolean") return !rawDeleted;
      const numeric = Number(rawDeleted);
      if (!Number.isNaN(numeric)) return numeric === 0;
      const normalized = String(rawDeleted).trim().toLowerCase();
      if (normalized === "true") return false;
      if (normalized === "false") return true;
    }
  }
  const rawStatus = getColumnValue(row, COLUMN_LOOKUP.Status);
  return resolveStatusIsActive(rawStatus, statusActivityMap);
}

const MULTI_FILTER_DELIMITER_REGEX = /\s*(?:\|\||\||,|;|\bor\b|\bveya\b)\s*/i;
const AGE_RANGE_TOKEN_REGEX = /^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*$/;
const AGE_SINGLE_TOKEN_REGEX = /^\s*\d+(?:\.\d+)?\s*$/;

function splitMultiFilterValues(value) {
  if (value === undefined || value === null) return [];
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  const trimmed = String(value).trim();
  if (!trimmed) return [];
  if (!MULTI_FILTER_DELIMITER_REGEX.test(trimmed)) return [trimmed];
  return trimmed
    .split(MULTI_FILTER_DELIMITER_REGEX)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatFilterTokens(tokens) {
  if (!tokens.length) return "";
  if (tokens.length === 1) return tokens[0];
  return tokens.join(" OR ");
}

function normalizeFilterTokens(value, isChoice) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value !== "string") return [];
  const trimmed = value.trim();
  if (!trimmed) return [];
  return isChoice ? [trimmed] : splitMultiFilterValues(trimmed);
}

function dedupeTokens(tokens, normalize = (value) => foldTr(value)) {
  const seen = new Set();
  const result = [];
  tokens.forEach((token) => {
    const key = normalize(token);
    if (!key || seen.has(key)) return;
    seen.add(key);
    result.push(token);
  });
  return result;
}

function formatDateLabel(value) {
  if (!value) return "";
  const formatted = formatDateForDisplay(value);
  return formatted || String(value);
}

function describeDateFilter(filter) {
  if (!filter || !filter.isActive) return "";
  if (filter.mode === "range") {
    return `${filter.displayFrom} – ${filter.displayTo}`;
  }
  if (filter.mode === "on_or_after") {
    return `From ${filter.displayFrom}`;
  }
  if (filter.mode === "on_or_before") {
    return `Until ${filter.displayTo}`;
  }
  return "";
}

const percentFormatter = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1, minimumFractionDigits: 0 });
const integerFormatter = new Intl.NumberFormat("en-US");

function normaliseCountryCode(value) {
  const raw = value?.toString().trim().toLowerCase();
  if (!raw) return "";
  return COUNTRY_ALIASES[raw] ?? raw;
}

function getColumnValue(row, column) {
  if (!row || !column) return "";
  for (const key of column.accessors) {
    const value = row?.[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return "";
}

function shortenDepartment(value) {
  const str = String(value ?? "").trim();
  if (!str) return "";
  const match = str.match(/^([^-\s]+)/);
  return match?.[1] ?? str;
}

function formatCellValue(value) {
  if (value === undefined || value === null || value === "") return "-";
  if (Array.isArray(value)) {
    const compact = value
      .filter((item) => item !== undefined && item !== null && item !== "")
      .map((item) => String(item).trim())
      .filter(Boolean);
    return compact.length ? compact.join(", ") : "-";
  }
  if (value instanceof Date && !Number.isNaN(value.getTime())) return dateLabelFormatter.format(value);
  if (typeof value === "number" && Number.isFinite(value)) return integerFormatter.format(value);
  return String(value);
}

function formatTableCellValue(row, column) {
  const raw = getColumnValue(row, column);
  if (column.key === DATE_FILTER_COLUMN) {
    const formattedDate = formatDateForDisplay(raw);
    if (formattedDate) return formattedDate;
  }
  if (column.key === "Department") {
    const short = shortenDepartment(raw);
    return short || formatCellValue(raw);
  }
  return formatCellValue(raw);
}

function normalizeChoiceValue(value, columnKey) {
  if (value === undefined || value === null || value === "") return "";
  if (columnKey === "Country") {
    return normaliseCountryCode(value) || foldTr(value);
  }
  return foldTr(value);
}

function matchChoiceTokens(rawValue, tokens, columnKey) {
  if (!tokens.length) return true;
  const rowValues = Array.isArray(rawValue) ? rawValue : [rawValue];
  const normalizedRowValues = rowValues
    .map((value) => normalizeChoiceValue(value, columnKey))
    .filter(Boolean);
  if (!normalizedRowValues.length) return false;
  const normalizedTokens = tokens
    .map((token) => normalizeChoiceValue(token, columnKey))
    .filter(Boolean);
  return normalizedTokens.some((token) => normalizedRowValues.includes(token));
}

function matchTextTokens(rawValue, tokens) {
  if (!tokens.length) return true;
  const normalizedTokens = tokens.map((token) => foldTr(token)).filter(Boolean);
  if (!normalizedTokens.length) return true;
  const rowValues = Array.isArray(rawValue) ? rawValue : [rawValue];
  return rowValues.some((value) => {
    if (value === undefined || value === null || value === "") return false;
    const normalizedValue = foldTr(value);
    if (!normalizedValue) return false;
    return normalizedTokens.some((token) => normalizedValue.includes(token));
  });
}

function parseAgeRangeToken(token) {
  if (token === undefined || token === null) return null;
  const match = String(token).trim().match(AGE_RANGE_TOKEN_REGEX);
  if (!match) return null;
  const start = Number(match[1]);
  const end = Number(match[2]);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  return { min: Math.min(start, end), max: Math.max(start, end) };
}

function parseAgeSingleToken(token) {
  if (token === undefined || token === null) return null;
  const trimmed = String(token).trim();
  if (!AGE_SINGLE_TOKEN_REGEX.test(trimmed)) return null;
  const numeric = Number(trimmed);
  if (!Number.isFinite(numeric)) return null;
  return numeric;
}

function hasAgeRangeToken(tokens = []) {
  return tokens.some((token) => parseAgeRangeToken(token));
}

function matchAgeTokens(rawValue, tokens) {
  if (!tokens.length) return true;
  const numericValue = Number(rawValue);
  if (!Number.isFinite(numericValue)) return false;
  for (const token of tokens) {
    const range = parseAgeRangeToken(token);
    if (range) {
      if (numericValue >= range.min && numericValue <= range.max) return true;
      continue;
    }
    const single = parseAgeSingleToken(token);
    if (single !== null && numericValue === single) return true;
  }
  return false;
}

function rowMatchesFilter(row, filter) {
  const column = COLUMN_LOOKUP[filter.key];
  if (!column) return true;
  const rawValue = getColumnValue(row, column);
  const tokens = filter.tokens ?? [];
  if (filter.key === "Age") {
    return matchAgeTokens(rawValue, tokens);
  }
  if (CHOICE_COLUMN_SET.has(filter.key) || filter.type === "choice") {
    return matchChoiceTokens(rawValue, tokens, filter.key);
  }
  return matchTextTokens(rawValue, tokens);
}

function parseAgeValue(row) {
  const column = COLUMN_LOOKUP.Age;
  if (!column) return null;
  const rawValue = getColumnValue(row, column);
  if (rawValue === undefined || rawValue === null || rawValue === "") return null;
  const numeric = Number(rawValue);
  if (!Number.isFinite(numeric)) return null;
  return numeric;
}

function sortRowsByAge(rows, direction) {
  const sorted = [...rows];
  sorted.sort((a, b) => {
    const aValue = parseAgeValue(a);
    const bValue = parseAgeValue(b);
    if (aValue === null && bValue === null) return 0;
    if (aValue === null) return 1;
    if (bValue === null) return -1;
    if (direction === "desc") return bValue - aValue;
    return aValue - bValue;
  });
  return sorted;
}

function App() {
  const [rows, setRows] = useState([]);
  const [clientFilteredRows, setClientFilteredRows] = useState([]);
  const [loadingRows, setLoadingRows] = useState(true);
  const [limit] = useState(DEFAULT_LIMIT);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [activeNav, setActiveNav] = useState("home");
  const [currentUser, setCurrentUser] = useState(null);
  const [loadingCurrentUser, setLoadingCurrentUser] = useState(true);
  const [navBackStack, setNavBackStack] = useState([]);
  const [navForwardStack, setNavForwardStack] = useState([]);
  const [ratios, setRatios] = useState([]);
  const [loadingRatios, setLoadingRatios] = useState(true);
  const [selectedCountry, setSelectedCountry] = useState(null);
  const [searchColumnKey, setSearchColumnKey] = useState(DEFAULT_SEARCH_COLUMN);
  const [searchQuery, setSearchQuery] = useState("");
  const [filters, setFilters] = useState({});
  const [dateFilter, setDateFilter] = useState(() => createDefaultDateFilter());
  const [ageSort, setAgeSort] = useState("none");
  const [editingRow, setEditingRow] = useState(null);
  const [formReturnNav, setFormReturnNav] = useState("home");
  const [rowsVersion, setRowsVersion] = useState(0);
  const rowsRequestIdRef = useRef(0);
  const [choiceFieldMap, setChoiceFieldMap] = useState({});
  const statusActivityMap = useMemo(
    () => buildStatusActivityMap(choiceFieldMap?.Status),
    [choiceFieldMap]
  );
  const inventoryCountryOptions = useMemo(() => {
    const rawOptions = choiceFieldMap?.Country ?? [];
    const normalized = (Array.isArray(rawOptions) ? rawOptions : [])
      .map((item) => {
        if (typeof item === "string") return { value: item, label: item };
        const value = item?.value ?? item?.label ?? "";
        if (!value) return null;
        const label = item?.label ?? value;
        return { value, label };
      })
      .filter(Boolean);
    const fallback =
      normalized.length === 0
        ? MAP_COUNTRIES.map((item) => ({ value: item.id, label: item.name }))
        : normalized;
    const seen = new Set();
    return fallback
      .filter((item) => {
        const key = String(item.value).toLowerCase();
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .sort((a, b) => String(a.label).localeCompare(String(b.label)));
  }, [choiceFieldMap]);
  const selectedInventoryCountries = useMemo(() => {
    const current = filters.Country;
    if (Array.isArray(current)) return current;
    if (typeof current === "string" && current) return [current];
    return [];
  }, [filters]);
  const hasInventoryCountryFilters = selectedInventoryCountries.length > 0;
  const [openChoiceColumn, setOpenChoiceColumn] = useState(null);
  const [choiceSearchQuery, setChoiceSearchQuery] = useState("");
  const [loadingChoices, setLoadingChoices] = useState(false);
  const choiceMenuRef = useRef(null);
  const [choiceMenuPos, setChoiceMenuPos] = useState({ top: 0, left: 0 });
  const [datePopoverOpen, setDatePopoverOpen] = useState(false);
  const datePopoverRef = useRef(null);
  const chartRef = useRef(null);
  const permissions = useMemo(() => resolvePermissions(currentUser), [currentUser]);
  const isAuthenticated = Boolean(currentUser?.username || currentUser?.displayName);
  const {
    canEditInventory,
    canEditCharts,
    canManageParameters,
    canManageUsers,
  } = permissions;
  const allowedNavIds = useMemo(() => {
    const allowed = new Set(["home", "inventory", "deleted", "charts"]);
    if (canEditInventory) allowed.add("new");
    if (canManageParameters) allowed.add("parameters");
    if (canManageUsers) allowed.add("users");
    return Array.from(allowed);
  }, [canEditInventory, canManageParameters, canManageUsers]);

  // —— Visible Columns (NEW)
  const ALL_COL_KEYS = useMemo(() => DISPLAY_COLUMN_KEYS, []);
  const [visibleColKeys, setVisibleColKeys] = useState(ALL_COL_KEYS);
  const viewColumns = useMemo(() => {
    if (activeNav === "inventory" || activeNav === "deleted") {
      const base = activeNav === "deleted"
        ? TABLE_COLUMNS
        : TABLE_COLUMNS.filter((column) => column.key !== "If_Deleted");
      const filtered = base.filter((column) => DISPLAY_COLUMN_KEYS.includes(column.key));
      const ordered = filtered.sort(
        (a, b) => DISPLAY_COLUMN_KEYS.indexOf(a.key) - DISPLAY_COLUMN_KEYS.indexOf(b.key)
      );
      return ordered;
    }
    return TABLE_COLUMNS;
  }, [activeNav]);
  const viewColumnKeys = useMemo(() => viewColumns.map((column) => column.key), [viewColumns]);
  const searchableColumns = useMemo(
    () => viewColumns.filter((column) => !CHOICE_COLUMN_SET.has(column.key)),
    [viewColumns]
  );
  useEffect(() => {
    let ignore = false;
    async function loadCurrentUser() {
      setLoadingCurrentUser(true);
      for (const endpoint of CURRENT_USER_ENDPOINTS) {
        try {
          const response = await api.get(endpoint);
          const normalized = normalizeCurrentUser(response.data ?? response);
          if (!ignore) {
            setCurrentUser(normalized);
            setLoadingCurrentUser(false);
          }
          return;
        } catch (err) {
          const status = err?.response?.status;
          if (status === 404) {
            continue;
          }
          if (!ignore) {
            setCurrentUser(null);
            setLoadingCurrentUser(false);
          }
          return;
        }
      }
      if (!ignore) {
        setCurrentUser(null);
        setLoadingCurrentUser(false);
      }
    }
    loadCurrentUser();
    return () => {
      ignore = true;
    };
  }, []);
  useEffect(() => {
    setVisibleColKeys((prev) => {
      const allowed = new Set(viewColumnKeys);
      const filtered = prev.filter((key) => allowed.has(key));
      const missing = viewColumnKeys.filter((key) => !filtered.includes(key));
      if (!filtered.length) return [];
      if (!missing.length && filtered.length === prev.length) return prev;
      return filtered.concat(missing);
    });
  }, [viewColumnKeys]);
  useEffect(() => {
    const pool = searchableColumns.length ? searchableColumns : viewColumns;
    if (pool.some((column) => column.key === searchColumnKey)) return;
    const fallbackKey = pool[0]?.key ?? DEFAULT_SEARCH_COLUMN;
    if (fallbackKey) setSearchColumnKey(fallbackKey);
  }, [viewColumns, searchableColumns, searchColumnKey]);
  useEffect(() => {
    setFilters((prev) => {
      const allowed = new Set(viewColumnKeys);
      const next = { ...prev };
      let changed = false;
      Object.keys(next).forEach((key) => {
        if (!allowed.has(key)) {
          delete next[key];
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, [viewColumnKeys]);
  const visibleColumns = useMemo(
    () => viewColumns.filter((column) => visibleColKeys.includes(column.key)),
    [viewColumns, visibleColKeys]
  );
  const refreshRows = useCallback(() => {
    setRowsVersion((prev) => prev + 1);
  }, []);

  const dateFilterState = useMemo(() => {
    const mode = dateFilter.mode;
    const trimmedFrom = dateFilter.from.trim();
    const trimmedTo = dateFilter.to.trim();
    const base = {
      mode,
      from: "",
      to: "",
      displayFrom: "",
      displayTo: "",
      isActive: false,
      error: null,
    };

    if (mode === "all") return base;

    if (mode === "range") {
      if (!trimmedFrom || !trimmedTo) {
        return { ...base, error: "Select a start and end date" };
      }
      const normalizedFrom = normalizeDateInput(trimmedFrom, "start");
      const normalizedTo = normalizeDateInput(trimmedTo, "end");
      if (!normalizedFrom || !normalizedTo) {
        return { ...base, error: "Enter valid dates (YYYY, YYYY-MM, or YYYY-MM-DD)" };
      }
      if (normalizedFrom > normalizedTo) {
        return { ...base, error: "Start date must come before end date" };
      }
      return {
        mode,
        from: normalizedFrom,
        to: normalizedTo,
        displayFrom: formatDateLabel(normalizedFrom),
        displayTo: formatDateLabel(normalizedTo),
        isActive: true,
        error: null,
      };
    }

    if (mode === "on_or_after") {
      if (!trimmedFrom) {
        return { ...base, error: "Enter a starting date" };
      }
      const normalizedFrom = normalizeDateInput(trimmedFrom, "start");
      if (!normalizedFrom) {
        return { ...base, error: "Enter a valid starting date" };
      }
      return {
        mode,
        from: normalizedFrom,
        to: "",
        displayFrom: formatDateLabel(normalizedFrom),
        displayTo: "",
        isActive: true,
        error: null,
      };
    }

    if (mode === "on_or_before") {
      if (!trimmedTo) {
        return { ...base, error: "Enter an end date" };
      }
      const normalizedTo = normalizeDateInput(trimmedTo, "end");
      if (!normalizedTo) {
        return { ...base, error: "Enter a valid end date" };
      }
      return {
        mode,
        from: "",
        to: normalizedTo,
        displayFrom: "",
        displayTo: formatDateLabel(normalizedTo),
        isActive: true,
        error: null,
      };
    }

    return base;
  }, [dateFilter]);

  const hasDateFilter = dateFilterState.isActive;
  const dateFilterError = dateFilterState.error;
  const dateFilterColumnDef = COLUMN_LOOKUP[DATE_FILTER_COLUMN];

  useEffect(() => {
    if (!isAuthenticated) {
      setRatios([]);
      setLoadingRatios(false);
      return;
    }
    let ignore = false;
    setLoadingRatios(true);
    api.get("/spare_ratios")
      .then((res) => { if (!ignore) setRatios(res.data?.items ?? []); })
      .catch((err) => { console.error("/spare_ratios error", err); })
      .finally(() => { if (!ignore) setLoadingRatios(false); });
    return () => { ignore = true; };
  }, [isAuthenticated]);

  useEffect(() => {
    if (activeNav !== "home" && activeNav !== "inventory") {
      setSelectedCountry(null);
    }
  }, [activeNav]);

  const applyNav = useCallback((target) => {
    if (target === "home" || target === "inventory") {
      setCurrentPage(1);
    }
    setActiveNav(target);
  }, []);

  const navigateTo = useCallback((target) => {
    if (!target || target === activeNav) return;
    setNavBackStack((prev) => [...prev, activeNav]);
    setNavForwardStack([]);
    applyNav(target);
  }, [activeNav, applyNav]);

  const handleBackNav = useCallback(() => {
    setNavBackStack((prevBack) => {
      if (!prevBack.length) {
        if (activeNav !== "home") {
          setNavForwardStack((prevForward) => [...prevForward, activeNav]);
          applyNav("home");
        }
        return prevBack;
      }
      const previous = prevBack[prevBack.length - 1];
      setNavForwardStack((prevForward) => [...prevForward, activeNav]);
      applyNav(previous);
      return prevBack.slice(0, -1);
    });
  }, [activeNav, applyNav]);

  const handleForwardNav = useCallback(() => {
    setNavForwardStack((prevForward) => {
      if (!prevForward.length) return prevForward;
      const next = prevForward[prevForward.length - 1];
      setNavBackStack((prevBack) => [...prevBack, activeNav]);
      applyNav(next);
      return prevForward.slice(0, -1);
    });
  }, [activeNav, applyNav]);

  const handleNavigate = useCallback((target) => {
    if (target === "new" && !canEditInventory) return;
    if (target === "users" && !canManageUsers) return;
    if (target === "parameters" && !canManageParameters) return;
    if (target === "new") {
      setFormReturnNav(
        activeNav === "deleted"
          ? "deleted"
          : activeNav === "inventory"
          ? "inventory"
          : "home"
      );
      setEditingRow(null);
    }
    navigateTo(target);
  }, [navigateTo, canEditInventory, canManageParameters, canManageUsers, activeNav]);

  const handleInventoryCountryClear = useCallback(() => {
    setFilters((prev) => {
      if (!prev.Country) return prev;
      const next = { ...prev };
      delete next.Country;
      return next;
    });
    setSelectedCountry(null);
    if (activeNav !== "inventory") handleNavigate("inventory");
  }, [activeNav, handleNavigate]);

  const handleInventoryCountryToggle = useCallback((value) => {
    if (!value) return;
    setFilters((prev) => {
      const next = { ...prev };
      const current = next.Country;
      if (Array.isArray(current)) {
        const exists = current.includes(value);
        const updated = exists
          ? current.filter((item) => item !== value)
          : current.concat(value);
        if (updated.length) next.Country = updated;
        else delete next.Country;
        return next;
      }
      if (typeof current === "string" && current) {
        if (current === value) delete next.Country;
        else next.Country = [current, value];
        return next;
      }
      next.Country = value;
      return next;
    });
    setSelectedCountry(null);
    if (activeNav !== "inventory") handleNavigate("inventory");
  }, [activeNav, handleNavigate]);

  const handleCreateNew = useCallback(() => {
    if (!canEditInventory) return;
    setFormReturnNav(
      activeNav === "deleted"
        ? "deleted"
        : activeNav === "inventory"
        ? "inventory"
        : "home"
    );
    setEditingRow(null);
    navigateTo("new");
  }, [navigateTo, canEditInventory, activeNav]);

  const handleEditRow = useCallback((row) => {
    if (!row || !canEditInventory) return;
    setFormReturnNav(activeNav === "deleted" ? "deleted" : "inventory");
    setEditingRow(row);
    navigateTo("new");
  }, [navigateTo, canEditInventory, activeNav]);

  const handleFormCancel = useCallback(() => {
    const targetNav =
      editingRow && (formReturnNav === "inventory" || formReturnNav === "deleted")
        ? formReturnNav
        : "home";
    setEditingRow(null);
    navigateTo(targetNav);
  }, [navigateTo, editingRow, formReturnNav]);

  const handleFormSaved = useCallback((responseData, meta = {}) => {
    refreshRows();
    setEditingRow(null);
    const statusValue =
      responseData?.Status ??
      responseData?.status ??
      meta?.status ??
      "";
    const statusIsActive = typeof meta?.statusIsActive === "boolean"
      ? meta.statusIsActive
      : resolveStatusIsActive(statusValue, statusActivityMap);
    const shouldShowDeleted = !statusIsActive;
    navigateTo(shouldShowDeleted ? "deleted" : "inventory");
  }, [refreshRows, navigateTo, statusActivityMap]);

  const mapData = useMemo(() => {
    const byCode = new Map();
    ratios.forEach((item) => {
      const code = normaliseCountryCode(item?.country ?? item?.Country)?.toUpperCase();
      if (!code) return;
      const name = MAP_COUNTRIES.find((entry) => entry.id === code)?.name ?? code;
      const ratio = Number(item?.ratio ?? item?.coverage ?? 0) || 0;
      const spare = Number(item?.spare ?? item?.spareCount ?? 0) || 0;
      const total = Number(item?.total ?? item?.totalCount ?? 0) || 0;
      byCode.set(code, { id: code, name, value: ratio, ratio, spare, total });
    });
    MAP_COUNTRIES.forEach((country) => {
      if (!byCode.has(country.id)) byCode.set(country.id, { id: country.id, name: country.name, value: 0, ratio: 0, spare: 0, total: 0 });
    });
    return Array.from(byCode.values()).sort((a, b) => a.id.localeCompare(b.id));
  }, [ratios]);

  const averageRatio = useMemo(() => {
    if (!mapData.length) return 0;
    const totals = mapData.reduce((acc, item) => { acc.spare += Number(item.spare) || 0; acc.total += Number(item.total) || 0; return acc; }, { spare: 0, total: 0 });
    if (!totals.total) return 0;
    return totals.spare / totals.total;
  }, [mapData]);

  const exportSvgToCanvas = useCallback((svgEl) => new Promise((resolve, reject) => {
    if (!svgEl) {
      reject(new Error("SVG not found"));
      return;
    }
    const serializer = new XMLSerializer();
    const svgString = serializer.serializeToString(svgEl);
    const blob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    const { width, height } = (() => {
      const viewBox = svgEl.viewBox?.baseVal;
      if (viewBox?.width && viewBox?.height) return { width: viewBox.width, height: viewBox.height };
      const rect = svgEl.getBoundingClientRect();
      return { width: Math.max(1, rect.width), height: Math.max(1, rect.height) };
    })();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0, width, height);
      URL.revokeObjectURL(url);
      resolve(canvas);
    };
    img.onerror = reject;
    img.src = url;
  }), []);

  const handleExportVisuals = useCallback(async () => {
    try {
      const mapSvg = document.querySelector(".map-canvas");
      const chartSvg = chartRef.current?.querySelector("svg");
      if (!mapSvg || !chartSvg) return;

      const [mapCanvas, chartCanvas] = await Promise.all([
        exportSvgToCanvas(mapSvg),
        exportSvgToCanvas(chartSvg),
      ]);

      const gap = 24;
      const exportCanvas = document.createElement("canvas");
      exportCanvas.width = mapCanvas.width + chartCanvas.width + gap;
      exportCanvas.height = Math.max(mapCanvas.height, chartCanvas.height);
      const ctx = exportCanvas.getContext("2d");
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, exportCanvas.width, exportCanvas.height);
      ctx.drawImage(mapCanvas, 0, 0);
      ctx.drawImage(chartCanvas, mapCanvas.width + gap, 0);

      const link = document.createElement("a");
      link.download = "spare-coverage-visuals.png";
      link.href = exportCanvas.toDataURL("image/png");
      link.click();

      if (mapData.length) {
        const rows = [["Country", "Spare coverage", "Spare", "Total"]];
        mapData.forEach((item) => {
          rows.push([
            item.name ?? item.id,
            `${(Number(item.value ?? item.ratio ?? 0) * 100).toFixed(1)}%`,
            Number(item.spare ?? 0) || 0,
            Number(item.total ?? 0) || 0,
          ]);
        });
        const ws = XLSX.utils.aoa_to_sheet(rows);
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, "Coverage");
        XLSX.writeFile(wb, "spare_coverage.xlsx");
      }
    } catch (err) {
      console.error("export visuals error", err);
    }
  }, [chartRef, exportSvgToCanvas, mapData]);

  const activeColumn = useMemo(() => {
    const pool = searchableColumns.length ? searchableColumns : viewColumns;
    const fallback = pool[0] ?? TABLE_COLUMNS[0];
    return pool.find((column) => column.key === searchColumnKey) ?? fallback;
  }, [searchColumnKey, searchableColumns, viewColumns]);
  const searchTerm = useMemo(() => searchQuery.trim(), [searchQuery]);
  const searchDraftTokens = useMemo(() => splitMultiFilterValues(searchQuery), [searchQuery]);

  const commitSearchTokens = useCallback((columnKey, tokens) => {
    if (!columnKey) return;
    const cleanedTokens = tokens.map((item) => String(item).trim()).filter(Boolean);
    if (!cleanedTokens.length) return;
    setFilters((prev) => {
      const next = { ...prev };
      const existing = normalizeFilterTokens(prev[columnKey], false);
      const merged = dedupeTokens(existing.concat(cleanedTokens));
      if (merged.length) next[columnKey] = merged;
      else delete next[columnKey];
      return next;
    });
    setSearchQuery("");
    setCurrentPage(1);
  }, []);
  const activeSearchTokens = useMemo(() => {
    if (!activeColumn?.key) return [];
    return normalizeFilterTokens(filters[activeColumn.key], false);
  }, [filters, activeColumn?.key]);
  const showSearchClear = Boolean(searchQuery.trim()) || activeSearchTokens.length > 0;

  const preparedFilters = useMemo(() => {
    const entries = [];
    const filterKeys = new Set(Object.keys(filters));
    if (searchDraftTokens.length && searchColumnKey) {
      filterKeys.add(searchColumnKey);
    }

    filterKeys.forEach((key) => {
      const isChoice = CHOICE_COLUMN_SET.has(key);
      const value = filters[key];
      let tokens = normalizeFilterTokens(value, isChoice);
      if (!isChoice && key === searchColumnKey && searchDraftTokens.length) {
        tokens = tokens.concat(searchDraftTokens);
      }
      const cleanedTokens = dedupeTokens(
        tokens,
        isChoice
          ? (token) => normalizeChoiceValue(token, key) || String(token).trim().toLowerCase()
          : (token) => foldTr(token)
      );
      if (!cleanedTokens.length) return;
      entries.push({
        key,
        value,
        tokens: cleanedTokens,
        trimmed: formatFilterTokens(cleanedTokens),
        label: COLUMN_LOOKUP[key]?.label ?? key,
        type: isChoice ? "choice" : "text",
      });
    });

    if (dateFilterState.isActive) {
      entries.push({
        key: DATE_RANGE_FILTER_ID,
        value: { from: dateFilterState.from, to: dateFilterState.to },
        trimmed: describeDateFilter(dateFilterState),
        label: COLUMN_LOOKUP[DATE_FILTER_COLUMN]?.label ?? "Capitalization Date",
        type: "date",
        tokens: [],
        meta: dateFilterState,
      });
    }

    return entries;
  }, [filters, dateFilterState, searchDraftTokens, searchColumnKey]);

  const activeFilters = useMemo(() => {
    const result = [];
    preparedFilters.forEach((filter) => {
      const column = COLUMN_LOOKUP[filter.key];
      const base = {
        key: filter.key,
        label: filter.label ?? column?.label ?? filter.key,
        value: filter.value,
        type: filter.type,
        meta: filter.meta,
      };

      if (filter.type === "text" && Array.isArray(filter.tokens) && filter.tokens.length) {
        filter.tokens.forEach((token, index) => {
          const tokenKey = foldTr(token) || `${index}`;
          result.push({
            ...base,
            id: `${filter.key}:${tokenKey}:${index}`,
            token,
            trimmed: token,
          });
        });
        return;
      }

      result.push({
        ...base,
        id: filter.key,
        token: null,
        trimmed: filter.trimmed,
      });
    });
    return result;
  }, [preparedFilters]);

  const nonDateFilters = useMemo(
    () => preparedFilters.filter((filter) => filter.type !== "date"),
    [preparedFilters]
  );
  const hasMultiValueFilters = useMemo(
    () => nonDateFilters.some((filter) => (filter.tokens?.length ?? 0) > 1),
    [nonDateFilters]
  );
  const hasAgeRangeFilters = useMemo(
    () => nonDateFilters.some((filter) => filter.key === "Age" && hasAgeRangeToken(filter.tokens)),
    [nonDateFilters]
  );

  const hasFilters = activeFilters.length > 0;
  const isTableViewActive = activeNav === "inventory" || activeNav === "deleted";
  const columnOptions = searchableColumns.length ? searchableColumns : viewColumns;
  const useStatusViewFilter = isTableViewActive;
  const useClientFiltering = hasMultiValueFilters || hasAgeRangeFilters || useStatusViewFilter;
  const useClientSorting = isTableViewActive && ageSort !== "none";
  const useUnboundedLimit = useClientFiltering || useClientSorting;
  const effectivePage = useUnboundedLimit ? 1 : currentPage;

  const rowParams = useMemo(() => {
    const isDeletedView = activeNav === "deleted";
    const effectiveLimit = useUnboundedLimit ? UNBOUNDED_LIMIT : limit;
    const offset = useUnboundedLimit ? 0 : (effectivePage - 1) * limit;
    const params = {
      limit: effectiveLimit,
      offset,
    };
    if (activeNav === "inventory" || activeNav === "deleted") {
      params.if_deleted = isDeletedView ? 1 : 0;
    }
      if (selectedCountry?.id && !hasInventoryCountryFilters) {
        params.country = selectedCountry.id.toUpperCase();
      }

    preparedFilters.forEach((filter) => {
      if (filter.type === "date") {
        const range = filter.meta ?? filter.value ?? {};
        if (range.from) params[DATE_PARAM_FROM] = range.from;
        if (range.to) params[DATE_PARAM_TO] = range.to;
        return;
      }
      const tokens = filter.tokens ?? [];
      if (!tokens.length) return;
      if (filter.key === "Age" && hasAgeRangeToken(tokens)) return;
      if (tokens.length > 1) return;
      const trimmed = String(tokens[0]).trim();
      if (!trimmed) return;
      const paramKey = COLUMN_PARAM_MAP[filter.key];
      if (paramKey === "country") {
        const code = normaliseCountryCode(trimmed);
        if (code) params.country = code.toUpperCase();
        return;
      }
      if (paramKey === "if_deleted") {
        const numeric = Number(trimmed);
        if (!Number.isNaN(numeric)) params.if_deleted = numeric;
        return;
      }
      if (paramKey) {
        if (CHOICE_COLUMN_SET.has(filter.key)) {
          params[paramKey] = trimmed;
        } else {
          params[paramKey] = foldTr(trimmed);
        }
        return;
      }
      if (!params.search) {
        const accessor = COLUMN_LOOKUP[filter.key]?.accessors?.[0];
        if (accessor) {
          params.column = accessor;
          params.search = foldTr(trimmed);
        }
      }
    });
    return params;
  }, [useUnboundedLimit, limit, effectivePage, selectedCountry?.id, preparedFilters, activeNav, hasInventoryCountryFilters]);

  const pageDisplayCount = pageCount || rows.length;
  const totalDisplayCount = totalCount || rows.length;
  const totalPages = Math.max(1, Math.ceil(totalDisplayCount / limit));
  const safeCurrentPage = Math.min(Math.max(currentPage, 1), totalPages);
  const pageNumbers = useMemo(() => {
    const maxButtons = 5;
    let start = Math.max(1, safeCurrentPage - 2);
    let end = Math.min(totalPages, start + maxButtons - 1);
    start = Math.max(1, end - maxButtons + 1);
    const list = [];
    for (let i = start; i <= end; i += 1) list.push(i);
    return list;
  }, [safeCurrentPage, totalPages]);

  const goToPage = useCallback((page) => {
    const target = Math.min(Math.max(page, 1), totalPages);
    setCurrentPage(target);
  }, [totalPages]);

  useEffect(() => {
    if (currentPage !== safeCurrentPage) {
      setCurrentPage(safeCurrentPage);
    }
  }, [currentPage, safeCurrentPage]);

  useEffect(() => {
    if ((activeNav !== "home" && activeNav !== "deleted") || safeCurrentPage === 1) return;
    setCurrentPage(1);
  }, [selectedCountry?.id, preparedFilters, activeNav, safeCurrentPage]);

  useEffect(() => {
    if (!dateFilterState.isActive) return;
    setCurrentPage(1);
  }, [dateFilterState.isActive]);

  useEffect(() => {
    setCurrentPage(1);
  }, [ageSort]);

  const handleRemoveFilter = useCallback((columnKey, tokenToRemove = null) => {
    if (columnKey === DATE_RANGE_FILTER_ID) {
      setDateFilter(createDefaultDateFilter());
      setCurrentPage(1);
      return;
    }

    const normalizedToken = tokenToRemove ? foldTr(tokenToRemove) : "";
    const removeSingleToken = Boolean(normalizedToken);
    let removed = false;
    setFilters((prev) => {
      if (!Object.prototype.hasOwnProperty.call(prev, columnKey)) return prev;
      if (!removeSingleToken) {
        removed = true;
        const next = { ...prev };
        delete next[columnKey];
        return next;
      }

      const currentTokens = normalizeFilterTokens(prev[columnKey], false);
      if (!currentTokens.length) return prev;
      const nextTokens = currentTokens.filter((token) => foldTr(token) !== normalizedToken);
      if (nextTokens.length === currentTokens.length) return prev;
      removed = true;
      const next = { ...prev };
      if (nextTokens.length) next[columnKey] = nextTokens;
      else delete next[columnKey];
      return next;
    });

    let draftChanged = false;
    if (activeColumn?.key === columnKey && searchQuery.trim()) {
      if (removeSingleToken) {
        const draftTokens = splitMultiFilterValues(searchQuery);
        const nextDraftTokens = draftTokens.filter((token) => foldTr(token) !== normalizedToken);
        if (nextDraftTokens.length !== draftTokens.length) {
          setSearchQuery(nextDraftTokens.join(" OR "));
          draftChanged = true;
        }
      } else {
        setSearchQuery("");
        draftChanged = true;
      }
    }

    if (!removed && !draftChanged) return;
    setCurrentPage(1);
  }, [activeColumn?.key, searchQuery]);

  const handleClearAllFilters = useCallback(() => {
    if (!preparedFilters.length && !searchQuery && !hasDateFilter) return;
    setFilters({});
    setDateFilter(createDefaultDateFilter());
    setSearchQuery("");
    setCurrentPage(1);
  }, [preparedFilters.length, searchQuery, hasDateFilter]);

  const handleChoiceSelect = useCallback((columnKey, optionValue) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (!optionValue) {
        delete next[columnKey];
        return next;
      }
      const current = next[columnKey];
      if (Array.isArray(current)) {
        const exists = current.includes(optionValue);
        const updated = exists
          ? current.filter((item) => item !== optionValue)
          : current.concat(optionValue);
        if (updated.length) next[columnKey] = updated;
        else delete next[columnKey];
        return next;
      }
      if (typeof current === "string" && current) {
        if (current === optionValue) delete next[columnKey];
        else next[columnKey] = [current, optionValue];
        return next;
      }
      next[columnKey] = optionValue;
      return next;
    });
    setOpenChoiceColumn(null);
    setCurrentPage(1);
  }, []);

  const handleAgeSortSelect = useCallback((nextValue) => {
    setAgeSort(nextValue || "none");
    setOpenChoiceColumn(null);
  }, []);

  const handleChoiceToggle = useCallback((columnKey, anchorEl) => {
    setOpenChoiceColumn((prev) => {
      const next = prev === columnKey ? null : columnKey;
      if (!next) return null;
      if (anchorEl?.getBoundingClientRect) {
        const rect = anchorEl.getBoundingClientRect();
        const width = 240;
        const left = Math.min(rect.left, Math.max(8, window.innerWidth - width - 8));
        const top = rect.bottom + 8;
        setChoiceMenuPos({ top, left });
      }
      return next;
    });
  }, []);

  const handleAgeSortToggle = useCallback((anchorEl) => {
    setOpenChoiceColumn((prev) => {
      const next = prev === AGE_SORT_MENU_KEY ? null : AGE_SORT_MENU_KEY;
      if (!next) return null;
      if (anchorEl?.getBoundingClientRect) {
        const rect = anchorEl.getBoundingClientRect();
        const width = 200;
        const left = Math.min(rect.left, Math.max(8, window.innerWidth - width - 8));
        const top = rect.bottom + 8;
        setChoiceMenuPos({ top, left });
      }
      return next;
    });
  }, []);
  const handleDateModeChange = useCallback((nextMode) => {
    setDateFilter((prev) => ({ ...prev, mode: nextMode }));
    setDatePopoverOpen(nextMode !== "all");
  }, []);
  const handleVisibleColumnChange = useCallback((nextKeys) => {
    const allowed = new Set(viewColumnKeys);
    const filtered = (nextKeys ?? []).filter((key) => allowed.has(key));
    setVisibleColKeys(filtered);
  }, [viewColumnKeys]);

  useEffect(() => {
    const isTableView = activeNav === "inventory" || activeNav === "deleted";
    document.body.classList.toggle("is-table-view", isTableView);
    return () => {
      document.body.classList.remove("is-table-view");
    };
  }, [activeNav]);

  useEffect(() => {
    const isParametersView = activeNav === "parameters";
    document.body.classList.toggle("is-parameters-view", isParametersView);
    return () => {
      document.body.classList.remove("is-parameters-view");
    };
  }, [activeNav]);

  useEffect(() => {
    const isHomeView = activeNav === "home";
    document.body.classList.toggle("is-home-view", isHomeView);
    return () => {
      document.body.classList.remove("is-home-view");
    };
  }, [activeNav]);

  useEffect(() => {
    const isChartsView = activeNav === "charts";
    document.body.classList.toggle("is-charts-view", isChartsView);
    return () => {
      document.body.classList.remove("is-charts-view");
    };
  }, [activeNav]);

  useEffect(() => {
    if (!isAuthenticated) {
      setChoiceFieldMap({});
      setLoadingChoices(false);
      return;
    }
    if (activeNav !== "inventory" && activeNav !== "deleted") return;
    let ignore = false;
    setLoadingChoices(true);
    api.get("/field-parameters")
      .then(({ data }) => {
        if (!ignore) setChoiceFieldMap(data?.fields ?? {});
      })
      .catch((err) => {
        console.error("/field-parameters error", err);
      })
      .finally(() => {
        if (!ignore) setLoadingChoices(false);
      });
    return () => {
      ignore = true;
    };
  }, [activeNav, isAuthenticated]);

  useEffect(() => {
    setChoiceSearchQuery("");
  }, [openChoiceColumn]);

  useEffect(() => {
    if (!openChoiceColumn) return;
    function handleClick(event) {
      if (choiceMenuRef.current && !choiceMenuRef.current.contains(event.target)) {
        setOpenChoiceColumn(null);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [openChoiceColumn]);

  useEffect(() => {
    if (!openChoiceColumn) choiceMenuRef.current = null;
  }, [openChoiceColumn]);

  useEffect(() => {
    function handleDocClick(event) {
      if (datePopoverRef.current && !datePopoverRef.current.contains(event.target)) {
        setDatePopoverOpen(false);
      }
    }
    document.addEventListener("mousedown", handleDocClick);
    return () => document.removeEventListener("mousedown", handleDocClick);
  }, []);

  useEffect(() => {
    setOpenChoiceColumn(null);
  }, [activeNav, visibleColumns]);

  useEffect(() => {
    if (!isAuthenticated) {
      rowsRequestIdRef.current += 1;
      setRows([]);
      setClientFilteredRows([]);
      setPageCount(0);
      setTotalCount(0);
      setLoadingRows(false);
      return;
    }
    if (activeNav !== "home" && activeNav !== "inventory" && activeNav !== "deleted") {
      rowsRequestIdRef.current += 1;
      setRows([]);
      setClientFilteredRows([]);
      setPageCount(0);
      setTotalCount(0);
      setLoadingRows(false);
      return;
    }
    const requestId = ++rowsRequestIdRef.current;
    setLoadingRows(true);
    api.get("/rows", { params: rowParams })
      .then(({ data }) => {
        if (requestId !== rowsRequestIdRef.current) return;
        const items = Array.isArray(data?.items) ? data.items : [];
        const hydratedItems = items.map((item) =>
          item && typeof item === "object" ? { ...item } : item
        ); // keep every field (including ID) intact for edit flow
        let processedItems = hydratedItems;

        if (dateFilterState.isActive && dateFilterColumnDef) {
          processedItems = hydratedItems.filter((row) => {
            const rawValue = getColumnValue(row, dateFilterColumnDef);
            if (rawValue === undefined || rawValue === null || rawValue === "") return false;
            const normalizedValue = normalizeRowDate(rawValue);
            if (!normalizedValue) return false;
            if (dateFilterState.from && normalizedValue < dateFilterState.from) return false;
            if (dateFilterState.to && normalizedValue > dateFilterState.to) return false;
            return true;
          });
        }

        if (useStatusViewFilter) {
          processedItems = processedItems.filter((row) => {
            const rowIsActive = resolveRowIsActive(row, statusActivityMap);
            return activeNav === "deleted" ? !rowIsActive : rowIsActive;
          });
        }

        if (useClientFiltering && nonDateFilters.length) {
          processedItems = processedItems.filter((row) =>
            nonDateFilters.every((filter) => rowMatchesFilter(row, filter))
          );
        }

        if (useClientSorting) {
          processedItems = sortRowsByAge(processedItems, ageSort);
        }

        if (useClientFiltering || useClientSorting) {
          setClientFilteredRows(processedItems);
          setTotalCount(processedItems.length);
          return;
        }

        setClientFilteredRows([]);
        setRows(processedItems);

        const rawTotalCount = Number(data?.total_count ?? data?.total ?? data?.count ?? processedItems.length);
        const baseTotalCount = Number.isFinite(rawTotalCount) ? rawTotalCount : processedItems.length;

        setPageCount(processedItems.length);
        setTotalCount(baseTotalCount);
      })
      .catch((err) => {
        if (requestId === rowsRequestIdRef.current) {
          console.error("/rows error", err);
          setRows([]);
          setClientFilteredRows([]);
          setPageCount(0);
          setTotalCount(0);
        }
      })
      .finally(() => {
        if (requestId === rowsRequestIdRef.current) setLoadingRows(false);
      });
  }, [
    activeNav,
    rowParams,
    dateFilterState,
    dateFilterColumnDef,
    rowsVersion,
    useClientFiltering,
    useClientSorting,
    nonDateFilters,
    ageSort,
    useStatusViewFilter,
    statusActivityMap,
    isAuthenticated,
  ]);

  useEffect(() => {
    if (!useClientFiltering && !useClientSorting) return;
    const start = (currentPage - 1) * limit;
    const pageItems = clientFilteredRows.slice(start, start + limit);
    setRows(pageItems);
    setPageCount(pageItems.length);
  }, [useClientFiltering, useClientSorting, clientFilteredRows, currentPage, limit]);

  useEffect(() => {
    if (!selectedCountry) return;
    const updated = mapData.find((item) => item.id === selectedCountry.id);
    if (updated) {
      if (updated.spare !== selectedCountry.spare || updated.total !== selectedCountry.total || updated.ratio !== selectedCountry.ratio) {
        setSelectedCountry(updated);
      }
    }
  }, [mapData, selectedCountry]);

  const handleSelectCountry = (country) => {
    if (!country?.id) return;
    setSelectedCountry((prev) => {
      if (prev?.id === country.id) return null;
      const enriched = mapData.find((item) => item.id === country.id) ?? country;
      return enriched;
    });
  };

  // ——— Excel’e sadece seçili kolonları aktar (NEW)
  const exportSelectedToExcel = async () => {
    if (!visibleColumns.length) return;

    // Tüm veri (filtreli veya filtresiz) için büyük limit ile çek
    const exportParams = { ...rowParams, limit: UNBOUNDED_LIMIT, offset: 0 };
    try {
      let items = [];
      if (useClientFiltering) {
        items = clientFilteredRows;
      } else {
        const { data } = await api.get("/rows", { params: exportParams });
        items = Array.isArray(data?.items) ? data.items : rows;
      }
      if (!items.length) return;

      const headerMap = Object.fromEntries(visibleColumns.map(c => [c.key, c.label]));
      const dataset = items.map(r => {
        const obj = {};
        visibleColumns.forEach(c => {
          const val = formatCellValue(getColumnValue(r, c));
          obj[headerMap[c.key] || c.key] = val;
        });
        return obj;
      });

      const ws = XLSX.utils.json_to_sheet(dataset);
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, "Inventory");
      XLSX.writeFile(wb, "inventory_selected_columns.xlsx");
    } catch (err) {
      console.error("export error", err);
    }
  };

  const activeLabel = NAV_LABELS[activeNav] ?? "Workspace";

  const renderTableSection = (heading, { showCreate = true, showCountryChip = false } = {}) => {
    const showCountryIndicator = showCountryChip && selectedCountry;
    const allowCreate = showCreate && canEditInventory;
    const showHeader =
      Boolean(heading) || showCountryIndicator || allowCreate || loadingRows;

    return (
      <section className="table-section">
        {showHeader ? (
          <header className="table-header">
            <div>
              {heading ? <h2>{heading}</h2> : null}
              {showCountryIndicator ? (
                <div className="table-country-filter">
                  <button
                    type="button"
                    className="table-filter-chip"
                    onClick={() => setSelectedCountry(null)}
                    aria-label={`Clear country filter ${selectedCountry.name ?? selectedCountry.id}`}
                  >
                    <span className="table-filter-chip-label">Country</span>
                    <span className="table-filter-chip-value">{selectedCountry.name ?? selectedCountry.id}</span>
                    <span className="table-filter-chip-remove">x</span>
                  </button>
                </div>
              ) : null}
            </div>
            {allowCreate ? (
              <div className="table-header-meta">
                {allowCreate ? (
                  <button
                    type="button"
                    className="add-circle-button"
                    onClick={handleCreateNew}
                    aria-label="Add new item"
                  >
                    <span aria-hidden="true">+</span>
                  </button>
                ) : null}
              </div>
            ) : null}
          </header>
        ) : null}

      <div className="table-controls" role="search">
        <div className="table-filters">
          <div className="table-controls-group table-column-group">
            <label htmlFor="table-column">Column</label>
            <CustomSelect
              options={columnOptions.map((column) => ({ value: column.key, label: column.label }))}
              value={activeColumn?.key}
              onChange={(nextKey) => {
                if (activeColumn?.key && searchDraftTokens.length) {
                  commitSearchTokens(activeColumn.key, searchDraftTokens);
                }
                setSearchColumnKey(nextKey);
                setSearchQuery("");
              }}
              disabled={!columnOptions.length}
              placeholder="Select column"
            />
          </div>

          <div className="table-controls-group table-search-group">
            <label htmlFor="table-search">Search</label>
            <div className="table-search-field">
              <input
                id="table-search"
                type="search"
                placeholder={`Search ${activeColumn.label.toLowerCase()}`}
                value={searchQuery}
                onChange={(event) => {
                  const value = event.target.value;
                  const previousValue = searchQuery;
                  const inputType = event.nativeEvent?.inputType;
                  if (!activeColumn?.key) return;
                  if (
                    inputType &&
                    inputType.startsWith("insert") &&
                    inputType !== "insertText" &&
                    previousValue.trim() &&
                    value.trim() &&
                    previousValue.trim() !== value.trim()
                  ) {
                    commitSearchTokens(activeColumn.key, splitMultiFilterValues(previousValue));
                  }
                  setSearchQuery(value);
                  if (MULTI_FILTER_DELIMITER_REGEX.test(value)) {
                    commitSearchTokens(activeColumn.key, splitMultiFilterValues(value));
                  }
                  setCurrentPage(1);
                }}
                onKeyDown={(event) => {
                  if (event.key !== "Enter") return;
                  event.preventDefault();
                  if (!activeColumn?.key) return;
                  commitSearchTokens(activeColumn.key, searchDraftTokens);
                }}
                onBlur={() => {
                  if (!activeColumn?.key) return;
                  if (!searchDraftTokens.length) return;
                  commitSearchTokens(activeColumn.key, searchDraftTokens);
                }}
              />
              {showSearchClear ? (
                <button
                  type="button"
                  className="clear-search-button"
                  onClick={() => {
                    setSearchQuery("");
                    setFilters((prev) => {
                      if (!activeColumn?.key) return prev;
                      const next = { ...prev };
                      delete next[activeColumn.key];
                      return next;
                    });
                    setCurrentPage(1);
                  }}
                >
                  Clear
                </button>
              ) : null}
            </div>
          </div>

          <div className="table-controls-group table-date-group" ref={datePopoverRef}>
            <label htmlFor="table-date-mode">{COLUMN_LOOKUP[DATE_FILTER_COLUMN]?.label ?? "Capitalization Date"}</label>
            <div className="table-date-controls">
              <CustomSelect
                options={DATE_FILTER_OPTIONS}
                value={dateFilter.mode}
                onChange={(nextMode) => {
                  handleDateModeChange(nextMode);
                  setDatePopoverOpen(nextMode !== "all");
                }}
                onOpenChange={(nextOpen) => {
                  if (nextOpen) setDatePopoverOpen(false);
                }}
                placeholder="All dates"
              />
            </div>
            {dateFilter.mode !== "all" && datePopoverOpen ? (
              <div className="table-date-popover" role="dialog" aria-label="Capitalization date filter">
                {dateFilter.mode === "range" ? (
                  <>
                    <input
                      className="table-date-input"
                      type="text"
                      inputMode="numeric"
                      placeholder="From YYYY or YYYY-MM-DD"
                      value={dateFilter.from}
                      onChange={(event) =>
                        setDateFilter((prev) => ({ ...prev, from: event.target.value }))
                      }
                    />
                    <input
                      className="table-date-input"
                      type="text"
                      inputMode="numeric"
                      placeholder="To YYYY or YYYY-MM-DD"
                      value={dateFilter.to}
                      onChange={(event) =>
                        setDateFilter((prev) => ({ ...prev, to: event.target.value }))
                      }
                    />
                  </>
                ) : null}

                {dateFilter.mode === "on_or_after" ? (
                  <input
                    className="table-date-input table-date-input--single"
                    type="text"
                    inputMode="numeric"
                    placeholder="From YYYY or YYYY-MM-DD"
                    value={dateFilter.from}
                    onChange={(event) =>
                      setDateFilter((prev) => ({ ...prev, from: event.target.value }))
                    }
                  />
                ) : null}

                {dateFilter.mode === "on_or_before" ? (
                  <input
                    className="table-date-input table-date-input--single"
                    type="text"
                    inputMode="numeric"
                    placeholder="Until YYYY or YYYY-MM-DD"
                    value={dateFilter.to}
                    onChange={(event) =>
                      setDateFilter((prev) => ({ ...prev, to: event.target.value }))
                    }
                  />
                ) : null}

                {dateFilterError ? (
                  <span className="table-date-error" role="alert">{dateFilterError}</span>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        <div className="table-actions">
          <span className="table-controls-label">Quick actions</span>
          <div className="table-actions-buttons">
            <VisibleColumns
              columns={viewColumns}
              selected={visibleColKeys}
              onChange={handleVisibleColumnChange}
              label="Visible Columns"
              buttonClassName="circle-button circle-button--neutral table-visible-button"
              buttonAriaLabel="Adjust visible columns"
              renderButtonContent={({ selectedCount }) => (
                <span className="table-visible-count">{selectedCount}</span>
              )}
            />
            <button
              type="button"
              className="circle-button circle-button--primary"
              onClick={handleCreateNew}
              aria-label="Add new item"
            >
              <span aria-hidden="true">+</span>
            </button>
            <button
              type="button"
              className="circle-button circle-button--neutral"
              onClick={exportSelectedToExcel}
              disabled={!rows.length}
              aria-label="Export selected rows to Excel"
            >
              <svg className="excel-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M5 3h9l5 5v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zm9 1v4h4zM8.4 11h1.7l1.4 2.5L12.9 11h1.7l-2.1 3.3 2.2 3.7h-1.7l-1.5-2.6-1.5 2.6H8.3l2.2-3.7zM13 12h2v1h-2zm0 3h2v1h-2z" />
              </svg>
            </button>
          </div>
        </div>

      </div>
      {activeFilters.length ? (
        <div className="table-active-filters" aria-live="polite">
          <span className="table-active-filters-label">Active filters:</span>
          {activeFilters.map((filter) => (
            <button
              type="button"
              key={filter.id}
              className="table-filter-chip"
              onClick={() => handleRemoveFilter(filter.key, filter.token)}
              aria-label={`Remove filter ${filter.label}${filter.token ? ` ${filter.token}` : ""}`}
            >
              <span className="table-filter-chip-label">{filter.label}</span>
              <span className="table-filter-chip-value">{filter.trimmed}</span>
              <span className="table-filter-chip-remove">x</span>
            </button>
          ))}
          {activeFilters.length ? (
            <button type="button" className="table-clear-filters" onClick={handleClearAllFilters}>
              Clear all
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="table-body">
        {loadingRows ? (
        <div className="table-placeholder table-placeholder--logo">
          <LoadingLogo label="Loading data" size={112} />
        </div>
      ) : !rows.length ? (
        <div className="table-placeholder">
          {searchTerm
            ? `No results for "${searchTerm}" in ${activeColumn.label}.`
            : hasFilters
            ? "No records matched the active filters."
            : selectedCountry
            ? `No inventory records found for ${selectedCountry.name ?? selectedCountry.id}.`
            : "Inventory feed returned no rows."}
        </div>
      ) : (
        <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  {canEditInventory ? (
                    <th className="table-actions-column">Actions</th>
                  ) : null}
                  {visibleColumns.map((column) => {
                    const isChoiceColumn = CHOICE_COLUMN_SET.has(column.key);
                    const hideCountryFilter =
                      activeNav === "inventory" &&
                      column.key === "Country" &&
                      inventoryCountryOptions.length > 0;
                    const isAgeColumn = column.key === "Age";
                    const optionList = choiceFieldMap[column.key] ?? [];
                    const normalizedChoiceSearch = foldTr(choiceSearchQuery);
                    const hasChoiceSearch = Boolean(normalizedChoiceSearch);
                    const choiceOptions = (Array.isArray(optionList) ? optionList : [])
                      .map((item) => {
                        if (typeof item === "string") {
                          return { value: item, label: item };
                        }
                        const value = item?.value ?? item?.label ?? "";
                        if (!value) return null;
                        const label = item?.label ?? value;
                        return { value, label };
                      })
                      .filter(Boolean);
                    const filteredChoiceOptions = hasChoiceSearch
                      ? choiceOptions.filter((option) => {
                          const normalizedValue = foldTr(option.value);
                          const normalizedLabel = foldTr(option.label);
                          return (
                            normalizedValue.startsWith(normalizedChoiceSearch) ||
                            normalizedLabel.startsWith(normalizedChoiceSearch)
                          );
                        })
                      : choiceOptions;
                    return (
                      <th key={column.key}>
                        <div className="column-header-inner">
                          <span>{column.label}</span>
                          {isChoiceColumn && !hideCountryFilter ? (
                            <div className="choice-filter">
                              <button
                                type="button"
                                className="choice-trigger"
                                onClick={(event) => handleChoiceToggle(column.key, event.currentTarget)}
                                aria-label={`Filter ${column.label}`}
                              >
                                <svg viewBox="0 0 12 7" aria-hidden="true" focusable="false">
                                  <path d="M1 1l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                                </svg>
                              </button>
                              {openChoiceColumn === column.key ? (
                                <div
                                  className="choice-menu"
                                  ref={(node) => {
                                    if (openChoiceColumn === column.key) choiceMenuRef.current = node;
                                  }}
                                  style={{
                                    position: "fixed",
                                    top: choiceMenuPos.top,
                                    left: choiceMenuPos.left,
                                    width: 240,
                                    maxHeight: 260,
                                  }}
                                >
                                  <div className="choice-search">
                                    <input
                                      type="text"
                                      className="choice-search-input"
                                      placeholder={`Search ${column.label}`}
                                      value={choiceSearchQuery}
                                      onChange={(event) => setChoiceSearchQuery(event.target.value)}
                                      autoFocus
                                      autoComplete="off"
                                    />
                                  </div>
                                  <button
                                    type="button"
                                    className="choice-option choice-option--clear"
                                    onClick={() => handleChoiceSelect(column.key, null)}
                                  >
                                    Clear filter
                                  </button>
                                  {loadingChoices ? (
                                    <div className="choice-menu-status">Loading...</div>
                                  ) : filteredChoiceOptions.length ? (
                                    filteredChoiceOptions.map((option) => {
                                      const optionValue = option.value;
                                      const activeValue = filters[column.key];
                                      const isActive = Array.isArray(activeValue)
                                        ? activeValue.includes(optionValue)
                                        : activeValue === optionValue;
                                      return (
                                        <button
                                          type="button"
                                          key={optionValue}
                                          className={`choice-option${isActive ? " is-active" : ""}`}
                                          onClick={() => handleChoiceSelect(column.key, optionValue)}
                                        >
                                          {optionValue}
                                        </button>
                                      );
                                    })
                                  ) : (
                                    <div className="choice-menu-status">
                                      {hasChoiceSearch ? "No matches" : "No options"}
                                    </div>
                                  )}
                                </div>
                              ) : null}
                            </div>
                          ) : null}
                          {isAgeColumn ? (
                            <div className="choice-filter">
                              <button
                                type="button"
                                className="choice-trigger"
                                onClick={(event) => handleAgeSortToggle(event.currentTarget)}
                                aria-label="Sort age"
                              >
                                <svg viewBox="0 0 12 7" aria-hidden="true" focusable="false">
                                  <path d="M1 1l5 5 5-5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                                </svg>
                              </button>
                              {openChoiceColumn === AGE_SORT_MENU_KEY ? (
                                <div
                                  className="choice-menu"
                                  ref={(node) => {
                                    if (openChoiceColumn === AGE_SORT_MENU_KEY) {
                                      choiceMenuRef.current = node;
                                    }
                                  }}
                                  style={{
                                    position: "fixed",
                                    top: choiceMenuPos.top,
                                    left: choiceMenuPos.left,
                                    width: 200,
                                    maxHeight: 220,
                                  }}
                                >
                                  <button
                                    type="button"
                                    className="choice-option choice-option--clear"
                                    onClick={() => handleAgeSortSelect("none")}
                                  >
                                    Clear sort
                                  </button>
                                  {AGE_SORT_CHOICES.map((option) => {
                                    const isActive = ageSort === option.value;
                                    return (
                                      <button
                                        type="button"
                                        key={option.value}
                                        className={`choice-option${isActive ? " is-active" : ""}`}
                                        onClick={() => handleAgeSortSelect(option.value)}
                                      >
                                        {option.label}
                                      </button>
                                    );
                                  })}
                                </div>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => {
                  const rowKey =
                    row.ID ??
                    row.Id ??
                    row.id ??
                    row.Asset_Number ??
                    row.Hardware_Serial_Number ??
                    row.Identity ??
                    row.Windows_Computer_Name ??
                    row.Name_Surname ??
                    `row-${index}`;
                  return (
                    <tr key={rowKey}>
                      {canEditInventory ? (
                        <td className="table-actions-cell">
                          <button
                            type="button"
                            className="ghost-button table-edit-button"
                            onClick={() => handleEditRow(row)}
                          >
                            Edit
                          </button>
                        </td>
                      ) : null}
                      {visibleColumns.map((column) => (
                        <td key={column.key}>{formatTableCellValue(row, column)}</td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
      )}
        <div className="table-footer">
          <div className="table-result-counter" aria-live="polite">
        {`${integerFormatter.format(pageDisplayCount)} / ${integerFormatter.format(totalDisplayCount)} records`}
      </div>
          {rows.length ? (
          <div className="table-pagination" aria-label="Pagination controls">
            <button
              type="button"
              className="page-button"
              onClick={() => goToPage(1)}
              disabled={safeCurrentPage === 1 || loadingRows}
            >
              «
            </button>
            <button
              type="button"
              className="page-button"
              onClick={() => goToPage(safeCurrentPage - 1)}
              disabled={safeCurrentPage === 1 || loadingRows}
            >
              ‹
            </button>
            {pageNumbers.map((page) => (
              <button
                key={page}
                type="button"
                className={`page-button${page === safeCurrentPage ? " is-active" : ""}`}
                onClick={() => goToPage(page)}
                disabled={loadingRows}
              >
                {page}
              </button>
            ))}
            <button
              type="button"
              className="page-button"
              onClick={() => goToPage(safeCurrentPage + 1)}
              disabled={safeCurrentPage === totalPages || loadingRows}
            >
              ›
            </button>
            <button
              type="button"
              className="page-button"
              onClick={() => goToPage(totalPages)}
              disabled={safeCurrentPage === totalPages || loadingRows}
            >
              »
            </button>
          </div>
          ) : null}
        </div>
      </div>
    </section>
  );
  };

  const coverageSummary = {
    value: percentFormatter.format(selectedCountry ? selectedCountry.ratio ?? 0 : averageRatio ?? 0),
    label: selectedCountry ? `Spare coverage in ${selectedCountry.id}` : "Regional average coverage",
    note: selectedCountry
      ? `${integerFormatter.format(selectedCountry.spare ?? 0)} spare units / ${integerFormatter.format(selectedCountry.total ?? 0)} total`
      : loadingRatios
      ? ""
      : "Based on countries with reported inventory",
  };

  const homeContent = (
    <section className="map-section home-dashboard">
      <div className="home-grid">
        <div className="coverage-card coverage-card--map">
          <div className="coverage-card-header">
            <div>
              <span className="coverage-eyebrow">Coverage map</span>
              <h3 className="coverage-title">Country view</h3>
            </div>
          </div>
          <MiddleEastMap data={mapData} onSelect={handleSelectCountry} selectedCountry={selectedCountry} />
          {selectedCountry ? (
            <button type="button" className="ghost-button" onClick={() => setSelectedCountry(null)}>
              Clear country filter
            </button>
          ) : null}
        </div>
        <SpareCoverageChart
          data={mapData}
          onExportVisuals={handleExportVisuals}
          ref={chartRef}
          summary={coverageSummary}
        />
      </div>
    </section>
  );

  const chartsContent = (
    <ChartsDashboard columns={TABLE_COLUMNS} canEdit={canEditCharts} />
  );

  const inventoryContent = renderTableSection(
    selectedCountry ? `Assets in ${selectedCountry.name}` : null,
    { showCreate: false, showCountryChip: true }
  );

  const deletedContent = renderTableSection(null, { showCreate: false });

  const placeholderContent = (
    <section className="placeholder-section">
      <div className="placeholder-card">
        <span className="placeholder-eyebrow">Coming soon</span>
        <h2>{activeLabel}</h2>
        <p>
          This workspace will host the {activeLabel.toLowerCase()} tools. Design is underway and the
          backend endpoints will follow the main inventory rollout.
        </p>
        <ul>
          <li>Align required data fields and filters with the backend squad.</li>
          <li>Define the KPIs to display at the top of the page.</li>
          <li>Plan the core table layout and actions before implementation.</li>
        </ul>
      </div>
    </section>
  );

  const restrictedContent = (title) => (
    <section className="placeholder-section">
      <div className="placeholder-card">
        <span className="placeholder-eyebrow">Restricted</span>
        <h2>{title}</h2>
        <p>
          {loadingCurrentUser
            ? "Loading your user profile..."
            : "You do not have access to this page."}
        </p>
      </div>
    </section>
  );

  if (loadingCurrentUser) {
    return (
      <div className="app-shell">
        <section className="placeholder-section">
          <LoadingLogo label="Loading your user profile" size={168} />
        </section>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="app-shell">
        <section className="placeholder-section">
          <div className="placeholder-card">
            <span className="placeholder-eyebrow">Authentication required</span>
            <h2>Sign in</h2>
            <p>You must sign in to access the inventory application.</p>
          </div>
        </section>
      </div>
    );
  }

  const canGoBack = navBackStack.length > 0 || activeNav !== "home";
  const canGoForward = navForwardStack.length > 0;
  const resolvedUserName =
    currentUser?.displayName?.trim() ||
    currentUser?.username?.trim() ||
    "Guest";
  const headerUserName = loadingCurrentUser ? "Loading..." : resolvedUserName;

  return (
    <div className="app-shell">
      <Header
        active={activeNav}
        onNavigate={handleNavigate}
        userName={headerUserName}
        canGoBack={canGoBack}
        canGoForward={canGoForward}
        onBack={handleBackNav}
        onForward={handleForwardNav}
        allowedNav={allowedNavIds}
        inventoryCountries={inventoryCountryOptions}
        selectedInventoryCountries={selectedInventoryCountries}
        onInventoryCountryToggle={handleInventoryCountryToggle}
        onInventoryCountryClear={handleInventoryCountryClear}
      />
      <main className="app-main">
        {activeNav === "home" ? (
          homeContent
        ) : activeNav === "charts" ? (
          chartsContent
        ) : activeNav === "inventory" ? (
          inventoryContent
        ) : activeNav === "deleted" ? (
          deletedContent
        ) : activeNav === "parameters" ? (
          canManageParameters ? (
            <FieldParameters canEdit />
          ) : (
            restrictedContent("Edit Field Parameters")
          )
        ) : activeNav === "users" ? (
          <UsersPage
            canManageUsers={canManageUsers}
            currentUser={currentUser}
            loadingCurrentUser={loadingCurrentUser}
          />
        ) : activeNav === "new" ? (
          canEditInventory ? (
            <section className="form-section">
              <AddItemForm
                initialData={editingRow}
                mode={editingRow ? "edit" : "create"}
                onCancel={handleFormCancel}
                onSaved={handleFormSaved}
              />
            </section>
          ) : (
            restrictedContent("Add new item")
          )
        ) : (
          placeholderContent
        )}
      </main>
    </div>
  );
}

export default App;
