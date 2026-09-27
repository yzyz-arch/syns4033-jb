# List-Based UI Patterns for Telegram Bots

## Core Principle: Never Text-Only Lists

**Rule**: Any list output (files, users, items, search results) MUST have per-item action buttons. Text-only lists are incomplete UX and signal missing functionality.

**Pattern**: Each item in a list gets its own row of inline buttons attached to that item's entry in the message.

## File Manager Pattern (Session Example)

### The Problem
Initial version showed files but only as text:
```
📂 Files in workspace/
1. file1.txt (1.2 MB)
2. file2.py (3.5 KB)
3. data.json (256 KB)
```
❌ User can't do anything without additional menus or commands.

### The Solution
Each file entry gets its own action button row:

```markdown
📂 Files in workspace/ - Page 1/3

1. 📄 `file1.txt`
   1.2 MB • 2026-08-23 13:45
   [⚡ file1.txt] ← per-file menu button

2. 📄 `file2.py`
   3.5 KB • 2026-08-23 12:30
   [⚡ file2.py] ← per-file menu button

3. 📎 `data.json`
   256 KB • 2026-08-23 11:15
   [⚡ data.json] ← per-file menu button

[◀️ Prev] [1/3] [Next ▶️]
[🔙 Main Menu]
```

Clicking `[⚡ file1.txt]` shows action menu for that specific file:
```
📄 file1.txt

Size: 1.2 MB
Modified: 2026-08-23 13:45
Type: Text

[⬇️ Download] 
[👁️ Preview]
[✏️ Rename] [🗑️ Delete]
[🔙 Back to Browse]
```

### Code Pattern

**Step 1: Build file list with per-item buttons**

```python
async def handle_browse(query, user_id: int, workspace: Path, page: int = 0):
    files = list_workspace_files(workspace)
    
    # Pagination
    total_pages = (len(files) - 1) // FILES_PER_PAGE + 1
    page = max(0, min(page, total_pages - 1))
    start_idx = page * FILES_PER_PAGE
    end_idx = start_idx + FILES_PER_PAGE
    page_files = files[start_idx:end_idx]
    
    # Message with file list
    msg = f"📂 **Files ({len(files)} total)** - Page {page + 1}/{total_pages}\n\n"
    
    keyboard = []
    for idx, f in enumerate(page_files, start=start_idx + 1):
        icon = "📄" if f['is_text'] else "📎"
        msg += f"{idx}. {icon} `{f['name']}`\n   {f['size_fmt']} • {f['modified']}\n"
        
        # ACTION BUTTON FOR EACH FILE ← This is the key
        keyboard.append([
            InlineKeyboardButton(f"⚡ {f['name'][:30]}", callback_data=f"file_{f['name']}")
        ])
    
    # Pagination controls
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"browse_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"browse_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data="back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
```

**Step 2: Handle per-item action menu**

```python
async def handle_file_actions(query, user_id: int, workspace: Path, filename: str):
    file_path = workspace / filename
    
    # Security validation
    if not validate_path(file_path, workspace):
        await query.answer("❌ Akses ditolak!", show_alert=True)
        return
    
    # Format file info
    size = file_path.stat().st_size
    size_fmt = format_file_size(size)
    mtime = datetime.fromtimestamp(file_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
    is_text = is_text_file(file_path)
    
    msg = f"📄 **{filename}**\n\n"
    msg += f"Size: `{size_fmt}`\n"
    msg += f"Modified: `{mtime}`\n"
    msg += f"Type: {'Text' if is_text else 'Binary'}\n\n"
    msg += "Pilih aksi:"
    
    # Action buttons for this file
    keyboard = [
        [InlineKeyboardButton("⬇️ Download", callback_data=f"download_{filename}")],
    ]
    
    if is_text:
        keyboard.append([InlineKeyboardButton("👁️ Preview", callback_data=f"preview_{filename}")])
    
    keyboard.extend([
        [InlineKeyboardButton("✏️ Rename", callback_data=f"rename_{filename}"),
         InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{filename}")],
        [InlineKeyboardButton("🔙 Back to Browse", callback_data="browse_0")]
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
```

**Step 3: Callback routing for per-item actions**

```python
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # ALWAYS answer first
    
    user_id = update.effective_user.id
    workspace = get_user_workspace(user_id)
    action = query.data
    
    # Route to per-item handler
    if action.startswith("file_"):
        filename = action.replace("file_", "")
        await handle_file_actions(query, user_id, workspace, filename)
    
    elif action.startswith("download_"):
        filename = action.replace("download_", "")
        await handle_download_file(query, user_id, workspace, filename)
    
    elif action.startswith("delete_"):
        filename = action.replace("delete_", "")
        await handle_delete_file(query, user_id, workspace, filename)
    
    # ... more actions
```

## Pagination Pattern

For lists >10 items, always paginate:

```python
FILES_PER_PAGE = 10

# Calculate pages
total_pages = (len(files) - 1) // FILES_PER_PAGE + 1
page = max(0, min(page, total_pages - 1))
start_idx = page * FILES_PER_PAGE
end_idx = start_idx + FILES_PER_PAGE
page_files = files[start_idx:end_idx]

# Navigation buttons
nav_buttons = []
if page > 0:
    nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"browse_{page-1}"))
nav_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
if page < total_pages - 1:
    nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"browse_{page+1}"))
```

**Note**: The page indicator button has `callback_data="noop"` — it doesn't do anything when clicked, just shows current page. This prevents errors from "do nothing" callbacks.

## Search Results Pattern

Same as browse, but filtered list:

