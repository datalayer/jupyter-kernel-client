<!--
  ~ Copyright (c) 2023-2024 Datalayer, Inc.
  ~
  ~ BSD 3-Clause License
-->

# Making a new release of jupyter_kernel_client

A tag releases `jupyter-kernel-client` to PyPI, with no stored publishing token: PyPI
trusts `.github/workflows/release.yaml` through OIDC (trusted publishing, the `pypi`
environment). The version lives in `jupyter_kernel_client/__version__.py`, which Hatch
reads; the tag must name it.

## Steps

1. Bump `__version__` in `jupyter_kernel_client/__version__.py` (and the CHANGELOG) on a
   branch, and open a pull request.

1. Squash-merge it once its checks are green, then tag the squash commit on `main` and
   push the tag:

   ```bash
   git checkout main && git pull
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

1. The `Release` workflow checks that the tag names the version, runs the tests of
   `build.yaml` on the tagged commit, builds the sdist and the wheel, publishes them to PyPI
   unless that version is published already, and creates a GitHub release with generated
   notes. A tag whose tests fail publishes nothing.

## Trusted publishing

PyPI project `jupyter-kernel-client`: owner `datalayer`, repository
`jupyter-kernel-client`, workflow `release.yaml`, environment `pypi`. The registry's
configuration must match the repository, the workflow file name and the environment
exactly; renaming any of them means updating the trusted publisher.

## Building by hand

To check the packages locally:

```bash
pip install build
python -m build
```

## Publishing to `conda-forge`

If the package is not on conda forge yet, check the documentation to learn how to add it: https://conda-forge.org/docs/maintainer/adding_pkgs.html

Otherwise a bot should pick up the new version publish to PyPI, and open a new PR on the feedstock repository automatically.
