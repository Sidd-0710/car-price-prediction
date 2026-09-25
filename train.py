"""Train the car price model.

    python train.py            # full run: compare 9 algorithms, tune the best
    python train.py --quick    # skip tuning (fast check)

Everything lives in the `carprice` package; this file is just the entry point.
"""

import argparse
import warnings

import matplotlib

matplotlib.use("Agg")  # draw the report figures to files; no windows needed

from carprice.training import run  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--quick", action="store_true", help="skip hyper-parameter tuning")
    arguments = parser.parse_args()
    warnings.filterwarnings("ignore", category=UserWarning)
    run(quick=arguments.quick)
