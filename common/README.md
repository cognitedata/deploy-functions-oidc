
# Shared-code folder: `common`

A common use case when you deal with the deployment of multiple functions simultaneously, is that you do not want to replicate shared code between all the function folders. In order to accomodate this, as part of the workflow `function-action-oidc` this template relies on, a feature exists that will copy all the contents of any particular folder you'd like to be "shared". In this repo, that folder is named `common`, and is used by `example_function2`-

#### Handling imports
A typical setup looks like this:
```
├── common
│   └── utils.py
└── my_function
    └── handler.py
```
The code we zip and send off to the FilesAPI will look like this:
```
├── common
│   └── utils.py
└── handler.py
```
This means your `handler.py`-file should do imports from `common/utils.py` like this:
```py
from common.utils import my_helper1, my_helper2
import common.utils as utils  # alternative
```
