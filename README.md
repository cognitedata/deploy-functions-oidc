## Cognite function template
[![Deploy Function to CDF project using OIDC](https://github.com/cognitedata/deploy-functions-oidc/actions/workflows/deploy-push-master.yaml/badge.svg)](https://github.com/cognitedata/deploy-functions-oidc/actions/workflows/deploy-push-master.yaml)

### NB: Due to how we have to deploy code, [running locally](https://github.com/cognitedata/deploy-functions-oidc#run-code-locally) requires an extra step. Please read it!

This repository can be used as a template on how to use and deploy code/models to Cognite Functions within a CI/CD pipeline using OIDC. It uses different GitHub workflows with the key component being the GitHub action [function-action-oidc](https://github.com/cognitedata/function-action-oidc).

 # Prerequisites
As of September 8, 2021 these are the required steps to use Cognite Functions with OIDC (hereinafter referred to as *Functions*):
1. The CDF project you will deploy functions to needs to be setup for OIDC authentication! For the foreseeable future, we assume the identity provider (IdP) will be Azure Active Directory (AAD).
1. In the most likely scenario you do not have access to this, so you need to request the following from the customer's IT department. (If you do have access, either through a personal test project or for some other reason, you can create them yourself!)
    - 1 app registration for the deployment service principal
    - **[optional]** If you need your functions to be run on schedule(s): 1 additional app registration for the schedules service principal
    - Create a client secret for both, then store them immediately in LastPass or similar together with the corresponding client ID for the app registration. You'll find that under Overview / Application (client) ID.
    - The deployment service principal must be added as a member to an existing (or create a new) ADD security group that is then linked to a CDF group with capabilities necessary for functions deployment. The way you link these is by copying the `Object ID` of the ADD group and using that as the `Source ID` for the CDF group. The latest updated deployment requirements can be found on [Confluence / Cognite Functions](https://cognitedata.atlassian.net/wiki/spaces/MLOP/pages/1963098642/Cognite+Functions), but **typically require the following**:
        - `Functions:WRITE` and `Functions:READ` in `scope: all`
        - `Files:READ` and `Files:WRITE` in `scope: all` OR scoped to a data set (recommended, but then you also need dataset capabilities like `Datasets:READ` - and if it is write protected, `Datasets:OWNER` as well!)
        - `Projects:LIST` in `scope: all`
        - `Groups:LIST` in `scope: all` OR scoped to "current user" (i.e. list its own groups)
    - The schedule service principal needs a *special capability*:
        - `Sessions:CREATE` in `scope: all`
        - And all other capabilites needed to run the function
        - ...but **don't worry** too much about making sure all of these are 100 % correct: the action used by this template, namely the `function-action-oidc`, will list all missing capabilities for you! 🙌
1. Get Functions whitelisted for your project, *if it is not already*.
   * How? Patch [this file](https://github.com/cognitedata/context-api/blob/master/src/utils/functions_whitelist.py) with the name of the CDF project. Make sure that you add it to the list for the *correct cluster*, e.g.:
        1. `https://api.cognitedata.com`
        2. `https://greenfield.cognitedata.com`
        3. `https://statnett.cognitedata.com`
        6. etc.
1. Check if your project is listed by going to https://unleash-apps.cognite.ai/#/features. Click on `ML_OPS_cognite_functions`
   * If your project is NOT listed, add the name of your project and hit update.

# Structure of this repository

## Functions

Here you can find two simple functions implemented: `example_function1` and `example_function2`.

The first function, `example_function1`, implements a basic echo capability and prints and sends back any content it receives.
The second, `example_function2` implements an "A+B problem" solver and has expectations for the `data` it receives,
which then might raise an exception.

Generally a function, named `my_cognite_function` in the example below, consists of the following files:
```
📦my_cognite_function
 ┣ 📂schedules
 ┃ ┗ 📜master.yaml - (Optional) Schedule if you want to execute the function on a schedule.
 ┣ 📜__init__.py - Empty file (required to make the function into a package)
 ┣ 📜function_config.yaml - Configuration for the function
 ┣ 📜handler.py - Module with script inside a handle function
 ┗ 📜requirements.txt - Explicitly states the dependencies needed to run the handler.py script.
```

<details>
<summary><code>schedules/master.yaml</code></summary>

Each function's folder contains a `schedules` folder where you can put your files that define your
schedules. By default, we have added a file here called `master.yaml` which will be used whenever
you merge a PR to `master` (read more in the "deployment" section). If you don't need any schedules
for a specific function, just delete it!

Example
```yaml
- name: My daily schedule
  cron: "0 0 * * *"
  data:
    lovely-parameter: True
    greeting: "World"
```

</details>

<details>
<summary><code>function_config.yaml</code></summary>

Each function's folder contains a `function_config.yaml` file where you can specify most
configuration parameters (per function). These parameters are extracted and used by the Github
Workflow files during deployment (read more in the "build and deployment" section).

Example template, see [function details](https://github.com/cognitedata/function-action-oidc#function-metadata-in-github-workflow) for description of all configuration parameters.

```yaml
description: "Analysis performed by my_cognite_function"
owner: data.liberator@cognite.com
```

</details>


<details>
<summary><code>handler.py</code></summary>

Example below, for a full description of the arguments that can be passed to this function see
[cognite-experimental-sdk](https://cognite-sdk-experimental.readthedocs-hosted.com/en/latest/cognite.html#create-function).

```python
def handle(data, client, secrets, function_call_info):
    print(f"Hello from {__name__}!")
    print("I got the following data:")
    print(data)
    print("Will now return data")
    return data
```

</details>

<details>
<summary><code>requirements.txt</code></summary>

Each function's folder contains `requirements.txt`. You can use that file to add extra dependencies
that your code is depending on. By default, you have a newer version of `cognite-sdk` installed,
but it doesn't hurt to be specific here!

Example ``requirements.txt`` file

```text
cognite-sdk==2.38.2
function/my_private_package-1.3.1-py3-none-any.whl
python-dotenv==0.19.2
```

**Private Dependencies**: You can include private packages (dependencies which are not published
to PyPi.org) by building and adding the wheel to the function folder. You can build a wheel
by running the following command inside your private package root directory

```
poetry build
```

This builds a wheel and source for your private package inside a ``dist`` directory. Copy the
``*.whl`` and put it inside your function folder.

Finally, you specify the dependency as shown above ``function/my_private_package-1.3.1-py3-none-any.whl``.
Note that ``function/`` is **not** a placeholder. For more information about wheels see
[What Are Python Wheels and Why Should You Care?](https://realpython.com/python-wheels/)



**Caveat**: If you create the ``requirements.txt`` by using poetry, you must set the option
``--without-hashes`` as Azure does not support hashes in the ``requirements.txt`` file.

```bash
poetry export -f requirements.txt --output requirements.txt --without-hashes
```

</details>


## Tests

You can find the corresponding folder in `tests`, tagged with `unit` for each function.
Unit tests are supposed to validate the behaviour of your `handle` function, without the need for actual deployment. Good coverage of tests will speed up your deployment and ensure that your logic behaves as expected if someone decides to make any change.

* Each test folder for function contains `conftest.py` with predefined fixtures and helpers to accelerate your test development.
* Each test folder may have an infinite number of files with tests. You can separate all tests into different files based on your favourite classification
* When you create a PR, by default, each function runs its corresponding unit-tests *and* any tests in the common/shared folder.

### Run tests locally
To run all unit tests for the function `example_function2` locally, execute the following command in your terminal:
```
$ PYTHONPATH=example_function2 poetry run pytest tests/example_function2 -m "unit"
```

## Run code locally
To run code locally, you may create a `run_locally.py` file to handle the creation of the Cognite client (and potentially `data`/`secrets` etc.) before passing that/those into your `handle` function that you simply import (like any other function). You (probably) also need to set the `PYTHONPATH` environment variable to the root directory you are running from (this is mostly to make sure the `common_folder` works as expected!):
```
$ PYTHONPATH=. poetry run python example_function2/run_locally.py
```

## Code quality and style check

This template uses a list of style checks you will need to pass to merge your PRs to any branch. These checks help keep code clean and make sure it looks the same across Cognite repositories.

### Run all checks locally
To run all checks locally - which is typically needed if the GitHub check is failing - e.g. you haven't set up `pre-commit` to run automatically:
```sh
$ poetry run pre-commit install  # Only needed if not installed
$ poetry run pre-commit run --all-files
```

## Build and deployment

The template uses GitHub Actions to perform Code quality and Deployment operations. All workflows are located in the [.github/workflows](https://github.com/cognitedata/deploy-functions-oidc/tree/master/.github/workflows) folder.
* `code-quality.yaml` Runs all code-quality checks and ensures the style, linting, basic static analysis
* `deploy-push-master.yaml` Responsible for you PR deployment to customer environment(s)
* `deploy-pr.yaml` Responsible for running tests / verification on Pull Requests

Each workflow consists of a series of sequentially executed steps. As an input to the workflows, you will need to provide parameters per each function in `function_config.yaml`.

**Note**: If the `deploy-push-master.yaml` workflow fails after you have merged to `master`, you can check out the tab `Actions` in GitHub, where you will it. Here you can drill down to find the cause - and if it is unrelated to your code changes, simply do a re-run.

## Secrets

**All client secrets *must* be stored as GitHub secrets.**
All secrets could be classified into two orthogonal groups: by branch (deploying to different CDF projects) and by role (deploy or schedules):
* `DEPLOY_MASTER` should contain the client secret for the service account used to deploy Functions on merges to the `master` branch.
* `SCHEDULES_MASTER` should contain the client secret for the service account used at runtime when running on a schedule.
* **Super-pro-tip:** You can create similar `[DEPLOY|SCHEDULES]_{other-branch}` secrets to support more than one target CDF project!

Adding extra secrets to specific functions:
* In order to make secrets available to a specific function (and branch, say *master*), you need to add it as a Github Secret in your repository with a *very* specific name:
```
SECRETS_{ your function name }_{ your branch name }
```
Example, for function folder `example_function2` to branch `master`:
```
SECRETS_EXAMPLE_FUNCTION2_MASTER
```
These additional secrets require a bit of special care. You must follow these steps precisely:
[Link to secrets README](https://github.com/cognitedata/function-action-oidc#function-secrets)

### Why is this secret stuff so complicated?
The short answer is: because GitHub asks us to:
> To help ensure that GitHub redacts your secret in logs, avoid using structured data as the values of secrets. For example, avoid creating secrets that contain JSON or encoded Git blobs.
https://docs.github.com/en/actions/reference/encrypted-secrets

## Continuous Deployment

Some customers may require you to have more than a single project. Often we have two: `development` and `production`, some customers have up to 4: `dev`, `test`, `pre-prod`, `prod`.
In order to support that, we need to have a process with formal gatekeepers and approvals. GitHub doesn't support tag protection but has branch protection mechanisms with PRs as gatekeeping. For that purpose, `deploy-push-master.yaml` has a specific branch that triggers the action (this can actually be a list, but please create another workflow file for that!). In addition to that your function' name receives branch name as a suffix, so you can deploy them separately.

If you want to support more than one deployment (by default we only deploy and keep the content of `master` branch) you need the following:
1. Create a new separate workflow file for the new environment and name it accordingly, i.e. `deploy-push-prod.yaml` if it should run on merges to the `prod` branch. You then need to modify it so that all occurrences of `master` are changed to `prod`.
1. For each function, in the `schedules` directory, create a yaml file matching the branch name, i.e. `prod` as in this example.
   * If the branch name has underscores like `pre_prod`, the file should be named `pre-prod.yaml`
1. Create 1 (or 2 if using schedules) additional client secret(s) for each new environment. For example, you are adding `pre_prod`, then you need to add: `DEPLOY_PRE_PROD` and `SCHEDULES_PRE_PROD`.

# How to use it
## Create a repository with this template
First, click the green ["Use this template"](https://github.com/cognitedata/deploy-functions-oidc/generate) button to create a repository from this template.

## [optional] Access
Secondly, go to "Settings", "Manage access" and add `forge` team to Administrators, so we can help you faster with fewer questions.

## Getting started
1. Open your terminal and navigate to your newly cloned repo.
1. Run `poetry install`
1. Run `poetry run pre-commit install`

## Modify the template

* You *must* rename the function folders, i.e. `example_function1` to better describe what it will be doing/solving. These function folders end up as part of the function `external ID`, so please *don't hold back to avoid name conflicts*.
* Do whatever changes you want to do in the functions folders. You can create as many functions as you want in one repository.
* Remember to update `function_config.yaml` with relevant parameters per function, for example `owner` or `description`, or maybe `cpu` and `memory` if you need more (or less) power!
* Go into `Settings` in your repository to create the secrets. You need the client secrets you created as part of the prerequisites. Add them!

Once you have modified the functions and added secrets, modify the files in `.github/workflows`. These are the things you will have to modify:
* List of functions
  * Only the function folders listed in the workflow file(s) will be deployed. You therefore must keep it updated with any changes to the folder names.

For more details on how to set up your workflows to deploy to Cognite Functions, please see the [function-action-oidc](https://github.com/cognitedata/function-action-oidc) repository.

# I have a question

There will be questions. Crowdsourcing is required. Use issues, or if you are an internal Cognite employee, you can also hit us up on slack on #help-inso-tech-community
