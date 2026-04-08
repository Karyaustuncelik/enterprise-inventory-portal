import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as XLSX from "xlsx";
import { api } from "../api";
import { exportSvgToCanvas } from "../utils/svgExport";
import CustomSelect from "./CustomSelect";
import LoadingLogo from "./LoadingLogo";
import "./ChartsDashboard.css";

const STORAGE_KEY = "enterprise.charts.v1";
const FETCH_LIMIT = 1000000;
const GROUP_VALUE_OPTION_LIMIT = 300;
const NULL_FILTER_VALUE = "__NULL_FILTER__";
const NULL_FILTER_LABEL = "Null";

const METRIC_OPTIONS = [
  { value: "count", label: "Count items" },
  { value: "ratio", label: "Ratio (%)" },
];

const COUNTRY_ALIASES = {
  uae: "ae",
  "u.a.e": "ae",
  ksa: "sa",
  "saudi arabia": "sa",
  "kingdom of saudi arabia": "sa",
  "the kingdom of saudi arabia": "sa",
  turkiye: "tr",
  turkey: "tr",
  "united arab emirates": "ae",
  "birlesik arap emirlikleri": "ae",
};

const MULTI_FILTER_DELIMITER_REGEX = /\s*(?:\|\||\||,|;|\+|\bor\b|\bveya\b)\s*/i;

function splitMultiFilterValues(value) {
  if (value === undefined || value === null) return [];
  const trimmed = String(value).trim();
  if (!trimmed) return [];
  if (!MULTI_FILTER_DELIMITER_REGEX.test(trimmed)) return [trimmed];
  return trimmed
    .split(MULTI_FILTER_DELIMITER_REGEX)
    .map((item) => item.trim())
    .filter(Boolean);
}

function isNullFilterToken(value) {
  return typeof value === "string" && value.trim() === NULL_FILTER_VALUE;
}

function isBlankFilterValue(value) {
  return value === undefined || value === null || (typeof value === "string" && value.trim() === "");
}

function formatFilterTokenLabel(value) {
  if (isNullFilterToken(value)) return NULL_FILTER_LABEL;
  return String(value ?? "").trim();
}

function formatFilterTokenSummary(value) {
  const tokens = splitMultiFilterValues(value);
  if (!tokens.length) return formatFilterTokenLabel(value);
  return tokens.map((token) => formatFilterTokenLabel(token)).filter(Boolean).join("+");
}

function withNullChoiceOption(options) {
  const list = Array.isArray(options) ? options.filter(Boolean) : [];
  if (list.some((option) => option?.value === NULL_FILTER_VALUE)) return list;
  return [{ value: NULL_FILTER_VALUE, label: NULL_FILTER_LABEL }, ...list];
}

function foldTr(str = "") {
  return String(str)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[\u00e7\u00c7]/g, "c")
    .replace(/[\u011f\u011e]/g, "g")
    .replace(/[\u0131\u0130]/g, "i")
    .replace(/[\u00f6\u00d6]/g, "o")
    .replace(/[\u015f\u015e]/g, "s")
    .replace(/[\u00fc\u00dc]/g, "u")
    .toLowerCase()
    .trim();
}

function splitSearchTerms(value) {
  return foldTr(value)
    .split(/\s+/)
    .filter(Boolean);
}

