#!/usr/bin/env python3
"""
Generic Python Class & Function Copy Tool

A robust AST-based tool for copying classes and functions between Python files.
Handles imports, dependencies, and maintains proper code structure.

Usage:
    python copy_tool.py copy-class source.py target.py ClassName
    python copy_tool.py copy-function source.py target.py function_name
    python copy_tool.py extract-classes source.py target_dir/ Class1 Class2 Class3
    python copy_tool.py analyze source.py
"""

import ast
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Union
from dataclasses import dataclass
import re
from collections import defaultdict

@dataclass
class CodeElement:
    """Information about a class or function definition."""
    name: str
    type: str  # 'class' or 'function'
    start_line: int
    end_line: int
    source_lines: List[str]
    imports_used: Set[str]
    dependencies: Set[str]
    decorators: List[str]
    docstring: Optional[str]
    node: Union[ast.ClassDef, ast.FunctionDef]

@dataclass
class ImportInfo:
    """Information about an import statement."""
    line: str
    module: Optional[str]
    names: List[str]
    is_from_import: bool
    level: int  # For relative imports

class PythonCopyTool:
    """AST-based tool for copying Python code elements between files."""
    
    def __init__(self):
        self.verbose = False
        
    def log(self, message: str, level: str = "INFO"):
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            prefix = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌", "SUCCESS": "✅"}
            print(f"{prefix.get(level, 'ℹ️')} {message}")
    
    def analyze_file(self, file_path: Path) -> Tuple[List[CodeElement], List[ImportInfo]]:
        """Analyze a Python file and extract all classes, functions, and imports."""
        try:
            content = file_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            tree = ast.parse(content, filename=str(file_path))
            
            elements = []
            imports = []
            
            # Extract imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        import_info = ImportInfo(
                            line=f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""),
                            module=None,
                            names=[alias.name],
                            is_from_import=False,
                            level=0
                        )
                        imports.append(import_info)
                        
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    names = []
                    line_parts = [f"from {module}" if module else "from"]
                    if node.level > 0:
                        line_parts[0] = "from " + "." * node.level + (module if module else "")
                    
                    name_parts = []
                    for alias in node.names:
                        name = alias.name
                        names.append(name)
                        if alias.asname:
                            name_parts.append(f"{name} as {alias.asname}")
                        else:
                            name_parts.append(name)
                    
                    line = f"{line_parts[0]} import {', '.join(name_parts)}"
                    
                    import_info = ImportInfo(
                        line=line,
                        module=module,
                        names=names,
                        is_from_import=True,
                        level=node.level
                    )
                    imports.append(import_info)
            
            # Extract classes and functions from top-level only
            for node in tree.body:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    element = self._extract_code_element(node, lines, tree)
                    if element:
                        elements.append(element)
            
            return elements, imports
            
        except Exception as e:
            self.log(f"Error analyzing {file_path}: {e}", "ERROR")
            return [], []
    
    def _extract_code_element(self, node: Union[ast.ClassDef, ast.FunctionDef], 
                             lines: List[str], tree: ast.AST) -> Optional[CodeElement]:
        """Extract information about a class or function node."""
        try:
            start_line = node.lineno - 1  # Convert to 0-based
            
            # Find the end line by looking for the next top-level element
            end_line = len(lines) - 1
            for other_node in tree.body:
                if (isinstance(other_node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and 
                    other_node.lineno > node.lineno):
                    end_line = other_node.lineno - 2
                    break
            
            # Extract source lines
            source_lines = lines[start_line:end_line + 1]
            
            # Get docstring
            docstring = None
            if (node.body and isinstance(node.body[0], ast.Expr) and 
                isinstance(node.body[0].value, ast.Constant) and 
                isinstance(node.body[0].value.value, str)):
                docstring = node.body[0].value.value
            
            # Extract decorators
            decorators = []
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name):
                    decorators.append(decorator.id)
                elif isinstance(decorator, ast.Attribute):
                    decorators.append(ast.unparse(decorator))
                else:
                    decorators.append(ast.unparse(decorator))
            
            # Find dependencies (other classes/functions referenced)
            dependencies = set()
            imports_used = set()
            
            for line in source_lines:
                # Find class/function references (simple heuristic)
                # Look for capitalized words that might be class names
                class_refs = re.findall(r'\b([A-Z][a-zA-Z0-9_]+)\b', line)
                dependencies.update(class_refs)
                
                # Look for function calls
                func_refs = re.findall(r'\b([a-z_][a-zA-Z0-9_]*)\s*\(', line)
                dependencies.update(func_refs)
                
                # Look for imports being used
                import_refs = re.findall(r'\b(\w+)\.[a-zA-Z_]', line)
                imports_used.update(import_refs)
            
            # Remove the element's own name from dependencies
            dependencies.discard(node.name)
            
            element_type = "class" if isinstance(node, ast.ClassDef) else "function"
            
            return CodeElement(
                name=node.name,
                type=element_type,
                start_line=start_line + 1,  # Convert back to 1-based
                end_line=end_line + 1,
                source_lines=source_lines,
                imports_used=imports_used,
                dependencies=dependencies,
                decorators=decorators,
                docstring=docstring,
                node=node
            )
            
        except Exception as e:
            self.log(f"Error extracting element {getattr(node, 'name', 'unknown')}: {e}", "ERROR")
            return None
    
    def find_element(self, file_path: Path, element_name: str) -> Optional[CodeElement]:
        """Find a specific class or function in a file."""
        elements, _ = self.analyze_file(file_path)
        for element in elements:
            if element.name == element_name:
                return element
        return None
    
    def copy_element(self, source_file: Path, target_file: Path, element_name: str, 
                    copy_dependencies: bool = True) -> bool:
        """Copy a class or function from source to target file."""
        
        self.log(f"Copying {element_name} from {source_file} to {target_file}")
        
        # Find the element in source
        element = self.find_element(source_file, element_name)
        if not element:
            self.log(f"Element '{element_name}' not found in {source_file}", "ERROR")
            return False
        
        # Get source imports
        _, source_imports = self.analyze_file(source_file)
        
        # Determine which imports are needed
        needed_imports = self._determine_needed_imports(element, source_imports)
        
        # Read target file or create if it doesn't exist
        target_content = ""
        existing_imports = []
        existing_elements = []
        
        if target_file.exists():
            target_content = target_file.read_text(encoding='utf-8')
            existing_elements, existing_imports_info = self.analyze_file(target_file)
            existing_imports = [imp.line for imp in existing_imports_info]
        
        # Check if element already exists
        for existing in existing_elements:
            if existing.name == element_name:
                self.log(f"Element '{element_name}' already exists in {target_file}", "WARN")
                response = input("Overwrite? (y/N): ").lower().strip()
                if response != 'y':
                    return False
                break
        
        # Generate new file content
        new_content = self._generate_target_content(
            target_content, element, needed_imports, existing_imports
        )
        
        # Write the file
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(new_content, encoding='utf-8')
            self.log(f"Successfully copied {element_name} to {target_file}", "SUCCESS")
            return True
        except Exception as e:
            self.log(f"Error writing to {target_file}: {e}", "ERROR")
            return False
    
    def _determine_needed_imports(self, element: CodeElement, 
                                 source_imports: List[ImportInfo]) -> List[str]:
        """Determine which imports are needed for this element."""
        needed = []
        
        # Simple heuristic: include imports that are referenced in the element
        for import_info in source_imports:
            # Check if any imported names are used in the element
            for name in import_info.names:
                if name in element.imports_used or any(name in line for line in element.source_lines):
                    needed.append(import_info.line)
                    break
        
        return needed
    
    def _generate_target_content(self, existing_content: str, element: CodeElement, 
                                needed_imports: List[str], existing_imports: List[str]) -> str:
        """Generate the new content for the target file."""
        
        lines = []
        
        if existing_content:
            # Parse existing file to maintain structure
            existing_lines = existing_content.split('\n')
            
            # Find where imports end and where to insert new element
            import_end_line = 0
            for i, line in enumerate(existing_lines):
                if (line.strip() and not line.startswith('#') and 
                    not line.startswith('import') and not line.startswith('from')):
                    import_end_line = i
                    break
            
            # Add existing content up to import end
            lines.extend(existing_lines[:import_end_line])
            
            # Add needed imports that don't already exist
            for import_line in needed_imports:
                if import_line not in existing_imports:
                    lines.append(import_line)
            
            # Add blank line if we added imports
            if any(imp not in existing_imports for imp in needed_imports):
                lines.append("")
            
            # Add rest of existing content
            lines.extend(existing_lines[import_end_line:])
            
            # Add blank lines before new element
            if lines and lines[-1].strip():
                lines.append("")
                lines.append("")
        else:
            # New file - add header and imports
            lines.append('"""')
            lines.append('Module with copied Python elements.')
            lines.append('"""')
            lines.append("")
            
            # Add imports
            for import_line in needed_imports:
                lines.append(import_line)
            
            if needed_imports:
                lines.append("")
                lines.append("")
        
        # Add the element
        lines.extend(element.source_lines)
        
        return '\n'.join(lines)
    
    def extract_multiple(self, source_file: Path, target_dir: Path, 
                        element_names: List[str]) -> bool:
        """Extract multiple elements into separate files in target directory."""
        
        self.log(f"Extracting {len(element_names)} elements from {source_file}")
        
        target_dir.mkdir(parents=True, exist_ok=True)
        success_count = 0
        
        for element_name in element_names:
            # Create target file name
            target_file = target_dir / f"{element_name.lower()}.py"
            
            if self.copy_element(source_file, target_file, element_name):
                success_count += 1
        
        self.log(f"Successfully extracted {success_count}/{len(element_names)} elements", 
                "SUCCESS" if success_count == len(element_names) else "WARN")
        
        return success_count == len(element_names)
    
    def analyze_command(self, file_path: Path):
        """Analyze a file and print detailed information."""
        elements, imports = self.analyze_file(file_path)
        
        print(f"📄 Analysis of {file_path}")
        print("=" * 50)
        
        print(f"\n📦 Imports ({len(imports)}):")
        for imp in imports:
            print(f"  {imp.line}")
        
        print(f"\n🏗️  Classes ({len([e for e in elements if e.type == 'class'])}):")
        for element in elements:
            if element.type == 'class':
                print(f"  📋 {element.name} (lines {element.start_line}-{element.end_line})")
                if element.dependencies:
                    deps = ', '.join(sorted(element.dependencies))
                    print(f"     Dependencies: {deps}")
        
        print(f"\n⚙️  Functions ({len([e for e in elements if e.type == 'function'])}):")
        for element in elements:
            if element.type == 'function':
                print(f"  🔧 {element.name} (lines {element.start_line}-{element.end_line})")
                if element.decorators:
                    print(f"     Decorators: {', '.join(element.decorators)}")

