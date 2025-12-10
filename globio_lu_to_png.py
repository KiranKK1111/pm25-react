import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image
import rasterio
from rasterio.warp import reproject, Resampling
from affine import Affine
from tqdm import tqdm

# ----------------------------------------------------
# ADVANCED VEGETATION PALETTE
# ----------------------------------------------------
ADVANCED_COLORS = {
    # Dense vegetation
    1: (0, 69, 41, 255),       # Deep evergreen forest
    2: (0, 104, 55, 255),      # Dense rainforest / wet forest
    3: (35, 132, 67, 255),     # Forest / woodland

    # Medium & open vegetation
    4: (65, 171, 93, 255),     # Shrub / woody savanna
    5: (120, 198, 121, 255),   # Grassland / open forest

    # Sparse vegetation
    6: (173, 221, 142, 255),   # Sparse shrubs / semi-arid
    7: (217, 240, 163, 255),   # Very sparse vegetation / transition

    # Bare ground & desert gradient
    8: (254, 224, 139, 255),   # Light desert
    9: (254, 196, 79, 255),    # Medium desert
    10: (236, 112, 20, 255),   # Rocky / very dry
}

# Ocean / NoData color (EXACT blue from your image)
OCEAN = (25, 118, 174, 255)      # #1976AE

SNOW = (255, 255, 255, 255)      # White
URBAN = (90, 90, 90, 255)        # Dark gray
NO_DATA_COLOR = OCEAN

# Map GLOBIO LU codes → vegetation levels
LU_TO_ADV = {
    10: 1,   # Forest            -> dense evergreen
    90: 3,   # Shrubland         -> forest/woodland
    100: 4,  # Other natural     -> shrub/woody savanna

    20: 5,   # Grassland         -> grass/open veg
    30: 6,   # Cropland          -> sparse veg
    70: 2,   # Wetland           -> wet dense veg

    50: 8,   # Barren            -> light desert
    80: None,  # Snow handled separately
    40: None,  # Urban handled separately
    60: None,  # Water handled separately
}

# Canonical Web-Mercator world square extent
WORLD_MIN = -20037508.342789244
WORLD_MAX = 20037508.342789244


# ----------------------------------------------------
# Reproject to EPSG:3857 on a square WORLD grid
# ----------------------------------------------------
def reproject_to_world_square(in_tif: Path, pixel_size: float):
    """
    Reproject band 1 of input GeoTIFF to EPSG:3857 on a fixed,
    square world grid (Web Mercator world extent).
    Output array is square: side x side pixels.
    """
    dst_crs = "EPSG:3857"

    with rasterio.open(in_tif) as src:
        if src.crs is None:
            raise ValueError("Source dataset has no CRS; cannot reproject.")

        print(f"Source size   : {src.width} x {src.height}")
        print(f"Source CRS    : {src.crs}")
        print(f"Source bounds : {src.bounds}")
        print(f"Source nodata : {src.nodata}")

        world_width = WORLD_MAX - WORLD_MIN
        side = math.ceil(world_width / pixel_size)

        print(f"Target CRS    : {dst_crs}")
        print(f"World extent  : [{WORLD_MIN}, {WORLD_MIN}, {WORLD_MAX}, {WORLD_MAX}]")
        print(f"Target size   : {side} x {side} (square)")
        print(f"Pixel size    : {pixel_size} m")

        # Affine transform: top-left origin, square pixels
        transform = Affine(pixel_size, 0, WORLD_MIN,
                           0, -pixel_size, WORLD_MAX)

        dst_array = np.empty((side, side), dtype=src.dtypes[0])
        nodata = src.nodata

        print("Reprojecting to world square grid...")
        reproject(
            source=rasterio.band(src, 1),
            destination=dst_array,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=dst_crs,
            resampling=Resampling.nearest,  # keep classes
            src_nodata=nodata,
            dst_nodata=nodata,
        )

    return dst_array, nodata


# ----------------------------------------------------
# Advanced vegetation RGBA mapping with progress
# ----------------------------------------------------
def landuse_to_rgba(arr, nodata=None):
    """
    Convert GLOBIO land-use integer raster -> RGBA image using
    advanced vegetation + desert + water palette.
    """
    h, w = arr.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    # Default = ocean blue
    rgba[:, :, :] = OCEAN

    # NoData mask
    if nodata is not None:
        nodata_mask = (arr == nodata) | ~np.isfinite(arr)
    else:
        nodata_mask = ~np.isfinite(arr)

    # Snow/Ice (80)
    mask = arr == 80
    rgba[mask] = SNOW

    # Urban (40)
    mask = arr == 40
    rgba[mask] = URBAN

    # Water (60)
    mask = arr == 60
    rgba[mask] = OCEAN

    # Vegetation & desert gradient
    with tqdm(total=len(LU_TO_ADV), desc="Color mapping", unit="class") as pbar:
        for lu_value, adv_level in LU_TO_ADV.items():
            if adv_level is None:
                pbar.update(1)
                continue

            if adv_level not in ADVANCED_COLORS:
                pbar.update(1)
                continue

            mask = arr == lu_value
            rgba[mask] = ADVANCED_COLORS[adv_level]
            pbar.update(1)

    # Ensure NoData stays ocean blue
    rgba[nodata_mask] = NO_DATA_COLOR

    return rgba


# ----------------------------------------------------
# Single file: TIFF -> PNG
# ----------------------------------------------------
def convert_single_tif_to_png(in_tif: Path, out_png: Path, pixel_size: float):
    print(f"\n=== Processing file: {in_tif.name} ===")
    print(f"Input  : {in_tif}")
    print(f"Output : {out_png}")
    print(f"Pixel size: {pixel_size} m")

    data_world, nodata = reproject_to_world_square(in_tif, pixel_size)
    rgba = landuse_to_rgba(data_world, nodata=nodata)

    img = Image.fromarray(rgba, mode="RGBA")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)

    print(f"Saved PNG: {out_png}\n")


# ----------------------------------------------------
# MAIN: single file or whole folder
# ----------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description=(
            "Reproject one or many GLOBIO Land-Use TIFFs to EPSG:3857 square world "
            "grid and render PNGs with an advanced vegetation palette."
        )
    )
    parser.add_argument(
        "input_path",
        help="Path to input .tif OR a folder containing many .tif files",
    )
    parser.add_argument(
        "output_dir",
        help="Directory where PNG files will be written",
    )
    parser.add_argument(
        "--pixel-size",
        type=float,
        default=5000.0,
        help="Pixel size in meters in EPSG:3857 (smaller = sharper, more RAM). Default: 5000",
    )
    args = parser.parse_args()

    input_path = Path(args.input_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Case 1: single TIFF file
    if input_path.is_file():
        out_png = output_dir / (input_path.stem + ".png")
        convert_single_tif_to_png(input_path, out_png, args.pixel_size)
        return

    # Case 2: directory -> process all .tif files
    if input_path.is_dir():
        tif_files = sorted(list(input_path.glob("*.tif")))
        if not tif_files:
            print(f"No .tif files found in directory: {input_path}")
            return

        print(f"Found {len(tif_files)} TIFF files in {input_path}")

        for tif in tif_files:
            out_png = output_dir / (tif.stem + ".png")
            convert_single_tif_to_png(tif, out_png, args.pixel_size)

        print("ALL FILES PROCESSED SUCCESSFULLY.")
        return

    print("ERROR: input_path is neither a file nor a directory.")


if __name__ == "__main__":
    main()
