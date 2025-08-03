# Builder Concept Removal Refactor Plan

## Overview
The builder concept was designed for a community-driven app marketplace but is no longer relevant to fairydust's current vision. This document outlines the complete removal strategy.

## Database Changes

### 1. Schema Modifications
```sql
-- Remove is_builder from users table
ALTER TABLE users DROP COLUMN is_builder;

-- Remove builder_id from apps table
ALTER TABLE apps DROP COLUMN builder_id;

-- Drop related indexes
DROP INDEX IF EXISTS idx_apps_builder;
```

### 2. Data Migration
- All existing apps would become "system apps" with no owner
- Remove builder validation from app creation

## Code Changes Required

### A. Database Layer (`/shared/database.py`)
- Remove `is_builder` from users table schema
- Remove `builder_id` from apps table schema
- Update all INSERT statements for built-in apps
- Remove builder_id index creation

### B. Apps Service (`/services/apps/`)
**routes.py**:
- Remove builder validation in `register_app()`
- Remove builder_id from app creation
- Delete `/builders` endpoint
- Remove builder joins from app queries
- Remove `builder_name` from responses

**service_routes.py**:
- Remove auto-creation of builder users
- Remove `UPDATE users SET is_builder = true` logic

**models.py**:
- Remove `builder_id` from App model
- Remove builder-related response models

### C. Admin Service (`/services/admin/`)
**routes/users.py**:
- Remove `is_builder` from user queries
- Remove `/toggle-builder` endpoint
- Remove builder badge logic

**routes/dashboard.py**:
- Remove `is_builder` from dashboard stats queries

**Templates** (if any remain):
- Remove builder badges from UI

### D. Authentication (`/services/identity/`)
**auth.py**:
- Remove `is_builder` from JWT token claims
- Remove from token validation

### E. Shared Components
**auth_middleware.py**:
- Remove `is_builder` from `AuthUser` model
- Remove from token parsing

### F. Frontend (Admin UI)
**types/admin.ts**:
- Remove `is_builder` from User interface
- Remove `builder_id` from App interface

**Components**:
- Remove builder badges from user lists
- Remove builder toggle buttons
- Remove builder name displays in app lists

### G. Scripts & Tests
- Update `generate_service_token.py`
- Update test fixtures in `conftest.py`
- Remove builder-related SQL scripts

## Migration Strategy

### Phase 1: Create System Apps (Current Approach)
✅ Create system user placeholder
✅ Migrate all apps to system user
- Maintains backward compatibility

### Phase 2: Remove Builder UI
- Remove builder badges from admin portal
- Remove builder toggle functionality
- Remove builder name from app displays

### Phase 3: Clean Authentication
- Remove `is_builder` from JWT tokens
- Update auth middleware
- Deploy identity service changes

### Phase 4: Schema Cleanup
- Remove database columns
- Update all queries
- Remove validation logic

### Phase 5: Final Cleanup
- Remove unused endpoints
- Clean up models and types
- Update documentation

## Impact Assessment

### Low Risk Areas:
- Admin portal display changes
- Removing unused endpoints
- Cleaning up models

### Medium Risk Areas:
- JWT token changes (needs coordinated deployment)
- Database queries that expect builder_id

### High Risk Areas:
- Database schema changes (requires downtime or careful migration)
- App creation flow changes

## Benefits of Removal
1. Simplified codebase
2. Reduced cognitive overhead
3. Cleaner data model
4. No orphaned apps when users delete accounts
5. Aligns with current fairydust vision

## Alternative: Keep Minimal Structure
Instead of full removal, we could:
- Keep `builder_id` but always set to system user
- Remove `is_builder` flag entirely
- Remove all builder UI/UX elements
- Treat it as internal metadata only

This would be less risky but doesn't fully clean up the codebase.