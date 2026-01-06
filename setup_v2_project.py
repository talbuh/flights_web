#!/usr/bin/env python3
"""
Setup v1/v2 project structure for flights_bot
- Backs up v1 (current working version)
- Creates v2 development folder
- Preserves everything so v1 keeps working
"""

import os
import shutil
import sys
from pathlib import Path

def main():
    print("🚀 Setting up v1/v2 project structure...")
    print()
    
    # Get current directory
    current_dir = Path.cwd()
    print(f"📁 Working in: {current_dir}")
    print()
    
    # Check if we're in the right place
    if not (current_dir / "app.py").exists():
        print("❌ Error: app.py not found!")
        print("   Run this script from flights_bot directory.")
        sys.exit(1)
    
    # Step 1: Create v1_original (backup of current working version)
    v1_dir = current_dir / "v1_original"
    if v1_dir.exists():
        response = input(f"⚠️  {v1_dir} already exists. Overwrite? (y/n): ")
        if response.lower() != 'y':
            print("Skipping v1_original backup.")
        else:
            shutil.rmtree(v1_dir)
            print(f"🗑️  Removed old {v1_dir}")
    
    if not v1_dir.exists():
        print(f"📦 Creating v1_original backup...")
        v1_dir.mkdir()
        
        # Copy essential files
        files_to_copy = [
            "app.py",
            "requirements.txt",
            "runtime.txt",
            "Procfile",
            "wsgi.py",
            ".gitignore",
        ]
        
        for file in files_to_copy:
            src = current_dir / file
            if src.exists():
                shutil.copy2(src, v1_dir / file)
                print(f"   ✅ Copied {file}")
        
        # Copy directories
        dirs_to_copy = ["templates", "static"]
        for dir_name in dirs_to_copy:
            src_dir = current_dir / dir_name
            if src_dir.exists():
                shutil.copytree(src_dir, v1_dir / dir_name)
                print(f"   ✅ Copied {dir_name}/")
        
        # Copy database (important!)
        if (current_dir / "jobs.db").exists():
            shutil.copy2(current_dir / "jobs.db", v1_dir / "jobs.db")
            print(f"   ✅ Copied jobs.db")
        
        print("✅ v1_original backup complete!")
    print()
    
    # Step 2: Create v2_development (copy for new development)
    v2_dir = current_dir / "v2_development"
    if v2_dir.exists():
        response = input(f"⚠️  {v2_dir} already exists. Overwrite? (y/n): ")
        if response.lower() != 'y':
            print("Skipping v2_development creation.")
        else:
            shutil.rmtree(v2_dir)
            print(f"🗑️  Removed old {v2_dir}")
    
    if not v2_dir.exists():
        print(f"📦 Creating v2_development folder...")
        v2_dir.mkdir()
        
        # Copy everything from v1
        files_to_copy = [
            "app.py",
            "requirements.txt",
            "runtime.txt",
            "Procfile",
            "wsgi.py",
            ".gitignore",
        ]
        
        for file in files_to_copy:
            src = current_dir / file
            if src.exists():
                shutil.copy2(src, v2_dir / file)
                print(f"   ✅ Copied {file}")
        
        # Copy directories
        dirs_to_copy = ["templates", "static"]
        for dir_name in dirs_to_copy:
            src_dir = current_dir / dir_name
            if src_dir.exists():
                shutil.copytree(src_dir, v2_dir / dir_name)
                print(f"   ✅ Copied {dir_name}/")
        
        # Create fresh database for v2 (don't copy - start clean)
        print(f"   ℹ️  v2 will use fresh jobs.db (create tables later)")
        
        print("✅ v2_development ready for development!")
    print()
    
    # Step 3: Update v2 requirements.txt with new dependencies
    v2_requirements = v2_dir / "requirements.txt"
    if v2_requirements.exists():
        print("📝 Updating v2 requirements.txt with auth dependencies...")
        with open(v2_requirements, 'a') as f:
            f.write("\n# Authentication for v2\n")
            f.write("descope>=1.0.0\n")
        print("   ✅ Added descope to requirements.txt")
    print()
    
    # Step 4: Create README in each folder
    print("📝 Creating README files...")
    
    v1_readme = v1_dir / "README.md"
    with open(v1_readme, 'w') as f:
        f.write("# v1_original - Stable Working Version\n\n")
        f.write("This is the original working version (free, no auth).\n\n")
        f.write("**DO NOT MODIFY** - Keep as backup/reference.\n\n")
        f.write("## Run locally:\n")
        f.write("```bash\n")
        f.write("cd v1_original\n")
        f.write("python app.py\n")
        f.write("# Opens on http://localhost:5000\n")
        f.write("```\n")
    print(f"   ✅ Created {v1_readme}")
    
    v2_readme = v2_dir / "README.md"
    with open(v2_readme, 'w') as f:
        f.write("# v2_development - New Version with Auth\n\n")
        f.write("This is the development version with:\n")
        f.write("- Descope authentication (Google login)\n")
        f.write("- User quotas\n")
        f.write("- Stripe payments\n\n")
        f.write("## Setup:\n")
        f.write("```bash\n")
        f.write("cd v2_development\n")
        f.write("pip install -r requirements.txt\n")
        f.write("```\n\n")
        f.write("## Run locally:\n")
        f.write("```bash\n")
        f.write("python app.py --port 5001\n")
        f.write("# Opens on http://localhost:5001\n")
        f.write("```\n\n")
        f.write("## Next steps:\n")
        f.write("1. Follow Product_Requirements_Document.md\n")
        f.write("2. Sign up for Descope (free tier)\n")
        f.write("3. Add authentication to app.py\n")
        f.write("4. Test locally\n")
        f.write("5. Deploy to PythonAnywhere when ready\n")
    print(f"   ✅ Created {v2_readme}")
    print()
    
    # Step 5: Create .gitignore entries
    gitignore = current_dir / ".gitignore"
    if gitignore.exists():
        with open(gitignore, 'a') as f:
            f.write("\n# v2 development environment\n")
            f.write("v2_development/.env\n")
            f.write("v2_development/jobs.db\n")
            f.write("v2_development/__pycache__/\n")
        print("✅ Updated .gitignore")
    print()
    
    # Summary
    print("=" * 60)
    print("✅ Setup complete!")
    print("=" * 60)
    print()
    print("📂 Project structure:")
    print(f"   {current_dir}/")
    print(f"   ├── v1_original/        ← Backup (don't touch!)")
    print(f"   │   ├── app.py")
    print(f"   │   ├── templates/")
    print(f"   │   └── jobs.db")
    print(f"   │")
    print(f"   ├── v2_development/     ← Work here!")
    print(f"   │   ├── app.py          (modify this)")
    print(f"   │   ├── templates/      (modify this)")
    print(f"   │   └── README.md       (read this)")
    print(f"   │")
    print(f"   └── Product_Requirements_Document.md")
    print()
    print("🚀 Next steps:")
    print("   1. cd v2_development")
    print("   2. Read README.md")
    print("   3. Follow Product_Requirements_Document.md")
    print("   4. Start coding!")
    print()
    print("💡 Tips:")
    print("   - v1_original stays working (for rollback)")
    print("   - Develop only in v2_development")
    print("   - Test both versions side-by-side (different ports)")
    print("   - When v2 is ready, deploy to PythonAnywhere")
    print()

if __name__ == "__main__":
    main()


