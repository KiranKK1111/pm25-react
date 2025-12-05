import xarray as xr
import os

src_folder = "./NetCDF4_emi_PM2.5"      # folder with original 50 NetCDF-4 files
dst_folder = "./NetCDF3_emi_PM2.5"     # output folder for NetCDF-3 files
os.makedirs(dst_folder, exist_ok=True)

for file in os.listdir(src_folder):
    if file.endswith(".nc"):
        src_path = os.path.join(src_folder, file)
        dst_path = os.path.join(dst_folder, file.replace(".nc", "_nc3.nc"))

        print("Converting:", file)
        ds = xr.open_dataset(src_path)
        ds.to_netcdf(dst_path, format="NETCDF3_CLASSIC")

print("All conversions done!")
