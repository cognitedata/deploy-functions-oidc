## Cognite function template
![Deploy function](https://github.com/cognitedata/deploy-functions/workflows/Deploy%20function/badge.svg)

This repository can be used as a template on how to use and deploy code/models to Cognite Functions within a CI/CD pipeline using OIDC. It uses different GitHub workflows with the key component being the GitHub action [function-action-oidc](https://github.com/cognitedata/function-action-oidc).

 # Prerequisites
As of September 8, 2021 these are the required steps to use Cognite Functions with OIDC (hereinafter referred to as *Functions*):
1. The CDF project you will deploy functions to needs to be setup for OIDC authentication! For the forseeable future, we assume the identity provider (IdP) will be Azure Active Directory (AAD).
1. In the most likely scenario you do not have access to this, so you need to request the following from the customer's IT department. (If you do have access, either through a personal test project or for some other reason, you can create them yourself!)
    - 1 app registration for the deployment service principal
    - **[optional]** If you need your functions to be run on schedule(s): 1 additional app registration for the schedules service principal
    - Create a client secret for both, then store them immediately in LastPass or similar together with the corresponding client ID for the app registration. You'll find that under Overview / Application (client) ID.
    - The deployment service principal must be added as a member to an existing (or create a new) ADD security group that is then linked to a CDF group with capabilites necessary for functions deployment. The way you link these is by copying the `Object ID` of the ADD group and using that as the `Source ID` for the CDF group. The latest updated deployment requirements can be found on [Confluence / Cognite Functions](https://cognitedata.atlassian.net/wiki/spaces/MLOP/pages/1963098642/Cognite+Functions), but **typically require the following**:
        - `Functions:WRITE` and `Functions:READ` in `scope: all`
        - `Files:READ` and `Files:WRITE` in `scope: all` OR scoped to a data set (recommended, but then you also need dataset capabilities like `Datasets:READ` - and if it is write protected, `Datasets:OWNER` as well!)
        - `Projects:LIST` in `scope: all`
        - `Groups:LIST` in `scope: all` OR scoped to "current user" (i.e. list its own groups)
    - And a *special capability* for the group that your sessions service principal is part of:
        - `Sessions:CREATE` in `scope: all`
        - ...but **don't worry** too much about making sure all of these are 100 % correct: the action used by this template, namely the `function-action-oidc`, will list all missing capabilities for you! 🙌
1. Get Functions whitelisted for your project, *if it is not already*.
   * How? Patch [this file](https://github.com/cognitedata/context-api/blob/master/src/api/functions/whitelist.py) with the name of the CDF project. Make sure that you add it to the list for the *correct cluster*, e.g.:
        1. `https://api.cognitedata.com`
        2. `https://greenfield.cognitedata.com`
        3. `https://statnett.cognitedata.com`
        6. etc.
1. Check if your project is listed by going to https://unleash-apps.cognite.ai/#/features. Click on `ML_OPS_cognite_functions`
   * If your project is NOT listed, add the name of your project and hit update.

# Structure of this repository

## Functions

Here you can find three simple functions implemented: `example_function1`, `example_function2` and `example_with_logging`.

The first function, `example_function1`, implements a basic echo capability and prints and sends back any content it receives. The second, `example_function2` implements an "A+B problem" solver and has expectations for the `data` it receives, which then might raise an exception. The last example just shows how you can use the `logging` module in Python without causing problems with Functions.

* Each function' folder contains `requirements.txt`. You can use that file to add extra dependencies that your code is depending on. By default you have a newer version of `cognite-sdk` installed, but it doesnt hurt to be specific here!
* Each function's folder contains a `schedules` folder where you can put your files that define your schedules. By default we have added a file here called `master.yaml` which will be used whenever you merge a PR to `master` (read more in the "deployment" section). If you don't need any schedules for a specific function, just delete it!
* Each function's folder contains a `function_config.yaml` file where you can specify most configuration parameters (per function). These parameters are extracted and used by the Github Workflow files during deployment (read more in the "build and deployment" section).

## Tests

You can find the corresponding folder in `tests`, tagget with `unit` for each function.
Unit tests are supposed to validate the behavior of your `handle` function, without the need for actual deployment. Good coverage of tests will speed up your deployment and ensure that your logic behaves as expected if someone decides to make any change.

* Each test folder for function contains `conftest.py` with predefined fixtures and helpers to accelerate your test development.
* Each test folder may have an infinite number of files with tests. You can separate all tests into different files based on your favorite classification
* When you create a PR, by default, each function runs its correspondig unit-tests *and* any tests in the common/shared folder.

### Run tests locally
To run all unit tests for the function `example_function2` locally, execute the following command in your terminal:
```
$ PYTHONPATH=example_function2 poetry run pytest tests/example_function2 -m "unit"
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

The template uses GitHub Actions to perform Code quality and Deployment operations. All workflows are located in the [.github/workflows](https://github.com/cognitedata/deploy-functions/tree/master/.github/workflows) folder.
* `code-quality.yaml` Runs all code-quality checks and ensures the style, linting, basic static analysis
* `deploy-push-master.yaml` Responsible for you PR deployment to customer environment(s)
* `deploy-pr.yaml` Responsible for running tests / verification on Pull Requests

Each workflow consists of a series of sequentially executed steps. As an input to the workflows, you will need to provide parameters per each function in `function_config.yaml`.

**Note**: If the `deploy-push-master.yaml` workflow fails after you have merged to `master`, you can check out the tab `Actions` in GitHub, where you will it. Here you can drill down to find the cause - and if it is unrelated to your code changes, simply do a re-run.

## Secrets

**All client secrets *must* be stored as GitHub secrets.**
All secrets could be classified into two orthogonal groups: by branch (deploying to different CDF projects) and by role (deploy or schedules):
* `DEPLOY_MASTER` should contain the client secret for the service account that doing deployments on merges to the `master` branch.
* `SCHEDULES_MASTER` should contain the client secret for the service account that will be used at runtime of the function when running on a schedule.
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
[Link to secrets README](https://github.com/cognitedata/function-action#function-secrets)


## Continuous Deployment

Some customers may require you to have more than a single project. Often we have two: `development` and `production`, some customers have up to 4: `dev`, `test`, `pre-prod`, `prod`.
In order to support that we need to have a process with formal gatekeepers and approvals. GitHub doesn't support tag protection but has a branch protection mechanisms with PRs as gatekeeping. For that purpose, `deploy-push-master.yaml` has a list of branches it triggers the action. In addition to that your function' name receives branch name as a suffix, so you can deploy them separately.

If you want to support more than one deployment (by default we only deploy and keep the content of `master` branch) you need the following:
1. Create a new separate workflow file for the new environment and name it accordingly, i.e. `deploy-push-prod.yaml` if it should run on merges to the `prod` branch. You then need to modify it so that all occurences of `master` is changed to `prod`.
1. For each function, in the `schedules` directory create yaml file matching the branch name, i.e. `prod` as in this example.
   * If the branch name has underscores like `pre_prod`, the file should be named `pre-prod.yaml`
1. Create 1 (or 2 if using schedules) additional client secret(s) for each new environment. For example, you are adding `pre_prod`, then you need to add: `DEPLOY_PRE_PROD` and `SCHEDULES_PRE_PROD`.

# How to use it
## Create a repository with this template
First, click the green ["Use this template"](https://github.com/cognitedata/deploy-functions/generate) button to create a repository from this template.

## Access
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

There will be questions. Crowdsourcing is required.

**Going to #help-forge on Slack is a good place to start!**