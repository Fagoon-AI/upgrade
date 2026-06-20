#!/usr/bin/env python3
"""
Vibe Code Mode: Rust → Python Migration Helper

This script helps convert patterns from the Rust Goose codebase to Python equivalents.
It can:
1. Parse Rust code structures and generate Python models
2. Extract provider implementations and create Python adapters
3. Scan for tool definitions and generate Python registry entries
4. Create stub implementations for services

Usage:
    python migrate_from_rust.py <rust_codebase_path> <output_python_path>
"""

import os
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

@dataclass
class RustStruct:
    name: str
    fields: Dict[str, str]  # field_name -> type
    doc: Optional[str] = None

@dataclass
class RustFunction:
    name: str
    params: List[Tuple[str, str]]  # (param_name, param_type)
    return_type: str
    doc: Optional[str] = None

class RustToQuickstart:
    """Analyzer for Rust Goose code → Python migration"""
    
    def __init__(self, rust_root: Path):
        self.rust_root = Path(rust_root)
        self.structs: List[RustStruct] = []
        self.functions: List[RustFunction] = []
        self.providers: List[str] = []
    
    def analyze_crates(self) -> None:
        """Scan Rust crates for structures and patterns"""
        
        crates_path = self.rust_root / "crates"
        if not crates_path.exists():
            print(f"⚠️  No 'crates' directory found at {crates_path}")
            return
        
        # Scan key crates
        for crate_name in ["goose", "goose-server", "goose-mcp"]:
            crate_path = crates_path / crate_name / "src"
            if crate_path.exists():
                print(f"📁 Scanning {crate_name}...")
                self._scan_crate(crate_path)
    
    def _scan_crate(self, crate_path: Path) -> None:
        """Scan a single crate for patterns"""
        
        for rs_file in crate_path.rglob("*.rs"):
            content = rs_file.read_text()
            self._extract_structs(content)
            self._extract_functions(content)
            self._extract_providers(content)
    
    def _extract_structs(self, content: str) -> None:
        """Extract Rust struct definitions"""
        
        # Regex to match: pub struct Name { fields }
        struct_pattern = r'pub struct (\w+)\s*\{([^}]*)\}'
        
        for match in re.finditer(struct_pattern, content):
            name = match.group(1)
            fields_text = match.group(2)
            fields = {}
            
            # Extract individual fields
            field_pattern = r'(\w+):\s*([^,}]+)'
            for field_match in re.finditer(field_pattern, fields_text):
                field_name = field_match.group(1)
                field_type = field_match.group(2).strip()
                fields[field_name] = field_type
            
            if fields:
                self.structs.append(RustStruct(name=name, fields=fields))
    
    def _extract_functions(self, content: str) -> None:
        """Extract Rust async function signatures"""
        
        # Regex to match: pub async fn name(...) -> Type
        func_pattern = r'pub async fn (\w+)\s*\(([^)]*)\)\s*->\s*([^{]+)'
        
        for match in re.finditer(func_pattern, content):
            name = match.group(1)
            params_text = match.group(2)
            return_type = match.group(3).strip()
            
            params = []
            param_pattern = r'(\w+):\s*([^,)]+)'
            for param_match in re.finditer(param_pattern, params_text):
                param_name = param_match.group(1)
                param_type = param_match.group(2).strip()
                params.append((param_name, param_type))
            
            if name not in ["new", "default"]:  # Skip constructors
                self.functions.append(RustFunction(
                    name=name,
                    params=params,
                    return_type=return_type,
                ))
    
    def _extract_providers(self, content: str) -> None:
        """Extract LLM provider patterns"""
        
        provider_pattern = r'struct (\w+Provider|impl.*Provider)'
        for match in re.finditer(provider_pattern, content):
            provider = match.group(1)
            if "Provider" in provider and provider not in self.providers:
                self.providers.append(provider)
    
    def generate_python_models(self) -> str:
        """Generate Python Pydantic models from Rust structs"""
        
        if not self.structs:
            return "# No structs found to convert\n"
        
        output = "# Auto-generated from Rust codebase\nfrom pydantic import BaseModel\nfrom typing import Optional\n\n"
        
        rust_to_py_type = {
            "String": "str",
            "u32": "int",
            "u64": "int",
            "f32": "float",
            "f64": "float",
            "bool": "bool",
            "Vec": "List",
            "Option": "Optional",
            "Result": "Union",
            "HashMap": "Dict",
        }
        
        for struct in self.structs:
            output += f"class {struct.name}(BaseModel):\n"
            
            if not struct.fields:
                output += "    pass\n\n"
                continue
            
            for field_name, field_type in struct.fields.items():
                # Convert Rust types to Python
                py_type = field_type
                for rust_type, py_type_replacement in rust_to_py_type.items():
                    if rust_type in py_type:
                        py_type = py_type.replace(rust_type, py_type_replacement)
                
                # Handle Option types (nullable)
                if "Option" in py_type:
                    py_type = py_type.replace("Optional[", "").replace("]", "")
                    output += f"    {field_name}: Optional[{py_type}] = None\n"
                else:
                    output += f"    {field_name}: {py_type}\n"
            
            output += "\n"
        
        return output
    
    def generate_service_stubs(self) -> str:
        """Generate Python service class stubs"""
        
        if not self.functions:
            return "# No functions found to convert\n"
        
        output = "# Auto-generated service stubs\nimport logging\nfrom typing import Any\n\nlogger = logging.getLogger(__name__)\n\n"
        
        # Group functions by prefix
        service_methods: Dict[str, List[RustFunction]] = {}
        
        for func in self.functions:
            # Extract service name from function name
            parts = func.name.split('_')
            service = parts[0].title() if parts else "General"
            
            if service not in service_methods:
                service_methods[service] = []
            service_methods[service].append(func)
        
        for service_name, methods in service_methods.items():
            output += f"class {service_name}Service:\n"
            output += '    """Auto-generated from Rust codebase"""\n\n'
            
            for method in methods:
                params_str = ", ".join([f"{name}: {self._py_type(ptype)}" for name, ptype in method.params])
                output += f"    async def {method.name}(self, {params_str}) -> Any:\n"
                output += f'        """TODO: Implement {method.name}"""\n'
                output += "        logger.info(f\"Called {method.name}\")\n"
                output += "        # Implementation here\n"
                output += "        pass\n\n"
            
            output += "\n"
        
        return output
    
    def generate_provider_adapters(self) -> str:
        """Generate Python provider adapter stubs"""
        
        if not self.providers:
            return "# No providers found to convert\n"
        
        output = "# Auto-generated provider adapters\nfrom abc import ABC, abstractmethod\nimport logging\n\nlogger = logging.getLogger(__name__)\n\n"
        
        output += "class BaseLLMProvider(ABC):\n"
        output += '    """Base provider interface"""\n\n'
        output += "    @abstractmethod\n"
        output += "    async def generate(self, prompt: str, **kwargs) -> str:\n"
        output += '        """Generate response from prompt"""\n'
        output += "        pass\n\n"
        
        for provider in self.providers:
            provider_name = provider.replace("Provider", "").replace("impl", "").strip()
            output += f"class {provider_name}Provider(BaseLLMProvider):\n"
            output += f'    """Adapter for {provider_name}"""\n\n'
            output += "    def __init__(self, api_key: str):\n"
            output += "        self.api_key = api_key\n\n"
            output += "    async def generate(self, prompt: str, **kwargs) -> str:\n"
            output += '        """Generate response from prompt"""\n'
            output += f"        logger.info(f\"Calling {provider_name}\")\n"
            output += "        # TODO: Implement API call\n"
            output += "        return f\"Response from {provider_name}\"\n\n"
        
        return output
    
    def _py_type(self, rust_type: str) -> str:
        """Convert Rust type to Python"""
        mapping = {
            "String": "str",
            "u32": "int",
            "u64": "int",
            "f32": "float",
            "f64": "float",
            "bool": "bool",
            "Vec": "List",
            "Option": "Optional",
        }
        
        for rust, py in mapping.items():
            if rust in rust_type:
                rust_type = rust_type.replace(rust, py)
        
        return rust_type if rust_type else "Any"
    
    def generate_migration_report(self) -> str:
        """Generate a comprehensive migration report"""
        
        output = "# Vibe Code Mode: Rust → Python Migration Report\n\n"
        output += f"## Scanned: {self.rust_root}\n\n"
        
        output += f"### Structures Found: {len(self.structs)}\n"
        for struct in self.structs[:5]:  # Show first 5
            output += f"- {struct.name} ({len(struct.fields)} fields)\n"
        if len(self.structs) > 5:
            output += f"- ... and {len(self.structs) - 5} more\n\n"
        
        output += f"### Functions Found: {len(self.functions)}\n"
        for func in self.functions[:5]:  # Show first 5
            output += f"- {func.name}({len(func.params)} params) -> {func.return_type}\n"
        if len(self.functions) > 5:
            output += f"- ... and {len(self.functions) - 5} more\n\n"
        
        output += f"### Providers Found: {len(self.providers)}\n"
        for provider in self.providers:
            output += f"- {provider}\n"
        
        output += "\n## Recommendations\n\n"
        output += "1. Review auto-generated models for accuracy\n"
        output += "2. Implement provider adapters with actual API calls\n"
        output += "3. Add error handling to service stubs\n"
        output += "4. Test against actual Rust implementation behavior\n"
        
        return output

