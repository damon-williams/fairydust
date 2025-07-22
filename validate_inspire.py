import ast
import sys

def validate_python_syntax(filepath):
    """Validate Python syntax of a file"""
    try:
        with open(filepath, 'r') as f:
            source = f.read()
        
        # Parse the AST to check syntax
        ast.parse(source, filename=filepath)
        print(f"✅ {filepath} has valid Python syntax")
        return True
        
    except SyntaxError as e:
        print(f"❌ Syntax error in {filepath}:")
        print(f"   Line {e.lineno}: {e.text}")
        print(f"   Error: {e.msg}")
        return False
    except Exception as e:
        print(f"❌ Error reading {filepath}: {e}")
        return False

# Validate the inspire routes file
if validate_python_syntax("services/content/inspire_routes.py"):
    print("\n🎉 inspire_routes.py syntax validation passed!")
else:
    print("\n💥 inspire_routes.py syntax validation failed!")
    sys.exit(1)