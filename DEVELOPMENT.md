# Nyelux Backend Development Guide

## Table of Contents
1. [Getting Started](#getting-started)
2. [Development Workflow](#development-workflow)
3. [Code Standards](#code-standards)
4. [Testing Guide](#testing-guide)
5. [API Development](#api-development)
6. [Database Management](#database-management)
7. [External Services](#external-services)
8. [Debugging](#debugging)
9. [Production Deployment](#production-deployment)

## Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose (optional)
- Make (for using Makefile commands)

### Initial Setup

1. **Clone the repository**
```bash
git clone https://github.com/nyelux/nyelux-backend.git
cd nyelux-backend
```

2. **Set up environment**
```bash
# Using Make (recommended)
make all

# Or manually:
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env with your local settings
```

4. **Set up database**
```bash
# Create databases
make setup-db

# Run migrations
make migrate

# Seed sample data (optional)
make seed
```

5. **Start the server**
```bash
make run
# API will be available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

## Development Workflow

### Branch Strategy
- `main` - Production-ready code
- `develop` - Integration branch
- `feature/*` - New features
- `bugfix/*` - Bug fixes
- `hotfix/*` - Emergency fixes

### Development Process

1. **Create feature branch**
```bash
git checkout -b feature/your-feature-name
```

2. **Make changes following code standards**

3. **Format code**
```bash
make format
```

4. **Run linting**
```bash
make lint
```

5. **Write/update tests**

6. **Run tests**
```bash
make test
```

7. **Commit with descriptive message**
```bash
git add .
git commit -m "feat: add device comparison endpoint"
```

8. **Push and create PR**
```bash
git push origin feature/your-feature-name
```

## Code Standards

### Python Style Guide
- Follow PEP 8
- Use Black for formatting (configured in pyproject.toml)
- Use isort for import sorting
- Maximum line length: 120 characters

### Docstring Requirements
Every function/class MUST have docstrings:

```python
def search_devices(
    self,
    db: AsyncSession,
    query: str,
    filters: Optional[Dict[str, Any]] = None
) -> List[Device]:
    """
    Search for devices using multiple strategies.
    
    This method implements a multi-strategy search approach including
    exact match, full-text search, and fuzzy matching.
    
    Args:
        db: Database session for queries
        query: Search query string
        filters: Optional filters to apply
        
    Returns:
        List of matching Device objects sorted by relevance
        
    Raises:
        ValueError: If query is empty or invalid
    """
    pass
```

### Type Hints
- All functions must have type hints
- Use `Optional[]` for nullable parameters
- Use `List[]`, `Dict[]`, etc. from typing

### Error Handling
```python
# Good
try:
    result = await external_service.call()
except ExternalServiceError as e:
    logger.error(f"External service failed: {e}")
    raise HTTPException(
        status_code=503,
        detail="Service temporarily unavailable"
    )

# Bad
try:
    result = await external_service.call()
except:
    return None  # Never swallow errors silently
```

## Testing Guide

### Test Structure
```
tests/
├── unit/           # Fast, isolated tests
├── integration/    # Tests with real database/services
├── fixtures/       # Shared test data
└── conftest.py     # Pytest configuration
```

### Writing Tests

#### Unit Test Example
```python
class TestSearchService:
    """Test suite for SearchService."""
    
    @pytest.fixture
    def search_service(self):
        """Create search service instance."""
        return SearchService()
    
    @pytest.mark.asyncio
    async def test_exact_match_search(self, search_service, mock_db):
        """Test exact DI match returns highest score."""
        # Arrange
        mock_device = create_mock_device(primary_di="12345")
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_device
        
        # Act
        results = await search_service._exact_match_search(
            mock_db, "12345"
        )
        
        # Assert
        assert len(results) == 1
        assert results[0]["score"] == 1.0
```

#### Integration Test Example
```python
@pytest.mark.asyncio
async def test_create_device_full_flow(client: AsyncClient, db: AsyncSession):
    """Test complete device creation flow."""
    # Create organization and user
    org = await create_test_organization(db)
    user = await create_test_user(db, org.id, role="vendor_admin")
    token = get_auth_token(user)
    
    # Create device
    response = await client.post(
        "/api/v1/devices",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "internal_sku": "TEST-001",
            "custom_name": "Test Device",
            "organization_id": org.id
        }
    )
    
    assert response.status_code == 201
    assert response.json()["internal_sku"] == "TEST-001"
    
    # Verify in database
    device = await db.get(VendorDevice, response.json()["id"])
    assert device is not None
```

### Running Tests
```bash
# All tests with coverage
make test

# Unit tests only
make test-unit

# Integration tests only
make test-integration

# Specific test file
pytest tests/unit/test_search_service.py -v

# With debugging
pytest tests/unit/test_auth_service.py::test_login -vvs
```

### Coverage Requirements
- Minimum 80% coverage required
- Critical paths must have 100% coverage
- View coverage report: `open htmlcov/index.html`

## API Development

### Creating New Endpoints

1. **Define schema** in `src/schemas/`
```python
# src/schemas/device.py
class DeviceCreate(BaseModel):
    internal_sku: str
    custom_name: Optional[str] = None
    
    class Config:
        orm_mode = True
```

2. **Create service** in `src/services/`
```python
# src/services/device_service.py
class DeviceService:
    async def create_device(
        self,
        db: AsyncSession,
        device_data: DeviceCreate,
        user_id: int
    ) -> VendorDevice:
        """Create new device with validation."""
        # Implementation
```

3. **Add endpoint** in `src/api/v1/endpoints/`
```python
# src/api/v1/endpoints/devices.py
@router.post("/", response_model=DeviceResponse)
async def create_device(
    *,
    db: AsyncSession = Depends(get_db),
    device_in: DeviceCreate,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Create new device.
    
    Full docstring with details...
    """
    device = await device_service.create_device(
        db, device_in, current_user.id
    )
    return device
```

### API Best Practices
- Use proper HTTP status codes
- Include request/response examples in docstrings
- Validate all inputs with Pydantic
- Handle errors gracefully
- Log important operations

## Database Management

### Creating Migrations
```bash
# Auto-generate migration
make migrate-create name="add_device_metadata"

# Review and edit the generated file
# Then apply:
make migrate
```

### Database Best Practices
- Always use migrations, never modify schema directly
- Add indexes for frequently queried columns
- Use soft deletes (deleted_at timestamp)
- Include created_at/updated_at on all tables
- Use transactions for multi-table operations

### Common Patterns

#### Async Query Pattern
```python
async def get_devices_with_counts(
    db: AsyncSession,
    organization_id: int
) -> List[Dict[str, Any]]:
    """Get devices with document counts."""
    # Main query
    devices = await db.execute(
        select(VendorDevice)
        .where(VendorDevice.organization_id == organization_id)
        .options(selectinload(VendorDevice.gudid_device))
    )
    
    result = []
    for device in devices.scalars():
        # Get counts
        doc_count = await db.scalar(
            select(func.count(DeviceDocument.id))
            .where(DeviceDocument.device_id == device.id)
        )
        
        result.append({
            "device": device,
            "document_count": doc_count
        })
    
    return result
```

## External Services

### Required Services

#### PostgreSQL
- Version: 15+
- Extensions: pg_vector, pg_trgm
- Connection pool: 5-10 connections

#### Redis
- Version: 7+
- Used for: Caching, rate limiting
- Key patterns: `search:*`, `device:*`, `user:*`

#### OpenAI (Optional)
- Used for: AI chat, embeddings
- Set `OPENAI_API_KEY` in .env
- Falls back gracefully if not configured

#### AWS S3 (Production)
- Used for: Document/video storage
- Local development uses filesystem
- Set AWS credentials in .env

### Service Health Checks
```python
# Check all services
make health-check

# Or manually
python scripts/health_check.py
```

## Debugging

### Common Issues

#### Database Connection Errors
```bash
# Check PostgreSQL is running
pg_isready

# Check connection string
psql $DATABASE_URL

# Reset database
dropdb nyelux_development
make setup-db migrate
```

#### Import Errors
```bash
# Ensure you're in virtual environment
which python  # Should show venv path

# Reinstall dependencies
pip install -r requirements.txt
```

#### Test Failures
```bash
# Run specific test with verbose output
pytest path/to/test.py::test_name -vvs

# Check test database
psql nyelux_test
```

### Debugging Tools

#### Interactive Shell
```bash
# Open Python shell with app context
make shell

# Example usage:
>>> from src.db.models.user import User
>>> from src.db.session import AsyncSessionLocal
>>> async with AsyncSessionLocal() as db:
...     users = await db.execute(select(User))
...     print(users.scalars().all())
```

#### Logging
```python
import logging
logger = logging.getLogger(__name__)

# Add debug logging
logger.debug(f"Query parameters: {params}")
logger.info(f"User {user.id} accessed device {device.id}")
logger.error(f"Failed to process document: {e}")
```

## Production Deployment

### Pre-deployment Checklist
- [ ] All tests passing
- [ ] Coverage > 80%
- [ ] No security vulnerabilities (`make check-security`)
- [ ] Environment variables configured
- [ ] Database migrations tested
- [ ] API documentation updated
- [ ] Performance tested

### Deployment Steps

1. **Build Docker image**
```bash
make docker-build
```

2. **Run production checks**
```bash
# Lint and format
make lint

# Security scan
make check-security

# Full test suite
make test
```

3. **Deploy**
```bash
# Using Docker
docker run -d \
  --name nyelux-backend \
  -p 8000:8000 \
  --env-file .env.production \
  nyelux-backend:latest

# Or using gunicorn directly
make run-prod
```

### Monitoring
- Health endpoint: `/health`
- Metrics: Datadog/Prometheus integration
- Logs: Structured JSON logging
- Alerts: Set up for errors, high latency

### Rollback Procedure
1. Stop current deployment
2. Restore previous Docker image
3. Run database rollback if needed
4. Verify health checks pass

## Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Python Async/Await Guide](https://docs.python.org/3/library/asyncio.html)

## Getting Help

- Check existing issues on GitHub
- Ask in #backend Slack channel
- Review test cases for examples
- Consult API documentation at `/docs`

Remember: **If it doesn't work in production, it doesn't exist. No fake implementations!**
