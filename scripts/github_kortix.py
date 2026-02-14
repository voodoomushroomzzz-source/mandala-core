#!/usr/bin/env python3
"""
GitHub Kortix Automation Script
Automates GitHub operations from instruction JSON files.
Supports surgical updates for Mandala Core modules.
"""

import json
import os
import sys
import argparse
from datetime import datetime
from github import Github, GithubException, Auth
from pathlib import Path
import shutil
import tempfile


class GitHubKortix:
    """Main class for GitHub automation via Kortix."""
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize with config file."""
        self.config = self._load_config(config_path)
        
        # Use modern authentication
        auth = Auth.Token(self.config["github"]["token"])
        self.github = Github(auth=auth, per_page=100)
        
        self.repo = self.github.get_repo(
            f"{self.config['github']['owner']}/{self.config['github']['repo']}"
        )
        self.repo_root = Path(self.config["paths"]["repo_root"]).resolve()
        self.temp_dir = None
        self.changes_made = False
    
    def _load_config(self, path: str) -> dict:
        """Load configuration from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        # Support environment variable for token
        if "${GITHUB_TOKEN}" in config["github"].get("token", ""):
            env_token = os.environ.get("GITHUB_TOKEN")
            if env_token:
                config["github"]["token"] = env_token
        return config
    
    def apply_instruction(self, instruction_path: str, dry_run: bool = True) -> dict:
        """
        Apply a single instruction file to the repository.
        
        Args:
            instruction_path: Path to JSON instruction file
            dry_run: If True, only simulate changes
        
        Returns:
            Result dictionary with status and details
        """
        with open(instruction_path, 'r', encoding='utf-8') as f:
            instruction = json.load(f)
        
        result = {
            "status": "success",
            "instruction_id": instruction.get("update_id", "unknown"),
            "branch": None,
            "commit": None,
            "pr": None,
            "operations": [],
            "errors": []
        }
        
        # Generate branch name
        branch_name = instruction.get(
            "branch_name",
            f"{self.config['defaults']['branch_prefix']}/{instruction.get('update_id', 'update')}"
        )
        
        # Create temporary directory for file operations
        self.temp_dir = tempfile.mkdtemp(prefix="kortix_")
        
        try:
            # Check if branch already exists
            branch_exists = self._branch_exists(branch_name)
            
            if not dry_run and not branch_exists:
                result["branch"] = self._create_branch(branch_name)
            elif not dry_run and branch_exists:
                result["branch"] = branch_name
                print(f"Using existing branch: {branch_name}")
            else:
                result["branch"] = branch_name
                print(f"[DRY-RUN] Would use/create branch: {branch_name}")
            
            # Apply operations with transaction support
            for idx, op in enumerate(instruction.get("operations", [])):
                print(f"\n🔄 Operation {idx+1}: {op.get('type', 'unknown')}")
                op_result = self._apply_operation(op, branch_name, dry_run)
                result["operations"].append(op_result)
                
                if op_result["status"] == "failed":
                    result["status"] = "failed"
                    result["errors"].append({
                        "operation": idx,
                        "error": op_result.get("error", "Unknown error")
                    })
                    
                    # Rollback if this is not dry run
                    if not dry_run:
                        print("❌ Operation failed, rolling back...")
                        self._rollback(branch_name)
                        break
            
            # Create commit and PR if all operations succeeded
            if not dry_run and result["status"] == "success" and self.changes_made:
                result["commit"] = self._create_commit(
                    branch_name,
                    instruction.get("commit_message", f"Kortix: {instruction.get('update_id', 'Update')}")
                )
                
                # Create PR if configured
                if self.config["defaults"]["create_pr"]:
                    result["pr"] = self._create_pull_request(
                        branch_name,
                        instruction.get("pr_title", f"Kortix: {instruction.get('update_id', 'Update')}"),
                        instruction.get("pr_description", "Automated update via Kortix")
                    )
            
            elif not dry_run and result["status"] == "failed":
                print("❌ Operations failed, no commit created")
            
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            if not dry_run:
                self._rollback(branch_name)
        
        finally:
            # Clean up temporary directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        
        return result
    
    def _branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists."""
        try:
            self.repo.get_git_ref(f"heads/{branch_name}")
            return True
        except GithubException:
            return False
    
    def _create_branch(self, branch_name: str) -> str:
        """Create a new branch from main/master."""
        # Get default branch name
        default_branch = self.repo.default_branch
        
        # Get the SHA of the latest commit on default branch
        main_ref = self.repo.get_git_ref(f"heads/{default_branch}")
        main_sha = main_ref.object.sha
        
        # Create new branch
        self.repo.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=main_sha
        )
        
        print(f"✅ Created branch: {branch_name}")
        return branch_name
    
    def _apply_operation(self, operation: dict, branch_name: str, dry_run: bool) -> dict:
        """Apply a single operation to the repository."""
        op_type = operation.get("type")
        file_path = operation.get("file", "")
        
        result = {
            "type": op_type,
            "file": file_path,
            "status": "pending"
        }
        
        try:
            # Get file content
            content, sha = self._get_file_content(file_path, branch_name)
            
            # Apply operation based on type
            if op_type == "add_object_to_array":
                new_content = self._add_to_array(content, operation)
            elif op_type == "update_object":
                new_content = self._update_object(content, operation)
            elif op_type == "delete_object":
                new_content = self._delete_object(content, operation)
            elif op_type == "update_field":
                new_content = self._update_field(content, operation)
            elif op_type == "replace_value":
                new_content = self._replace_value(content, operation)
            else:
                result["status"] = "failed"
                result["error"] = f"Unknown operation type: {op_type}"
                return result
            
            # Update file if content changed
            if new_content != content:
                self.changes_made = True
                if not dry_run:
                    self._update_file(file_path, new_content, sha, branch_name, op_type)
                print(f"  ✅ Applied {op_type} to {file_path}")
            else:
                print(f"  ⏭️  No changes needed for {file_path}")
            
            result["status"] = "success"
            
        except ValueError as e:
            result["status"] = "failed"
            result["error"] = str(e)
            print(f"  ❌ Validation error: {e}")
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            print(f"  ❌ Error: {e}")
        
        return result
    
    def _get_file_content(self, file_path: str, branch_name: str) -> tuple:
        """Get file content from repository."""
        # 🔧 FIX: Убираем ведущий слеш, если он есть
        clean_path = file_path.lstrip('/')
        
        try:
            # Try to get from branch
            file_content = self.repo.get_contents(clean_path, ref=branch_name)
            content = file_content.decoded_content.decode('utf-8')
            sha = file_content.sha
        except GithubException:
            try:
                # Try to get from default branch
                file_content = self.repo.get_contents(clean_path, ref=self.repo.default_branch)
                content = file_content.decoded_content.decode('utf-8')
                sha = None  # Will create new file on branch
            except GithubException:
                # File doesn't exist
                content = "{}" if file_path.endswith('.json') else ""
                sha = None
        
        return content, sha
    
    def _update_file(self, file_path: str, content: str, sha: str, branch_name: str, op_type: str):
        """Update or create file on branch."""
        # 🔧 FIX: Убираем ведущий слеш, если он есть
        clean_path = file_path.lstrip('/')
        
        if sha:
            self.repo.update_file(
                path=clean_path,
                message=f"Kortix: {op_type} in {os.path.basename(file_path)}",
                content=content,
                sha=sha,
                branch=branch_name
            )
        else:
            self.repo.create_file(
                path=clean_path,
                message=f"Kortix: create {os.path.basename(file_path)}",
                content=content,
                branch=branch_name
            )
    
    def _add_to_array(self, content: str, operation: dict) -> str:
        """Add an object to a JSON array with validation."""
        data = json.loads(content)
        target_path = operation.get("target_path", "").split(".")
        new_object = operation.get("new_object", {})
        validation = operation.get("validation", {})
        
        # Navigate to target
        current = data
        for key in target_path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        array_key = target_path[-1]
        if array_key not in current:
            current[array_key] = []
        elif not isinstance(current[array_key], list):
            raise ValueError(f"Target '{array_key}' is not an array")
        
        # Check must_not_exist
        must_not_exist = validation.get("must_not_exist")
        if must_not_exist:
            for item in current[array_key]:
                if isinstance(item, dict) and item.get("id") == must_not_exist:
                    raise ValueError(f"Object with id '{must_not_exist}' already exists")
        
        # Check for duplicate new ID
        new_id = new_object.get("id")
        if new_id:
            for item in current[array_key]:
                if isinstance(item, dict) and item.get("id") == new_id:
                    raise ValueError(f"Object with id '{new_id}' already exists")
        
        current[array_key].append(new_object)
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def _update_object(self, content: str, operation: dict) -> str:
        """Update an existing object in a JSON array."""
        data = json.loads(content)
        target_path = operation.get("target_path", "").split(".")
        object_id = operation.get("object_id")
        updates = operation.get("updates", {})
        
        # Navigate to target
        current = data
        for key in target_path[:-1]:
            if key not in current:
                raise ValueError(f"Path '{key}' not found")
            current = current[key]
        
        array_key = target_path[-1]
        if array_key not in current or not isinstance(current[array_key], list):
            raise ValueError(f"Target '{array_key}' is not an array")
        
        # Find and update object
        found = False
        for item in current[array_key]:
            if isinstance(item, dict) and item.get("id") == object_id:
                item.update(updates)
                found = True
                break
        
        if not found:
            raise ValueError(f"Object with id '{object_id}' not found")
        
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def _delete_object(self, content: str, operation: dict) -> str:
        """Delete an object from a JSON array."""
        data = json.loads(content)
        target_path = operation.get("target_path", "").split(".")
        object_id = operation.get("object_id")
        
        # Navigate to target
        current = data
        for key in target_path[:-1]:
            if key not in current:
                raise ValueError(f"Path '{key}' not found")
            current = current[key]
        
        array_key = target_path[-1]
        if array_key not in current or not isinstance(current[array_key], list):
            raise ValueError(f"Target '{array_key}' is not an array")
        
        # Remove object
        original_length = len(current[array_key])
        current[array_key] = [
            item for item in current[array_key]
            if not (isinstance(item, dict) and item.get("id") == object_id)
        ]
        
        if len(current[array_key]) == original_length:
            raise ValueError(f"Object with id '{object_id}' not found")
        
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def _update_field(self, content: str, operation: dict) -> str:
        """Update a specific field in JSON."""
        data = json.loads(content)
        target_path = operation.get("target_path", "").split(".")
        new_value = operation.get("value")
        
        # Navigate and update
        current = data
        for key in target_path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[target_path[-1]] = new_value
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def _replace_value(self, content: str, operation: dict) -> str:
        """Replace a specific value in JSON."""
        data = json.loads(content)
        search_value = operation.get("search_value")
        new_value = operation.get("new_value")
        
        def replace_recursive(obj):
            if isinstance(obj, dict):
                for key in list(obj.keys()):
                    if obj[key] == search_value:
                        obj[key] = new_value
                    elif isinstance(obj[key], (dict, list)):
                        replace_recursive(obj[key])
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    if item == search_value:
                        obj[i] = new_value
                    elif isinstance(item, (dict, list)):
                        replace_recursive(item)
        
        replace_recursive(data)
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def _create_commit(self, branch_name: str, message: str) -> dict:
        """Get commit info."""
        branch = self.repo.get_branch(branch_name)
        commit = branch.commit
        return {
            "sha": commit.sha,
            "message": commit.commit.message,
            "url": commit.html_url
        }
    
    def _create_pull_request(self, branch_name: str, title: str, body: str) -> dict:
        """Create a pull request."""
        try:
            pr = self.repo.create_pull(
                title=title,
                body=body,
                head=branch_name,
                base=self.repo.default_branch
            )
            print(f"✅ Created PR #{pr.number}: {pr.html_url}")
            return {
                "number": pr.number,
                "title": pr.title,
                "url": pr.html_url
            }
        except GithubException as e:
            # PR might already exist
            if e.status == 422:
                pulls = self.repo.get_pulls(state='open', head=branch_name)
                for pr in pulls:
                    if pr.head.ref == branch_name:
                        print(f"ℹ️  PR already exists: #{pr.number}")
                        return {
                            "number": pr.number,
                            "title": pr.title,
                            "url": pr.html_url
                        }
            raise
    
    def _rollback(self, branch_name: str):
        """Rollback changes by deleting the branch if it was newly created."""
        try:
            # Check if branch was created in this session
            if self._branch_exists(branch_name):
                # Get all commits on branch
                branch = self.repo.get_branch(branch_name)
                commits = list(self.repo.get_commits(sha=branch_name))
                
                # If only one commit (the branch creation), delete it
                if len(commits) <= 1:
                    ref = self.repo.get_git_ref(f"heads/{branch_name}")
                    ref.delete()
                    print(f"🗑️  Deleted branch {branch_name} (rollback)")
        
        except Exception as e:
            print(f"⚠️  Rollback warning: {e}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="GitHub Kortix Automation"
    )
    parser.add_argument(
        "-f", "--file",
        required=True,
        help="Path to instruction JSON file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate changes without applying them"
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config file (default: config.json)"
    )
    
    args = parser.parse_args()
    
    # Initialize
    try:
        kortix = GitHubKortix(args.config)
    except Exception as e:
        print(f"Error initializing: {e}")
        sys.exit(1)
    
    # Apply instruction
    print(f"\n📋 Processing: {args.file}")
    if args.dry_run:
        print("🔍 DRY RUN MODE - no changes will be made\n")
    
    result = kortix.apply_instruction(args.file, dry_run=args.dry_run)
    
    # Output result
    print("\n" + "="*50)
    print("📊 RESULT:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Exit with appropriate code
    if result["status"] == "failed":
        print("\n❌ Operation failed")
        sys.exit(1)
    else:
        print(f"\n✅ {result['status'].upper()}")
        if result.get("pr"):
            print(f"🔗 PR: {result['pr']['url']}")


if __name__ == "__main__":
    main()
