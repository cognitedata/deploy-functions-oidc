import argparse
import json
import os
import subprocess
import sys

from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Upload Python code to Functions in CDF")
    parser.add_argument(
        "folders",
        type=str,
        nargs=1,
        help="The folders to monitor for deployment to cognite functions",
    )
    parser.add_argument("deploy_all", type=str, nargs="?", help="The folders to deploy to all ", default=None)
    return parser.parse_args()


def main():
    print(sys.argv)
    args = parse_args()
    print(f"Got function folders: {args.folders!r}")
    print(f"And deploy all folders: {args.deploy_all!r}")
    function_folders = {f.strip() for f in args.folders[0].split(",")}
    deploy_all_folders = set()
    if args.deploy_all:
        deploy_all_folders = {f.strip() for f in args.deploy_all.split(",")}

    changed_folders = subprocess.check_output("git diff --name-only HEAD^ HEAD".split(), text=True).split()
    changed_folders = {
        "/".join(parts if clean.name != "schedules" else parts.parts)
        for f in changed_folders
        if (clean := Path(f).parent) and clean.exists() and (parts := clean.parts)
    }
    print(f"Detected changed folders: {sorted(changed_folders)}")
    deploy = []
    for changed_folder in changed_folders:
        if any(changed_folder.startswith(deploy_all) for deploy_all in deploy_all_folders):
            deploy = list(function_folders)
            break
        if changed_folder in function_folders:
            deploy.append(changed_folder)

    if not deploy:
        deploy = ["skipDeploy"]

    json_format = json.dumps({"folders": deploy})

    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        print(f"matrix={json_format}", file=fh)
        print(f"folders={str(deploy)}", file=fh)


if __name__ == "__main__":
    main()
