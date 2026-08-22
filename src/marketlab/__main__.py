"""CLI entrypoint: ``python -m marketlab`` prints build info (smoke check)."""

from marketlab import __version__


def main() -> None:
    print(f"MarketLab v{__version__}")


if __name__ == "__main__":
    main()
