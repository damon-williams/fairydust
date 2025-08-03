# Frontend Team: SSO Name Extraction Implementation

## Issue Resolution

We've identified and fixed the "None None" display issue in the Apple SSO flow. The backend now properly extracts and returns name data from Apple Sign In.

## Updated AuthResponse Structure

The identity service now returns enhanced name data in the OAuth callback response:

```typescript
interface AuthResponse {
  // ... existing fields
  
  // NEW: Enhanced name extraction fields
  extracted_name?: string;           // Full name: "John Doe"
  extracted_first_name?: string;     // First name only: "John"  
  extracted_last_name?: string;      // Last name only: "Doe"
  extracted_birthdate?: string;      // DOB (typically null for Apple)
}
```

## Implementation Changes Required

### ❌ **OLD WAY** (causing "None None"):
```typescript
// Don't use these - they don't exist or contain null values
const firstName = response.user.first_name;  // undefined/null
const lastName = response.user.last_name;    // undefined/null
```

### ✅ **NEW WAY** (correct implementation):
```typescript
const handleSSO = (response: AuthResponse) => {
  // Use the extracted fields from SSO providers
  const firstName = response.extracted_first_name || '';
  const lastName = response.extracted_last_name || '';
  const fullName = response.extracted_name || '';
  
  if (response.is_new_user) {
    // Pre-populate onboarding forms
    navigation.navigate('Onboarding', {
      prefilledData: {
        firstName,
        lastName,
        fullName
      }
    });
  }
};
```

## Key Points

1. **Always provide fallbacks** - SSO fields can be empty:
   ```typescript
   const firstName = response.extracted_first_name || '';  // ✅ Good
   const firstName = response.extracted_first_name;        // ❌ Could be null
   ```

2. **Apple name data limitations**:
   - Only provided on **first authorization**
   - If user has previously authorized the app, name fields will be empty
   - To test: remove Apple provider link from test account first

3. **Handle both scenarios**:
   ```typescript
   const getDisplayName = (response: AuthResponse) => {
     // Try extracted name first (from SSO)
     if (response.extracted_first_name) {
       return `${response.extracted_first_name} ${response.extracted_last_name || ''}`.trim();
     }
     
     // Fallback to stored user data
     if (response.user.first_name) {
       return `${response.user.first_name} ${response.user.last_name || ''}`.trim();
     }
     
     // Last resort
     return response.user.fairyname || 'User';
   };
   ```

## Testing

When testing Apple SSO name extraction:

1. **Backend logs** will show (check Railway identity service logs):
   ```
   📝 APPLE: Parsed name - First: 'John', Last: 'Doe'
   📤 OAUTH RESPONSE: Returning to client:
      - extracted_first_name: John
      - extracted_last_name: Doe
   ```

2. **Frontend should receive**:
   ```javascript
   console.log('SSO Response:', {
     extracted_name: response.extracted_name,
     extracted_first_name: response.extracted_first_name,
     extracted_last_name: response.extracted_last_name
   });
   ```

## Next Steps

1. **Update your SSO response handling** to use `extracted_first_name` and `extracted_last_name`
2. **Add proper null checking** with empty string fallbacks
3. **Test with a fresh Apple authorization** (not a returning user)
4. **Deploy and verify** the "None None" issue is resolved

The backend changes are ready and committed. This should completely resolve the name display issue once you update to use the correct response fields.

---
**Questions?** Check the identity service logs or reach out if you need clarification on the response structure.