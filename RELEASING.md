# Release Process

This document outlines the steps to create a new release of the Dwellir Harvester.

## Prerequisites

- Python 3.9 or higher
- `build` and `twine` packages installed:
  ```bash
  pip install build twine
  ```
- Write access to the repository
- Clean working directory (no uncommitted changes)

## Release Steps

1. **Update the version number**
   - Edit `pyproject.toml` and update the `version` field (e.g., `0.1.10`)

2. **Update the changelog**
   - Update `CHANGELOG.md` with the new version and changes
   - Follow the format of previous entries
   - Include all notable changes, bug fixes, and new features

3. **Commit the changes**
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "Bump version to X.Y.Z"
   git push origin main  # or your development branch
   ```

4. **Create a Git tag**
   ```bash
   git tag -a vX.Y.Z -m "Version X.Y.Z"
   git push origin vX.Y.Z
   ```

5. **Build the package**
   ```bash
   python -m build
   ```
   This will create distribution files in the `dist/` directory.

6. **Test the package** (optional but recommended)
   ```bash
   # Create a test virtual environment
   python -m venv test-env
   source test-env/bin/activate  # On Windows: test-env\Scripts\activate
   
   # Install the package in development mode
   pip install -e .
   
   # Run tests
   pytest
   ```

7. **Upload to PyPI**
   ```bash
   twine upload dist/*
   ```
   You'll need your PyPI username and password (or API token).

8. **Create a GitHub Release**
   - Go to the [Releases](https://github.com/dwellir-public/blockchain-collector/releases) page
   - Click "Draft a new release"
   - Enter the tag you just pushed (vX.Y.Z)
   - Use the same title as the tag (vX.Y.Z)
   - Copy the changelog entries for this version into the release notes
   - Attach the distribution files from the `dist/` directory
   - Publish the release

## Post-Release

1. Update the version to the next development version in `pyproject.toml` (e.g., `0.1.11-dev`)
2. Commit the changes:
   ```bash
   git add pyproject.toml
   git commit -m "Bump version to X.Y.Z-dev"
   git push origin main  # or your development branch
   ```

## Troubleshooting

- If the build fails, check for syntax errors or missing dependencies
- If the upload fails, ensure you have the correct PyPI permissions
- If the version update script fails, verify the format of `pyproject.toml`
