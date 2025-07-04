---
name: "Format and Commit"
description: "Format code, run quality checks, and commit changes with proper message"
category: "git"
---

# Format and Commit

Automated workflow for formatting code and creating commits following fairydust standards.

## What this command does:

1. **Auto-format code** using `./scripts/format.sh`
2. **Check code quality** using `./scripts/lint.sh` 
3. **Stage all changes** with `git add .`
4. **Create commit** with descriptive message and Claude signature
5. **Show status** of the commit

## Usage:
```
/project:format-and-commit [commit message]
```

## Arguments:
- `$ARGUMENTS` - The commit message (required)

## Example:
```
/project:format-and-commit "Update user profile models to use birth_date"
```

This follows the mandatory pre-commit workflow from CLAUDE.md:
- ✅ Always run formatting before committing
- ✅ Check for code quality issues
- ✅ Use standardized commit message format