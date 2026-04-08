const SVG_EXPORT_STYLE_PROPERTIES = [
  "fill",
  "stroke",
  "color",
  "opacity",
  "filter",
  "transform",
  "transform-origin",
  "stroke-width",
  "stroke-linecap",
  "stroke-linejoin",
  "font-size",
  "font-family",
  "font-weight",
  "letter-spacing",
  "text-anchor",
  "dominant-baseline",
  "display",
  "visibility",
];

function getSvgDimensions(svgEl) {
  const viewBox = svgEl.viewBox?.baseVal;
  if (viewBox?.width && viewBox?.height) {
    return { width: viewBox.width, height: viewBox.height };
  }
  const rect = svgEl.getBoundingClientRect();
  return {
    width: Math.max(1, Math.round(rect.width)),
    height: Math.max(1, Math.round(rect.height)),
  };
}

function buildExportableSvg(svgEl) {
  const clone = svgEl.cloneNode(true);
  const sourceNodes = [svgEl, ...svgEl.querySelectorAll("*")];
  const cloneNodes = [clone, ...clone.querySelectorAll("*")];

  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");

  const { width, height } = getSvgDimensions(svgEl);
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));

  sourceNodes.forEach((sourceNode, index) => {
    const cloneNode = cloneNodes[index];
    if (!cloneNode) return;
    const computed = window.getComputedStyle(sourceNode);
    SVG_EXPORT_STYLE_PROPERTIES.forEach((property) => {
      const value = computed.getPropertyValue(property);
      if (!value) return;
      cloneNode.style.setProperty(property, value);
    });
  });

  return { clone, width, height };
}

export function exportSvgToCanvas(svgEl) {
  return new Promise((resolve, reject) => {
    if (!svgEl) {
      reject(new Error("SVG not found"));
      return;
    }

    const serializer = new XMLSerializer();
    const { clone, width, height } = buildExportableSvg(svgEl);
    const svgString = serializer.serializeToString(clone);
    const blob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const img = new Image();

    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(img, 0, 0, width, height);
      URL.revokeObjectURL(url);
      resolve(canvas);
    };

    img.onerror = (error) => {
      URL.revokeObjectURL(url);
      reject(error);
    };

    img.src = url;
  });
}
