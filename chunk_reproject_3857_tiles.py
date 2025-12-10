import argparse
import pathlib
import json

import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.windows import Window
from rasterio.transform import array_bounds
from tqdm import tqdm
from PIL import Image


def hex_to_rgb(h):
    """Convert #RRGGBB → (R, G, B)."""
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def chunk_reproject_to_3857_png(
    in_path,
    out_dir,
    tile_size=1024,      # small tiles by default
    target_res=150.0,    # meters per pixel (EPSG:3857)
    base_url=None,       # e.g. "http://localhost:3000/geo-png"
):
    """
    Chunk big EPSG:4326 GLOBIO-style MSA raster into EPSG:3857 colored PNG tiles.

    - Reprojects on the fly using WarpedVRT
    - Uses nodata (-999 or src.nodata) as ocean
    - Land: GLOBIO green classes for MSA 0–1
    - Ocean: blue
    - Resumable: skips tiles whose PNG already exists
    - Writes tile_manifest.json with filename, url, bbox (EPSG:3857), crs
    """

    in_path = pathlib.Path(in_path).resolve()
    out_dir = pathlib.Path(out_dir).resolve()

    print(f"Input       : {in_path}")
    print(f"Output dir  : {out_dir}")
    print(f"Tile size   : {tile_size} x {tile_size}")
    print(f"Target res  : {target_res} m/pixel (EPSG:3857)")
    print(f"Base URL    : {base_url}\n")

    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / "tile_manifest.json"

    # --- Load existing manifest (if any) so we can resume cleanly ---
    tile_manifest = {}
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            for entry in existing:
                fn = entry.get("filename")
                if fn:
                    tile_manifest[fn] = entry
            print(f"Loaded existing manifest with {len(tile_manifest)} entries.\n")
        except Exception as e:
            print(f"Warning: failed to read existing manifest: {e}\n")

    with rasterio.open(in_path) as src:
        src_crs = src.crs or "EPSG:4326"
        if str(src_crs) != "EPSG:4326":
            print(f"WARNING: source CRS is {src_crs}, expected EPSG:4326")

        print(f"Source size   : {src.width} x {src.height}")
        print(f"Source CRS    : {src_crs}")
        print(f"Source bounds : {src.bounds}")
        print(f"Source nodata : {src.nodata}\n")

        # Use nodata from file if present, otherwise assume -999 (GLOBIO conv.)
        nodata_value = src.nodata if src.nodata is not None else -999.0
        print(f"Using nodata value: {nodata_value}\n")

        # WarpedVRT: on-the-fly reprojection to EPSG:3857 at desired resolution
        vrt_options = dict(
            crs="EPSG:3857",
            resampling=Resampling.bilinear,
            src_nodata=nodata_value,
            dst_nodata=nodata_value,
            resolution=(target_res, target_res),
        )

        with WarpedVRT(src, **vrt_options) as vrt:
            print(f"VRT (3857) width x height: {vrt.width} x {vrt.height}")
            print(f"VRT CRS     : {vrt.crs}")
            print(f"VRT bounds  : {vrt.bounds}")
            print(f"VRT res     : {vrt.res}\n")

            # --- Estimation of tiles & approximate storage ---
            n_tiles_x = (vrt.width + tile_size - 1) // tile_size
            n_tiles_y = (vrt.height + tile_size - 1) // tile_size
            total_tiles = n_tiles_x * n_tiles_y

            total_pixels = vrt.width * vrt.height
            approx_raw_bytes = total_pixels * 3  # RGB
            approx_raw_gb = approx_raw_bytes / (1024**3)

            print("=== Estimation ===")
            print(f"Tiles X × Y : {n_tiles_x} × {n_tiles_y}")
            print(f"Total tiles : {total_tiles}")
            print(f"Total pixels: {total_pixels:,}")
            print(f"Approx raw RGB data (uncompressed): {approx_raw_gb:.2f} GB")
            print("PNG compression will reduce disk size, but this is a ballpark.\n")

            # --- Color settings ---
            # Ocean color (blue)
            ocean_color = hex_to_rgb("#1f78b4")

            # GLOBIO-style greens, low → high MSA
            hex_colors = [
                "#e0f3db",  # 0.0–0.1
                "#f7fcf5",  # 0.1–0.2
                "#e5f5e0",  # 0.2–0.3
                "#c7e9c0",  # 0.3–0.4
                "#a1d99b",  # 0.4–0.5
                "#74c476",  # 0.5–0.6
                "#41ab5d",  # 0.6–0.7
                "#238b45",  # 0.7–0.8
                "#006d2c",  # 0.8–0.9
                "#00441b",  # 0.9–1.0
            ]
            palette = np.array([hex_to_rgb(h) for h in hex_colors], dtype=np.uint8)
            bins = np.array(
                [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0001],
                dtype="float32",
            )

            tile_index = 0

            # Progress bar with ETA
            with tqdm(
                total=total_tiles,
                desc="Reprojecting tiles",
                unit="tile",
                dynamic_ncols=True,
                mininterval=0.3,
                smoothing=0.2,
            ) as pbar:
                for ty in range(n_tiles_y):
                    for tx in range(n_tiles_x):
                        tile_index += 1

                        col_off = tx * tile_size
                        row_off = ty * tile_size
                        w = min(tile_size, vrt.width - col_off)
                        h = min(tile_size, vrt.height - row_off)

                        if w <= 0 or h <= 0:
                            pbar.update(1)
                            continue

                        window = Window(col_off, row_off, w, h)

                        # File naming: flat in out_dir
                        tile_name = (
                            f"{in_path.stem}_3857_res{int(target_res)}m_"
                            f"tile_y{ty:04d}_x{tx:04d}.png"
                        )
                        out_path = out_dir / tile_name

                        # --- Compute bounds for manifest (EPSG:3857) ---
                        transform = vrt.window_transform(window)
                        left3857, bottom3857, right3857, top3857 = array_bounds(
                            h, w, transform
                        )

                        rel_path = out_path.name
                        if base_url:
                            url = base_url.rstrip("/") + "/" + rel_path
                        else:
                            url = rel_path

                        entry = {
                            "filename": rel_path,
                            "url": url,
                            "bbox": [
                                float(left3857),
                                float(bottom3857),
                                float(right3857),
                                float(top3857),
                            ],
                            "crs": "EPSG:3857",
                        }

                        # Store/overwrite in manifest dict
                        tile_manifest[rel_path] = entry

                        # --- RESUME LOGIC: skip if PNG already exists ---
                        if out_path.exists():
                            # Already generated earlier; just skip heavy work
                            pbar.update(1)
                            continue

                        # Read tile as masked array (nodata already masked)
                        data_ma = vrt.read(1, window=window, masked=True)
                        data = data_ma.filled(np.nan).astype("float32")
                        nodata_mask = data_ma.mask | ~np.isfinite(data)

                        # Debug stats for first few tiles
                        if tile_index <= 3:
                            valid = np.isfinite(data)
                            if np.any(valid):
                                print(
                                    f"Tile {tile_index} stats: "
                                    f"min={np.nanmin(data):.4f}, "
                                    f"max={np.nanmax(data):.4f}, "
                                    f"mean={np.nanmean(data):.4f}"
                                )
                            else:
                                print(f"Tile {tile_index} stats: all nodata")

                        # Clip MSA values to [0,1]
                        data = np.clip(data, 0.0, 1.0)

                        # Ocean = nodata OR very small values
                        ocean_mask = nodata_mask | (data < 0.001)
                        land_mask = ~ocean_mask

                        # Prepare RGB tile
                        rgb = np.zeros((h, w, 3), dtype=np.uint8)

                        # Blue oceans
                        rgb[ocean_mask] = ocean_color

                        # Green land by MSA class
                        if np.any(land_mask):
                            classes = np.digitize(data[land_mask], bins) - 1
                            classes = np.clip(classes, 0, len(palette) - 1)
                            rgb[land_mask] = palette[classes]

                        # Save RGB PNG
                        Image.fromarray(rgb, mode="RGB").save(out_path)

                        # Optional log (comment out if too noisy)
                        print(
                            f"[{tile_index}/{total_tiles}] "
                            f"Writing {out_path.name} ({w}x{h}px)"
                        )

                        pbar.update(1)

    # --- Write manifest at the end (deduplicated by filename) ---
    manifest_list = list(tile_manifest.values())
    # optional: sort by filename for stable order
    manifest_list.sort(key=lambda e: e["filename"])

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_list, f, indent=2)

    print(f"\nTile manifest written: {manifest_path}")
    print("All colored PNG tiles written (CRS = EPSG:3857).")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Chunk big EPSG:4326 MSA raster into high-resolution "
            "EPSG:3857 colored PNG tiles (resumable, with manifest)."
        )
    )
    parser.add_argument("input_tif", help="Path to big EPSG:4326 .tif")
    parser.add_argument("output_dir", help="Directory for PNG tiles")
    parser.add_argument(
        "--tile_size",
        type=int,
        default=1024,
        help="Tile width/height in pixels (default 1024)",
    )
    parser.add_argument(
        "--resolution",
        type=float,
        default=150.0,
        help="Target resolution in meters per pixel in EPSG:3857 (default 150)",
    )
    parser.add_argument(
        "--base_url",
        type=str,
        default=None,
        help="Base URL prefix for tiles in manifest "
             "(e.g. http://localhost:3000/geo-png or /geo-png)",
    )
    args = parser.parse_args()

    chunk_reproject_to_3857_png(
        args.input_tif,
        args.output_dir,
        tile_size=args.tile_size,
        target_res=args.resolution,
        base_url=args.base_url,
    )


if __name__ == "__main__":
    main()