```python
async def handle_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    search_term = ' '.join(context.args)
    files = list_workspace_files(workspace, search_term=search_term)
    
    if not files:
        await update.message.reply_text(f"🔍 No results for: `{search_term}`")
        return
    
    msg = f"🔍 **Search Results: {search_term}**\n\nFound {len(files)} file(s):\n\n"
    
    keyboard = []
    for idx, f in enumerate(files[:20], 1):  # Limit to 20 results
        icon = "📄" if f['is_text'] else "📎"
        msg += f"{idx}. {icon} `{f['name']}`\n"
        keyboard.append([
            InlineKeyboardButton(f"⚡ {f['name'][:30]}", callback_data=f"file_{f['name']}")
        ])
    
    if len(files) > 20:
        msg += f"\n_...and {len(files) - 20} more_"
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
```

## Inline Action Menus

When a user clicks an item button, show contextual menu **without leaving the list view**:

**Bad (old pattern):**
```
List → Click item → New screen → Back → Back to list
```

**Good (inline pattern):**
```
List → Click item → Action menu (in same message, edit_message_text) → Back to list
```

**Code:**
```python
# When item clicked, EDIT the current message (don't send new one)
await query.edit_message_text(
    new_content,
    parse_mode='Markdown',
    reply_markup=new_keyboard
)

# Back button returns to list (also via edit_message_text)
await query.edit_message_text(
    list_content,
    parse_mode='Markdown',
    reply_markup=list_keyboard
)
```

Benefits:
- No message spam
- Smooth navigation (feels like a desktop app)
- Cleaner chat history

## Icon & Emoji Strategy

Use consistent icons for quick visual scanning:

```
📂 Folder/List contexts
📄 Text/Document file
📎 Generic/binary file
⚡ Action/Menu button (click for options)
⬇️ Download
📤 Upload
👁️ Preview
✏️ Edit/Rename
🗑️ Delete
📦 Archive/Zip
🔍 Search
ℹ️ Info
🔙 Back/Navigate
◀️ Previous page
▶️ Next page
✅ Success/Confirm
❌ Error/Reject
⚠️ Warning
⏳ Loading/Processing
```

## Security Considerations

**Path Validation for Per-Item Actions:**

```python
def validate_path(file_path: Path, workspace: Path) -> bool:
    """Ensure file is within user's workspace (prevent traversal)"""
    try:
        file_path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False

# Use before ANY file operation
if not validate_path(file_path, workspace):
    await query.answer("❌ Akses ditolak!", show_alert=True)
    return
```

**Callback Data Injection Prevention:**

Never trust callback_data directly. Validate and reconstruct:

```python
# WRONG - trusts callback_data as path
filename = query.data.replace("file_", "")
file_path = workspace / filename  # ← Could be malicious

# RIGHT - validate first
filename = query.data.replace("file_", "")
filename = sanitize_path(filename)  # Remove .., ~, etc.
file_path = workspace / filename
if not validate_path(file_path, workspace):
    return  # Reject malicious paths
```

## Common Pitfalls

### 1. Forgetting to Answer Callback Query
```python
# WRONG
await query.edit_message_text(new_text)  # User sees forever "loading..."

# RIGHT
await query.answer()  # ALWAYS first
await query.edit_message_text(new_text)
```

### 2. Text-Only List with No Actions
```python
# WRONG (LO's feedback)
msg = "1. file1.txt\n2. file2.txt\n3. file3.txt"
await query.edit_message_text(msg)  # User can't do anything

# RIGHT
keyboard = [
    [InlineKeyboardButton("⚡ file1.txt", callback_data="file_file1.txt")],
    [InlineKeyboardButton("⚡ file2.txt", callback_data="file_file2.txt")],
    [InlineKeyboardButton("⚡ file3.txt", callback_data="file_file3.txt")],
]
```

### 3. Button Labels Too Long
Telegram truncates long button text. Keep labels under 30 characters:

```python
# WRONG
InlineKeyboardButton("Download this very important document", callback_data="...")

# RIGHT
InlineKeyboardButton("⬇️ Download", callback_data="download_...")
# Or truncate the filename
InlineKeyboardButton(f"⚡ {filename[:30]}", callback_data=f"file_{filename}")
```

### 4. Missing Pagination Check
```python
# WRONG - crashes if fewer files than per_page
page_files = files[start:end]  # Could be empty on last page

# RIGHT
total_pages = (len(files) - 1) // FILES_PER_PAGE + 1
page = max(0, min(page, total_pages - 1))  # Clamp to valid range
start_idx = page * FILES_PER_PAGE
end_idx = start_idx + FILES_PER_PAGE
page_files = files[start_idx:end_idx]

# Handle empty list
if not files:
    msg = "No items"
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back")]]
```

## File Size Formatting

Always format bytes for readability in lists:

```python
def format_file_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

# Usage in message
msg += f"Size: {format_file_size(file.stat().st_size)}\n"
```

## Related Patterns

- **Search + Filter**: Same pagination logic, with search_term filter applied
- **User Directory**: Replace files with users, same button pattern
- **Admin Dashboard**: Paginated user/activity lists with per-item actions
- **Product Catalog**: Paginated items with "Add to Cart", "View Details", etc.

## Testing Checklist

When building list-based bots, verify:

- [ ] List shows with per-item buttons (no text-only output)
- [ ] Clicking item button shows action menu for that item
- [ ] Back button returns to list
- [ ] Pagination works (prev/next buttons)
- [ ] Empty list case handled (doesn't crash)
- [ ] Button labels are under 30 chars
- [ ] All callback_data is validated before use
- [ ] File/item operations are user-scoped (no access to other users' data)
- [ ] Error messages are user-friendly
- [ ] Chat remains readable (use edit_message_text, not repeated sends)
