import { useEffect, useState } from "react";
import { MapContainer, TileLayer, Rectangle, Tooltip } from "react-leaflet";
import { NetCDFReader } from "netcdfjs";
import { YEARS } from "./years";

function getColor(value) {
  if (!value || value <= 0) return "transparent"; // or background ocean color

  if (value < 0.0025) return "#1b4f9a";  // deep blue (0–0.0025)
  if (value < 0.025) return "#2166c5";  // blue
  if (value < 0.10) return "#1ba8c4";  // cyan
  if (value < 0.25) return "#46d46b";  // green
  if (value < 0.50) return "#d4e840";  // yellow‑green
  if (value < 1.20) return "#f79433";  // orange
  return "#c63a26";                  // >1.2, red‑brown hotspot
}

// Build filename for each year (adjust prefix/suffix if needed)
function buildFileName(year) {
  const prefix = "v8.1_FT2022_AP_PM2.5_";
  const suffix = "_TOTALS_emi_nc3.nc";  // Make sure your converted files follow this
  return `/data/pm25/${prefix}${year}${suffix}`;
}

export default function App() {
  const [year, setYear] = useState(1970);
  const [cells, setCells] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function loadNetCDF() {
      setLoading(true);
      setCells([]);

      try {
        const url = buildFileName(year);
        console.log("Loading:", url);

        const res = await fetch(url);
        const buf = await res.arrayBuffer();
        const reader = new NetCDFReader(buf);

        console.log(reader);

        const lats = reader.getDataVariable("lat");
        const lons = reader.getDataVariable("lon");
        const emissions = reader.getDataVariable("emissions");

        const emissionsVar = reader.variables.find(v => v.name === "emissions");
        const substanceAttr = emissionsVar.attributes.find(a => a.name === "substance");
        const yearAttr = emissionsVar.attributes.find(a => a.name === "year");

        const substance = substanceAttr?.value;
        const fileYear = yearAttr?.value;

        console.log("Substance =", substance);
        console.log("Year =", fileYear);
        const nLat = lats.length;
        const nLon = lons.length;

        console.log("Grid size:", nLat, nLon);

        const STEP = 10;

        // helper: indices 0, STEP, 2*STEP, ... but
        // always with i + STEP < length  (like your original for-loop)
        const makeSteppedIndices = (length, step) => {
          const count = Math.max(0, Math.ceil((length - step) / step)); // < length - step
          return Array.from({ length: count }, (_, k) => k * step);
        };

        const latIndices = makeSteppedIndices(nLat, STEP);
        const lonIndices = makeSteppedIndices(nLon, STEP);

        const rects = latIndices
          .flatMap((i) =>
            lonIndices.map((j) => {
              const idx = i * nLon + j;
              const value = emissions[idx];

              if (!value || value <= 0 || Number.isNaN(value)) return null;

              const lat1 = lats[i];
              const lat2 = lats[i + STEP];
              const lon1 = lons[j];
              const lon2 = lons[j + STEP];

              // Extra safety guard
              if (
                !Number.isFinite(lat1) ||
                !Number.isFinite(lat2) ||
                !Number.isFinite(lon1) ||
                !Number.isFinite(lon2)
              ) {
                return null;
              }

              return {
                bounds: [
                  [lat1, lon1],
                  [lat2, lon2],
                ],
                value,
              };
            })
          )
          .filter(Boolean);

        console.log("Rendered rectangles:", rects.length);
        console.log(rects);
        
        setCells(rects);
      } catch (err) {
        console.error("Error loading:", err);
      } finally {
        setLoading(false);
      }
    }

    loadNetCDF();
  }, [year]);


  const center = [20, 80];

  const myRenderer = L.canvas({ padding: 0.5 });

  return (
    <div style={{ width: "100vw", height: "100vh", position: "relative" }}>
      {/* Year Selector */}
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
        <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
          {YEARS.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>

        {loading && <div style={{ marginTop: 8 }}>Loading {year}...</div>}
      </div>

      {/* Map */}
      <MapContainer
        center={center}
        zoom={3}
        style={{ width: "100%", height: "100%" }}
      >
        <TileLayer
          attribution="OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {cells.map((cell, i) => (
          <Rectangle
            key={i}
            bounds={cell.bounds}
            pathOptions={{
              stroke: false,                 // no borders
              fill: true,
              fillColor: getColor(cell.value),
              fillOpacity: 0.8,              // tweak 0.6–0.9 as you like
              renderer: myRenderer,
            }}
          >

            <Tooltip sticky>
              <div>
                <div>
                  <strong>Year:</strong> {year}
                </div>
                <div>
                  <strong>Emissions:</strong> {cell.value.toFixed(2)}
                </div>
                <div>
                  Lat: {cell.bounds[0][0].toFixed(2)}, Lon: {cell.bounds[0][1].toFixed(2)}
                </div>
              </div>
            </Tooltip>
          </Rectangle>
        ))}
      </MapContainer>
    </div>
  );
}
