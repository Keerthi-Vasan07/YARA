from data_sources.noaa_oisst import NOAAOISSTSource


def main():

    source = NOAAOISSTSource()

    print("Testing YARA NOAA OISST DataSource")
    print("=" * 50)

    print("\nChecking availability...")

    available = source.is_available()

    print("Available:", available)

    if not available:
        print("\nNOAA OPeNDAP is not reachable.")
        return

    print("\nReading metadata...")

    metadata = source.get_metadata()

    print("\nSource:")
    print(metadata["source"])

    print("Protocol:")
    print(metadata["protocol"])

    print("Variable:")
    print(metadata["variable"])

    print("Dimensions:")
    print(metadata["dimensions"])

    print("Latitude:")
    print(metadata["coordinates"]["latitude"])

    print("Longitude:")
    print(metadata["coordinates"]["longitude"])

    print("\nRetrieving latest SST...")

    latest = source.get_latest()

    print("\nLatest SST retrieved!")

    print("Time index:", latest["time_index"])
    print("Time:", latest["time"])

    print("Shape:", latest["shape"])
    print("Units:", latest["units"])

    print("\nStatistics:")

    for key, value in latest["statistics"].items():
        print(f"  {key}: {value}")

    print("\nSUCCESS")
    print("YARA DataSource → NOAA OPeNDAP → Real SST")


if __name__ == "__main__":
    main()
