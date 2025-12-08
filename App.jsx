// // App.jsx
// import { useEffect, useState } from "react";
// import { MapContainer, TileLayer, ImageOverlay } from "react-leaflet";
// import { NetCDFReader } from "netcdfjs";
// import { YEARS } from "./years";

// // --- Color scale (EDGAR-like palette) ---
// function getColor(value) {
//   if (!value || value <= 0) return "transparent";

//   if (value < 0.0025) return "#1b4f9a";
//   if (value < 0.025)  return "#2166c5";
//   if (value < 0.10)   return "#1ba8c4";
//   if (value < 0.25)   return "#46d46b";
//   if (value < 0.50)   return "#d4e840";
//   if (value < 1.20)   return "#f79433";
//   return "#c63a26";
// }

// // Your NC3 files (lat/lon in degrees)
// function buildFileName(year) {
//   const prefix = "v8.1_FT2022_AP_PM2.5_";
//   const suffix = "_TOTALS_emi_nc3.nc";
//   return `/data/pm25/${prefix}${year}${suffix}`;
// }

// function hexToRgb(hex) {
//   if (!hex || hex === "transparent") return null;
//   let c = hex.replace("#", "");
//   if (c.length === 3) {
//     c = c.split("").map((ch) => ch + ch).join("");
//   }
//   const num = parseInt(c, 16);
//   return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
// }

// export default function App() {
//   const [year, setYear] = useState(1970);
//   const [overlayUrl, setOverlayUrl] = useState(null);
//   const [overlayBounds, setOverlayBounds] = useState(null);
//   const [loading, setLoading] = useState(false);
//   const [meta, setMeta] = useState({ substance: null, fileYear: null });

//   useEffect(() => {
//     async function loadNetCDF() {
//       setLoading(true);
//       setOverlayUrl(null);
//       setOverlayBounds(null);

//       try {
//         const url = buildFileName(year);
//         console.log("Loading:", url);

//         const res = await fetch(url);
//         const buf = await res.arrayBuffer();
//         const reader = new NetCDFReader(buf);
//         console.log(reader);

//         // lat / lon **already in degrees**
//         const lats = reader.getDataVariable("lat");
//         const lons = reader.getDataVariable("lon");
//         const emissions = reader.getDataVariable("emissions");

//         if (!lats || !lons || !emissions) {
//           console.error("Missing lat/lon/emissions variables", {
//             lats,
//             lons,
//             emissions,
//           });
//           return;
//         }

//         const nLat = lats.length; // 1800
//         const nLon = lons.length; // 3600
//         console.log("Grid size y x:", nLat, "x", nLon);

//         // Attributes (substance, year) if present
//         const emissionsVar = reader.variables.find((v) => v.name === "emissions");
//         let substance = null;
//         let fileYear = null;
//         if (emissionsVar?.attributes) {
//           const substanceAttr = emissionsVar.attributes.find(
//             (a) => a.name === "substance"
//           );
//           const yearAttr = emissionsVar.attributes.find((a) => a.name === "year");
//           substance = substanceAttr?.value ?? null;
//           fileYear = yearAttr?.value ?? null;
//         }
//         setMeta({ substance, fileYear });

//         // Ascending / descending
//         const latAscending = lats[0] < lats[nLat - 1];
//         const lonAscending = lons[0] < lons[nLon - 1];

//         // Bounds directly in degrees
//         const latMin = Math.min(lats[0], lats[nLat - 1]);
//         const latMax = Math.max(lats[0], lats[nLat - 1]);
//         const lonMin = Math.min(lons[0], lons[nLon - 1]);
//         const lonMax = Math.max(lons[0], lons[nLon - 1]);

//         const bounds = [
//           [latMin, lonMin], // south-west
//           [latMax, lonMax], // north-east
//         ];
//         console.log("Overlay bounds:", bounds);
//         setOverlayBounds(bounds);

//         // ---- Canvas heatmap with DOWNSAMPLING ----
//         const MAX_WIDTH = 4000;
//         const MAX_HEIGHT = 2000;

//         const scaleX = nLon / MAX_WIDTH;
//         const scaleY = nLat / MAX_HEIGHT;
//         const scale = Math.max(scaleX, scaleY, 1); // overall downsample factor

//         const canvasWidth = Math.floor(nLon / scale);
//         const canvasHeight = Math.floor(nLat / scale);

//         console.log(
//           "Canvas size:",
//           canvasWidth,
//           "x",
//           canvasHeight,
//           "(scale factor:",
//           scale,
//           ")"
//         );

//         const canvas = document.createElement("canvas");
//         canvas.width = canvasWidth;
//         canvas.height = canvasHeight;

//         const ctx = canvas.getContext("2d");
//         const imageData = ctx.createImageData(canvas.width, canvas.height);
//         const dataArr = imageData.data;

//         for (let yImg = 0; yImg < canvasHeight; yImg++) {
//           // Map image row → source row index
//           let srcY = Math.floor(yImg * scale);
//           if (srcY >= nLat) srcY = nLat - 1;
//           if (latAscending) {
//             // flip so north at top if array goes south→north
//             srcY = nLat - 1 - srcY;
//           }

