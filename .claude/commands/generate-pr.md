---
name: "Generate Pull Request"
description: "Create a pull request with proper formatting, following fairydust development workflow"
category: "git"
---

# Generate Pull Request

Create a pull request following the fairydust development workflow from develop → main.

## Workflow Steps:

1. **Check Current Status**
   - Verify we're on the develop branch
   - Show git status and all modified files
   - Display recent commits to understand the scope of changes

2. **Code Quality & Formatting**
   - Run `./scripts/format.sh` to auto-format all code
   - Run `./scripts/lint.sh` to check for code quality issues
   - Run tests if applicable: `pytest tests/` 

3. **Commit Management**
   - Stage all changes with `git add .`
   - Create a descriptive commit message based on the changes
   - Commit with the fairydust standard format including Claude signature

4. **Push & PR Creation**
   - Push to origin develop branch
   - Create PR from develop → main for production deployment
   - Use proper PR title and description with testing instructions

## Usage:
```
/project:generate-pr [optional description or focus area]
```

## Arguments:
- `$ARGUMENTS` - Optional hint about the PR focus or description (e.g., "user profile migration", "admin portal improvements")

## Example:
```
/project:generate-pr "Migration from age_range to birth_date core property"
```

This command follows the critical git workflow documented in CLAUDE.md:
- ✅ Work on develop branch
- ✅ Test in staging environment 
- ✅ Only merge to main via PR after staging approval
- ⚠️ NEVER commit directly to main branch