from pydap.client import open_url
import numpy as np


OPENDAP_URL = (
    "https://psl.noaa.gov/thredds/dodsC/"
    "Datasets/noaa.oisst.v2.highres/"
    "sst.day.mean.2026.nc"
)


def main():

    print("Opening NOAA OPeNDAP...")

    dataset = open_url(OPENDAP_URL)

    print("Connected successfully.")

    # ---------------------------------------------------------
    # 1. Dataset dimensions
    # ---------------------------------------------------------

    time = dataset["time"]
    lat = dataset["lat"]
    lon = dataset["lon"]

    print("\nDataset dimensions")
    print("------------------")
    print("Time:", len(time))
    print("Latitude:", len(lat))
    print("Longitude:", len(lon))

    # ---------------------------------------------------------
    # 2. Get latest time index
    # ---------------------------------------------------------

    latest_index = len(time) - 1

    print("\nLatest time index:", latest_index)

    # ---------------------------------------------------------
    # 3. Retrieve latest time
    # ---------------------------------------------------------

    latest_time = np.asarray(
        time[latest_index]
    ).item()

    print("Latest time raw value:", latest_time)

    # ---------------------------------------------------------
    # 4. Retrieve coordinates
    # ---------------------------------------------------------

    lat_values = np.asarray(lat[:])
    lon_values = np.asarray(lon[:])

    print("\nLatitude")
    print("--------")
    print("Shape:", lat_values.shape)
    print("First:", lat_values[0])
    print("Last:", lat_values[-1])

    print("\nLongitude")
    print("---------")
    print("Shape:", lon_values.shape)
    print("First:", lon_values[0])
    print("Last:", lon_values[-1])

    # ---------------------------------------------------------
    # 5. Retrieve ONLY latest SST
    # ---------------------------------------------------------

    print("\nRequesting latest SST grid...")
    print("This may take a little time...")

    sst = dataset["sst"][
        latest_index,
        :,
        :
    ]

    sst_values = np.asarray(sst)

    print("\nSST successfully retrieved!")
    print("--------------------------")

    print("Shape:", sst_values.shape)
    print("dtype:", sst_values.dtype)

    # ---------------------------------------------------------
    # 6. Convert invalid values to NaN
    # ---------------------------------------------------------

    sst_values = sst_values.astype(np.float32)

    valid = (
        np.isfinite(sst_values)
        & (sst_values >= -3)
        & (sst_values <= 45)
    )

    valid_values = sst_values[valid]

    print("\nSST statistics")
    print("--------------")

    print("Valid points:", valid_values.size)

    if valid_values.size > 0:

        print(
            "Minimum:",
            float(valid_values.min())
        )

        print(
            "Maximum:",
            float(valid_values.max())
        )

        print(
            "Mean:",
            float(valid_values.mean())
        )

    print("\nSUCCESS:")
    print("Real NOAA SST data retrieved through OPeNDAP.")


if __name__ == "__main__":
    main()