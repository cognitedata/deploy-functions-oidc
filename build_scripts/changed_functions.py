import argparse
import json
import os
import subprocess

from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Upload PDFs to CDF")
    parser.add_argument(
        "folders",
        type=str,
        nargs=1,
        help="The folders to monitor for deployment to cognite functions",
    )
    parser.add_argument("deploy_all", type=str, nargs="?", help="The folders to deploy to all ", default=None)
    return parser.parse_args()


def main():
    args = parse_args()
    print(f"Got function folders: {args.folders!r}")  # noqa
    print(f"And deploy all folders: {args.deploy_all!r}")  # noqa
    function_folders = {f.strip() for f in args.folders[0].split(",")}
    deploy_all_folders = (args.deploy_all or {}) and {f.strip() for f in args.deploy_all.split(",")}

    process = subprocess.Popen("git diff --name-only HEAD^ HEAD".split(" "), stdout=subprocess.PIPE)  # nosec
    changed_folders, _ = process.communicate()
    changed_folders = list(
        {
            "/".join(clean.parts if clean.name != "schedules" else clean.parts.parts)
            for f in changed_folders.decode().split("\n")
            if (clean := Path(f).parent) and clean.exists()
        }
    )
    print(f"Detected changed folders: {changed_folders}")  # noqa
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
        print(f"matrix={json_format}", file=fh)  # noqa
        print(f"folders={str(deploy)}", file=fh)  # noqa


if __name__ == "__main__":
    main()
