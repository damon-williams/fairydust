# Stuffie Stories Backend Requirements

## Project Overview

Stuffie Stories is a new mobile app focused on AI-generated stories featuring children's stuffed animals, with optional illustrations. The app will reuse fairydust's backend infrastructure while maintaining complete user and data separation.

## Architecture Decision

**Extend Existing Content Service** (port 8006)
- **Rationale**: Maximum code reuse while maintaining data separation
- **Shared Infrastructure**: Same service, same story generation code, same Redis/database connections
- **Isolated Data**: Separate users, separate DUST balances, separate story storage
- **New Routes**: Add `/stuffie-stories/*` endpoints to existing content service

## Database Schema Requirements

### New Tables

#### 1. `stuffie_stories_users`
```sql
CREATE TABLE stuffie_stories_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    display_name VARCHAR(100), -- Child's name/nickname
    birth_date DATE, -- For age-appropriate content
    avatar_url TEXT,
    is_active BOOLEAN DEFAULT true,
    email_verified BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'::jsonb
);
```

#### 2. `stuffie_stories_dust_balances`
```sql
CREATE TABLE stuffie_stories_dust_balances (
    user_id UUID PRIMARY KEY REFERENCES stuffie_stories_users(id) ON DELETE CASCADE,
    balance INTEGER NOT NULL DEFAULT 0,
    total_earned INTEGER NOT NULL DEFAULT 0,
    total_spent INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

#### 3. `stuffie_stories_dust_transactions`
```sql
CREATE TABLE stuffie_stories_dust_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES stuffie_stories_users(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL, -- Positive for grants, negative for consumption
    type VARCHAR(20) NOT NULL, -- 'grant', 'consumption', 'adjustment'
    description TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

#### 4. `stuffie_stories_people` (Reuses fairydust pattern)
```sql
CREATE TABLE stuffie_stories_people (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES stuffie_stories_users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    relationship VARCHAR(100) NOT NULL,
    birth_date DATE,
    age INTEGER,
    entry_type VARCHAR(20) NOT NULL DEFAULT 'person', -- 'person', 'pet', 'stuffie'
    species VARCHAR(100), -- For pets: 'Golden Retriever', for stuffies: 'Teddy Bear'
    traits TEXT[], -- Array of personality traits
    photo_url TEXT,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}'::jsonb, -- Stuffie-specific attributes
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

#### 5. `stuffie_stories_system_stuffies`
```sql
CREATE TABLE stuffie_stories_system_stuffies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    species VARCHAR(100) NOT NULL, -- 'Teddy Bear', 'Bunny', 'Dragon', etc.
    description TEXT NOT NULL,
    personality_traits TEXT[] NOT NULL,
    therapeutic_themes TEXT[], -- 'courage', 'friendship', 'empathy', etc.
    educational_topics TEXT[], -- 'colors', 'counting', 'sharing', etc.
    age_range_min INTEGER, -- Minimum recommended age
    age_range_max INTEGER, -- Maximum recommended age
    photo_url TEXT,
    is_active BOOLEAN DEFAULT true,
    sort_order INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

#### 6. `stuffie_stories_user_stories` (Modified from fairydust pattern)
```sql
CREATE TABLE stuffie_stories_user_stories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES stuffie_stories_users(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    story_length VARCHAR(20) NOT NULL, -- 'quick', 'medium', 'long'
    target_audience VARCHAR(30) NOT NULL,
    word_count INTEGER,
    estimated_reading_time VARCHAR(20),
    characters_involved JSONB NOT NULL DEFAULT '[]'::jsonb,
    has_images BOOLEAN DEFAULT false,
    images_complete BOOLEAN DEFAULT false,
    image_ids TEXT[],
    is_shared BOOLEAN DEFAULT false,
    share_code VARCHAR(50) UNIQUE, -- For public sharing
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### Database Indexes
```sql
-- Performance indexes
CREATE INDEX idx_stuffie_stories_users_email ON stuffie_stories_users(email);
CREATE INDEX idx_stuffie_stories_people_user_id ON stuffie_stories_people(user_id);
CREATE INDEX idx_stuffie_stories_people_entry_type ON stuffie_stories_people(entry_type);
CREATE INDEX idx_stuffie_stories_user_stories_user_id ON stuffie_stories_user_stories(user_id);
CREATE INDEX idx_stuffie_stories_user_stories_created_at ON stuffie_stories_user_stories(created_at DESC);
CREATE INDEX idx_stuffie_stories_system_stuffies_active ON stuffie_stories_system_stuffies(is_active, sort_order);
CREATE INDEX idx_stuffie_stories_dust_transactions_user_id ON stuffie_stories_dust_transactions(user_id);
```

## API Endpoints Required

**All endpoints will be added to the existing content service with `/stuffie-stories/` prefix**

### Authentication & User Management
```
POST   /stuffie-stories/auth/register           # User registration
POST   /stuffie-stories/auth/login              # User login
POST   /stuffie-stories/auth/logout             # User logout
POST   /stuffie-stories/auth/refresh            # Token refresh
GET    /stuffie-stories/auth/me                 # Get current user
PUT    /stuffie-stories/auth/me                 # Update user profile
POST   /stuffie-stories/auth/forgot-password    # Password reset
POST   /stuffie-stories/auth/reset-password     # Password reset confirmation
```

### DUST Management
```
GET    /stuffie-stories/dust/balance            # Get user's DUST balance
GET    /stuffie-stories/dust/transactions       # Get transaction history
POST   /stuffie-stories/dust/purchase           # Purchase DUST (integrate with app store)
```

### People/Pets/Stuffies Management
```
GET    /stuffie-stories/people                  # Get all user's people/pets/stuffies
POST   /stuffie-stories/people                  # Create new person/pet/stuffie
GET    /stuffie-stories/people/{id}             # Get specific person/pet/stuffie
PUT    /stuffie-stories/people/{id}             # Update person/pet/stuffie
DELETE /stuffie-stories/people/{id}             # Delete person/pet/stuffie
GET    /stuffie-stories/system-stuffies         # Get available system stuffies
```

### Story Generation & Management (Reuses Existing Code)
```
POST   /stuffie-stories/stories/generate        # Generate new story (reuses story_routes.py)
GET    /stuffie-stories/stories                 # Get user's stories
GET    /stuffie-stories/stories/{id}            # Get specific story
DELETE /stuffie-stories/stories/{id}            # Delete story
POST   /stuffie-stories/stories/{id}/images     # Generate images for story (reuses image_routes.py)
GET    /stuffie-stories/stories/{id}/images     # Get story image status
```

### Story Sharing & Export
```
POST   /stuffie-stories/stories/{id}/share      # Create shareable link
GET    /stuffie-stories/shared/{share_code}     # View shared story (public)
POST   /stuffie-stories/stories/{id}/export     # Export story (PDF, print format)
GET    /stuffie-stories/export/{export_id}      # Download exported story
```

### Admin/System Management
```
GET    /stuffie-stories/admin/system-stuffies   # Admin: List system stuffies
POST   /stuffie-stories/admin/system-stuffies   # Admin: Create system stuffie
PUT    /stuffie-stories/admin/system-stuffies/{id} # Admin: Update system stuffie
DELETE /stuffie-stories/admin/system-stuffies/{id} # Admin: Delete system stuffie
```

## Code Reuse Strategy

### Story Generation (100% Reuse)
- **Existing Functions**: Reuse `story_routes.py` generation logic directly
- **Same LLM Integration**: Use existing Anthropic/OpenAI clients
- **Same Cost Calculation**: Reuse existing pricing logic
- **Database Change Only**: Save to `stuffie_stories_user_stories` instead of `user_stories`

### Image Generation (100% Reuse)
- **Existing Image Routes**: Reuse `image_routes.py` endpoints
- **Same Generation Logic**: Use existing Replicate integration
- **Same Storage**: Use existing image storage patterns

### Authentication (Adapt Existing Patterns)
- **JWT Utilities**: Reuse existing JWT helper functions from `/shared/`
- **Password Hashing**: Reuse existing bcrypt utilities
- **Session Management**: Use existing Redis session patterns
- **Database Tables**: New user tables but same auth logic

### DUST Management (Adapt Existing Patterns)
- **Transaction Logic**: Reuse existing ledger service patterns
- **Balance Management**: Same logic, different tables
- **Cost Deduction**: Reuse existing DUST deduction functions

## Required Environment Variables

```bash
# No new environment variables needed!
# Reuses existing content service configuration:

# Existing variables that will be reused:
SERVICE_NAME=content  # Same service
PORT=8006            # Same port
DATABASE_URL=postgresql://... # Same database, new tables
ANTHROPIC_API_KEY=... # Same LLM keys
OPENAI_API_KEY=...    # Same LLM keys

# Future additions for app store integration:
APPLE_APP_STORE_SHARED_SECRET=...
GOOGLE_PLAY_SERVICE_ACCOUNT_KEY=...
```

## Development Phases

### Phase 1: Database & Routes Setup
1. Add new database tables to existing content service
2. Create `stuffie_stories_routes.py` with auth endpoints
3. Implement authentication system (reuse existing patterns)
4. Basic people/stuffies management endpoints

### Phase 2: Story Generation (Minimal Code Changes)
1. Create story generation endpoints that call existing `story_routes.py` functions
2. Modify database save logic to use new `stuffie_stories_user_stories` table
3. Story retrieval and management endpoints
4. Test story generation flow

### Phase 3: System Stuffies
1. System stuffies management endpoints
2. Admin interface integration (add to existing admin service)
3. Integration with story character selection

### Phase 4: Images & Export
1. Reuse existing image generation with new story IDs
2. Story export functionality (PDF/print)
3. Story sharing capabilities with public links

### Phase 5: Enhancement
1. Therapeutic/educational content features
2. Age-appropriate content filtering
3. Advanced export options
4. App store integration for DUST purchases

## Security Considerations

- **User Isolation**: Complete separation from fairydust users
- **Content Filtering**: Age-appropriate content validation
- **Data Privacy**: COPPA compliance for children's data
- **API Security**: Same JWT patterns as existing services
- **File Storage**: Secure image/export file handling

## Testing Strategy

- **Unit Tests**: All service endpoints
- **Integration Tests**: Content service integration
- **E2E Tests**: Complete story generation flow
- **Performance Tests**: Story generation under load
- **Security Tests**: Authentication and authorization

## Deployment Considerations

- **Same Railway Service**: No new service deployment needed
- **Database Migration**: Add new tables to existing content service database
- **Environment Variables**: No new variables required
- **Monitoring**: Use existing content service monitoring
- **Rollback Strategy**: Database migration rollback plans for new tables only

## Questions for Product Team

1. **System Stuffies Content**: What specific therapeutic themes and educational topics should we start with?
2. **Age Ranges**: What age ranges should we support (2-5, 6-8, 9-12)?
3. **Export Formats**: What specific print/export formats are needed?
4. **Content Moderation**: What content filtering is needed for user-generated stuffie descriptions?
5. **Analytics**: What usage analytics should we track?
6. **Monetization**: What DUST pricing should we start with?

---

**Document Version**: 1.0  
**Created**: 2025-08-19  
**Next Review**: After product team feedback