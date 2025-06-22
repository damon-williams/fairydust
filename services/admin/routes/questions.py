from fastapi import APIRouter, Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional
import httpx
import os

from shared.database import get_db, Database
from shared.redis_client import get_redis
from auth import AdminAuth, get_current_admin_user, optional_admin_user

questions_router = APIRouter()

@questions_router.get("/", response_class=HTMLResponse)
async def questions_list(
    request: Request,
    category: Optional[str] = None,
    status: Optional[str] = None,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    # Build query with optional filters
    base_query = """
        SELECT q.*, 
               COUNT(r.id) as response_count
        FROM profiling_questions q
        LEFT JOIN user_question_responses r ON q.id = r.question_id
    """
    
    params = []
    where_conditions = []
    
    if category and category != "all":
        where_conditions.append("q.category = $" + str(len(params) + 1))
        params.append(category)
    
    if status == "active":
        where_conditions.append("q.is_active = true")
    elif status == "inactive":
        where_conditions.append("q.is_active = false")
    
    where_clause = ""
    if where_conditions:
        where_clause = " WHERE " + " AND ".join(where_conditions)
    
    questions = await db.fetch_all(
        f"{base_query}{where_clause} GROUP BY q.id ORDER BY q.priority DESC, q.category, q.id",
        *params
    )
    
    # Get categories for filter dropdown
    categories = await db.fetch_all("SELECT DISTINCT category FROM profiling_questions ORDER BY category")
    
    # Build filter dropdown options
    category_options = '<option value="all">All Categories</option>'
    for cat in categories:
        selected = 'selected' if category == cat["category"] else ''
        category_options += f'<option value="{cat["category"]}" {selected}>{cat["category"].title()}</option>'
    
    # Build questions table
    questions_html = ""
    for q in questions:
        status_badge = '<span class="badge bg-success">Active</span>' if q["is_active"] else '<span class="badge bg-secondary">Inactive</span>'
        type_badge = f'<span class="badge bg-light text-dark">{q["question_type"]}</span>'
        
        # Truncate long question text
        question_text = q["question_text"]
        if len(question_text) > 80:
            question_text = question_text[:80] + "..."
        
        questions_html += f"""
        <tr>
            <td>
                <strong>{question_text}</strong><br>
                <small class="text-muted">ID: {q["id"]}</small>
            </td>
            <td><span class="text-capitalize">{q["category"]}</span></td>
            <td>{type_badge}</td>
            <td><span class="badge bg-primary">{q["priority"]}</span></td>
            <td><span class="badge bg-info">{q["response_count"]}</span></td>
            <td>{status_badge}</td>
            <td>
                <button class="btn btn-sm btn-primary me-1" onclick="editQuestion('{q["id"]}')" title="Edit">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn btn-sm {'btn-success' if q["is_active"] else 'btn-warning'} me-1" 
                        onclick="toggleQuestion('{q["id"]}', '{q["question_text"][:30]}...', {str(q["is_active"]).lower()})"
                        title="{'Disable' if q["is_active"] else 'Enable'}">
                    <i class="fas fa-{'toggle-on' if q["is_active"] else 'toggle-off'}"></i>
                </button>
                <button class="btn btn-sm btn-secondary me-1" 
                        onclick="duplicateQuestion('{q["id"]}', '{q["question_text"][:30]}...')"
                        title="Duplicate">
                    <i class="fas fa-copy"></i>
                </button>
                <button class="btn btn-sm btn-danger" 
                        onclick="deleteQuestion('{q["id"]}', '{q["question_text"][:30]}...')"
                        title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        </tr>
        """
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Question Management - fairydust Admin</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            .fairy-dust {{ color: #ffd700; text-shadow: 0 0 5px rgba(255,215,0,0.5); }}
        </style>
    </head>
    <body>
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
            <div class="container-fluid">
                <a class="navbar-brand" href="/admin/dashboard">
                    <i class="fas fa-magic fairy-dust"></i> fairydust
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {admin_user['fairyname']}</span>
                    <a class="nav-link" href="/admin/logout">Logout</a>
                </div>
            </div>
        </nav>
        
        <div class="container-fluid mt-4">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1><i class="fas fa-question-circle me-2"></i>Question Management</h1>
                <div>
                    <a href="/admin/questions/new" class="btn btn-success me-2">
                        <i class="fas fa-plus"></i> Add New Question
                    </a>
                    <a href="/admin/dashboard" class="btn btn-secondary">← Back to Dashboard</a>
                </div>
            </div>
            
            <!-- Filters -->
            <div class="card mb-4">
                <div class="card-body">
                    <form method="get" class="row g-3">
                        <div class="col-md-4">
                            <label class="form-label">Category</label>
                            <select name="category" class="form-select" onchange="this.form.submit()">
                                {category_options}
                            </select>
                        </div>
                        <div class="col-md-4">
                            <label class="form-label">Status</label>
                            <select name="status" class="form-select" onchange="this.form.submit()">
                                <option value="">All Status</option>
                                <option value="active" {'selected' if status == 'active' else ''}>Active</option>
                                <option value="inactive" {'selected' if status == 'inactive' else ''}>Inactive</option>
                            </select>
                        </div>
                        <div class="col-md-4 d-flex align-items-end">
                            <button type="submit" class="btn btn-primary me-2">Filter</button>
                            <a href="/admin/questions" class="btn btn-outline-secondary">Clear</a>
                        </div>
                    </form>
                </div>
            </div>
            
            <!-- Questions Table -->
            <div class="card">
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-hover">
                            <thead>
                                <tr>
                                    <th>Question</th>
                                    <th>Category</th>
                                    <th>Type</th>
                                    <th>Priority</th>
                                    <th>Responses</th>
                                    <th>Status</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {questions_html}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function editQuestion(questionId) {{
                window.location.href = `/admin/questions/${{questionId}}/edit`;
            }}
            
            function toggleQuestion(questionId, questionText, isCurrentlyActive) {{
                const action = isCurrentlyActive ? 'disable' : 'enable';
                if (confirm(`${{action === 'enable' ? 'Enable' : 'Disable'}} question "${{questionText}}"?`)) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/admin/questions/${{questionId}}/toggle`;
                    document.body.appendChild(form);
                    form.submit();
                }}
            }}
            
            function duplicateQuestion(questionId, questionText) {{
                if (confirm(`Duplicate question "${{questionText}}"?`)) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/admin/questions/${{questionId}}/duplicate`;
                    document.body.appendChild(form);
                    form.submit();
                }}
            }}
            
            function deleteQuestion(questionId, questionText) {{
                if (confirm(`DELETE question "${{questionText}}"? This cannot be undone!`)) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = `/admin/questions/${{questionId}}/delete`;
                    document.body.appendChild(form);
                    form.submit();
                }}
            }}
        </script>
    </body>
    </html>
    """)

@questions_router.get("/new", response_class=HTMLResponse)
async def new_question_form(
    request: Request,
    admin_user: dict = Depends(get_current_admin_user)
):
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Add New Question - fairydust Admin</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            .fairy-dust {{ color: #ffd700; text-shadow: 0 0 5px rgba(255,215,0,0.5); }}
        </style>
    </head>
    <body>
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
            <div class="container-fluid">
                <a class="navbar-brand" href="/admin/dashboard">
                    <i class="fas fa-magic fairy-dust"></i> fairydust
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {admin_user['fairyname']}</span>
                    <a class="nav-link" href="/admin/logout">Logout</a>
                </div>
            </div>
        </nav>
        
        <div class="container mt-4">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1><i class="fas fa-plus-circle me-2"></i>Add New Question</h1>
                <a href="/admin/questions" class="btn btn-secondary">← Back to Questions</a>
            </div>
            
            <div class="card">
                <div class="card-body">
                    <form method="post" action="/admin/questions">
                        <div class="row">
                            <div class="col-md-8">
                                <div class="mb-3">
                                    <label class="form-label">Question ID</label>
                                    <input type="text" class="form-control" name="id" required 
                                           placeholder="e.g., cooking_experience" pattern="[a-z_]+" 
                                           title="Lowercase letters and underscores only">
                                    <div class="form-text">Unique identifier (lowercase, underscores only)</div>
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label">Question Text</label>
                                    <textarea class="form-control" name="question_text" rows="3" required 
                                              placeholder="How would you describe your cooking experience?"></textarea>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Category</label>
                                            <input type="text" class="form-control" name="category" required 
                                                   placeholder="e.g., cooking, personality, goals">
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Question Type</label>
                                            <select class="form-select" name="question_type" required onchange="updateOptionsSection()">
                                                <option value="">Select Type</option>
                                                <option value="single_choice">Single Choice</option>
                                                <option value="multi_select">Multi Select</option>
                                                <option value="scale">Scale (1-5)</option>
                                                <option value="text">Text Input</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Profile Field</label>
                                            <input type="text" class="form-control" name="profile_field" required 
                                                   placeholder="cooking_experience">
                                            <div class="form-text">Field name to store in user profile</div>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Priority</label>
                                            <input type="number" class="form-control" name="priority" value="5" min="1" max="10" required>
                                            <div class="form-text">1-10 (higher = shown earlier)</div>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label">App Context</label>
                                    <input type="text" class="form-control" name="app_context" 
                                           placeholder='["fairydust-recipe", "fairydust-inspire"]' 
                                           value='["fairydust-recipe"]'>
                                    <div class="form-text">JSON array of apps that should show this question</div>
                                </div>
                                
                                <div id="optionsSection" style="display: none;">
                                    <div class="mb-3">
                                        <label class="form-label">Options (JSON)</label>
                                        <textarea class="form-control" name="options" rows="6" 
                                                  placeholder='[{"id": "beginner", "label": "Beginner"}, {"id": "intermediate", "label": "Intermediate"}]'></textarea>
                                        <div class="form-text">JSON array of options for choice questions</div>
                                    </div>
                                </div>
                                
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" name="is_active" checked>
                                    <label class="form-check-label">
                                        Active (show to users)
                                    </label>
                                </div>
                            </div>
                            
                            <div class="col-md-4">
                                <div class="card bg-light">
                                    <div class="card-header">
                                        <h6 class="mb-0">Preview</h6>
                                    </div>
                                    <div class="card-body">
                                        <div id="questionPreview">
                                            <em>Fill out the form to see preview</em>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <hr>
                        <div class="d-flex justify-content-end">
                            <a href="/admin/questions" class="btn btn-outline-secondary me-2">Cancel</a>
                            <button type="submit" class="btn btn-success">
                                <i class="fas fa-save"></i> Create Question
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function updateOptionsSection() {{
                const questionType = document.querySelector('[name="question_type"]').value;
                const optionsSection = document.getElementById('optionsSection');
                const optionsTextarea = document.querySelector('[name="options"]');
                
                if (questionType === 'single_choice' || questionType === 'multi_select') {{
                    optionsSection.style.display = 'block';
                    optionsTextarea.required = true;
                    
                    if (questionType === 'single_choice') {{
                        optionsTextarea.placeholder = '[{{"id": "beginner", "label": "Beginner"}}, {{"id": "intermediate", "label": "Intermediate"}}, {{"id": "advanced", "label": "Advanced"}}]';
                    }} else {{
                        optionsTextarea.placeholder = '[{{"id": "option1", "label": "Option 1"}}, {{"id": "option2", "label": "Option 2"}}, {{"id": "option3", "label": "Option 3"}}]';
                    }}
                }} else if (questionType === 'scale') {{
                    optionsSection.style.display = 'block';
                    optionsTextarea.required = true;
                    optionsTextarea.placeholder = '{{"min": 1, "max": 5, "labels": {{"1": "Not at all", "3": "Somewhat", "5": "Very much"}}}}';
                }} else {{
                    optionsSection.style.display = 'none';
                    optionsTextarea.required = false;
                    optionsTextarea.value = '';
                }}
                
                updatePreview();
            }}
            
            function updatePreview() {{
                const questionText = document.querySelector('[name="question_text"]').value;
                const questionType = document.querySelector('[name="question_type"]').value;
                const preview = document.getElementById('questionPreview');
                
                if (questionText && questionType) {{
                    let previewHtml = `<strong>${{questionText}}</strong><br><br>`;
                    
                    if (questionType === 'single_choice') {{
                        previewHtml += '<div class="form-check"><input class="form-check-input" type="radio" disabled><label class="form-check-label">Option 1</label></div>';
                        previewHtml += '<div class="form-check"><input class="form-check-input" type="radio" disabled><label class="form-check-label">Option 2</label></div>';
                    }} else if (questionType === 'multi_select') {{
                        previewHtml += '<div class="form-check"><input class="form-check-input" type="checkbox" disabled><label class="form-check-label">Option 1</label></div>';
                        previewHtml += '<div class="form-check"><input class="form-check-input" type="checkbox" disabled><label class="form-check-label">Option 2</label></div>';
                    }} else if (questionType === 'scale') {{
                        previewHtml += '<input type="range" class="form-range" min="1" max="5" disabled><div class="d-flex justify-content-between small"><span>1</span><span>5</span></div>';
                    }} else if (questionType === 'text') {{
                        previewHtml += '<input type="text" class="form-control" placeholder="User types here..." disabled>';
                    }}
                    
                    preview.innerHTML = previewHtml;
                }} else {{
                    preview.innerHTML = '<em>Fill out the form to see preview</em>';
                }}
            }}
            
            // Update preview on input
            document.querySelector('[name="question_text"]').addEventListener('input', updatePreview);
            document.querySelector('[name="question_type"]').addEventListener('change', updatePreview);
        </script>
    </body>
    </html>
    """)

