-- Migration to add account_deletion_logs table
-- Run this if the table doesn't exist yet

CREATE TABLE IF NOT EXISTS account_deletion_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    fairyname VARCHAR(255),
    email VARCHAR(255),
    deletion_reason VARCHAR(50),
    deletion_feedback TEXT,
    deleted_by VARCHAR(50) NOT NULL DEFAULT 'self',
    deleted_by_user_id UUID,
    user_created_at TIMESTAMP WITH TIME ZONE,
    deletion_requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deletion_completed_at TIMESTAMP WITH TIME ZONE,
    data_summary JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT deletion_reason_check CHECK (deletion_reason IN (
        'not_using_anymore', 'privacy_concerns', 'too_expensive', 
        'switching_platform', 'other'
    )),
    CONSTRAINT deleted_by_check CHECK (deleted_by IN ('self', 'admin'))
);

CREATE INDEX IF NOT EXISTS idx_account_deletion_logs_user_id ON account_deletion_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_account_deletion_logs_deletion_requested_at ON account_deletion_logs(deletion_requested_at DESC);
CREATE INDEX IF NOT EXISTS idx_account_deletion_logs_deleted_by ON account_deletion_logs(deleted_by);
CREATE INDEX IF NOT EXISTS idx_account_deletion_logs_reason ON account_deletion_logs(deletion_reason);