class ProjectGenerator:
    """Generate complete Python project structure"""
    
    def __init__(self, output_root: Path):
        self.output_root = Path(output_root)
    
    def create_structure(self) -> None:
        """Create Python project directory structure"""
        
        directories = [
            "config",
            "core",
            "schemas",
            "services",
            "repositories",
            "models",
            "api/routes",
            "utils",
            "tests",
            "sandbox/runtime",
        ]
        
        for d in directories:
            (self.output_root / d).mkdir(parents=True, exist_ok=True)
            # Create __init__.py
            init_file = self.output_root / d / "__init__.py"
            if not init_file.exists():
                init_file.touch()
        
        print(f"✅ Created project structure at {self.output_root}")
    
    def write_gitignore(self) -> None:
        """Create .gitignore"""
        
        gitignore = self.output_root / ".gitignore"
        content = """venv/
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.env
.env.local
.vscode/
.idea/
*.db
.pytest_cache/
.coverage
htmlcov/
"""
        gitignore.write_text(content)
        print(f"✅ Created .gitignore")
    
    def write_requirements(self) -> None:
        """Create requirements.txt"""
        
        requirements = self.output_root / "requirements.txt"
        content = """fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0
httpx==0.25.1
python-dotenv==1.0.0
anthropic==0.7.0
openai==1.3.0
google-cloud-aiplatform==1.38.0
aiofiles==23.2.1
sqlalchemy==2.0.23
pytest==7.4.3
pytest-asyncio==0.21.1
"""
        requirements.write_text(content)
        print(f"✅ Created requirements.txt")