function createChartId() {
  return `chart-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

const countFormatter = new Intl.NumberFormat("en-US");

function getColumnValue(row, column) {
  if (!row || !column) return "";
  for (const key of column.accessors) {
    const value = row?.[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return "";
}

function sanitizeFileName(value) {
  return String(value || "chart")
    .trim()
    .replace(/[^a-z0-9_-]+/gi, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}

function getColumnLabel(columns, key) {
  const column = columns.find((item) => item.key === key);
  return column?.label ?? key;
}

function getMetricLabel(metric) {
  const match = METRIC_OPTIONS.find((option) => option.value === metric);
  return match?.label ?? METRIC_OPTIONS[0]?.label ?? "Count items";
}

function normalizeFilterValue(value, columnKey) {
  if (isNullFilterToken(value)) return NULL_FILTER_VALUE;
  const normalized = foldTr(value);
  if (columnKey === "Country") {
    return COUNTRY_ALIASES[normalized] ?? normalized;
  }
  return normalized;
}

function hasDiscreteChartOptions(choiceFieldMap, columnKey) {
  if (!columnKey || columnKey === "none") return false;
  if (columnKey === "Country") return true;
  const rawOptions = choiceFieldMap?.[columnKey];
  return Array.isArray(rawOptions) && rawOptions.length > 0;
}

function matchesChartTokens(value, tokens, columnKey, exactMatch) {
  if (!tokens.length) return true;
  const normalizedTokens = tokens.map((token) => normalizeFilterValue(token, columnKey)).filter(Boolean);
  if (!normalizedTokens.length) return true;
  const wantsNull = normalizedTokens.includes(NULL_FILTER_VALUE);
  if (isBlankFilterValue(value)) return wantsNull;
  const normalizedValue = normalizeFilterValue(value, columnKey);
  if (!normalizedValue) return false;
  const searchableTokens = normalizedTokens.filter((token) => token !== NULL_FILTER_VALUE);
  if (!searchableTokens.length) return false;

  if (exactMatch) {
    return searchableTokens.some((token) => token === normalizedValue);
  }

  const tokenGroups = searchableTokens
    .map((token) => splitSearchTerms(token))
    .filter((group) => group.length);
  if (!tokenGroups.length) return false;
  return tokenGroups.some((group) => group.every((term) => normalizedValue.includes(term)));
}

function buildDefaultChart(columns) {
  const defaultGroup =
    columns.find((column) => column.key === "Country")?.key ??
    columns[0]?.key ??
    "none";
  return {
    id: createChartId(),
    title: "",
    groupBy: defaultGroup,
    groupFilterValue: "",
    metric: "count",
    filterBy: "none",
    filterValue: "",
  };
}

function sanitizeChart(raw, columns) {
  if (!raw || typeof raw !== "object") return null;
  const validKeys = new Set(columns.map((column) => column.key));
  const groupBy = validKeys.has(raw.groupBy) ? raw.groupBy : "none";
  const filterBy = validKeys.has(raw.filterBy) ? raw.filterBy : "none";
  const metric = raw.metric === "ratio" ? "ratio" : "count";
  const title = typeof raw.title === "string" ? raw.title : "";
  const filterValue = typeof raw.filterValue === "string" ? raw.filterValue : "";
  const groupFilterValue =
    groupBy !== "none" && typeof raw.groupFilterValue === "string"
      ? raw.groupFilterValue
      : "";
  const id = typeof raw.id === "string" && raw.id ? raw.id : createChartId();
  return { id, title, groupBy, groupFilterValue, metric, filterBy, filterValue };
}

function normalizeChartsPayload(payload, columns) {
  if (!payload) return [];
  const items = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.items)
    ? payload.items
    : Array.isArray(payload?.results)
    ? payload.results
    : [];
  return items.map((item) => sanitizeChart(item, columns)).filter(Boolean);
}

function buildChartPayload(chart) {
  return {
    id: chart.id,
    title: chart.title,
    groupBy: chart.groupBy,
    groupFilterValue: chart.groupFilterValue ?? "",
    metric: chart.metric,
    filterBy: chart.filterBy,
    filterValue: chart.filterValue,
  };
}

function loadChartsFromStorage(columns) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map((item) => sanitizeChart(item, columns)).filter(Boolean);
  } catch (err) {
    console.warn("Failed to read chart storage", err);
    return [];
  }
}

function buildChartTitle(chart, columns) {
  if (chart.title?.trim()) return chart.title.trim();
  const metricPrefix = chart.metric === "ratio" ? "Ratio" : "Count";
  const groupLabel =
    chart.groupBy === "none" ? "Total" : getColumnLabel(columns, chart.groupBy);
  const groupFilterLabel =
    chart.groupBy !== "none" && chart.groupFilterValue?.trim()
      ? ` (${formatFilterTokenSummary(chart.groupFilterValue)})`
      : "";
  const filterLabel =
    chart.filterBy !== "none" && chart.filterValue?.trim()
      ? ` - ${getColumnLabel(columns, chart.filterBy)} = ${formatFilterTokenSummary(chart.filterValue)}`
      : "";
  return `${metricPrefix} by ${groupLabel}${groupFilterLabel}${filterLabel}`;
}

function filterRowsForChart(rows, chart, columns, choiceFieldMap) {
  if (!chart.filterBy || chart.filterBy === "none") return rows;
  const filterColumn = columns.find((column) => column.key === chart.filterBy);
  if (!filterColumn) return rows;
  const tokens = splitMultiFilterValues(chart.filterValue)
    .filter(Boolean);
  if (!tokens.length) return rows;
  const exactMatch = hasDiscreteChartOptions(choiceFieldMap, chart.filterBy);
  return rows.filter((row) => {
    const rawValue = getColumnValue(row, filterColumn);
    const values = Array.isArray(rawValue) ? rawValue : [rawValue];
    return values.some((value) => matchesChartTokens(value, tokens, chart.filterBy, exactMatch));
  });
}

function buildChartBars(rows, chart, columns, choiceFieldMap) {
  const filtered = filterRowsForChart(rows, chart, columns, choiceFieldMap);
  if (chart.groupBy === "none") {
    const totalCount = filtered.length;
    if (!totalCount) return [];
    const value = chart.metric === "ratio" ? 100 : totalCount;
    return [{ label: "Total", value }];
  }
  const groupColumn = columns.find((column) => column.key === chart.groupBy);
  if (!groupColumn) return [];
  const groupTokens = splitMultiFilterValues(chart.groupFilterValue)
    .filter(Boolean);
  const exactGroupMatch = hasDiscreteChartOptions(choiceFieldMap, chart.groupBy);
  const counts = new Map();
  filtered.forEach((row) => {
    const rawValue = getColumnValue(row, groupColumn);
    const values = Array.isArray(rawValue) ? rawValue : [rawValue];
    values.forEach((value) => {
      const isBlankValue = isBlankFilterValue(value);
      const label = isBlankValue ? NULL_FILTER_LABEL : String(value ?? "").trim() || "Unknown";
      const normalizedKey = isBlankValue
        ? NULL_FILTER_VALUE
        : normalizeFilterValue(label, chart.groupBy) || "unknown";
      if (groupTokens.length && !matchesChartTokens(value, groupTokens, chart.groupBy, exactGroupMatch)) {
        return;
      }
      const existing = counts.get(normalizedKey);
      if (existing) {
        existing.value += 1;
      } else {
        counts.set(normalizedKey, { label, value: 1 });
      }
    });
  });
  let bars = Array.from(counts.values()).sort((a, b) => b.value - a.value);
  if (chart.metric === "ratio") {
    const total = bars.reduce((sum, bar) => sum + bar.value, 0);
    bars = bars.map((bar) => ({
      ...bar,
      value: total ? (bar.value / total) * 100 : 0,
    }));
  }
  return bars.filter((bar) => {
    if (bar.value <= 0) return false;
    if (chart.metric === "ratio" && Number(formatPercent(bar.value)) === 0) return false;
    return true;
  });
}

function formatPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "0";
  const fixed = numeric.toFixed(1);
  return fixed.endsWith(".0") ? fixed.slice(0, -2) : fixed;
}

function truncateLabel(label, maxChars) {
  const str = String(label ?? "").trim();
  if (!str) return "";
  if (str.length <= maxChars) return str;
  return `${str.slice(0, Math.max(0, maxChars - 3))}...`;
}

function ChartCard({
  chart,
  title,
  bars,
  meta,
  onEdit,
  onDelete,
  onExportExcel,
  onExportPng,
  isSingle,
  isDeleting = false,
  canEdit = true,
}) {
  const svgRef = useRef(null);
  const isEditable = canEdit && typeof onEdit === "function";
  const isRatioMetric = chart.metric === "ratio";
  const maxValue = isRatioMetric ? 100 : Math.max(...bars.map((bar) => bar.value), 1);
  const chartHeight = 240;
  const padding = { top: 24, right: 16, bottom: 64, left: 46 };
  const gap = 14;
  const baseBarWidth = 34;
  const chartWidth =
    padding.left +
    padding.right +
    bars.length * baseBarWidth +
    Math.max(0, bars.length - 1) * gap;
  const innerHeight = chartHeight - padding.top - padding.bottom;
  const labelMaxChars = bars.length > 10 ? 8 : 12;

  return (
    <article
      className={`chart-card${isSingle ? " is-full" : ""}`}
      onClick={isEditable ? () => onEdit(chart) : undefined}
      role={isEditable ? "button" : undefined}
      tabIndex={isEditable ? 0 : undefined}
      onKeyDown={isEditable ? (event) => {
        if (event.key === "Enter") onEdit(chart);
      } : undefined}
    >
      <div className="chart-card-header">
        <div>
          <h3 className="chart-card-title">{title}</h3>
          <p className="chart-card-meta">{meta}</p>
        </div>
        <div className="chart-card-actions">
          <button
            type="button"
            className="chart-button"
            onClick={(event) => {
              event.stopPropagation();
              onExportExcel(chart, bars, title);
            }}
          >
            Export Excel
          </button>
          <button
            type="button"
            className="chart-button"
            onClick={async (event) => {
              event.stopPropagation();
              await onExportPng(chart, svgRef.current, title);
            }}
          >
            Export PNG
          </button>
          {canEdit ? (
            <button
              type="button"
              className="chart-button chart-button--danger"
              onClick={(event) => {
                event.stopPropagation();
                onDelete?.(chart);
              }}
              disabled={isDeleting}
            >
              {isDeleting ? "Deleting..." : "Delete"}
            </button>
          ) : null}
        </div>
      </div>

      {bars.length ? (
        <div className="chart-canvas">
          <svg
            ref={svgRef}
            className="chart-svg"
            width="100%"
            height={chartHeight}
            viewBox={`0 0 ${chartWidth} ${chartHeight}`}
            role="img"
            aria-label={title}
          >
            {[0, 0.25, 0.5, 0.75, 1].map((t) => {
              const y = padding.top + innerHeight * (1 - t);
              const tickValue = isRatioMetric ? Math.round(t * 100) : Math.round(maxValue * t);
              return (
                <g key={t}>
                  <line
                    x1={padding.left}
                    x2={chartWidth - padding.right}
                    y1={y}
                    y2={y}
                    stroke="rgba(31,35,40,0.08)"
                    strokeWidth="1"
                  />
                  <text
                    x={padding.left - 8}
                    y={y + 4}
                    textAnchor="end"
                    fontSize="10"
                    fill="rgba(31,35,40,0.6)"
                  >
                    {isRatioMetric ? `${tickValue}%` : countFormatter.format(tickValue)}
                  </text>
                </g>
              );
            })}
            {bars.map((bar, index) => {
              const height = maxValue ? (bar.value / maxValue) * innerHeight : 0;
              const x = padding.left + index * (baseBarWidth + gap);
              const y = padding.top + innerHeight - height;
              const labelText = truncateLabel(bar.label, labelMaxChars);
              const labelY = height + 18;
              const valueLabel = isRatioMetric
                ? `${formatPercent(bar.value)}%`
                : countFormatter.format(bar.value);
              return (
                <g key={`${bar.label}-${index}`} transform={`translate(${x}, ${y})`}>
                  <rect width={baseBarWidth} height={height} rx="6" fill="var(--accent)" />
                  <text
                    x={baseBarWidth / 2}
                    y={labelY}
                    textAnchor="end"
                    fontSize="9"
                    fill="rgba(74, 83, 98, 0.82)"
                    transform={`rotate(-35 ${baseBarWidth / 2} ${labelY})`}
                  >
                    {labelText}
                  </text>
                  <text
                    x={baseBarWidth / 2}
                    y={-6}
                    textAnchor="middle"
                    fontSize="10"
                    fill="var(--accent)"
                    fontWeight="600"
                  >
                    {valueLabel}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      ) : (
        <div className="chart-placeholder">No data for this chart.</div>
      )}
    </article>
  );
}

export default function ChartsDashboard({ columns = [], canEdit = true }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [charts, setCharts] = useState([]);
  const [chartsLoading, setChartsLoading] = useState(true);
  const [chartsError, setChartsError] = useState("");
  const [actionError, setActionError] = useState("");
  const [savingChart, setSavingChart] = useState(false);
  const [deletingChartIds, setDeletingChartIds] = useState({});
  const [editorOpen, setEditorOpen] = useState(false);
  const [chartDraft, setChartDraft] = useState(null);
  const [choiceFieldMap, setChoiceFieldMap] = useState({});
  const [loadingChoices, setLoadingChoices] = useState(false);
  const canEditCharts = Boolean(canEdit);

  const columnOptions = useMemo(
    () => columns.map((column) => ({ value: column.key, label: column.label })),
    [columns],
  );
  const groupOptions = useMemo(
    () => [{ value: "none", label: "Total (single bar)" }, ...columnOptions],
    [columnOptions],
  );
  const filterOptions = useMemo(
    () => [{ value: "none", label: "No filter" }, ...columnOptions],
    [columnOptions],
  );

  const choiceOptions = useMemo(() => {
    if (!chartDraft || chartDraft.filterBy === "none") return [];
    const rawOptions = choiceFieldMap[chartDraft.filterBy];
    if (!Array.isArray(rawOptions)) return [];
    return withNullChoiceOption(rawOptions
      .map((item) => {
        if (typeof item === "string") return { value: item, label: item };
        const value = item?.value ?? item?.label ?? "";
        const label = item?.label ?? item?.value ?? value;
        if (!value) return null;
        return { value, label };
      })
      .filter(Boolean));
  }, [chartDraft, choiceFieldMap]);

  const groupValueOptions = useMemo(() => {
    if (!chartDraft || chartDraft.groupBy === "none") return [];

    const fromChoiceFields = choiceFieldMap?.[chartDraft.groupBy];
    if (Array.isArray(fromChoiceFields) && fromChoiceFields.length) {
      const optionsMap = new Map();
      fromChoiceFields.forEach((item) => {
        const value = typeof item === "string" ? item : item?.value ?? item?.label ?? "";
        const label = typeof item === "string" ? item : item?.label ?? item?.value ?? value;
        if (!value) return;
        const normalizedKey = normalizeFilterValue(value, chartDraft.groupBy);
        if (!normalizedKey || optionsMap.has(normalizedKey)) return;
        optionsMap.set(normalizedKey, { value, label });
      });
      return withNullChoiceOption(Array.from(optionsMap.values()).sort((a, b) =>
        String(a.label).localeCompare(String(b.label), undefined, { numeric: true, sensitivity: "base" }),
      ));
    }

    const groupColumn = columns.find((column) => column.key === chartDraft.groupBy);
    if (!groupColumn) return [];

    const optionsMap = new Map();
    for (const row of rows) {
      const rawValue = getColumnValue(row, groupColumn);
      const values = Array.isArray(rawValue) ? rawValue : [rawValue];
      for (const value of values) {
        const isBlankValue = isBlankFilterValue(value);
        const label = isBlankValue ? NULL_FILTER_LABEL : String(value ?? "").trim() || "Unknown";
        const normalizedKey = isBlankValue
          ? NULL_FILTER_VALUE
          : normalizeFilterValue(label, chartDraft.groupBy) || "unknown";
        if (optionsMap.has(normalizedKey)) continue;
        optionsMap.set(normalizedKey, { value: label, label });
        if (optionsMap.size >= GROUP_VALUE_OPTION_LIMIT) break;
      }
      if (optionsMap.size >= GROUP_VALUE_OPTION_LIMIT) break;
    }
    return withNullChoiceOption(Array.from(optionsMap.values()).sort((a, b) =>
      String(a.label).localeCompare(String(b.label), undefined, { numeric: true, sensitivity: "base" }),
    ));
  }, [chartDraft, choiceFieldMap, columns, rows]);

  const fetchRows = useCallback(() => {
    let ignore = false;
    setLoading(true);
    setLoadError("");
    api.get("/rows", { params: { limit: FETCH_LIMIT, offset: 0, if_deleted: 0 } })
      .then(({ data }) => {
        if (ignore) return;
        const items = Array.isArray(data?.items) ? data.items : [];
        setRows(items);
      })
      .catch((err) => {
        if (ignore) return;
        console.error("charts rows error", err);
        setLoadError("Failed to load chart data.");
        setRows([]);
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    const cleanup = fetchRows();
    return cleanup;
  }, [fetchRows]);

  const fetchCharts = useCallback(() => {
    let ignore = false;
    setChartsLoading(true);
    setChartsError("");
    api.get("/charts")
      .then(({ data }) => {
        if (ignore) return;
        const normalized = normalizeChartsPayload(data, columns);
        setCharts(normalized);
      })
      .catch((err) => {
        if (ignore) return;
        console.error("charts load error", err);
        setChartsError("Failed to load saved charts.");
        const fallback = loadChartsFromStorage(columns);
        if (fallback.length) setCharts(fallback);
      })
      .finally(() => {
        if (!ignore) setChartsLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [columns]);

  useEffect(() => {
    const cleanup = fetchCharts();
    return cleanup;
  }, [fetchCharts]);

  useEffect(() => {
    let ignore = false;
    setLoadingChoices(true);
    api.get("/field-parameters")
      .then(({ data }) => {
        if (!ignore) setChoiceFieldMap(data?.fields ?? {});
      })
      .catch((err) => {
        if (!ignore) console.error("charts field-parameters error", err);
      })
      .finally(() => {
        if (!ignore) setLoadingChoices(false);
      });
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (chartsLoading) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(charts));
    } catch (err) {
      console.warn("Failed to cache charts", err);
    }
  }, [charts, chartsLoading]);

  const selectedFilterTokens = useMemo(() => {
    if (!chartDraft?.filterValue) return [];
    return splitMultiFilterValues(chartDraft.filterValue);
  }, [chartDraft]);

  const selectedFilterDisplay = selectedFilterTokens.length
    ? selectedFilterTokens.map((token) => formatFilterTokenLabel(token)).join("+")
    : "";

  const selectedGroupTokens = useMemo(() => {
    if (!chartDraft?.groupFilterValue || chartDraft.groupBy === "none") return [];
    return splitMultiFilterValues(chartDraft.groupFilterValue);
  }, [chartDraft]);

  const selectedGroupDisplay = selectedGroupTokens.length
    ? selectedGroupTokens.map((token) => formatFilterTokenLabel(token)).join("+")
    : "";

  const toggleFilterValue = useCallback((optionValue) => {
    setChartDraft((prev) => {
      if (!prev) return prev;
      const tokens = splitMultiFilterValues(prev.filterValue);
      const normalizedTokens = tokens.map((token) => normalizeFilterValue(token, prev.filterBy));
      const target = normalizeFilterValue(optionValue, prev.filterBy);
      const matchIndex = normalizedTokens.findIndex((token) => token === target);
      let nextTokens = tokens;
      if (matchIndex >= 0) {
        nextTokens = tokens.filter((_, idx) => idx !== matchIndex);
      } else {
        nextTokens = tokens.concat(optionValue);
      }
      return { ...prev, filterValue: nextTokens.join("+") };
    });
  }, []);

  const clearFilterValues = useCallback(() => {
    setChartDraft((prev) => (prev ? { ...prev, filterValue: "" } : prev));
  }, []);

  const toggleGroupValue = useCallback((optionValue) => {
    setChartDraft((prev) => {
      if (!prev || prev.groupBy === "none") return prev;
      const tokens = splitMultiFilterValues(prev.groupFilterValue);
      const normalizedTokens = tokens.map((token) => normalizeFilterValue(token, prev.groupBy));
      const target = normalizeFilterValue(optionValue, prev.groupBy);
      const matchIndex = normalizedTokens.findIndex((token) => token === target);
      let nextTokens = tokens;
      if (matchIndex >= 0) {
        nextTokens = tokens.filter((_, idx) => idx !== matchIndex);
      } else {
        nextTokens = tokens.concat(optionValue);
      }
      return { ...prev, groupFilterValue: nextTokens.join("+") };
    });
  }, []);

  const clearGroupValues = useCallback(() => {
    setChartDraft((prev) => (prev ? { ...prev, groupFilterValue: "" } : prev));
  }, []);

  const openNewChart = () => {
    if (!canEditCharts) return;
    setActionError("");
    setChartDraft(buildDefaultChart(columns));
    setEditorOpen(true);
  };

  const openEditChart = (chart) => {
    if (!canEditCharts) return;
    setActionError("");
    const sanitized = sanitizeChart(chart, columns);
    setChartDraft(sanitized ? { ...sanitized } : null);
    setEditorOpen(true);
  };

  const closeEditor = () => {
    setEditorOpen(false);
    setChartDraft(null);
    setActionError("");
  };

  const saveChart = async () => {
    if (!canEditCharts || !chartDraft || savingChart) return;
    const nextChart = sanitizeChart(chartDraft, columns);
    if (!nextChart) return;
    setSavingChart(true);
    setActionError("");
    try {
      const exists = charts.some((item) => item.id === nextChart.id);
      const payload = buildChartPayload(nextChart);
      const response = exists
        ? await api.put(`/charts/${encodeURIComponent(nextChart.id)}`, payload)
        : await api.post("/charts", payload);
      const resolvedBase = sanitizeChart(response?.data ?? payload, columns) ?? nextChart;
      const resolved = {
        ...resolvedBase,
        groupFilterValue: nextChart.groupFilterValue ?? resolvedBase.groupFilterValue ?? "",
      };
      setCharts((prev) => {
        const existingIndex = prev.findIndex((item) => item.id === nextChart.id);
        if (existingIndex >= 0) {
          const updated = [...prev];
          updated[existingIndex] = resolved;
          return updated;
        }
        return [...prev, resolved];
      });
      closeEditor();
    } catch (err) {
      console.error("save chart error", err);
      setActionError("Chart could not be saved.");
    } finally {
      setSavingChart(false);
    }
  };

  const deleteChart = async (chart) => {
    if (!canEditCharts || !chart?.id || deletingChartIds[chart.id]) return;
    setActionError("");
    setDeletingChartIds((prev) => ({ ...prev, [chart.id]: true }));
    try {
      await api.delete(`/charts/${encodeURIComponent(chart.id)}`);
      setCharts((prev) => prev.filter((item) => item.id !== chart.id));
    } catch (err) {
      console.error("delete chart error", err);
      setActionError("Chart could not be deleted.");
    } finally {
      setDeletingChartIds((prev) => {
        const next = { ...prev };
        delete next[chart.id];
        return next;
      });
    }
  };

  const exportChartExcel = (chart, bars, title) => {
    if (!bars.length) return;
    const valueHeader = chart.metric === "ratio" ? "Ratio (%)" : "Count";
    const rowsData = [
      ["Label", valueHeader],
      ...bars.map((bar) => [
        bar.label,
        chart.metric === "ratio" ? Number(formatPercent(bar.value)) : bar.value,
      ]),
    ];
    const ws = XLSX.utils.aoa_to_sheet(rowsData);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Chart");
    XLSX.writeFile(wb, `${sanitizeFileName(title)}.xlsx`);
  };

  const exportChartPng = async (chart, svgEl, title) => {
    if (!svgEl) return;
    try {
      const canvas = await exportSvgToCanvas(svgEl);
      const link = document.createElement("a");
      link.download = `${sanitizeFileName(title)}.png`;
      link.href = canvas.toDataURL("image/png");
      link.click();
    } catch (err) {
      console.error("export chart png error", err);
    }
  };

  const chartCards = useMemo(() => {
    return charts.map((chart) => {
      const title = buildChartTitle(chart, columns);
      const bars = buildChartBars(rows, chart, columns, choiceFieldMap);
      const groupLabel =
        chart.groupBy === "none" ? "Total" : getColumnLabel(columns, chart.groupBy);
      const groupValueLabel =
        chart.groupBy !== "none" && chart.groupFilterValue
          ? `${getColumnLabel(columns, chart.groupBy)} in ${chart.groupFilterValue}`
          : "All group values";
      const filterLabel =
        chart.filterBy !== "none" && chart.filterValue
          ? `${getColumnLabel(columns, chart.filterBy)} = ${chart.filterValue}`
          : "No filter";
      const metricLabel = getMetricLabel(chart.metric);
      const meta = `${groupLabel} | ${groupValueLabel} | ${filterLabel} | ${metricLabel}`;
      return { chart, title, bars, meta };
    });
  }, [charts, choiceFieldMap, columns, rows]);

  return (
    <section className="charts-section">
      <div className="charts-header">
        <div>
          <h2 className="charts-title">Charts</h2>
          <p className="charts-subtitle">
            Build and save bar charts from inventory data.
          </p>
        </div>
        {canEditCharts ? (
          <div className="charts-actions">
            <button type="button" className="chart-button chart-button--primary" onClick={openNewChart}>
              Add chart
            </button>
          </div>
        ) : null}
      </div>

      {loading || chartsLoading ? (
        <div className="charts-loading">
          <LoadingLogo label="Loading chart data" size={112} />
        </div>
      ) : loadError ? (
        <div className="charts-error">{loadError}</div>
      ) : (
        <>
          {chartsError ? <div className="charts-error">{chartsError}</div> : null}
          {actionError ? <div className="charts-error">{actionError}</div> : null}
          <div className={`charts-grid${chartCards.length === 1 ? " charts-grid--single" : ""}`}>
            {chartCards.length ? (
              chartCards.map(({ chart, title, bars, meta }) => {
                const isDeleting = Boolean(deletingChartIds[chart.id]);
                return (
                  <ChartCard
                    key={chart.id}
                    chart={chart}
                    title={title}
                    bars={bars}
                    meta={meta}
                    onEdit={openEditChart}
                    onDelete={deleteChart}
                    onExportExcel={exportChartExcel}
                    onExportPng={exportChartPng}
                    isSingle={chartCards.length === 1}
                    isDeleting={isDeleting}
                    canEdit={canEditCharts}
                  />
                );
              })
            ) : (
              <div className="charts-empty">
                <p>{canEditCharts ? "No charts yet. Add your first chart to get started." : "No charts available."}</p>
                {canEditCharts ? (
                  <button type="button" className="chart-button chart-button--primary" onClick={openNewChart}>
                    Add chart
                  </button>
                ) : null}
              </div>
            )}
          </div>
        </>
      )}

      {editorOpen && chartDraft && canEditCharts ? (
        <div className="chart-modal-backdrop" role="dialog" aria-modal="true">
          <div className="chart-modal">
            <div className="chart-modal-header">
              <h3>{charts.some((item) => item.id === chartDraft.id) ? "Edit chart" : "New chart"}</h3>
              <p>Configure how the bar chart should be built.</p>
            </div>

            <div className="chart-modal-content custom-scrollbar">
              {actionError ? <div className="charts-error">{actionError}</div> : null}

              <div className="chart-form-grid">
              <div className="chart-form-field chart-form-field--full">
                <label htmlFor="chart-title">Title</label>
                <input
                  id="chart-title"
                  type="text"
                  value={chartDraft.title}
                  onChange={(event) =>
                    setChartDraft((prev) => ({ ...prev, title: event.target.value }))
                  }
                  placeholder="Optional custom title"
                />
              </div>

              <div className="chart-form-field">
                <label>Group by</label>
                <CustomSelect
                  options={groupOptions}
                  value={chartDraft.groupBy}
                  menuDirection="auto"
                  onChange={(value) =>
                    setChartDraft((prev) => ({
                      ...prev,
                      groupBy: value,
                      groupFilterValue: prev?.groupBy === value ? prev.groupFilterValue : "",
                    }))
                  }
                />
              </div>

              {chartDraft.groupBy !== "none" ? (
                groupValueOptions.length ? (
                  <div className="chart-form-field chart-form-field--full">
                    <label>Group values</label>
                    <input
                      type="text"
                      className="chart-choice-display"
                      value={selectedGroupDisplay}
                      placeholder="Select one or more group values"
                      readOnly
                    />
                    <div className="chart-choice-actions">
                      <span>
                        {selectedGroupTokens.length
                          ? `${selectedGroupTokens.length} selected`
                          : "No group values selected"}
                      </span>
                      <button type="button" className="chart-choice-clear" onClick={clearGroupValues}>
                        Clear
                      </button>
                    </div>
                    <div className="chart-choice-list custom-scrollbar">
                      {groupValueOptions.map((option) => {
                        const normalizedOption = normalizeFilterValue(option.value, chartDraft.groupBy);
                        const normalizedTokens = selectedGroupTokens.map((token) =>
                          normalizeFilterValue(token, chartDraft.groupBy),
                        );
                        const isActive = normalizedTokens.includes(normalizedOption);
                        return (
                          <button
                            key={option.value}
                            type="button"
                            className={`chart-choice-option${isActive ? " is-active" : ""}`}
                            onClick={() => toggleGroupValue(option.value)}
                          >
                            {option.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="chart-form-field chart-form-field--full">
                    <label>Group values</label>
                    <input
                      type="text"
                      value={chartDraft.groupFilterValue}
                      onChange={(event) =>
                        setChartDraft((prev) => ({ ...prev, groupFilterValue: event.target.value }))
                      }
                      placeholder="TR+JO or Laptop+Desktop"
                    />
                  </div>
                )
              ) : null}

              <div className="chart-form-field">
                <label>Metric</label>
                <CustomSelect
                  options={METRIC_OPTIONS}
                  value={chartDraft.metric}
                  menuDirection="auto"
                  onChange={(value) =>
                    setChartDraft((prev) => ({ ...prev, metric: value }))
                  }
                />
              </div>

              <div className="chart-form-field">
                <label>Filter by</label>
                <CustomSelect
                  options={filterOptions}
                  value={chartDraft.filterBy}
                  menuDirection="auto"
                  onChange={(value) =>
                    setChartDraft((prev) => ({
                      ...prev,
                      filterBy: value,
                      filterValue: prev?.filterBy === value ? prev.filterValue : "",
                    }))
                  }
                />
              </div>

              {chartDraft.filterBy !== "none" && (loadingChoices || choiceOptions.length) ? (
                <div className="chart-form-field chart-form-field--full">
                  <label>Filter values</label>
                  <input
                    type="text"
                    className="chart-choice-display"
                    value={selectedFilterDisplay}
                    placeholder={loadingChoices ? "Loading choices..." : "Select one or more values"}
                    readOnly
                  />
                  {!loadingChoices ? (
                    <>
                      <div className="chart-choice-actions">
                        <span>{selectedFilterTokens.length ? `${selectedFilterTokens.length} selected` : "No values selected"}</span>
                        <button type="button" className="chart-choice-clear" onClick={clearFilterValues}>
                          Clear
                        </button>
                      </div>
                      <div className="chart-choice-list custom-scrollbar">
                        {choiceOptions.map((option) => {
                          const normalizedOption = normalizeFilterValue(option.value, chartDraft.filterBy);
                          const normalizedTokens = selectedFilterTokens.map((token) =>
                            normalizeFilterValue(token, chartDraft.filterBy),
                          );
                          const isActive = normalizedTokens.includes(normalizedOption);
                          return (
                            <button
                              key={option.value}
                              type="button"
                              className={`chart-choice-option${isActive ? " is-active" : ""}`}
                              onClick={() => toggleFilterValue(option.value)}
                            >
                              {option.label}
                            </button>
                          );
                        })}
                      </div>
                    </>
                  ) : null}
                </div>
              ) : (
                <div className="chart-form-field">
                  <label>Filter value</label>
                  <input
                    type="text"
                    value={chartDraft.filterValue}
                    onChange={(event) =>
                      setChartDraft((prev) => ({ ...prev, filterValue: event.target.value }))
                    }
                    placeholder="Laptop+Desktop or User name"
                    disabled={chartDraft.filterBy === "none"}
                  />
                </div>
              )}

              </div>
            </div>

            <div className="chart-form-actions">
              <button type="button" className="chart-button" onClick={closeEditor}>
                Cancel
              </button>
              <button
                type="button"
                className="chart-button chart-button--primary"
                onClick={saveChart}
                disabled={savingChart}
              >
                {savingChart ? "Saving..." : "Save chart"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}


