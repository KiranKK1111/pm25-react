from pathlib import Path

import numpy as np
import xarray as xr
import rioxarray  # noqa: F401
from pyproj import Transformer
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import matplotlib.cm as cm
from rasterio.transform import from_bounds
from rasterio.enums import Resampling


# ---------------- CONFIG ----------------
INPUT_DIR = Path("./DynQual")        # Folder with BODload/TDSload .nc files
OUTPUT_DIR = Path("./DynQual_PNGs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DST_WIDTH = 8192
DST_HEIGHT = 8192

MINX = -20037508.342789244
MINY = -20037508.342789244
MAXX = 20037508.342789244
MAXY = 20037508.342789244

# 7-color palette (same as EDGAR)
COLOR_HEX = [
    "#03008b",  # dark blue
    "#0039b3",  # blue
    "#0099cc",  # light blue
    "#34d184",  # green
    "#d4e840",  # yellow
    "#f79433",  # orange
    "#c63a26",  # red
]
# ----------------------------------------


to_latlon = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
dst_transform = from_bounds(MINX, MINY, MAXX, MAXY, DST_WIDTH, DST_HEIGHT)

print("Input:", INPUT_DIR.resolve())
print("Output:", OUTPUT_DIR.resolve())

nc_files = sorted(INPUT_DIR.glob("*.nc"))
print(f"Found {len(nc_files)} DynQual files")


def detect_dynqual_variable(ds):
    """Find the DynQual variable and label it as BOD or TDS."""
    for key in ds.data_vars:
        lower = key.lower()
        if "bod" in lower:
            return key, "BOD"
        if "tds" in lower:
            return key, "TDS"
    raise ValueError("No DynQual variable (bodload / tdsload) found in dataset.")


for nc_path in nc_files:
    print("\n=== Processing", nc_path.name, "===")

    ds = xr.open_dataset(nc_path)

    var_name, substance = detect_dynqual_variable(ds)
    da_raw = ds[var_name]
    print("Detected substance:", substance)
    print("Original dims:", da_raw.dims)

    # ---- REDUCE TIME DIMENSION TO 2-D ----
    # Many DynQual files are (time, lat, lon). For mapping we only want one 2-D layer.
    if "time" in da_raw.dims:
        # Option 1: mean over all years (default)
        da_2d = da_raw.mean(dim="time")

        # If you ever want a specific year, comment the line above and use:
        # da_2d = da_raw.sel(time="1980")  # or isel(time=0) etc.
        print("Collapsed time dimension by mean → shape:", da_2d.shape)
    else:
        da_2d = da_raw

    lon = da_2d["lon"]
    lat = da_2d["lat"]

    # ---- AUTO COLOR BOUNDARIES (percentile-based on 2-D field) ----
    arr_all = da_2d.values.astype("float32")
    valid = arr_all[np.isfinite(arr_all) & (arr_all > 0)]

    if valid.size == 0:
        print("No valid data. Skipping.")
        ds.close()
        continue

    # 0,5,25,50,75,90,99,100 percentiles → 8 boundaries
    bounds = np.percentile(valid, [0, 5, 25, 50, 75, 90, 99, 100]).tolist()
    print("Dynamic bounds:", bounds)

    if len(bounds) != len(COLOR_HEX) + 1:
        raise ValueError("Bounds length mismatch.")

    # ---- Mask Antarctica ----
    da_masked = da_2d.where(lat >= -85.0, np.nan)

    # ---- Longitude Wrap to remove seam at 180° ----
    west_col = da_masked.isel(lon=-1).assign_coords(lon=-180.0)
    east_col = da_masked.isel(lon=0).assign_coords(lon=180.0)
    da_wrapped = xr.concat([west_col, da_masked, east_col], dim="lon")

    # ---- CRS + Spatial dims ----
    da_wrapped = da_wrapped.rio.set_spatial_dims(
        x_dim="lon", y_dim="lat", inplace=False
    )
    da_wrapped = da_wrapped.rio.write_crs("EPSG:4326")

    # ---- Reproject to Web-Mercator ----
    da_3857 = da_wrapped.rio.reproject(
        dst_crs="EPSG:3857",
        transform=dst_transform,
        shape=(DST_HEIGHT, DST_WIDTH),
        resampling=Resampling.nearest,
    )

    arr = da_3857.values.astype("float32")

    # clear bottom Mercator artefacts
    arr[-200:, :] = np.nan
    arr = np.where(~np.isfinite(arr) | (arr <= 0), np.nan, arr)

    # ---- Colour mapping ----
    cmap = ListedColormap(COLOR_HEX)
    norm = BoundaryNorm(bounds, len(COLOR_HEX))
    sm = cm.ScalarMappable(norm=norm, cmap=cmap)

    rgba = sm.to_rgba(arr)
    mask_nan = np.isnan(arr)
    rgba[mask_nan, 3] = 0.0
    rgba_uint8 = (rgba * 255).astype("uint8")

    # ---- Output folder ----
    out_subdir = OUTPUT_DIR / f"{substance.lower()}_png_3857"
    out_subdir.mkdir(parents=True, exist_ok=True)

    out_png = out_subdir / (nc_path.stem + "_3857.png")
    plt.imsave(out_png, rgba_uint8, origin="upper")
    print("Wrote PNG:", out_png)

    ds.close()
