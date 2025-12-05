#!/usr/bin/env python

import sys
import numpy as np
import xarray as xr

TOL = 1e-6  # numeric tolerance for data comparison


def compare_attrs(attrs1, attrs2, what):
    ok = True
    keys1 = set(attrs1.keys())
    keys2 = set(attrs2.keys())

    only1 = keys1 - keys2
    only2 = keys2 - keys1
    if only1:
        print(f"[ATTR] {what}: only in first: {sorted(only1)}")
        ok = False
    if only2:
        print(f"[ATTR] {what}: only in second: {sorted(only2)}")
        ok = False

    for k in keys1 & keys2:
        v1 = attrs1[k]
        v2 = attrs2[k]
        if str(v1) != str(v2):
            print(f"[ATTR] {what}.{k} differs:")
            print(f"   first : {v1!r}")
            print(f"   second: {v2!r}")
            ok = False
    return ok


def main(path1, path2):
    print(f"Comparing:\n  1) {path1}\n  2) {path2}\n")

    ds1 = xr.open_dataset(path1)
    ds2 = xr.open_dataset(path2)

    all_ok = True

    # --- Global attributes ---
    print("=== Global attributes ===")
    if compare_attrs(ds1.attrs, ds2.attrs, "global"):
        print("✅ Global attributes match")
    else:
        all_ok = False

    # --- Dimensions ---
    print("\n=== Dimensions ===")
    dims1 = dict(ds1.dims)
    dims2 = dict(ds2.dims)

    print("First dims :", dims1)
    print("Second dims:", dims2)

    if dims1 != dims2:
        all_ok = False
        # Detailed diff
        keys1 = set(dims1.keys())
        keys2 = set(dims2.keys())
        only1 = keys1 - keys2
        only2 = keys2 - keys1
        if only1:
            print("Dims only in first :", sorted(only1))
        if only2:
            print("Dims only in second:", sorted(only2))
        for k in keys1 & keys2:
            if dims1[k] != dims2[k]:
                print(f"Dim size differs for {k}: {dims1[k]} vs {dims2[k]}")
    else:
        print("✅ Dimensions match exactly")

    # --- Variables ---
    print("\n=== Variables ===")
    vars1 = set(ds1.variables.keys())
    vars2 = set(ds2.variables.keys())

    print("First vars :", sorted(vars1))
    print("Second vars:", sorted(vars2))

    only1 = vars1 - vars2
    only2 = vars2 - vars1
    if only1:
        print("Vars only in first :", sorted(only1))
        all_ok = False
    if only2:
        print("Vars only in second:", sorted(only2))
        all_ok = False

    common_vars = sorted(vars1 & vars2)

    # --- Per-variable comparison ---
    for name in common_vars:
        v1 = ds1[name]
        v2 = ds2[name]

        print(f"\n--- Variable: {name} ---")

        # dtype
        if v1.dtype != v2.dtype:
            print(f"[TYPE] {name}: {v1.dtype} vs {v2.dtype}")
            all_ok = False
        else:
            print(f"Type: {v1.dtype}")

        # shape
        if v1.shape != v2.shape:
            print(f"[SHAPE] {name}: {v1.shape} vs {v2.shape}")
            all_ok = False
        else:
            print(f"Shape: {v1.shape}")

        # attributes
        if compare_attrs(v1.attrs, v2.attrs, f"var:{name}"):
            print("Attr: ✅")
        else:
            all_ok = False

        # data comparison (careful with huge variables)
        try:
            arr1 = v1.values  # loads to memory
            arr2 = v2.values

            # Decide numeric vs non-numeric
            if np.issubdtype(arr1.dtype, np.number) and np.issubdtype(arr2.dtype, np.number):
                equal = np.allclose(arr1, arr2, rtol=TOL, atol=TOL, equal_nan=True)
            else:
                equal = np.array_equal(arr1, arr2)

            if equal:
                print("Data: ✅ (within tolerance)")
            else:
                all_ok = False
                # Optional diagnostics
                if np.issubdtype(arr1.dtype, np.number) and np.issubdtype(arr2.dtype, np.number):
                    diff = np.nanmax(np.abs(arr1 - arr2))
                    print(f"Data: ❌ differ (max abs diff = {diff})")
                else:
                    print("Data: ❌ differ (non-numeric)")
        except MemoryError:
            all_ok = False
            print("Data: ⚠️ too large to load completely (MemoryError) – consider chunked comparison")

    ds1.close()
    ds2.close()

    print("\n=== SUMMARY ===")
    if all_ok:
        print("🎉 All checked dimensions, attributes and variable data match (within tolerance).")
        return 0
    else:
        print("⚠ Some differences were found. Check details above.")
        return 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python compare_netcdf.py <netcdf4_file> <netcdf3_file>")
        sys.exit(1)
    sys.exit(main(sys.argv[1], sys.argv[2]))
