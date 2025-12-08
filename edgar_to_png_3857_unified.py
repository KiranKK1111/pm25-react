from pathlib import Path

import numpy as np
import xarray as xr
import rioxarray  # noqa: F401  # needed to register .rio
from pyproj import Transformer
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import matplotlib.cm as cm
from rasterio.transform import from_bounds
from rasterio.enums import Resampling

# ---------- CONFIG ----------
# Root directory containing all NC files (PM2.5, CO, NH3, SO2, NOx, TOX_Hg, etc.)
INPUT_ROOT = Path("./Edgar_NC4/NetCDF4_emi_Hg")

# Root directory for PNGs
OUTPUT_ROOT = Path("./Edgar_PNGs")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# Output PNG size (square)
DST_WIDTH = 8192
DST_HEIGHT = 8192

# Standard Web-Mercator world bounds (meters)
MINX = -20037508.342789244
MINY = -20037508.342789244
MAXX = 20037508.342789244
MAXY = 20037508.342789244

# Common EDGAR-like 7-colour ramp
COLOR_HEX = [
    "#03008b",   # deep blue
    "#0039b3",   # blue
    "#0099cc",   # cyan
    "#34d184",   # green
    "#d4e840",   # yellow
    "#f79433",   # orange
    "#c63a26",   # red
]

# Gas-specific bounds (each must have len(COLOR_HEX)+1 = 8 entries)
BOUNDS_BY_SUBSTANCE = {
    # Custom PM2.5 scale (less saturated)
    "PM2.5": [
        0.0,
        0.00025,
        0.0025,
        0.025,
        0.50,
        5.0,
        20.0,
        1e9,      # >=20 top red
    ],
    # CO scale (0–12)
    "CO": [
        0.0,
        0.00025,
        0.0025,
        0.025,
        0.25,
        1.0,
        5.0,
        12.0,     # >=12 top red
    ],
    # NH3 scale (EDGAR-like 0–1.2)
    "NH3": [
        0.0,
        0.00025,
        0.0025,
        0.025,
        0.25,
        0.50,
        1.2,
        1e9,      # >=1.2 top red
    ],
    # SO2 scale (0–1.2)
    "SO2": [
        0.0,
        0.00025,
        0.0025,
        0.025,
        0.25,
        0.50,
        1.2,
        1e9,      # >=1.2 top red
    ],
    # NOx scale (0–1.2)
    "NOX": [
        0.0,
        0.00025,
        0.0025,
        0.025,
        0.25,
        0.50,
        1.2,
        1e9,      # >=1.2 top red
    ],
    # 🔹 NEW: TOX_Hg (Hg) – very small emissions, log-like thresholds
    "TOX_Hg": [
        0.0,
        2e-07,    # deep blue → blue
        2e-06,    # blue → cyan
        2e-05,    # cyan → green
        2e-04,    # green → yellow
        2e-03,    # yellow → orange
        2e-02,    # orange → red
        1e9,      # clamp everything above here into red
    ],
}
# -----------------------------

to_latlon = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
dst_transform = from_bounds(MINX, MINY, MAXX, MAXY, DST_WIDTH, DST_HEIGHT)

print("Input root:", INPUT_ROOT.resolve())
print("Output root:", OUTPUT_ROOT.resolve())

nc_files = sorted(INPUT_ROOT.rglob("*.nc"))
if not nc_files:
    print("No .nc files found under", INPUT_ROOT)
else:
    print(f"Found {len(nc_files)} NetCDF files")

