#!/bin/bash
# Code formatting script for fairydust microservices
# This script formats all Python code using black and fixes import sorting with ruff

set -e  # Exit on any error

echo "🔧 Formatting fairydust Python codebase..."
echo "================================================"

# Check if formatting tools are installed
if ! command -v black &> /dev/null; then
    echo "❌ black is not installed. Please install dev requirements:"
    echo "   pip install -r requirements-dev.txt"
    exit 1
fi

if ! command -v ruff &> /dev/null; then
    echo "❌ ruff is not installed. Please install dev requirements:"
    echo "   pip install -r requirements-dev.txt"
    exit 1
fi

# Format all Python files with black
echo "📝 Running black code formatter..."
black --config pyproject.toml .

# Fix imports and other auto-fixable issues with ruff
echo "🔍 Running ruff auto-fixes..."
ruff check --fix .

# Show summary
echo ""
echo "✅ Code formatting completed!"
echo ""
echo "📊 Summary:"
echo "   • Black: Code formatting applied"
echo "   • Ruff: Import sorting and auto-fixes applied"
echo ""
echo "💡 To check for remaining issues: ./scripts/lint.sh"