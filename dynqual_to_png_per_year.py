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


# --------------- CONFIG ---------------
INPUT_DIR = Path("./DynQual")        # folder with BODload_*.nc, TDSload_*.nc
OUTPUT_DIR = Path("./DynQual_PNGs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DST_WIDTH = 8192
DST_HEIGHT = 8192

MINX = -20037508.342789244
MINY = -20037508.342789244
MAXX = 20037508.342789244
MAXY = 20037508.342789244

# 7-color palette
COLOR_HEX = [
    "#03008b",  # dark blue
    "#0039b3",  # blue
    "#0099cc",  # light blue
    "#34d184",  # green
    "#d4e840",  # yellow
    "#f79433",  # orange
    "#c63a26",  # red
]
# --------------------------------------


to_latlon = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
dst_transform = from_bounds(MINX, MINY, MAXX, MAXY, DST_WIDTH, DST_HEIGHT)

print("Input:", INPUT_DIR.resolve())
print("Output:", OUTPUT_DIR.resolve())

nc_files = sorted(INPUT_DIR.glob("*.nc"))
print(f"Found {len(nc_files)} DynQual files")


def detect_dynqual_variable(ds):
    """Return (variable_name, substance_label) -> ('bodload', 'BOD') etc."""
    for key in ds.data_vars:
        lower = key.lower()
        if "bod" in lower:
            return key, "BOD"
        if "tds" in lower:
            return key, "TDS"
    raise ValueError("No DynQual variable (bodload / tdsload) found in dataset.")


def time_label(time_value):
    """Build a safe label for filenames from a scalar time coordinate."""
    # time_value is typically numpy.datetime64 or a number
    val = np.array(time_value)
    if np.issubdtype(val.dtype, np.datetime64):
        # year only (e.g. '1980')
        return np.datetime_as_string(val, unit="Y")
    else:
        return str(val)


for nc_path in nc_files:
    print("\n=== Processing", nc_path.name, "===")

    ds = xr.open_dataset(nc_path)

    var_name, substance = detect_dynqual_variable(ds)
    da_raw = ds[var_name]
    print("Detected variable:", var_name)
    print("Detected substance:", substance)
    print("Dims:", da_raw.dims)

    lon = ds["lon"]
    lat = ds["lat"]

    has_time = "time" in da_raw.dims
    if has_time:
        times = ds["time"]
        n_time = times.size
        print("Time steps:", n_time)
    else:
        n_time = 1
        times = [None]

    # choose subfolder: bod_png_3857 / tds_png_3857
    out_subdir = OUTPUT_DIR / f"{substance.lower()}_png_3857"
    out_subdir.mkdir(parents=True, exist_ok=True)

    # ----- LOOP OVER YEARS (or single slice if no time dim) -----
    for t_idx in range(n_time):
        if has_time:
            da_2d = da_raw.isel(time=t_idx)
            t_val = times.values[t_idx]
            year_str = time_label(t_val)
            print(f"  -> time index {t_idx}, label = {year_str}")
        else:
            da_2d = da_raw
            year_str = "all"

        # ---- auto color bounds for THIS year ----
        arr_all = da_2d.values.astype("float32")
        valid = arr_all[np.isfinite(arr_all) & (arr_all > 0)]
        if valid.size == 0:
            print(f"    [WARN] No valid data for {year_str}; skipping.")
            continue

        bounds = np.percentile(valid, [0, 5, 25, 50, 75, 90, 99, 100]).tolist()
        print(f"    Dynamic bounds for {year_str}:", bounds)

        # ---- mask Antarctica ----
        da_masked = da_2d.where(lat >= -85.0, np.nan)

        # ---- longitude wrap ----
        west_col = da_masked.isel(lon=-1).assign_coords(lon=-180.0)
        east_col = da_masked.isel(lon=0).assign_coords(lon=180.0)
        da_wrapped = xr.concat([west_col, da_masked, east_col], dim="lon")

        # ---- CRS + spatial dims ----
        da_wrapped = da_wrapped.rio.set_spatial_dims(
            x_dim="lon", y_dim="lat", inplace=False
        )
        da_wrapped = da_wrapped.rio.write_crs("EPSG:4326")

        # ---- reproject to Web Mercator ----
        da_3857 = da_wrapped.rio.reproject(
            dst_crs="EPSG:3857",
            transform=dst_transform,
            shape=(DST_HEIGHT, DST_WIDTH),
            resampling=Resampling.nearest,
        )

        arr = da_3857.values.astype("float32")
        # clear bottom artifacts
        arr[-200:, :] = np.nan
        arr = np.where(~np.isfinite(arr) | (arr <= 0), np.nan, arr)

        # ---- color mapping ----
        cmap = ListedColormap(COLOR_HEX)
        norm = BoundaryNorm(bounds, len(COLOR_HEX))
        sm = cm.ScalarMappable(norm=norm, cmap=cmap)

        rgba = sm.to_rgba(arr)
        mask_nan = np.isnan(arr)
        rgba[mask_nan, 3] = 0.0
        rgba_uint8 = (rgba * 255).astype("uint8")

        # ---- output filename with year ----
        stem = nc_path.stem
        out_png = out_subdir / f"{stem}_{year_str}_3857.png"
        plt.imsave(out_png, rgba_uint8, origin="upper")
        print("    Wrote PNG:", out_png)

    ds.close()
