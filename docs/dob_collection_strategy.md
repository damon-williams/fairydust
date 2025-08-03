# Date of Birth Collection Strategy

Since Apple Sign In doesn't provide DOB, here's a recommended approach:

## Onboarding Flow

```typescript
// 1. Apple SSO Success
const handleAppleSignIn = async (authResponse) => {
  if (authResponse.is_new_user) {
    // Store what we got from Apple
    await AsyncStorage.setItem('onboarding_data', JSON.stringify({
      firstName: authResponse.extracted_first_name || '',
      lastName: authResponse.extracted_last_name || '',
      email: authResponse.user.email,
      needsDOB: true  // Flag for required fields
    }));
    
    // Navigate to profile completion
    navigation.navigate('CompleteProfile');
  }
};

// 2. Complete Profile Screen
const CompleteProfileScreen = () => {
  const [profileData, setProfileData] = useState({
    firstName: '', // Pre-filled from Apple
    lastName: '',  // Pre-filled from Apple
    birthdate: '', // Must be collected
  });
  
  return (
    <View>
      <Text>Almost done! Just a few more details...</Text>
      
      {/* Show pre-filled name */}
      <TextInput
        value={profileData.firstName}
        placeholder="First Name"
        editable={!profileData.firstName} // Only edit if not from SSO
      />
      
      {/* DOB is required */}
      <DatePicker
        label="Birthday"
        value={profileData.birthdate}
        onChange={setBirthdate}
        helperText="We use this to personalize your experience"
      />
      
      <Button onPress={completeProfile}>
        Continue
      </Button>
    </View>
  );
};
```

## Backend Support

Add a profile completion endpoint:

```python
@router.post("/users/{user_id}/complete-profile")
async def complete_profile(
    user_id: str,
    profile_data: ProfileCompletionRequest,
    current_user: AuthUser = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Complete user profile with required fields after SSO"""
    if str(current_user.user_id) != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    # Update user with DOB and any other required fields
    await db.execute("""
        UPDATE users 
        SET birthdate = $1,
            first_name = COALESCE($2, first_name),
            last_name = COALESCE($3, last_name),
            is_profile_complete = true,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $4
    """, profile_data.birthdate, profile_data.first_name, 
        profile_data.last_name, user_id)
    
    # Grant profile completion bonus
    if profile_data.birthdate:
        await grant_dust_bonus(user_id, 10, "profile_completion")
    
    return {"success": true, "dust_granted": 10}
```

## UX Best Practices

1. **Explain Why**: Tell users why you need their birthday
   - "To personalize recipes for your age group"
   - "To ensure age-appropriate content"
   - "To celebrate your special day!"

2. **Make it Optional (if possible)**: 
   - Core features work without it
   - Enhanced features require it

3. **Privacy Assurance**:
   - "Your birthday is private and never shared"
   - "Only used for personalization"

4. **Progressive Disclosure**:
   - Don't ask for everything at once
   - Collect DOB when relevant

## Alternative: Age Range Instead

If exact DOB isn't critical, consider age ranges:
- Under 13 (COPPA compliance)
- 13-17 (Teen)
- 18-24 (Young Adult)
- 25-34, 35-44, etc.

This feels less invasive while still enabling personalization.