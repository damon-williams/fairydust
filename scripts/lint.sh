#!/bin/bash
# Code quality checking script for fairydust microservices
# This script checks code quality without making changes

set -e  # Exit on any error

echo "🔍 Checking fairydust Python code quality..."
echo "=============================================="

# Check if linting tools are installed
if ! command -v ruff &> /dev/null; then
    echo "❌ ruff is not installed. Please install dev requirements:"
    echo "   pip install -r requirements-dev.txt"
    exit 1
fi

if ! command -v black &> /dev/null; then
    echo "❌ black is not installed. Please install dev requirements:"
    echo "   pip install -r requirements-dev.txt"
    exit 1
fi

# Track if any issues are found
issues_found=0

# Check if code is formatted with black
echo "📝 Checking black formatting..."
if ! black --config pyproject.toml --check --diff .; then
    echo "❌ Code formatting issues found. Run './scripts/format.sh' to fix."
    issues_found=1
else
    echo "✅ Code is properly formatted with black"
fi

# Check for linting issues with ruff
echo ""
echo "🔍 Checking with ruff linter..."
if ! ruff check .; then
    echo "❌ Linting issues found. Run './scripts/format.sh' to auto-fix or fix manually."
    issues_found=1
else
    echo "✅ No linting issues found"
fi

# Optional: Check type hints with mypy (if installed)
if command -v mypy &> /dev/null; then
    echo ""
    echo "🏷️  Checking type hints with mypy..."
    if ! mypy --config-file pyproject.toml .; then
        echo "⚠️  Type checking issues found (warnings only)"
    else
        echo "✅ Type checking passed"
    fi
fi

echo ""
if [ $issues_found -eq 0 ]; then
    echo "🎉 All code quality checks passed!"
    exit 0
else
    echo "❌ Code quality issues found. Please fix before committing."
    echo "💡 Run './scripts/format.sh' to auto-fix formatting issues."
    exit 1
fi