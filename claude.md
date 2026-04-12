# Claude Tool Usage Guide

## Current Date: November 2025

## Important: Working in a Restricted Shell Environment

When using Claude in this environment, basic Unix commands are **NOT available**. This includes:
- `ls`, `find` - for file listing/searching
- `grep`, `rg` - for content searching
- `cat`, `head`, `tail` - for reading files
- `sed`, `awk` - for file editing
- `echo`, `printf` - for output

## Use These Specialized Tools Instead

### 1. File Operations

#### Listing/Finding Files
```
❌ DON'T: ls -la
✅ DO: Use Glob tool with pattern "*" or ".*"

❌ DON'T: find . -name "*.py"
✅ DO: Use Glob tool with pattern "**/*.py"
```

#### Reading Files
```
❌ DON'T: cat filename.txt
✅ DO: Use Read tool with file_path="/full/path/to/filename.txt"

❌ DON'T: head -n 20 file.txt
✅ DO: Use Read tool with limit=20
```

#### Searching Content
```
❌ DON'T: grep "pattern" file.txt
✅ DO: Use Grep tool with pattern="pattern"

❌ DON'T: grep -r "TODO" .
✅ DO: Use Grep tool with pattern="TODO"
```

#### Writing Files
```
❌ DON'T: echo "content" > file.txt
✅ DO: Use Write tool with content="content"
```

#### Editing Files
```
❌ DON'T: sed -i 's/old/new/g' file.txt
✅ DO: Use Edit tool with old_string="old", new_string="new"
```

### 2. When to Use Bash Tool

The Bash tool should ONLY be used for:
- Python scripts: `./venv/bin/python script.py`
- Git operations: `git status`, `git diff`, `git commit`
- Package managers: `npm install`, `pip install`
- Docker commands
- Other actual programs/executables

### 3. Best Practices

1. **Always use absolute paths** with Read/Write/Edit tools
2. **Use Glob for pattern matching** instead of trying ls/find commands
3. **Use Grep for searching** instead of shell grep
4. **Chain tools efficiently** - run multiple searches in parallel when possible
5. **Check file existence** with Glob before trying to Read

### 4. Example Workflow

```python
# Wrong approach (will fail):
bash: ls -la | grep ".env"  # ❌ Commands not found
bash: cat .env  # ❌ Command not found

# Correct approach:
1. Glob pattern=".*" to find hidden files
2. Read file_path="/absolute/path/.env" to read content
3. Grep pattern="API_KEY" to search for specific content
```

### 5. Common Error Messages and Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `command not found: ls` | Using shell commands | Use Glob tool |
| `command not found: cat` | Trying to read files | Use Read tool |
| `command not found: grep` | Searching content | Use Grep tool |
| `Exit code 127` | Command doesn't exist | Use appropriate tool |

### 6. Performance Tips

- **Parallel execution**: Run multiple Glob/Grep operations in parallel
- **Use specific patterns**: More specific Glob patterns are faster
- **Limit output**: Use head_limit in Grep to avoid huge outputs
- **Cache awareness**: Repeated operations may be cached

## Summary

The key to efficiency is remembering that this is a **tool-based environment**, not a traditional shell. Every file operation has a dedicated tool that's optimized for that specific task. Using the right tool saves time and avoids errors.

**Remember**: If you're typing a Unix command, stop and think - there's probably a specialized tool for that!