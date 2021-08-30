# NOT UPDATED TO OIDC, YET!
# Cognite function template
![Deploy function](https://github.com/cognitedata/deploy-functions/workflows/Deploy%20function/badge.svg)

This repository can be used as a template on how to use and deploy code/models to Cognite Functions within a CI/CD pipeline. It uses different GitHub workflows with the key component being the GitHub action [function-action](https://github.com/cognitedata/function-action).

 ## Video tutorials
 For your utmost convenience, tutorial videos have been made as an alternative to the readme-steps below. They can be found here: [confluence/forge](https://cognitedata.atlassian.net/wiki/spaces/FORGE/pages/2248016119/Deploy+Functions+Template+Tutorials). Note that these are *slightly outdated*, as they were made for a more comprehensive earlier version of this template.


 # Prerequisites

As of March 27th, 2021 these are the required steps to use Cognite Functions (hereinafter referred to as Functions):
1. Get your CDF project, aka tenant, on which you want to run Functions.
1. Create service accounts and give them the correct permissions via https://fusion.cognite.com/:
      * Under "Manage and Configure" click on "Manage Access"
      * Under "Groups," if the `functions-deployment` group does not exist, either:
         * **[Scope: all]** Add `functions-deployment` group with the following capabilities: `Files:WRITE`, `Files:READ`, `Functions:WRITE`, `Functions:READ`
         * **[Scope: data set]** Do as above, but for `Files:WRITE` and `Files:READ`, choose "Data Sets" instead of "All" under Scope, and then select the data set you want your function deployment to be governed by (covers the code file only). You also need to add `Datasets:READ` for the same data set! **Note:** If you are going to use a write protected data set, additionally adding `Datasets:OWNER` *is required*.
      * Click "Create"
      * Go to "Service accounts"
      * Click on "Create new service accounts"
      * Create `<your-project>-github-action-deployment@internal.cognite.com` account and assign `functions-deployment` group to it. Click OK. NOTE: `<your-project>` refers to the name of your customer or use case. For example: `cool-use-case-github-action-deployment@internal.cognite.com`
      * Create `<your-project>-functions-sa@internal.cognite.com` account and assign groups that your function at runtime (inside Functions) requires, for example access to time series and assets. Click OK.
1. Get Functions whitelisted for that particular project, *if it is not already*.
   * Patch [this file](https://github.com/cognitedata/context-api/blob/master/src/api/functions/whitelist.py) with the service accounts we need for deployment and running functions:
      1. `<your-project>-github-action-deployment@internal.cognite.com`
      2. `<your-project>-functions-sa@internal.cognite.com`
   * Example: https://github.com/cognitedata/context-api/pull/1009/files
   * **Note**: In the whitelist dictionary, you need to know what the base URL for you tenant is, in order to whitelist it in the correct place. For example:
        1. `https://api.cognitedata.com`
        2. `https://greenfield.cognitedata.com`
        3. `https://statnett.cognitedata.com`
        5. `https://omv.cognitedata.com`
        6. etc.

1. Check if your tenant is listed by going to https://unleash-apps.cognite.ai/#/features. Click on `ML_OPS_cognite_functions`
   * If your tenant is NOT listed, add the name of your tenant and hit update.

# Structure of this repository

## Functions

Here you can find two simple functions implemented: `example_function1`, `example_function2` and `example_with_logging`.

The first function, `example_function1`, implements a basic echo capability and prints and sends back any content it receives. The second, `example_function2` implements an "A+B problem" solver and has expectations for the `data` it receives, which then might raise an exception.

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

### Run call checks locally
To run all checks locally - which is typically needed if the GitHub check is failing - e.g. you haven't set up `pre-commit` to run automatically:
```sh
$ poetry run pre-commit install  # Only needed if not installed
$ poetry run pre-commit run --all-files
```

## Build and deployment

The template uses GitHub Actions to perform Code quality and Deployment operations. All workflows are located in the [.github/workflows](https://github.com/cognitedata/deploy-functions/tree/master/.github/workflows) folder.
* `code-quality.yaml` Runs all code-quality checks and ensures the style, linting, basic static analysis
* `deploy-push.yaml` Responsible for you PR deployment to customer environment(s)
* `deploy-pr.yaml` Responsible for running tests / verification on Pull Requests

Each workflow consists of a series of sequentially executed steps. As an input to the workflows, you will need to provide parameters per each function in `function_config.yaml`.

**Note**: If the `deploy-push.yaml` workflow fails after you have merged to `master`, you can check out the tab `Actions` in GitHub, where you will it. Here you can drill down to find the cause - and if it is unrelated to your code changes, simply do a re-run.

## Secrets

**All API-keys *must* be stored as GitHub secrets.**
All secrets could be classified into two orthogonal groups: by branch and by role:
* `DEPLOY_MASTER` should contain the API-key for `<your-project>-github-action-deployment@internal.cognite.com`  service account (ref it's capabilities) and will be used for deployment in PRs and `master` branch
* `RUNTIME_MASTER` should contain the API-key for `<your-project>-functions-sa@internal.cognite.com` service account (ref it's capabilities) and will be deployed within function and used on every function' invocation.
* You can create similar `[DEPLOY|RUNTIME]_your_branch` secrets to support more than one target CDF project

This repository, when used as a template, requires two GitHub secrets to successfully build on a new tenant:
* `DEPLOY_MASTER`
* `RUNTIME_MASTER`

[optional] ...if you want to specify secrets per function:
* In order to make secrets available to a specific function (and branch, say master), you need to add it as a Github Secret in your repository with a *very* specific name:
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
In order to support that we need to have a process with formal gatekeepers and approvals. GitHub doesn't support tag protection but has a branch protection mechanisms with PRs as gatekeeping. For that purpose, `deploy-push.yaml` has a list of branches it triggers the action. In addition to that your function' name receives branch name as a suffix, so you can deploy them separately.

If you want to support more than one deployment (by default we only deploy and keep the content of `master` branch) you need the following:
1. Expand list of branches in `deploy-push.yaml` to the list of branches you want to deliver (f.ex. `master` -> `dev` environment; `prod` -> `production` environment) **OR** have separate workflow files per environment.
1. For each function, in the `schedules` directory create yaml file matching your branch name (`master` or `prod` in our example)
   * If the branch name has underscores like `pre_prod`, the file should be named `pre-prod.yaml`
1. Create 2 secrets with API-keys for each new environment. For example, you are adding `pre_prod`, then you need to add: `DEPLOY_PRE_PROD` and `RUNTIME_PRE_PROD`.

# How to use it
## Create a repository with this template
First, click the green [Use this template](https://github.com/cognitedata/deploy-functions/generate) button to create a repository from this template.

## Access
Secondly, go to "Settings", "Manage access" and add `forge` team to Administrators, so we can help you faster with fewer questions.

## Getting started
Corresponds to tutorial [Deploy Functions #005: Getting started, a high-level overview](https://cognitedata.atlassian.net/wiki/spaces/FORGE/pages/2248016119/Deploy+Functions+Template+Tutorials#Repo-overview).

1. Open your terminal and navigate to your newly cloned repo.
1. Run `poetry install`
1. Run `poetry run pre-commit install`

## Modify the template

* You *should* rename the function folders, i.e. `example_function1` to better describe what it will be doing/solving.
* Do whatever changes you want to do in the functions folders. You can create as many functions as you want in one repository.
Folder name will become the function name and the function's `external_id`. So be pragmatic in naming the folders!
* Remember to update `function_config.yaml` with relevant parameters per function, for example `owner` or `cdf_base_url` if your tenant has its own cluster, or maybe `cpu` and `memory` if you need more (or less) power!
* Go into Settings in your repository to create the secrets. You need the API keys you created as part of the prerequisites. Add them as `DEPLOY_MASTER` and `RUNTIME_MASTER`.

Once you have modified the functions and added secrets, modify the files in .github/workflows. These are the things you will have to modify:
* List of functions
  * Only the function folders listed in the workflow file(s) will be deployed. You therefore must keep it updated with any changes to the folder names, ([link to file](https://github.com/cognitedata/deploy-functions/blob/master/.github/workflows/deploy-push.yaml#L10))    .

For more details on how to set up your workflows to deploy to Cognite Functions, please see the [function-action](https://github.com/cognitedata/function-action) repository.

# I have a question

There will be questions. Crowdsourcing is required.

**Going to #forge-help on Slack is a good place to start!**

1. Q: Why is it so complicated?
   * Answer: Software is hard. Watch here for a few minutes: [link](https://www.youtube.com/watch?v=jlPaby7suOc&feature=youtu.be&t=163).
