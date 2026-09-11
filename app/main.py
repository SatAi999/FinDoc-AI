import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.database.database import engine, Base
from app.core.logging import logger
from app.api.routes.documents import router as documents_router

# Initialize database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=None,
    redoc_url=None
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(documents_router)

# Mount Static Files & Templates
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_static_dir = os.path.join(BASE_DIR, "frontend", "static")
frontend_templates_dir = os.path.join(BASE_DIR, "frontend", "templates")

if os.path.exists(frontend_static_dir):
    app.mount("/static", StaticFiles(directory=frontend_static_dir), name="static")

templates = Jinja2Templates(directory=frontend_templates_dir if os.path.exists(frontend_templates_dir) else BASE_DIR)

@app.get("/", response_class=HTMLResponse, summary="Dashboard UI")
def serve_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return HTMLResponse(f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>FinDoc AI — Swagger OpenAPI Documentation</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
  <link rel="stylesheet" href="/static/css/swagger_redoc.css">
</head>
<body>
  <header class="findoc-docs-topbar">
    <a href="/" class="findoc-brand-link">
      <div class="findoc-brand-icon"><i class="fa-solid fa-brain"></i></div>
      <div>
        <span class="findoc-brand-title">FinDoc AI</span>
        <span class="findoc-badge">Swagger OpenAPI</span>
      </div>
    </a>
    <div class="findoc-docs-actions">
      <a href="/" class="findoc-nav-btn"><i class="fa-solid fa-arrow-left"></i> Back to Workspace</a>
      <a href="/redoc" class="findoc-nav-btn"><i class="fa-regular fa-file-lines"></i> View ReDoc</a>
    </div>
  </header>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {{
      window.ui = SwaggerUIBundle({{
        url: '{settings.API_V1_STR}/openapi.json',
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIBundle.SwaggerUIStandalonePreset
        ],
        layout: "BaseLayout"
      }});
    }};
  </script>
</body>
</html>
""")

@app.get("/redoc", include_in_schema=False)
async def custom_redoc_html():
    return HTMLResponse(f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>FinDoc AI — ReDoc Reference</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <link rel="stylesheet" href="/static/css/swagger_redoc.css">
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    body {{ margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }}
  </style>
</head>
<body>
  <header class="findoc-docs-topbar">
    <a href="/" class="findoc-brand-link">
      <div class="findoc-brand-icon"><i class="fa-solid fa-brain"></i></div>
      <div>
        <span class="findoc-brand-title">FinDoc AI</span>
        <span class="findoc-badge">ReDoc Reference</span>
      </div>
    </a>
    <div class="findoc-docs-actions">
      <a href="/" class="findoc-nav-btn"><i class="fa-solid fa-arrow-left"></i> Back to Workspace</a>
      <a href="/docs" class="findoc-nav-btn"><i class="fa-solid fa-code"></i> View Swagger UI</a>
    </div>
  </header>
  <div id="redoc-container"></div>
  <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
  <script>
    Redoc.init('{settings.API_V1_STR}/openapi.json', {{
      theme: {{
        colors: {{
          primary: {{
            main: '#0f4a56'
          }}
        }},
        typography: {{
          fontFamily: "'Plus Jakarta Sans', sans-serif",
          headings: {{
            fontFamily: "'Plus Jakarta Sans', sans-serif",
            fontWeight: '700'
          }}
        }}
      }}
    }}, document.getElementById('redoc-container'));
  </script>
</body>
</html>
""")

@app.get("/view/{document_name}", response_class=HTMLResponse, summary="Document Inspection UI")
def serve_document_view(request: Request, document_name: str):
    return templates.TemplateResponse(request=request, name="document_result.html", context={"document_name": document_name})

# Custom Exception Handler for Structured Errors
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "HTTP_ERROR",
                "message": str(exc.detail)
            }
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred. Please check system logs."
            }
        }
    )
