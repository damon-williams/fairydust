#!/bin/bash

# Database connection details from docker-compose.yml
DB_HOST="localhost"
DB_PORT="5432"
DB_USER="postgres"
DB_PASS="password"
DB_NAME="fairydust"

echo "Connecting to PostgreSQL database..."

# Execute the DELETE command
PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<EOF
-- Show current count
SELECT COUNT(*) as "Current action_pricing records" FROM action_pricing;

-- Delete all records
DELETE FROM action_pricing;

-- Show final count
SELECT COUNT(*) as "Final action_pricing records" FROM action_pricing;
EOF

if [ $? -eq 0 ]; then
    echo "Successfully cleared action_pricing table"
else
    echo "Failed to clear action_pricing table"
    exit 1
fi