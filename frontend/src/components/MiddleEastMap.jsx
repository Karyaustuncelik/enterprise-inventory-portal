import { useMemo, useRef, useState } from "react";
import rawGeoData from "../assets/middle-east.geo.json";
import { topologyToFeatureCollection } from "../utils/topology";

const WIDTH = 620;
const HEIGHT = 520;
const FALLBACK_COLOR = "#d6d8dc";
const SUPPORTED_CODES = new Set(["TR", "SA", "JO", "IL", "AE"]);
const MAP_GEOMETRY_CODES = new Set(["TR", "SA", "JO", "IL", "AE", "PS"]);
const SHAPE_ID_ALIASES = {
  PS: "IL",
};

// Oran paleti (secim YOKKEN kullanilacak)
const HIGH_THRESHOLD = 0.05;
const COLOR_STOPS = [
  { id: "optimum", color: "#7ed957", label: "Optimum Spare" },
  { id: "high", color: "var(--accent)", label: "High Spare" },
];

const LEGEND_DIM_SWATCH = "#cbcfd9";
const TOOLTIP_WIDTH = 176;
const TOOLTIP_HEIGHT = 152;
const TOOLTIP_OFFSET_X = 16;
const TOOLTIP_OFFSET_Y = 16;
const TOOLTIP_MARGIN = 10;

// Secim VAR iken renkler
const SELECTED_COLOR = "var(--accent)";
const DIM_COLOR = "rgba(31, 35, 40, 0.64)";

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
  let minLon = Infinity;
  let maxLon = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;

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
  MAP_GEOMETRY_CODES.has(resolveId(feature)),
);

const { project } = computeProjection(filteredFeatures);

const COUNTRY_GROUPS = Array.from(
  filteredFeatures.reduce((map, feature) => {
    const rawId = resolveId(feature);
    const interactiveId = SHAPE_ID_ALIASES[rawId] ?? rawId;
    if (!SUPPORTED_CODES.has(interactiveId)) return map;
    const current = map.get(interactiveId) ?? {
      id: interactiveId,
      name: resolveName(feature),
      parts: [],
    };
    current.parts.push({
      id: rawId,
      path: geometryToPath(feature.geometry, project),
      overlay: interactiveId !== rawId,
    });
    if (interactiveId === rawId) {
      current.name = resolveName(feature);
    }
    map.set(interactiveId, current);
    return map;
  }, new Map()),
).map(([, group]) => ({
  ...group,
  combinedPath: group.parts.map((part) => part.path).join(" "),
  parts: group.parts.sort((a, b) => Number(a.overlay) - Number(b.overlay)),
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

function getFillForCountry(item, selectedId) {
  if (selectedId) {
    if (item?.id !== selectedId) return DIM_COLOR;
    const computed = computeColorByRatio(item?.ratio ?? item?.value ?? null);
    return computed === FALLBACK_COLOR ? SELECTED_COLOR : computed;
  }
  return computeColorByRatio(item?.ratio ?? item?.value ?? 0);
}

function getTooltipPosition(rect, clientX, clientY) {
  if (!rect) {
    return {
      x: clientX + TOOLTIP_OFFSET_X,
      y: clientY + TOOLTIP_OFFSET_Y,
    };
  }

  const relativeX = clientX - rect.left;
  const relativeY = clientY - rect.top;
  const maxX = Math.max(TOOLTIP_MARGIN, rect.width - TOOLTIP_WIDTH - TOOLTIP_MARGIN);
  const maxY = Math.max(TOOLTIP_MARGIN, rect.height - TOOLTIP_HEIGHT - TOOLTIP_MARGIN);

  let x = relativeX + TOOLTIP_OFFSET_X;
  let y = relativeY + TOOLTIP_OFFSET_Y;

  if (x + TOOLTIP_WIDTH + TOOLTIP_MARGIN > rect.width) {
    x = relativeX - TOOLTIP_WIDTH - TOOLTIP_OFFSET_X;
  }

  if (y + TOOLTIP_HEIGHT + TOOLTIP_MARGIN > rect.height) {
    y = relativeY - TOOLTIP_HEIGHT - TOOLTIP_OFFSET_Y;
  }

  return {
    x: Math.min(Math.max(TOOLTIP_MARGIN, x), maxX),
    y: Math.min(Math.max(TOOLTIP_MARGIN, y), maxY),
  };
}

const percentFormatter = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 1,
  minimumFractionDigits: 0,
});

export default function MiddleEastMap({ data = [], selectedCountry }) {
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
  const selectedLegendKey = selectedDataPoint
    ? classifyRatio(selectedDataPoint.value ?? selectedDataPoint.ratio ?? 0)
    : null;
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
        <defs>
          <filter
            id="map-country-outline"
            x="-8%"
            y="-8%"
            width="116%"
            height="116%"
          >
            <feMorphology
              in="SourceAlpha"
              operator="dilate"
              radius="1.2"
              result="expanded"
            />
            <feFlood floodColor="#ffffff" result="outlineColor" />
            <feComposite
              in="outlineColor"
              in2="expanded"
              operator="in"
              result="outline"
            />
            <feMerge>
              <feMergeNode in="outline" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter
            id="map-country-outline-selected"
            x="-10%"
            y="-10%"
            width="120%"
            height="120%"
          >
            <feMorphology
              in="SourceAlpha"
              operator="dilate"
              radius="2.2"
              result="expanded"
            />
            <feFlood floodColor="#ffffff" result="outlineColor" />
            <feComposite
              in="outlineColor"
              in2="expanded"
              operator="in"
              result="outline"
            />
            <feMerge>
              <feMergeNode in="outline" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {COUNTRY_GROUPS.map((shape) => {
          const dataPoint = dataById.get(shape.id);
          const ratio = dataPoint?.value ?? dataPoint?.ratio ?? 0;
          const isSelected = selectedId === shape.id;
          const useMergedFill = shape.id === "IL";
          const maskId = `map-country-mask-${shape.id}`;
          const fill = getFillForCountry(
            { id: shape.id, ratio, value: ratio },
            selectedId,
          );

          return (
            <g
              key={shape.id}
              className={`map-country${isSelected ? " selected" : ""}`}
              filter={`url(#${isSelected ? "map-country-outline-selected" : "map-country-outline"})`}
              onMouseMove={(event) => {
                const rect = containerRef.current?.getBoundingClientRect();
                const { x, y } = getTooltipPosition(rect, event.clientX, event.clientY);
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
              {useMergedFill ? (
                <>
                  <defs>
                    <clipPath id={maskId} clipPathUnits="userSpaceOnUse">
                      <path d={shape.combinedPath} />
                    </clipPath>
                  </defs>
                  <path
                    d={shape.combinedPath}
                    fill="transparent"
                    stroke="none"
                    pointerEvents="all"
                  />
                  <rect
                    x="0"
                    y="0"
                    width={WIDTH}
                    height={HEIGHT}
                    fill={fill}
                    clipPath={`url(#${maskId})`}
                    pointerEvents="none"
                  />
                </>
              ) : (
                <path
                  d={shape.combinedPath}
                  className="map-country-shape"
                  fill={fill}
                />
              )}
            </g>
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
