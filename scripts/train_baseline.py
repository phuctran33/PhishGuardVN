"""Run week-4 baselines; official test is never scored."""
from pathlib import Path
import argparse
import sys
import tomllib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from phishguard_vn.modeling import load_baseline_inputs, run_baseline
from phishguard_vn.paths import get_project_root
from phishguard_vn.reporting import save_results

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=None)
    args=parser.parse_args()
    root=get_project_root()
    config_path=args.config.resolve() if args.config else root/"configs/baseline.toml"
    # Config is kept inside the repo so it can be hashed with the source.
    if not config_path.is_relative_to(root):
        raise ValueError("Config must be inside this project checkout.")
    with config_path.open("rb") as handle:config=tomllib.load(handle)
    features,targets,folds=load_baseline_inputs(root)
    result=run_baseline(features,targets,folds,config)
    artifact=save_results(result,config,root,config_path)
    print(result["cv_summary"].to_string(index=False))
    print("Selected:",result["selected_model"])
    print("Validation is supplementary; official test was not scored.")
    print("Artifact:",artifact)

if __name__=="__main__":
    main()