for nc_path in nc_files:
    print("\n=== Processing", nc_path.relative_to(INPUT_ROOT), "===")

    ds = xr.open_dataset(nc_path)

    da_raw = ds["emissions"]  # (lat, lon)
    lon = da_raw["lon"]
    lat = da_raw["lat"]

    # --- Detect substance from filename first ---
    fname = nc_path.name.upper()
    if "_PM2.5_" in fname or "_PM25_" in fname:
        substance = "PM2.5"
    elif "_CO_" in fname:
        substance = "CO"
    elif "_NH3_" in fname:
        substance = "NH3"
    elif "_SO2_" in fname:
        substance = "SO2"
    elif "_NOX_" in fname:
        substance = "NOX"
    elif "_TOX_HG_" in fname or "_TOXHG_" in fname:
        substance = "TOX_Hg"
    else:
        # fallback to attribute if available
        substance_attr = da_raw.attrs.get("substance", "").upper()
        if "PM" in substance_attr and "2.5" in substance_attr:
            substance = "PM2.5"
        elif substance_attr == "CO":
            substance = "CO"
        elif substance_attr == "NH3":
            substance = "NH3"
        elif substance_attr == "SO2":
            substance = "SO2"
        elif substance_attr == "NOX":
            substance = "NOX"
        elif substance_attr == "HG":
            substance = "TOX_Hg"
        else:
            substance = "UNKNOWN"
    print("Detected substance:", substance)

    # pick colour bounds
    if substance in BOUNDS_BY_SUBSTANCE:
        bounds = BOUNDS_BY_SUBSTANCE[substance]
    else:
        # fallback: percentile-based bounds if substance unknown
        print("WARNING: Unknown substance; using percentile-based bounds.")
        arr_all = da_raw.values.astype("float32")
        valid = arr_all[np.isfinite(arr_all) & (arr_all > 0)]
        if valid.size == 0:
            print("No valid data; skipping file.")
            ds.close()
            continue
        p = np.percentile(valid, [0, 5, 25, 50, 75, 90, 99, 100])
        bounds = p.tolist()

    if len(bounds) != len(COLOR_HEX) + 1:
        raise ValueError(
            f"Bounds for {substance} must have {len(COLOR_HEX)+1} entries, got {len(bounds)}"
        )

    print("lat min/max BEFORE mask:", float(lat[0]), float(lat[-1]))
    print("lon min/max BEFORE wrap:", float(lon[0]), float(lon[-1]))

    # 1) mask latitudes < -85° (avoid Mercator pole artifacts)
    da_masked = da_raw.where(lat >= -85.0, np.nan)

    # 2) wrap-around in longitude to avoid seam at ±180°
    west_col = da_masked.isel(lon=-1).assign_coords(lon=-180.0)
    east_col = da_masked.isel(lon=0).assign_coords(lon=180.0)
    da_wrapped = xr.concat([west_col, da_masked, east_col], dim="lon")

    print(
        "lon min/max AFTER wrap:",
        float(da_wrapped["lon"][0]),
        float(da_wrapped["lon"][-1]),
    )

    # 3) set spatial dims and CRS
    da_wrapped = da_wrapped.rio.set_spatial_dims(
        x_dim="lon", y_dim="lat", inplace=False
    )
    da_wrapped = da_wrapped.rio.write_crs("EPSG:4326")

    print("Original (wrapped) shape (lat, lon):", da_wrapped.shape)

    # 4) reproject to EPSG:3857 into fixed global grid
    da_3857 = da_wrapped.rio.reproject(
        dst_crs="EPSG:3857",
        transform=dst_transform,
        shape=(DST_HEIGHT, DST_WIDTH),
        resampling=Resampling.nearest,
    )

    print("Reprojected shape (y, x):", da_3857.shape)

    # 5) convert to array and clear bottom strip (Mercator cutoff)
    arr = da_3857.values.astype("float32")
    arr[-200:, :] = np.nan

    # 6) diagnostics (optional)
    minx, miny, maxx, maxy = da_3857.rio.bounds()
    width_m = maxx - minx
    height_m = maxy - miny
    print(
        "Extent meters (w, h):",
        width_m,
        height_m,
        "ratio w/h =", width_m / height_m,
    )

    minlon_leaf, minlat_leaf = to_latlon.transform(minx, miny)
    maxlon_leaf, maxlat_leaf = to_latlon.transform(maxx, maxy)
    print("Leaflet bounds (lat, lon):")
    print("  SW:", (minlat_leaf, minlon_leaf))
    print("  NE:", (maxlat_leaf, maxlon_leaf))

    # 7) mask invalid / <= 0
    arr = np.where(~np.isfinite(arr) | (arr <= 0), np.nan, arr)

    # 8) colour mapping with gas-specific bounds
    cmap = ListedColormap(COLOR_HEX)
    norm = BoundaryNorm(bounds, len(COLOR_HEX))

    sm = cm.ScalarMappable(norm=norm, cmap=cmap)
    rgba = sm.to_rgba(arr)  # (H, W, 4) floats 0..1

    # NaNs fully transparent
    mask_nan = np.isnan(arr)
    if mask_nan.any():
        rgba[mask_nan, 3] = 0.0

    rgba_uint8 = (rgba * 255).astype("uint8")

    # 9) output path: per-substance subfolder
    sub_name = substance.lower().replace(".", "")  # "PM2.5" -> "pm25"
    out_subdir = OUTPUT_ROOT / f"{sub_name}_png_3857"
    out_subdir.mkdir(parents=True, exist_ok=True)

    out_png = out_subdir / (nc_path.stem + "_3857.png")
    plt.imsave(out_png, rgba_uint8, origin="upper")
    print("Wrote:", out_png)

    ds.close()
