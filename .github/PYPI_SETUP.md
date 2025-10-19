# PyPI Publishing Setup Guide

This document explains how to configure automated PyPI publishing with GitHub Actions.

## Prerequisites

- GitHub repository created
- PyPI account
- TestPyPI account

---

## Setup Instructions

### 1. Configure PyPI Trusted Publishing

GitHub Actions uses **Trusted Publishing** (secure and no API tokens required).

#### TestPyPI Configuration

1. Log in to https://test.pypi.org/
2. Navigate to **Account settings** -> **Publishing**
3. Click **Add a new pending publisher**
4. Enter the following details:
   - **PyPI Project Name**: `ticko`
   - **Owner**: `NakuRei` (your GitHub username)
   - **Repository name**: `ticko`
   - **Workflow name**: `publish.yml`
   - **Environment name**: `testpypi`
5. Click **Add**

#### Production PyPI Configuration

1. Log in to https://pypi.org/
2. Navigate to **Account settings** -> **Publishing**
3. Click **Add a new pending publisher**
4. Enter the following details:
   - **PyPI Project Name**: `ticko`
   - **Owner**: `NakuRei` (your GitHub username)
   - **Repository name**: `ticko`
   - **Workflow name**: `publish.yml`
   - **Environment name**: `pypi`
5. Click **Add**

---

### 2. Configure GitHub Environments

1. Go to your GitHub repository: https://github.com/NakuRei/ticko
2. Navigate to **Settings** tab -> **Environments**
3. Click **New environment**

#### testpypi Environment

1. Name: `testpypi`
2. Click **Configure environment**
3. **Deployment protection rules**:
   - Optional (recommended: no configuration needed)
4. Click **Save protection rules**

#### pypi Environment (Production)

1. Name: `pypi`
2. Click **Configure environment**
3. **Deployment protection rules**:
   - Enable **Required reviewers** (recommended)
   - Add yourself as a reviewer
4. Click **Save protection rules**

---

## Usage

### Publish a New Version

1. **Update version in pyproject.toml**
   ```toml
   version = "0.1.0"  # Example: change to 0.1.1
   ```

2. **Commit changes**
   ```bash
   git add pyproject.toml
   git commit -m "chore: bump version to 0.1.1"
   git push
   ```

3. **Create and push Git tag**
   ```bash
   git tag v0.1.1
   git push origin v0.1.1
   ```

4. **Automated publishing flow**
   ```
   Push tag
     |
     v
   GitHub Actions triggered
     |
     v
   Publish to TestPyPI
     |
     v
   Wait for manual approval
     |
     v
   Publish to PyPI
     |
     v
   Create GitHub Release
   ```

---

## Troubleshooting

### Error: "Publishing is not configured"

Verify Trusted Publishing configuration on PyPI

### Error: "Package already exists"

The same version already exists on TestPyPI. Increment the version number

### Workflow waiting for approval

Go to GitHub **Actions** tab, select workflow, then **Review deployments** to approve

---

## First-Time Publishing Note

For the first-time publishing, the Trusted Publishing configuration will be in **Pending** status.
After pushing the first tag, it will be automatically activated on the PyPI side.

---

## References

- [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
- [GitHub Actions - PyPI Publish](https://github.com/pypa/gh-action-pypi-publish)