//           for (let xImg = 0; xImg < canvasWidth; xImg++) {
//             let srcX = Math.floor(xImg * scale);
//             if (srcX >= nLon) srcX = nLon - 1;
//             if (!lonAscending) {
//               // if longitudes go east→west, flip to west→east
//               srcX = nLon - 1 - srcX;
//             }

//             const idxGrid = srcY * nLon + srcX;
//             const value = emissions[idxGrid];
//             const idxImg = (yImg * canvasWidth + xImg) * 4;

//             if (!value || value <= 0 || Number.isNaN(value)) {
//               dataArr[idxImg + 0] = 0;
//               dataArr[idxImg + 1] = 0;
//               dataArr[idxImg + 2] = 0;
//               dataArr[idxImg + 3] = 0;
//               continue;
//             }

//             const hex = getColor(value);
//             const rgb = hexToRgb(hex);

//             if (!rgb) {
//               dataArr[idxImg + 0] = 0;
//               dataArr[idxImg + 1] = 0;
//               dataArr[idxImg + 2] = 0;
//               dataArr[idxImg + 3] = 0;
//             } else {
//               const [r, g, b] = rgb;
//               dataArr[idxImg + 0] = r;
//               dataArr[idxImg + 1] = g;
//               dataArr[idxImg + 2] = b;
//               dataArr[idxImg + 3] = 220; // slightly transparent
//             }
//           }
//         }

//         ctx.putImageData(imageData, 0, 0);
//         const dataUrl = canvas.toDataURL("image/png");
//         setOverlayUrl(dataUrl);
//       } catch (err) {
//         console.error("Error loading NetCDF:", err);
//       } finally {
//         setLoading(false);
//       }
//     }

//     loadNetCDF();
//   }, [year]);

//   const center = [20, 80];

//   return (
//     <div style={{ width: "100vw", height: "100vh", position: "relative" }}>
//       {/* Controls */}
//       <div
//         style={{
//           position: "absolute",
//           top: 10,
//           left: 50,
//           zIndex: 1000,
//           background: "white",
//           padding: "8px 12px",
//           borderRadius: 6,
//           boxShadow: "0 0 5px rgba(0,0,0,0.3)",
//           minWidth: 220,
//         }}
//       >
//         <b>Select Year:</b>
//         <br />
//         <select
//           value={year}
//           onChange={(e) => setYear(Number(e.target.value))}
//           style={{ marginTop: 4, width: "100%" }}
//         >
//           {YEARS.map((y) => (
//             <option key={y} value={y}>
//               {y}
//             </option>
//           ))}
//         </select>

//         {loading && <div style={{ marginTop: 8 }}>Loading {year}...</div>}

//         {!loading && meta.substance && (
//           <div style={{ marginTop: 8, fontSize: 12, lineHeight: 1.4 }}>
//             <div>
//               <strong>Substance:</strong> {meta.substance}
//             </div>
//             {meta.fileYear && (
//               <div>
//                 <strong>File year attr:</strong> {meta.fileYear}
//               </div>
//             )}
//           </div>
//         )}
//       </div>

//       {/* Map + image overlay */}
//       <MapContainer center={center} zoom={3} style={{ width: "100%", height: "100%" }}>
//         <TileLayer
//           attribution="OpenStreetMap contributors"
//           url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
//         />

//         {overlayUrl && overlayBounds && (
//           <ImageOverlay
//             url={overlayUrl}
//             bounds={overlayBounds}
//             opacity={0.85}
//             zIndex={500}
//           />
//         )}
//       </MapContainer>
//     </div>
//   );
// }



import { MapContainer, TileLayer, ImageOverlay } from "react-leaflet";
import { useState } from "react";
import { YEARS } from "./years";
import "./App.css";
import { Legend } from "./Legend";

function buildPngName(year) {
  // adjust if your naming is different
  return `/data/pm25_png/v8.1_FT2022_AP_PM2.5_${year}_TOTALS_emi_nc3_3857.png`;
}

// copy the bounds printed by the Python script
const OVERLAY_BOUNDS = [
  [-85.04, -179.99],  // SW (lat, lon)
  [ 85.04,  179.99],  // NE
];

export default function App() {
  const [year, setYear] = useState(1970);

  return (
    <div style={{ width: "100vw", height: "100vh" }}>
      <MapContainer center={[20, 0]} zoom={2} style={{ width: "100%", height: "100%" }}>
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <ImageOverlay
          url={buildPngName(year)}
          bounds={OVERLAY_BOUNDS}
          opacity={0.8}
          zIndex={500}
          className="pm25-overlay"
        />
      </MapContainer>
      <Legend />
      <div
        style={{
          position: "absolute",
          top: 10,
          left: 50,
          zIndex: 1000,
          background: "white",
          padding: "8px 12px",
          borderRadius: 6,
          boxShadow: "0 0 5px rgba(0,0,0,0.3)",
        }}
      >
        <b>Select Year:</b>
        <br />
        <select
          value={year}
          onChange={(e) => setYear(Number(e.target.value))}
          style={{ marginTop: 4, width: "100%" }}
        >
          {YEARS.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
