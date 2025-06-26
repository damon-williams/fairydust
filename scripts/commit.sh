#!/bin/bash
# Smart commit script that automatically formats code before committing
# Usage: ./scripts/commit.sh "your commit message"

if [ $# -eq 0 ]; then
    echo "❌ Error: Please provide a commit message"
    echo "Usage: ./scripts/commit.sh \"your commit message\""
    exit 1
fi

COMMIT_MESSAGE="$1"

echo "🔧 Auto-formatting code before commit..."
echo "======================================"

# Step 1: Format code
if ! ./scripts/format.sh; then
    echo "❌ Formatting failed!"
    exit 1
fi

# Step 2: Check for remaining issues
echo ""
echo "🔍 Checking for code quality issues..."
if ! ./scripts/lint.sh; then
    echo "❌ Code quality issues found. Please fix before committing."
    exit 1
fi

# Step 3: Add and commit
echo ""
echo "📝 Committing formatted code..."
git add .
git commit -m "$COMMIT_MESSAGE"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Successfully committed with formatting applied!"
    echo "💡 Tip: Don't forget to push with 'git push origin develop'"
else
    echo "❌ Commit failed!"
    exit 1
fi