def main():
    parser = argparse.ArgumentParser(
        description="Migrate Rust Goose codebase to Python Vibe Code Mode"
    )
    parser.add_argument(
        "rust_path",
        help="Path to Rust Goose codebase",
        type=str,
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output directory for Python project (default: ./vibe-code-python)",
        type=str,
        default="vibe-code-python",
    )
    parser.add_argument(
        "--generate-project",
        action="store_true",
        help="Generate complete project structure",
    )
    parser.add_argument(
        "--models-only",
        action="store_true",
        help="Only generate Python models",
    )
    parser.add_argument(
        "--services-only",
        action="store_true",
        help="Only generate service stubs",
    )
    
    args = parser.parse_args()
    
    rust_root = Path(args.rust_path)
    output_root = Path(args.output)
    
    if not rust_root.exists():
        print(f"❌ Rust codebase not found at {rust_root}")
        return 1
    
    print(f"🔍 Analyzing Rust codebase at {rust_root}...")
    
    analyzer = RustToQuickstart(rust_root)
    analyzer.analyze_crates()
    
    # Generate project structure if requested
    if args.generate_project:
        output_root.mkdir(parents=True, exist_ok=True)
        generator = ProjectGenerator(output_root)
        generator.create_structure()
        generator.write_gitignore()
        generator.write_requirements()
    
    # Generate models
    if args.models_only or not args.services_only:
        models_file = output_root / "models" / "auto_generated.py"
        models_file.parent.mkdir(parents=True, exist_ok=True)
        models_file.write_text(analyzer.generate_python_models())
        print(f"✅ Generated models → {models_file}")
    
    # Generate services
    if args.services_only or not args.models_only:
        services_file = output_root / "services" / "auto_generated.py"
        services_file.parent.mkdir(parents=True, exist_ok=True)
        services_file.write_text(analyzer.generate_service_stubs())
        print(f"✅ Generated services → {services_file}")
    
    # Generate providers
    providers_file = output_root / "core" / "auto_generated_providers.py"
    providers_file.parent.mkdir(parents=True, exist_ok=True)
    providers_file.write_text(analyzer.generate_provider_adapters())
    print(f"✅ Generated providers → {providers_file}")
    
    # Generate report
    report_file = output_root / "MIGRATION_REPORT.md"
    report_file.write_text(analyzer.generate_migration_report())
    print(f"✅ Generated report → {report_file}")
    
    print("\n✨ Migration helper completed!")
    print(f"📂 Output directory: {output_root}")
    print("\n📋 Next steps:")
    print("1. Review auto-generated files")
    print("2. Implement provider API calls")
    print("3. Add error handling")
    print("4. Test against Rust behavior")
    
    return 0

if __name__ == "__main__":
    exit(main())
