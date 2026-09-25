"""Step 1: build data/used_cars_india.csv from the four public sources.

    python build_dataset.py
"""

from carprice.sources import main

if __name__ == "__main__":
    main()