def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(
        description="Generic Python Class & Function Copy Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python copy_tool.py copy-class src.py dest.py MyClass
  python copy_tool.py copy-function src.py dest.py my_function  
  python copy_tool.py extract-classes big_file.py modules/ Class1 Class2 Class3
  python copy_tool.py analyze big_file.py
        """
    )
    
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Copy class command
    copy_class = subparsers.add_parser("copy-class", help="Copy a class between files")
    copy_class.add_argument("source", type=Path, help="Source file")
    copy_class.add_argument("target", type=Path, help="Target file") 
    copy_class.add_argument("class_name", help="Name of class to copy")
    
    # Copy function command
    copy_func = subparsers.add_parser("copy-function", help="Copy a function between files")
    copy_func.add_argument("source", type=Path, help="Source file")
    copy_func.add_argument("target", type=Path, help="Target file")
    copy_func.add_argument("function_name", help="Name of function to copy")
    
    # Extract multiple command
    extract = subparsers.add_parser("extract-classes", help="Extract multiple classes to separate files")
    extract.add_argument("source", type=Path, help="Source file")
    extract.add_argument("target_dir", type=Path, help="Target directory")
    extract.add_argument("elements", nargs="+", help="Names of classes/functions to extract")
    
    # Analyze command
    analyze = subparsers.add_parser("analyze", help="Analyze a Python file")
    analyze.add_argument("file", type=Path, help="File to analyze")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    tool = PythonCopyTool()
    tool.verbose = args.verbose
    
    try:
        if args.command == "copy-class":
            success = tool.copy_element(args.source, args.target, args.class_name)
            return 0 if success else 1
            
        elif args.command == "copy-function":
            success = tool.copy_element(args.source, args.target, args.function_name)
            return 0 if success else 1
            
        elif args.command == "extract-classes":
            success = tool.extract_multiple(args.source, args.target_dir, args.elements)
            return 0 if success else 1
            
        elif args.command == "analyze":
            tool.analyze_command(args.file)
            return 0
            
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())