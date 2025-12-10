import { useEffect, useState } from "react";
import { MapContainer, TileLayer, ImageOverlay, GeoJSON } from "react-leaflet";

const R = 6378137;

// x (meters) -> lon
function mercatorXToLon(x) {
  return (x / R) * (180 / Math.PI);
}

// y (meters) -> lat
function mercatorYToLat(y) {
  return (2 * Math.atan(Math.exp(y / R)) - Math.PI / 2) * (180 / Math.PI);
}

function bbox3857ToLeafletBounds(bbox) {
  const [minX, minY, maxX, maxY] = bbox;
  const west = mercatorXToLon(minX);
  const east = mercatorXToLon(maxX);
  const south = mercatorYToLat(minY);
  const north = mercatorYToLat(maxY);
  return [
    [south, west],
    [north, east],
  ];
}

export default function MsaTilesMap() {
  const [tiles, setTiles] = useState([]);
  const [borders, setBorders] = useState(null);

  useEffect(() => {
    // load tile manifest
    fetch("/msa/tile_manifest.json")
      .then((r) => r.json())
      .then(setTiles)
      .catch((e) => console.error("Error loading tiles:", e));
  }, []);

  useEffect(() => {
    // load world borders GeoJSON
    fetch("/countries.json")
      .then((r) => r.json())
      .then(setBorders)
      .catch((e) => console.error("Error loading boundaries:", e));
  }, []);

  console.log(borders);
  

  // style for thick border lines
  const borderStyle = {
    color: "#f5f5d0",   // light yellowish line like GLOBIO
    weight: 1.5,        // thickness
    opacity: 1,
    fill: false,        // no polygon fill
  };

  return (
    <MapContainer
      center={[20, 0]}
      zoom={2}
      style={{ height: "100vh", width: "100%" }}
    >
      {/* optional OSM behind it */}
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="&copy; OpenStreetMap contributors"
      />

      {/* your MSA raster tiles */}
      {tiles.map((tile) => (
        <ImageOverlay
          key={tile.filename}
          url={tile.url}
          bounds={bbox3857ToLeafletBounds(tile.bbox)}
          opacity={1}
        />
      ))}

      {/* boundaries on top, to get those thick outlines */}
      {borders && (
        <GeoJSON
          data={borders}
          style={borderStyle}
        />
      )}
    </MapContainer>
  );
}