@questions_router.post("/")
async def create_question(
    request: Request,
    id: str = Form(...),
    question_text: str = Form(...),
    category: str = Form(...),
    question_type: str = Form(...),
    profile_field: str = Form(...),
    priority: int = Form(...),
    app_context: str = Form(...),
    options: str = Form(""),
    is_active: Optional[str] = Form(None),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    try:
        # Parse app_context JSON
        import json
        app_context_json = json.loads(app_context) if app_context else []
        
        # Parse options JSON if provided
        options_json = json.loads(options) if options else None
        
        # Convert is_active checkbox
        is_active_bool = is_active is not None
        
        # Insert question
        await db.execute(
            """
            INSERT INTO profiling_questions 
            (id, category, question_text, question_type, profile_field, priority, app_context, options, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9)
            """,
            id, category, question_text, question_type, profile_field, priority,
            json.dumps(app_context_json), json.dumps(options_json) if options_json else None, is_active_bool
        )
        
        return RedirectResponse(url="/admin/questions?created=1", status_code=302)
        
    except Exception as e:
        # Handle errors (duplicate ID, invalid JSON, etc.)
        return HTMLResponse(f"""
            <script>
                alert('Error creating question: {str(e)}');
                window.history.back();
            </script>
        """)

@questions_router.get("/{question_id}/edit", response_class=HTMLResponse)
async def edit_question_form(
    request: Request,
    question_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    # Get existing question
    question = await db.fetch_one(
        "SELECT * FROM profiling_questions WHERE id = $1", question_id
    )
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Convert JSONB fields to strings for the form
    import json
    app_context_str = json.dumps(question["app_context"]) if question["app_context"] else '[]'
    options_str = json.dumps(question["options"]) if question["options"] else ''
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Edit Question - fairydust Admin</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            .fairy-dust {{ color: #ffd700; text-shadow: 0 0 5px rgba(255,215,0,0.5); }}
        </style>
    </head>
    <body>
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
            <div class="container-fluid">
                <a class="navbar-brand" href="/admin/dashboard">
                    <i class="fas fa-magic fairy-dust"></i> fairydust
                </a>
                <div class="navbar-nav ms-auto">
                    <span class="navbar-text me-3">Welcome, {admin_user['fairyname']}</span>
                    <a class="nav-link" href="/admin/logout">Logout</a>
                </div>
            </div>
        </nav>
        
        <div class="container mt-4">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1><i class="fas fa-edit me-2"></i>Edit Question</h1>
                <a href="/admin/questions" class="btn btn-secondary">← Back to Questions</a>
            </div>
            
            <div class="card">
                <div class="card-body">
                    <form method="post" action="/admin/questions/{question_id}/update">
                        <div class="row">
                            <div class="col-md-8">
                                <div class="mb-3">
                                    <label class="form-label">Question ID</label>
                                    <input type="text" class="form-control" value="{question["id"]}" disabled>
                                    <div class="form-text">Question ID cannot be changed</div>
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label">Question Text</label>
                                    <textarea class="form-control" name="question_text" rows="3" required>{question["question_text"]}</textarea>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Category</label>
                                            <input type="text" class="form-control" name="category" required value="{question["category"]}">
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Question Type</label>
                                            <select class="form-select" name="question_type" required onchange="updateOptionsSection()">
                                                <option value="single_choice" {'selected' if question["question_type"] == 'single_choice' else ''}>Single Choice</option>
                                                <option value="multi_select" {'selected' if question["question_type"] == 'multi_select' else ''}>Multi Select</option>
                                                <option value="scale" {'selected' if question["question_type"] == 'scale' else ''}>Scale (1-5)</option>
                                                <option value="text" {'selected' if question["question_type"] == 'text' else ''}>Text Input</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Profile Field</label>
                                            <input type="text" class="form-control" name="profile_field" required value="{question["profile_field"]}">
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Priority</label>
                                            <input type="number" class="form-control" name="priority" value="{question["priority"]}" min="1" max="10" required>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label">App Context</label>
                                    <input type="text" class="form-control" name="app_context" value='{app_context_str}'>
                                </div>
                                
                                <div id="optionsSection" style="display: {'block' if question["question_type"] in ['single_choice', 'multi_select', 'scale'] else 'none'};">
                                    <div class="mb-3">
                                        <label class="form-label">Options (JSON)</label>
                                        <textarea class="form-control" name="options" rows="6">{options_str}</textarea>
                                    </div>
                                </div>
                                
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" name="is_active" {'checked' if question["is_active"] else ''}>
                                    <label class="form-check-label">
                                        Active (show to users)
                                    </label>
                                </div>
                            </div>
                            
                            <div class="col-md-4">
                                <div class="card bg-light">
                                    <div class="card-header">
                                        <h6 class="mb-0">Preview</h6>
                                    </div>
                                    <div class="card-body">
                                        <div id="questionPreview">
                                            <strong>{question["question_text"]}</strong><br><br>
                                            <em>Update form to see preview changes</em>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <hr>
                        <div class="d-flex justify-content-end">
                            <a href="/admin/questions" class="btn btn-outline-secondary me-2">Cancel</a>
                            <button type="submit" class="btn btn-success">
                                <i class="fas fa-save"></i> Update Question
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function updateOptionsSection() {{
                const questionType = document.querySelector('[name="question_type"]').value;
                const optionsSection = document.getElementById('optionsSection');
                const optionsTextarea = document.querySelector('[name="options"]');
                
                if (questionType === 'single_choice' || questionType === 'multi_select') {{
                    optionsSection.style.display = 'block';
                    optionsTextarea.required = true;
                }} else if (questionType === 'scale') {{
                    optionsSection.style.display = 'block';
                    optionsTextarea.required = true;
                }} else {{
                    optionsSection.style.display = 'none';
                    optionsTextarea.required = false;
                }}
            }}
            
            // Update preview on input
            document.querySelector('[name="question_text"]').addEventListener('input', function() {{
                document.getElementById('questionPreview').innerHTML = '<strong>' + this.value + '</strong><br><br><em>Update form to see preview changes</em>';
            }});
        </script>
    </body>
    </html>
    """)

@questions_router.post("/{question_id}/update")
async def update_question(
    request: Request,
    question_id: str,
    question_text: str = Form(...),
    category: str = Form(...),
    question_type: str = Form(...),
    profile_field: str = Form(...),
    priority: int = Form(...),
    app_context: str = Form(...),
    options: str = Form(""),
    is_active: Optional[str] = Form(None),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    try:
        # Parse JSON fields
        import json
        app_context_json = json.loads(app_context) if app_context else []
        options_json = json.loads(options) if options else None
        is_active_bool = is_active is not None
        
        # Update question
        await db.execute(
            """
            UPDATE profiling_questions 
            SET question_text = $1, category = $2, question_type = $3, profile_field = $4, 
                priority = $5, app_context = $6::jsonb, options = $7::jsonb, is_active = $8
            WHERE id = $9
            """,
            question_text, category, question_type, profile_field, priority,
            json.dumps(app_context_json), json.dumps(options_json) if options_json else None, 
            is_active_bool, question_id
        )
        
        return RedirectResponse(url="/admin/questions?updated=1", status_code=302)
        
    except Exception as e:
        return HTMLResponse(f"""
            <script>
                alert('Error updating question: {str(e)}');
                window.history.back();
            </script>
        """)

@questions_router.post("/{question_id}/toggle")
async def toggle_question(
    question_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    # Get current status
    question = await db.fetch_one("SELECT is_active FROM profiling_questions WHERE id = $1", question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Toggle status
    new_status = not question["is_active"]
    await db.execute(
        "UPDATE profiling_questions SET is_active = $1 WHERE id = $2",
        new_status, question_id
    )
    
    return RedirectResponse(url="/admin/questions", status_code=302)

@questions_router.post("/{question_id}/delete")
async def delete_question(
    question_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    # Check if question has responses
    response_count = await db.fetch_one(
        "SELECT COUNT(*) as count FROM user_question_responses WHERE question_id = $1",
        question_id
    )
    
    if response_count["count"] > 0:
        return HTMLResponse("""
            <script>
                alert('Cannot delete question with existing responses. Disable it instead.');
                window.location.href = '/admin/questions';
            </script>
        """)
    
    # Delete question
    await db.execute("DELETE FROM profiling_questions WHERE id = $1", question_id)
    
    return RedirectResponse(url="/admin/questions?deleted=1", status_code=302)