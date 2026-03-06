import { useMemo, useRef, useState } from "react";
import rawGeoData from "../assets/middle-east.geo.json";
import { topologyToFeatureCollection } from "../utils/topology";

const WIDTH = 620;
const HEIGHT = 520;
const FALLBACK_COLOR = "#d6d8dc";
const SUPPORTED_CODES = new Set(["TR", "SA", "JO", "IL", "AE"]);

// Oran paleti (seçim YOKKEN kullanılacak)
const HIGH_THRESHOLD = 0.05;
const COLOR_STOPS = [
  { id: "optimum", color: "#7ed957", label: "Optimum Spare" },
  { id: "high", color: "#e1000e", label: "High Spare" },
];


const LEGEND_DIM_SWATCH = "#cbcfd9";


// Seçim VAR iken renkler
const SELECTED_COLOR = "#e1000e";                // seçilen ülke
const DIM_COLOR = "rgba(31, 35, 40, 0.64)";      // diğer tüm ülkeler

const sourceFeatureCollection =
  rawGeoData?.type === "Topology"
    ? topologyToFeatureCollection(rawGeoData)
    : rawGeoData;

function extractRings(geometry) {
  if (!geometry) return [];
  if (geometry.type === "Polygon") return geometry.coordinates;
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flat();
  return [];
}

function computeProjection(features) {
  let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;

  features.forEach((feature) => {
    extractRings(feature.geometry).forEach((ring) => {
      ring.forEach(([lon, lat]) => {
        if (lon < minLon) minLon = lon;
        if (lon > maxLon) maxLon = lon;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
      });
    });
  });

  const lonSpan = maxLon - minLon || 1;
  const latSpan = maxLat - minLat || 1;
  const padding = 36;
  const usableWidth = WIDTH - padding * 2;
  const usableHeight = HEIGHT - padding * 2;
  const scale = Math.min(usableWidth / lonSpan, usableHeight / latSpan);

  const xOffset = (WIDTH - lonSpan * scale) / 2 - minLon * scale;
  const yOffset = (HEIGHT + latSpan * scale) / 2 + minLat * scale;

  const project = (lon, lat) => {
    const x = lon * scale + xOffset;
    const y = -lat * scale + yOffset;
    return [Number(x.toFixed(2)), Number(y.toFixed(2))];
  };

  return { project };
}

function geometryToPath(geometry, project) {
  const rings = extractRings(geometry);
  return rings
    .map((ring) =>
      ring
        .map(([lon, lat], index) => {
          const [x, y] = project(lon, lat);
          const command = index === 0 ? "M" : "L";
          return `${command}${x} ${y}`;
        })
        .join(" ")
        .concat(" Z"),
    )
    .join(" ");
}

function resolveId(feature) {
  const props = feature.properties ?? {};
  return (
    feature.id ??
    props.iso_a2 ??
    props.ISO_A2 ??
    props.id ??
    props.ID ??
    props.code ??
    props.CODE ??
    props.adm0_a3 ??
    props.ADM0_A3 ??
    props.name ??
    ""
  )
    .toString()
    .toUpperCase();
}

function resolveName(feature) {
  const props = feature.properties ?? {};
  return (
    props.name ??
    props.NAME ??
    props.name_en ??
    props.NAME_EN ??
    props.name_long ??
    props.NAME_LONG ??
    resolveId(feature)
  );
}

const filteredFeatures = (sourceFeatureCollection?.features ?? []).filter((feature) =>
  SUPPORTED_CODES.has(resolveId(feature)),
);

const { project } = computeProjection(filteredFeatures);

const COUNTRY_SHAPES = filteredFeatures.map((feature) => ({
  id: resolveId(feature),
  name: resolveName(feature),
  path: geometryToPath(feature.geometry, project),
}));

function classifyRatio(value) {
  if (value === null || value === undefined) return null;
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return null;
  const clamped = Math.max(0, Math.min(1, numeric));
  return clamped > HIGH_THRESHOLD ? "high" : "optimum";
}

function computeColorByRatio(value) {
  const key = classifyRatio(value);
  if (!key) return FALLBACK_COLOR;
  const stop = COLOR_STOPS.find((entry) => entry.id === key);
  return stop ? stop.color : FALLBACK_COLOR;
}

