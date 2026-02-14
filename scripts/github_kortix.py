#!/usr/bin/env python3
"""
GitHub Kortix Automation Script
Automates GitHub operations from instruction JSON files.
"""

import json
import os
import sys
import argparse
from datetime import datetime
from github import Github, GithubException
from pathlib import Path


class GitHubKortix:
    """Main class for GitHub automation via Kortix."""
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize with config file."""
        self.config = self._load_config(config_path)
        self.github = Github(
            self.config["github"]["token"],
            per_page=100
        )
        self.repo = self.github.get_repo(
            f"{self.config['github']['owner']}/{self.config['github']['repo']}"
        )
        self.repo_root = Path(self.config["paths"]["repo_root"])
    
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
            "operations": []
        }
        
        # Generate branch name
        branch_name = instruction.get(
            "branch_name",
            f"{self.config['defaults']['branch_prefix']}/{instruction.get('update_id', 'update')}"
        )
        
        try:
            # Get or create branch
            if not dry_run:
                result["branch"] = self._create_branch(branch_name)
            else:
                result["branch"] = branch_name
                print(f"[DRY-RUN] Would create branch: {branch_name}")
            
            # Apply operations
            for op in instruction.get("operations", []):
                op_result = self._apply_operation(op, branch_name, dry_run)
                result["operations"].append(op_result)
                
                if op_result["status"] == "failed":
                    result["status"] = "partial"
            
            # Create commit if not dry-run
            if not dry_run and result["status"] != "failed":
                result["commit"] = self._create_commit(
                    branch_name,
                    instruction.get("commit_message", f"Kortix: {instruction.get('update_id', 'Update')}")
                )
                
                # Create PR if configured
                if self.config["defaults"]["create_pr"]:
                    result["pr"] = self._create_pull_request(
                        branch_name,
                        instruction.get("pr_title", f"Kortix: {instruction.get('update_id', 'Update')}"),
                        instruction.get("pr_body", "Automated update via Kortix")
                    )
        
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
        
        return result
    
    def _create_branch(self, branch_name: str) -> str:
        """Create a new branch from main/master."""
        # Get default branch name
        default_branch = self.repo.default_branch
        
        # Get the SHA of the latest commit on default branch
        main_ref = self.repo.get_git_ref(f"heads/{default_branch}")
        main_sha = main_ref.object.sha
        
        # Create new branch
        new_branch = self.repo.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=main_sha
        )
        
        print(f"Created branch: {branch_name}")
        return branch_name
    
    def _apply_operation(self, operation: dict, branch_name: str, dry_run: bool) -> dict:
        """Apply a single operation to the repository."""
        op_type = operation.get("type")
        file_path = operation.get("file", "")
        full_path = self.repo_root / file_path
        
        result = {
            "type": op_type,
            "file": file_path,
            "status": "pending"
        }
        
        if dry_run:
            print(f"[DRY-RUN] Would apply {op_type} to {file_path}")
            result["status"] = "success"
            return result
        
        # Get file content from branch
        try:
            file_content = self.repo.get_contents(str(full_path), ref=branch_name)
            current_content = file_content.decoded_content.decode('utf-8')
            current_sha = file_content.sha
        except GithubException:
            # File doesn't exist on branch, get from main
            file_content = self.repo.get_contents(str(full_path), ref=self.repo.default_branch)
            current_content = file_content.decoded_content.decode('utf-8')
            current_sha = None
        
        # Apply operation based on type
        if op_type == "add_object_to_array":
            new_content = self._add_to_array(current_content, operation)
        elif op_type == "update_field":
            new_content = self._update_field(current_content, operation)
        elif op_type == "replace_value":
            new_content = self._replace_value(current_content, operation)
        else:
            result["status"] = "failed"
            result["error"] = f"Unknown operation type: {op_type}"
            return result
        
        # Update file on branch
        if current_sha:
            self.repo.update_file(
                path=str(full_path),
                message=f"Kortix: {op_type} in {file_path}",
                content=new_content,
                sha=current_sha,
                branch=branch_name
            )
        else:
            self.repo.create_file(
                path=str(full_path),
                message=f"Kortix: create {file_path}",
                content=new_content,
                branch=branch_name
            )
        
        print(f"Applied {op_type} to {file_path}")
        result["status"] = "success"
        return result
    
    def _add_to_array(self, content: str, operation: dict) -> str:
        """Add an object to a JSON array."""
        data = json.loads(content)
        target_path = operation.get("target_path", "").split(".")
        new_object = operation.get("new_object", {})
        
        # Navigate to target array
        current = data
        for key in target_path[:-1]:
            current = current.get(key, {})
        
        array_key = target_path[-1]
        if array_key not in current:
            current[array_key] = []
        
        current[array_key].append(new_object)
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def _update_field(self, content: str, operation: dict) -> str:
        """Update a specific field in JSON."""
        data = json.loads(content)
        target_path = operation.get("target_path", "").split(".")
        new_value = operation.get("value", {})
        
        # Navigate and update
        current = data
        for key in target_path[:-1]:
            current = current.get(key, {})
        
        current[target_path[-1]] = new_value
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def _replace_value(self, content: str, operation: dict) -> str:
        """Replace a specific value in JSON."""
        data = json.loads(content)
        search_value = operation.get("search_value")
        new_value = operation.get("new_value")
        
        def replace_recursive(obj):
            if isinstance(obj, dict):
                for key in obj:
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
        """Create a commit on the branch."""
        commit = self.repo.get_branch(branch_name).commit
        return {
            "sha": commit.sha,
            "message": commit.message,
            "url": commit.html_url
        }
    
    def _create_pull_request(self, branch_name: str, title: str, body: str) -> dict:
        """Create a pull request."""
        pr = self.repo.create_pull(
            title=title,
            body=body,
            head=branch_name,
            base=self.repo.default_branch
        )
        return {
            "number": pr.number,
            "title": pr.title,
            "url": pr.html_url
        }


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
    result = kortix.apply_instruction(args.file, dry_run=args.dry_run)
    
    # Output result
    print("\n" + "="*50)
    print("RESULT:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Exit with appropriate code
    if result["status"] == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
