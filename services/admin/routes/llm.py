from fastapi import APIRouter, Request, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional
from uuid import UUID
import httpx
import os
import json

from shared.database import get_db, Database
from shared.redis_client import get_redis
from auth import AdminAuth, get_current_admin_user, optional_admin_user

llm_router = APIRouter()

@llm_router.get("/", response_class=HTMLResponse)
async def llm_dashboard(
    request: Request,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    """LLM analytics and configuration dashboard"""
    
    # Get total usage stats (last 30 days)
    stats = await db.fetch_one("""
        SELECT 
            COUNT(*) as total_requests,
            SUM(total_tokens) as total_tokens,
            SUM(cost_usd) as total_cost_usd,
            AVG(latency_ms) as avg_latency_ms
        FROM llm_usage_logs
        WHERE created_at >= NOW() - INTERVAL '30 days'
    """)
    
    # Get model breakdown
    model_stats = await db.fetch_all("""
        SELECT 
            provider,
            model_id,
            COUNT(*) as requests,
            SUM(cost_usd) as cost,
            AVG(latency_ms) as avg_latency
        FROM llm_usage_logs
        WHERE created_at >= NOW() - INTERVAL '30 days'
        GROUP BY provider, model_id
        ORDER BY cost DESC
        LIMIT 10
    """)
    
    # Get app configurations (show all apps, even without configs)
    app_configs = await db.fetch_all("""
        SELECT 
            a.id as app_id,
            a.name as app_name,
            a.slug as app_slug,
            c.primary_provider,
            c.primary_model_id,
            c.updated_at
        FROM apps a
        LEFT JOIN app_model_configs c ON a.id = c.app_id
        ORDER BY a.name
    """)
    
    
    # Build model stats HTML
    model_stats_html = ""
    for stat in model_stats:
        model_stats_html += f"""
        <tr>
            <td>{stat['provider']}</td>
            <td>{stat['model_id']}</td>
            <td>{stat['requests']:,}</td>
            <td>${stat['cost']:.4f}</td>
            <td>{stat['avg_latency']:.0f}ms</td>
        </tr>
        """
    
    # Build app configs HTML
    app_configs_html = ""
    if app_configs:
        for config in app_configs:
            provider = config['primary_provider'] or 'Not configured'
            model = config['primary_model_id'] or 'Not configured'
            
            app_configs_html += f"""
            <tr>
                <td><strong>{config['app_name']}</strong><br><small class="text-muted">{config['app_slug']}</small></td>
                <td>{provider}</td>
                <td>{model}</td>
                <td>
                    <a href="/admin/llm/apps/{config['app_id']}" class="btn btn-sm btn-primary">
                        <i class="fas fa-cog"></i> Configure
                    </a>
                </td>
            </tr>
            """
    else:
        app_configs_html = """
        <tr>
            <td colspan="4" class="text-center text-muted">
                <i class="fas fa-info-circle me-2"></i>No active apps found. Create some apps first.
            </td>
        </tr>
        """
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>LLM Management - fairydust Admin</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            .fairy-dust {{ color: #ffd700; text-shadow: 0 0 5px rgba(255,215,0,0.5); }}
            .stat-card {{ border-left: 4px solid; }}
            .stat-card-primary {{ border-left-color: #4e73df; }}
            .stat-card-success {{ border-left-color: #1cc88a; }}
            .stat-card-warning {{ border-left-color: #f6c23e; }}
            .stat-card-info {{ border-left-color: #36b9cc; }}
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
                <h1><i class="fas fa-brain me-2"></i>LLM Management</h1>
                <a href="/admin/dashboard" class="btn btn-secondary">← Back to Dashboard</a>
            </div>
            
            <!-- Stats Cards -->
            <div class="row mb-4">
                <div class="col-xl-3 col-md-6 mb-4">
                    <div class="card stat-card stat-card-primary h-100">
                        <div class="card-body">
                            <div class="row align-items-center">
                                <div class="col">
                                    <div class="text-uppercase mb-1">Total Requests (30d)</div>
                                    <div class="h5 mb-0">{stats['total_requests'] or 0:,}</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-comments fa-2x text-muted"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-xl-3 col-md-6 mb-4">
                    <div class="card stat-card stat-card-success h-100">
                        <div class="card-body">
                            <div class="row align-items-center">
                                <div class="col">
                                    <div class="text-uppercase mb-1">Total Tokens</div>
                                    <div class="h5 mb-0">{stats['total_tokens'] or 0:,}</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-coins fa-2x text-muted"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-xl-3 col-md-6 mb-4">
                    <div class="card stat-card stat-card-warning h-100">
                        <div class="card-body">
                            <div class="row align-items-center">
                                <div class="col">
                                    <div class="text-uppercase mb-1">Total Cost</div>
                                    <div class="h5 mb-0">${stats['total_cost_usd'] or 0:.2f}</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-dollar-sign fa-2x text-muted"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="col-xl-3 col-md-6 mb-4">
                    <div class="card stat-card stat-card-info h-100">
                        <div class="card-body">
                            <div class="row align-items-center">
                                <div class="col">
                                    <div class="text-uppercase mb-1">Avg Latency</div>
                                    <div class="h5 mb-0">{stats['avg_latency_ms'] or 0:.0f}ms</div>
                                </div>
                                <div class="col-auto">
                                    <i class="fas fa-clock fa-2x text-muted"></i>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="row">
                <!-- Model Performance -->
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <h6 class="mb-0">Top Models by Cost (30 days)</h6>
                        </div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-sm">
                                    <thead>
                                        <tr>
                                            <th>Provider</th>
                                            <th>Model</th>
                                            <th>Requests</th>
                                            <th>Cost</th>
                                            <th>Avg Latency</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {model_stats_html}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- App Configurations -->
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <h6 class="mb-0">App Model Configurations</h6>
                        </div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-sm">
                                    <thead>
                                        <tr>
                                            <th>App</th>
                                            <th>Provider</th>
                                            <th>Model</th>
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {app_configs_html}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """)

@llm_router.get("/apps/{app_id}", response_class=HTMLResponse)
async def llm_app_config(
    request: Request,
    app_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    """LLM configuration interface for specific app"""
    
    # Check for success/error messages
    updated = request.query_params.get('updated')
    error = request.query_params.get('error')
    
    # Get app details (handle both UUID and slug)
    try:
        # Try UUID first
        uuid_app_id = UUID(app_id)
        app = await db.fetch_one("""
            SELECT id, name, slug FROM apps WHERE id = $1
        """, uuid_app_id)
    except (ValueError, TypeError):
        # If not UUID, try as slug
        app = await db.fetch_one("""
            SELECT id, name, slug FROM apps WHERE slug = $1
        """, app_id)
    
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    
    # Get current model configuration
    config = await db.fetch_one("""
        SELECT * FROM app_model_configs WHERE app_id = $1
    """, app['id'])
    
    if not config:
        # Create default config if none exists
        # Create default config based on app type
        default_provider = 'anthropic'
        default_model = 'claude-3-5-haiku-20241022'
        default_params = '{"temperature": 0.8, "max_tokens": 150, "top_p": 0.9}'
        default_fallbacks = '[{"provider": "openai", "model_id": "gpt-4o-mini", "trigger": "provider_error", "parameters": {"temperature": 0.8, "max_tokens": 150}}]'
        default_cost_limits = '{"per_request_max": 0.05, "daily_max": 10.0, "monthly_max": 100.0}'
        
        if app['slug'] == 'fairydust-recipe':
            default_model = 'claude-3-5-sonnet-20241022'
            default_params = '{"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9}'
            default_fallbacks = '[{"provider": "openai", "model_id": "gpt-4o", "trigger": "provider_error", "parameters": {"temperature": 0.7, "max_tokens": 1000}}, {"provider": "openai", "model_id": "gpt-4o-mini", "trigger": "cost_threshold_exceeded", "parameters": {"temperature": 0.7, "max_tokens": 1000}}]'
            default_cost_limits = '{"per_request_max": 0.15, "daily_max": 25.0, "monthly_max": 200.0}'
        
        await db.execute("""
            INSERT INTO app_model_configs (
                app_id, primary_provider, primary_model_id, primary_parameters,
                fallback_models, cost_limits, feature_flags
            ) VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb)
            ON CONFLICT (app_id) DO UPDATE SET
                primary_provider = EXCLUDED.primary_provider,
                primary_model_id = EXCLUDED.primary_model_id,
                primary_parameters = EXCLUDED.primary_parameters,
                fallback_models = EXCLUDED.fallback_models,
                cost_limits = EXCLUDED.cost_limits,
                feature_flags = EXCLUDED.feature_flags,
                updated_at = CURRENT_TIMESTAMP
        """, 
            app['id'], default_provider, default_model, default_params,
            default_fallbacks, default_cost_limits,
            '{"streaming_enabled": true, "cache_responses": true, "log_prompts": false}'
        )
        
        # Try to get config from cache first
        from shared.app_config_cache import get_app_config_cache
        cache = await get_app_config_cache()
        cached_config = await cache.get_model_config(str(app['id']))
        
        if cached_config:
            # Convert cached config back to database format for existing code compatibility
            config = {
                'primary_provider': cached_config.get('primary_provider'),
                'primary_model_id': cached_config.get('primary_model_id'),
                'primary_parameters': cached_config.get('primary_parameters'),
                'fallback_models': cached_config.get('fallback_models'),
                'cost_limits': cached_config.get('cost_limits'),
                'feature_flags': cached_config.get('feature_flags')
            }
        else:
            # Cache miss - fetch from database
            config = await db.fetch_one("""
                SELECT * FROM app_model_configs WHERE app_id = $1
            """, app['id'])
    
    # Available models by provider
    available_models = {
        'anthropic': [
            'claude-3-5-sonnet-20241022',
            'claude-3-5-haiku-20241022',
            'claude-3-sonnet-20240229',
            'claude-3-haiku-20240307',
            'claude-3-opus-20240229'
        ],
        'openai': [
            'gpt-4o',
            'gpt-4o-mini',
            'gpt-4-turbo',
            'gpt-4-turbo-preview',
            'gpt-4',
            'gpt-3.5-turbo',
            'gpt-3.5-turbo-16k'
        ]
    }
    
    # Parse JSONB fields from database (they come as strings)
    def parse_json_field(field_value, default=None):
        if field_value is None:
            return default or {}
        if isinstance(field_value, str):
            try:
                return json.loads(field_value)
            except json.JSONDecodeError:
                return default or {}
        return field_value
    
    # Parse all JSON fields
    primary_parameters = parse_json_field(config['primary_parameters'], {'temperature': 0.8, 'max_tokens': 150, 'top_p': 0.9})
    fallback_models = parse_json_field(config['fallback_models'], [])
    cost_limits = parse_json_field(config['cost_limits'], {'per_request_max': 0.05, 'daily_max': 10.0, 'monthly_max': 100.0})
    feature_flags = parse_json_field(config['feature_flags'], {'streaming_enabled': True, 'cache_responses': True, 'log_prompts': False})
    
    config_json = {
        'primary_provider': config['primary_provider'],
        'primary_model_id': config['primary_model_id'],
        'primary_parameters': primary_parameters,
        'fallback_models': fallback_models,
        'cost_limits': cost_limits,
        'feature_flags': feature_flags
    }
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Configure {app['name']} - fairydust Admin</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            .fairy-dust {{ color: #ffd700; text-shadow: 0 0 5px rgba(255,215,0,0.5); }}
            .json-preview {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 0.375rem; padding: 1rem; }}
            .fallback-model {{ border: 1px solid #dee2e6; border-radius: 0.375rem; padding: 1rem; margin-bottom: 1rem; }}
        </style>
    </head>
    <body class="bg-light">
        <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
            <div class="container-fluid">
                <a class="navbar-brand" href="/admin/dashboard">
                    <i class="fas fa-magic fairy-dust me-2"></i>fairydust Admin
                </a>
            </div>
        </nav>
        
        <div class="container-fluid mt-4">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1><i class="fas fa-cog me-2"></i>Configure {app['name']}</h1>
                <a href="/admin/llm" class="btn btn-secondary">← Back to LLM Dashboard</a>
            </div>
            
            <!-- Success/Error Messages -->
            {f'''
            <div class="alert alert-success alert-dismissible fade show" role="alert">
                <i class="fas fa-check-circle me-2"></i>
                <strong>Success!</strong> LLM configuration has been updated successfully.
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
            ''' if updated else ''}
            
            {f'''
            <div class="alert alert-danger alert-dismissible fade show" role="alert">
                <i class="fas fa-exclamation-triangle me-2"></i>
                <strong>Error!</strong> There was a problem updating the configuration. Please try again.
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
            ''' if error else ''}
            
            <div class="row">
                <div class="col-lg-8">
                    <form id="configForm" method="post" action="/admin/llm/apps/{app['id']}/update">
                        <!-- Primary Model Configuration -->
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0"><i class="fas fa-brain me-2"></i>Primary Model</h5>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Provider</label>
                                            <select class="form-select" name="primary_provider" required>
                                                <option value="anthropic" {'selected' if config['primary_provider'] == 'anthropic' else ''}>Anthropic</option>
                                                <option value="openai" {'selected' if config['primary_provider'] == 'openai' else ''}>OpenAI</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label class="form-label">Model ID</label>
                                            <select class="form-select" name="primary_model_id" id="primary_model_id" required>
                                                <!-- Options will be populated by JavaScript -->
                                            </select>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="row">
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Temperature</label>
                                            <input type="number" class="form-control" name="temperature" 
                                                   value="{primary_parameters.get('temperature', 0.8)}" 
                                                   min="0" max="2" step="0.1">
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Max Tokens</label>
                                            <input type="number" class="form-control" name="max_tokens" 
                                                   value="{primary_parameters.get('max_tokens', 150)}" 
                                                   min="1" max="4000">
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Top P</label>
                                            <input type="number" class="form-control" name="top_p" 
                                                   value="{primary_parameters.get('top_p', 0.9)}" 
                                                   min="0" max="1" step="0.1">
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Fallback Models -->
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0"><i class="fas fa-shield-alt me-2"></i>Fallback Models</h5>
                            </div>
                            <div class="card-body">
                                <div id="fallback-models-container">
                                    <!-- Fallback models will be populated by JavaScript -->
                                </div>
                                <button type="button" class="btn btn-outline-primary btn-sm" onclick="addFallbackModel()">
                                    <i class="fas fa-plus me-2"></i>Add Fallback Model
                                </button>
                            </div>
                        </div>
                        
                        <!-- Cost Limits -->
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0"><i class="fas fa-dollar-sign me-2"></i>Cost Limits</h5>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Per Request Max ($)</label>
                                            <input type="number" class="form-control" name="per_request_max" 
                                                   value="{cost_limits.get('per_request_max', 0.05)}" 
                                                   min="0" step="0.01">
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Daily Max ($)</label>
                                            <input type="number" class="form-control" name="daily_max" 
                                                   value="{cost_limits.get('daily_max', 10.0)}" 
                                                   min="0" step="0.01">
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Monthly Max ($)</label>
                                            <input type="number" class="form-control" name="monthly_max" 
                                                   value="{cost_limits.get('monthly_max', 100.0)}" 
                                                   min="0" step="0.01">
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Feature Flags -->
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0"><i class="fas fa-flag me-2"></i>Feature Flags</h5>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-md-4">
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" name="streaming_enabled" 
                                                   {'checked' if feature_flags.get('streaming_enabled', True) else ''}>
                                            <label class="form-check-label">Streaming Enabled</label>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" name="cache_responses" 
                                                   {'checked' if feature_flags.get('cache_responses', True) else ''}>
                                            <label class="form-check-label">Cache Responses</label>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" name="log_prompts" 
                                                   {'checked' if feature_flags.get('log_prompts', False) else ''}>
                                            <label class="form-check-label">Log Prompts</label>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="d-grid gap-2">
                            <button type="submit" class="btn btn-primary btn-lg">
                                <i class="fas fa-save me-2"></i>Update Configuration
                            </button>
                        </div>
                    </form>
                </div>
                
                <div class="col-lg-4">
                    <!-- Current Configuration Preview -->
                    <div class="card">
                        <div class="card-header">
                            <h5 class="mb-0"><i class="fas fa-code me-2"></i>Current Configuration</h5>
                        </div>
                        <div class="card-body">
                            <div class="json-preview">
                                <pre><code>{json.dumps(config_json, indent=2)}</code></pre>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            // Available models data
            const availableModels = {json.dumps(available_models)};
            const currentConfig = {json.dumps(config_json)};
            
            let fallbackCounter = 0;
            
            // Initialize form
            document.addEventListener('DOMContentLoaded', function() {{
                updateModelDropdown('primary_provider', 'primary_model_id', currentConfig.primary_model_id);
                loadFallbackModels();
                
                // Add event listener for provider change
                document.querySelector('select[name="primary_provider"]').addEventListener('change', function() {{
                    updateModelDropdown('primary_provider', 'primary_model_id');
                }});
            }});
            
            function updateModelDropdown(providerSelectId, modelSelectId, selectedModel = '') {{
                const providerSelect = document.querySelector(`select[name="${{providerSelectId}}"]`);
                const modelSelect = document.querySelector(`select[name="${{modelSelectId}}"], #${{modelSelectId}}`);
                const provider = providerSelect.value;
                
                // Clear existing options
                modelSelect.innerHTML = '';
                
                // Add models for selected provider
                if (availableModels[provider]) {{
                    availableModels[provider].forEach(model => {{
                        const option = document.createElement('option');
                        option.value = model;
                        option.textContent = model;
                        if (model === selectedModel) {{
                            option.selected = true;
                        }}
                        modelSelect.appendChild(option);
                    }});
                }}
            }}
            
            function loadFallbackModels() {{
                const container = document.getElementById('fallback-models-container');
                container.innerHTML = '';
                
                if (currentConfig.fallback_models && currentConfig.fallback_models.length > 0) {{
                    currentConfig.fallback_models.forEach((fallback, index) => {{
                        addFallbackModelElement(fallback, index);
                    }});
                }}
            }}
            
            function addFallbackModel() {{
                addFallbackModelElement({{
                    provider: 'openai',
                    model_id: 'gpt-3.5-turbo',
                    trigger: 'provider_error',
                    parameters: {{ temperature: 0.8, max_tokens: 150 }}
                }}, fallbackCounter++);
            }}
            
            function addFallbackModelElement(fallback, index) {{
                const container = document.getElementById('fallback-models-container');
                const fallbackDiv = document.createElement('div');
                fallbackDiv.className = 'fallback-model mb-3';
                fallbackDiv.innerHTML = `
                    <div class="row g-2">
                        <div class="col-md-3">
                            <label class="form-label">Provider</label>
                            <select class="form-select" name="fallback_provider_${{index}}" onchange="updateModelDropdown('fallback_provider_${{index}}', 'fallback_model_${{index}}')">
                                <option value="anthropic" ${{fallback.provider === 'anthropic' ? 'selected' : ''}}>Anthropic</option>
                                <option value="openai" ${{fallback.provider === 'openai' ? 'selected' : ''}}>OpenAI</option>
                            </select>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">Model</label>
                            <select class="form-select" name="fallback_model_${{index}}" id="fallback_model_${{index}}">
                            </select>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">Trigger</label>
                            <select class="form-select" name="fallback_trigger_${{index}}">
                                <option value="provider_error" ${{fallback.trigger === 'provider_error' ? 'selected' : ''}}>Provider Error</option>
                                <option value="cost_threshold_exceeded" ${{fallback.trigger === 'cost_threshold_exceeded' ? 'selected' : ''}}>Cost Threshold Exceeded</option>
                                <option value="rate_limit" ${{fallback.trigger === 'rate_limit' ? 'selected' : ''}}>Rate Limit</option>
                                <option value="model_unavailable" ${{fallback.trigger === 'model_unavailable' ? 'selected' : ''}}>Model Unavailable</option>
                            </select>
                        </div>
                        <div class="col-md-2">
                            <label class="form-label">Temperature</label>
                            <input type="number" class="form-control" name="fallback_temperature_${{index}}" 
                                   value="${{fallback.parameters?.temperature || 0.8}}" min="0" max="2" step="0.1">
                        </div>
                        <div class="col-md-1 d-flex align-items-end">
                            <button type="button" class="btn btn-outline-danger btn-sm" onclick="removeFallbackModel(this)">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                `;
                container.appendChild(fallbackDiv);
                
                // Update model dropdown for this fallback
                setTimeout(() => {{
                    updateModelDropdown(`fallback_provider_${{index}}`, `fallback_model_${{index}}`, fallback.model_id);
                }}, 10);
                
                fallbackCounter = Math.max(fallbackCounter, index + 1);
            }}
            
            function removeFallbackModel(button) {{
                button.closest('.fallback-model').remove();
            }}
            
            // Form submission handler
            document.getElementById('configForm').addEventListener('submit', function(e) {{
                // Collect fallback models data
                const fallbackModels = [];
                const fallbackElements = document.querySelectorAll('.fallback-model');
                
                fallbackElements.forEach((element, index) => {{
                    const provider = element.querySelector(`select[name^="fallback_provider_"]`).value;
                    const modelId = element.querySelector(`select[name^="fallback_model_"]`).value;
                    const trigger = element.querySelector(`select[name^="fallback_trigger_"]`).value;
                    const temperature = parseFloat(element.querySelector(`input[name^="fallback_temperature_"]`).value);
                    
                    fallbackModels.push({{
                        provider: provider,
                        model_id: modelId,
                        trigger: trigger,
                        parameters: {{
                            temperature: temperature,
                            max_tokens: parseInt(document.querySelector('input[name="max_tokens"]').value)
                        }}
                    }});
                }});
                
                // Add hidden input for fallback models
                const hiddenInput = document.createElement('input');
                hiddenInput.type = 'hidden';
                hiddenInput.name = 'fallback_models_json';
                hiddenInput.value = JSON.stringify(fallbackModels);
                this.appendChild(hiddenInput);
            }});
        </script>
    </body>
    </html>
    """)

@llm_router.post("/apps/{app_id}/update")
async def update_llm_app_config(
    app_id: str,
    request: Request,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db)
):
    """Update LLM configuration for an app"""
    
    # Get app details (handle both UUID and slug)
    try:
        # Try UUID first
        uuid_app_id = UUID(app_id)
        app = await db.fetch_one("""
            SELECT id, name, slug FROM apps WHERE id = $1
        """, uuid_app_id)
    except (ValueError, TypeError):
        # If not UUID, try as slug
        app = await db.fetch_one("""
            SELECT id, name, slug FROM apps WHERE slug = $1
        """, app_id)
    
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    
    # Get form data
    form = await request.form()
    
    # Parse fallback models from JSON if provided
    fallback_models = []
    if form.get("fallback_models_json"):
        try:
            fallback_models = json.loads(form.get("fallback_models_json"))
        except json.JSONDecodeError:
            fallback_models = []
    
    # Update configuration directly in database (admin portal has direct DB access)
    try:
        # Build JSON data for database
        primary_parameters_json = json.dumps({
            "temperature": float(form.get("temperature", 0.8)),
            "max_tokens": int(form.get("max_tokens", 150)),
            "top_p": float(form.get("top_p", 0.9))
        })
        
        cost_limits_json = json.dumps({
            "per_request_max": float(form.get("per_request_max", 0.05)),
            "daily_max": float(form.get("daily_max", 10.0)),
            "monthly_max": float(form.get("monthly_max", 100.0))
        })
        
        feature_flags_json = json.dumps({
            "streaming_enabled": "streaming_enabled" in form,
            "cache_responses": "cache_responses" in form,
            "log_prompts": "log_prompts" in form
        })
        
        fallback_models_json = json.dumps(fallback_models)
        
        # Update the database directly
        await db.execute("""
            UPDATE app_model_configs 
            SET 
                primary_provider = $1,
                primary_model_id = $2, 
                primary_parameters = $3::jsonb,
                fallback_models = $4::jsonb,
                cost_limits = $5::jsonb,
                feature_flags = $6::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE app_id = $7
        """, 
            form.get("primary_provider"),
            form.get("primary_model_id"),
            primary_parameters_json,
            fallback_models_json,
            cost_limits_json,
            feature_flags_json,
            app['id']
        )
        
        # Invalidate cache after successful update
        from shared.app_config_cache import get_app_config_cache
        cache = await get_app_config_cache()
        await cache.invalidate_model_config(str(app['id']))
        
        return RedirectResponse(
            url=f"/admin/llm/apps/{app_id}?updated=1",
            status_code=302
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating configuration: {type(e).__name__}: {str(e)}"
        )
    
    return RedirectResponse(
        url=f"/admin/llm/apps/{app_id}?error=1",
        status_code=302
    )