import argparse


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out_dir", type=str, default="results/")
    parser.add_argument("--tta_runs", type=int, default=3)
    parser.add_argument("--tta", action="store_true", dest="tta")
    parser.add_argument("--notta", action="store_false", dest="tta")
    parser.set_defaults(tta=True)
    return parser.parse_args()
