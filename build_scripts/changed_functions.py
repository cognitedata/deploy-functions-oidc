import argparse
import json
import os
import shlex
import subprocess

from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Upload Python code to Functions in CDF")
    parser.add_argument(
        "folders",
        type=str,
        nargs=1,
        help="The folders to monitor for deployment to cognite functions",
    )
    parser.add_argument("deploy_all", type=str, nargs="?", help="The folders to deploy to all", default=None)
    return parser.parse_args()


def main():
    args = parse_args()
    function_folders = sorted({f.strip() for f in args.folders[0].split(",")})
    print(f"Input: Function folders to consider (re)deploying: {function_folders}")

    deploy_all_folder = None
    if args.deploy_all:
        deploy_all_folder = args.deploy_all.strip()
        print(f"Input: Common folder (may force deploy all): {deploy_all_folder!r}")

    # Compare against previous commit under the assumption of squash-only merges:
    diff = subprocess.check_output(shlex.split("git diff --name-only HEAD^ HEAD"), text=True).split()
    changed_files = set(map(Path, diff))

    deploy_all = False
    if deploy_all_folder is not None:
        deploy_all = any(f.is_relative_to(deploy_all_folder) for f in changed_files)

    if deploy_all:
        to_deploy = function_folders
        print("Common folder has one or more changed file(s), will deploy all functions")
    else:
        to_deploy = [fld for fld in function_folders if any(f.is_relative_to(fld) for f in changed_files)]

    if to_deploy:
        print(f"To be deployed: {to_deploy}")
    else:
        print("No changed folders detected, skipping deployment!")
        to_deploy = ["skipDeploy"]

    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        print(f"matrix={json.dumps({'folders': to_deploy})}", file=fh)
        print(f"folders={to_deploy}", file=fh)


if __name__ == "__main__":
    main()
