import xarray as xr
import numpy as np
import sys

TOL = 1e-6  # numeric tolerance

def compare_variable(ds1, ds2, varname):
    if varname not in ds1.variables:
        print(f"❌ Variable '{varname}' not found in first dataset")
        return False
    if varname not in ds2.variables:
        print(f"❌ Variable '{varname}' not found in second dataset")
        return False

    v1 = ds1[varname]
    v2 = ds2[varname]

    print(f"Comparing variable: {varname}")

    # --- Shape ---
    print("Shape 1:", v1.shape)
    print("Shape 2:", v2.shape)
    if v1.shape != v2.shape:
        print("❌ Shape mismatch")
        return False
    print("✅ Shape matches")

    # --- Type ---
    print("Type 1:", v1.dtype)
    print("Type 2:", v2.dtype)
    if v1.dtype != v2.dtype:
        print("❌ Data type mismatch")
        return False
    print("✅ Data type matches")

    # --- Attributes ---
    print("Attributes 1:", v1.attrs)
    print("Attributes 2:", v2.attrs)
    if v1.attrs != v2.attrs:
        print("⚠️ Attribute mismatch")
    else:
        print("✅ Attributes match")

    # --- Data Comparison ---
    arr1 = v1.values
    arr2 = v2.values

    if np.issubdtype(arr1.dtype, np.number):
        equal = np.allclose(arr1, arr2, rtol=TOL, atol=TOL, equal_nan=True)
    else:
        equal = np.array_equal(arr1, arr2)

    if equal:
        print("🎉 Data matches (within tolerance)")
        return True
    else:
        diff = np.nanmax(np.abs(arr1 - arr2)) if np.issubdtype(arr1.dtype, np.number) else "non-numeric"
        print(f"❌ Data differs (max diff = {diff})")
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python compare_substance.py <file1.nc> <file2.nc>")
        sys.exit(1)

    file1, file2 = sys.argv[1], sys.argv[2]
    ds1 = xr.open_dataset(file1)
    ds2 = xr.open_dataset(file2)

    compare_variable(ds1, ds2, "substance")

    ds1.close()
    ds2.close()
