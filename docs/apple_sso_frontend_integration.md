# Apple SSO Frontend Integration Guide

## Enhanced OAuth Response Fields

The identity service now returns additional fields from Apple SSO that can be used to pre-populate onboarding forms.

### AuthResponse Structure

```typescript
interface AuthResponse {
  user: User;
  token: Token;
  is_new_user: boolean;
  dust_granted: number;
  is_first_login_today: boolean;
  daily_bonus_eligible: boolean;
  terms_acceptance_required: boolean;
  pending_terms: TermsDocument[];
  
  // OAuth extracted data for pre-population
  extracted_name?: string;           // Full name (e.g., "John Doe")
  extracted_first_name?: string;     // First name only (e.g., "John")
  extracted_last_name?: string;      // Last name only (e.g., "Doe")
  extracted_birthdate?: string;      // Date of birth (if provided by Apple)
}
```

## Implementation Example

```typescript
// After successful Apple SSO callback
const handleAppleSignInResponse = async (response: AuthResponse) => {
  if (response.is_new_user) {
    // Pre-populate onboarding forms
    const onboardingData = {
      firstName: response.extracted_first_name || '',
      lastName: response.extracted_last_name || '',
      fullName: response.extracted_name || '',
      birthdate: response.extracted_birthdate || ''
    };
    
    // Navigate to onboarding with pre-filled data
    navigation.navigate('Onboarding', { 
      prefilledData: onboardingData 
    });
  }
};
```

## Important Notes

1. **Apple Name Data**: Apple only provides name data on the **first authorization**. Subsequent sign-ins won't include name data unless the user revokes and re-authorizes the app.

2. **Date of Birth**: Apple typically does NOT provide DOB through SSO. The field is included for completeness but will likely be null.

3. **Fallback Handling**: Always provide fallbacks as these fields may be empty:
   ```typescript
   const firstName = response.extracted_first_name || '';
   ```

4. **Display Issue Fix**: If you're seeing "None None" in the app, check:
   - Are you reading `extracted_first_name` and `extracted_last_name` from the response?
   - Are you handling null/undefined values properly?
   - Is the onboarding form expecting different field names?

## Backend Logging

When testing, check the identity service logs for these debug messages:

```
🔍 APPLE: Raw user_data received: {...}
📝 APPLE: Parsed name - First: 'John', Last: 'Doe'
🎂 APPLE: DOB found: null
📤 OAUTH RESPONSE: Returning to client:
   - extracted_name: John Doe
   - extracted_first_name: John
   - extracted_last_name: Doe
   - extracted_birthdate: null
```

## Testing Tips

1. To test name extraction, you need to:
   - Remove Apple provider link from existing account
   - Sign in with Apple as if you're a new user
   - Apple will show the name/email sharing screen only on first authorization

2. The backend now logs extensive debug information - check Railway logs for the identity service to see what data Apple is providing.

## Next Steps

If you're still seeing "None None":
1. Check that your frontend is reading the new `extracted_first_name` and `extracted_last_name` fields
2. Ensure you're not trying to display Python `None` values (should be handled as empty strings)
3. Verify the onboarding form field names match what you're passing