// Seçim durumuna göre renk seçici
function getFillForCountry(item, selectedId) {
  if (selectedId) {
    if (item?.id !== selectedId) return DIM_COLOR;
    const computed = computeColorByRatio(item?.ratio ?? item?.value ?? null);
    return computed === FALLBACK_COLOR ? SELECTED_COLOR : computed;
  }
  return computeColorByRatio(item?.ratio ?? item?.value ?? 0);
}

const percentFormatter = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 1,
  minimumFractionDigits: 0,
});

export default function MiddleEastMap({ data = [], onSelect, selectedCountry }) {
  const containerRef = useRef(null);
  const [tooltip, setTooltip] = useState(null);

  const dataById = useMemo(() => {
    const next = new Map();
    data.forEach((item) => {
      next.set(item.id?.toUpperCase(), item);
    });
    return next;
  }, [data]);

  const selectedId = selectedCountry?.id;
  const selectedDataPoint = selectedId ? dataById.get(selectedId) : null;
  const selectedLegendKey = selectedDataPoint ? classifyRatio(selectedDataPoint.value ?? selectedDataPoint.ratio ?? 0) : null;
  const selectedColor = selectedDataPoint
    ? computeColorByRatio(selectedDataPoint.value ?? selectedDataPoint.ratio ?? 0)
    : null;
  const activeSwatchColor =
    selectedColor && selectedColor !== FALLBACK_COLOR ? selectedColor : SELECTED_COLOR;

  return (
    <div className="map-wrapper" ref={containerRef}>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="map-canvas"
        role="img"
        aria-label="Middle East spare assets heatmap"
      >
        <title>Middle East spare assets heatmap</title>
        {COUNTRY_SHAPES.map((shape) => {
          const dataPoint = dataById.get(shape.id);
          const ratio = dataPoint?.value ?? dataPoint?.ratio ?? 0;
          const isSelected = selectedId === shape.id;
          const fill = getFillForCountry(
            { id: shape.id, ratio, value: ratio },
            selectedId
          );

          return (
            <path
              key={shape.id}
              d={shape.path}
              className={`map-country ${isSelected ? "selected" : ""}`}
              fill={fill}
              stroke="#ffffff"
              strokeWidth={isSelected ? 4 : 2}
              vectorEffect="non-scaling-stroke"
              onClick={() =>
                onSelect?.(dataPoint ?? { id: shape.id, name: shape.name, value: ratio })
              }
              onMouseMove={(event) => {
                const rect = containerRef.current?.getBoundingClientRect();
                const x = rect ? event.clientX - rect.left : event.clientX;
                const y = rect ? event.clientY - rect.top : event.clientY;
                setTooltip({
                  name: dataPoint?.name ?? shape.name,
                  value: ratio,
                  spare: dataPoint?.spare ?? 0,
                  total: dataPoint?.total ?? 0,
                  isOptimum: classifyRatio(ratio) === "optimum",
                  x,
                  y,
                });
              }}
              onMouseLeave={() => setTooltip(null)}
            >
              <title>
                {`${dataPoint?.name ?? shape.name}: ${percentFormatter.format(ratio || 0)} coverage`}
              </title>
            </path>
          );
        })}
      </svg>

      <div className={`map-legend${selectedId ? " dimmed" : ""}`} aria-hidden>
        {COLOR_STOPS.map((stop) => {
          const isActive = selectedId && stop.id === selectedLegendKey;
          const swatchColor = selectedId
            ? isActive
              ? activeSwatchColor
              : LEGEND_DIM_SWATCH
            : stop.color;
          const legendItemClass = [
            "map-legend-item",
            selectedId ? (isActive ? "is-active" : "is-muted") : null,
          ]
            .filter(Boolean)
            .join(" ");

          return (
            <div
              key={stop.id}
              className={legendItemClass}
              style={isActive && selectedId ? { color: activeSwatchColor } : undefined}
            >
              <span
                className="map-legend-swatch"
                style={{ backgroundColor: swatchColor }}
              />
              <span>{stop.label}</span>
            </div>
          );
        })}
      </div>

      {tooltip && (
        <div
          className={`map-tooltip${tooltip.isOptimum ? " is-optimum" : ""}`}
          style={{ left: tooltip.x + 12, top: tooltip.y + 12 }}
        >
          <strong>{tooltip.name}</strong>
          <span className="map-tooltip-value">
            {percentFormatter.format(tooltip.value || 0)} spare coverage
          </span>
          <span>
            {tooltip.spare.toLocaleString()} spare / {tooltip.total.toLocaleString()} total
          </span>
        </div>
      )}
    </div>
  );
}

