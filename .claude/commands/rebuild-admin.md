---
name: "Rebuild Admin Portal"
description: "Rebuild React admin portal and commit static files to fix caching issues"
category: "admin"
---

# Rebuild Admin Portal

Rebuild the React admin portal and commit static files to resolve caching issues.

## What this command does:

1. **Navigate to admin-ui directory**
2. **Run npm run build** to rebuild React app
3. **Copy static files** from dist/ to admin service static/
4. **Update version number** in the admin portal
5. **Commit static files** with proper message
6. **Show deployment status**

## Usage:
```
/project:rebuild-admin [version increment type]
```

## Arguments:
- `$ARGUMENTS` - Version increment: "patch" (default), "minor", or "major"

## Example:
```
/project:rebuild-admin patch
```

This addresses the caching issue documented in CLAUDE.md:
- ✅ Always rebuild React app when making admin portal changes
- ✅ Commit static files to ensure deployment picks up changes
- ✅ Increment version number for cache busting
- ✅ Follow the 45-minute debugging lesson learned