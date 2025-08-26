# NYELUX Backend Integration Tests

Comprehensive test suite for the NYELUX medical device intelligence platform backend.

## Overview

This test suite contains **1,050+ integration tests** across **21 test modules** covering all aspects of the NYELUX backend system. Tests are organized according to the 6-phase implementation plan and follow industry best practices for healthcare software testing.

## Test Coverage

### Phase 1: Foundation (Weeks 1-2) - CRITICAL
- **Authentication & Authorization** (`test_auth_comprehensive.py`)
- **Multi-Tenant Architecture** (`test_multi_tenant.py`)
- **Public Access & Lead Generation** (`test_public_access.py`)

### Phase 2: Core Features (Weeks 3-4) - HIGH
- **Device Management & Search** (`test_device_management.py`)
- **Image Recognition & Barcode Scanning** (`test_image_recognition.py`)
- **Team Collaboration** (`test_team_collaboration.py`)

### Phase 3: Advanced Features (Weeks 5-6) - HIGH
- **AI-Powered Chat System** (`test_ai_chat_system.py`)
- **Document & Video Management** (`test_document_video_management.py`)
- **Calendar & Scheduling** (`test_calendar_scheduling.py`)
- **Incident Reporting** (`test_incident_reporting.py`)

### Phase 4: Integration & Scale (Weeks 7-8) - MEDIUM
- **Third-Party Integrations** (`test_integrations.py`)
- **Performance & Load Testing** (`test_performance_load.py`)
- **Offline Functionality** (`test_offline_functionality.py`)

### Phase 5: Security & Compliance (Weeks 9-10) - CRITICAL
- **Security & HIPAA Compliance** (`test_security_compliance.py`)

### Phase 6: Supporting Features & Operations
- **Hospital Administration** (`test_hospital_administration.py`)
- **Notification System** (`test_notification_system.py`)
- **Analytics & Reporting** (`test_analytics_reporting.py`)
- **Browser Compatibility** (`test_browser_compatibility.py`)
- **Billing & Subscription** (`test_billing_subscription.py`)
- **Deployment & Operations** (`test_deployment_operations.py`)
- **Test Execution Plan** (`test_execution_plan.py`)

## Prerequisites

### Required Services
- PostgreSQL 15+ with extensions (pg_vector, pg_trgm)
- Redis 7.x
- Elasticsearch 8.x
- AWS S3 (or MinIO for local testing)
- OpenAI API access (for AI features)

### Python Dependencies
```bash
pip install -r requirements-test.txt
```

## Running Tests

### Quick Start

```bash
# Run all tests
pytest tests/integration/ -v

# Run with coverage
pytest tests/integration/ --cov=src --cov-report=html -v

# Run in parallel (faster)
pytest tests/integration/ -n auto -v
```

### Using the Test Runner

The `run_tests.py` script provides orchestrated test execution:

```bash
# Run all phases in order
python run_tests.py --all

# Run only critical tests
python run_tests.py --critical

# Run specific phase
python run_tests.py --phase phase1

# Run with coverage and parallel execution
python run_tests.py --all --parallel --coverage

# Run specific test file
python run_tests.py --test test_auth_comprehensive.py
```

### Phase-by-Phase Execution

```bash
# Phase 1: Foundation (Must pass before proceeding)
pytest tests/integration/test_auth_comprehensive.py \
       tests/integration/test_multi_tenant.py \
       tests/integration/test_public_access.py -v

# Phase 2: Core Features
pytest tests/integration/test_device_management.py \
       tests/integration/test_image_recognition.py \
       tests/integration/test_team_collaboration.py -v

# Continue for other phases...
```

### Running Specific Test Categories

```bash
# Critical tests only
pytest tests/integration/ -m critical -v

# Performance tests
pytest tests/integration/test_performance_load.py -v

# Security tests
pytest tests/integration/test_security_compliance.py -v

# Tests for a specific phase
pytest tests/integration/ -m phase1 -v
```

## Test Configuration

### Environment Variables

Create a `.env.test` file:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/nyelux_test
SYNC_DATABASE_URL=postgresql://postgres:password@localhost:5432/nyelux_test

# Redis
REDIS_URL=redis://localhost:6379/1

# Elasticsearch
ELASTICSEARCH_URL=http://localhost:9200

# AWS S3 (or MinIO)
AWS_ACCESS_KEY_ID=test_key
AWS_SECRET_ACCESS_KEY=test_secret
S3_BUCKET=nyelux-test

# OpenAI (use test key or mock)
OPENAI_API_KEY=sk-test-...

# Test Configuration
TEST_ENVIRONMENT=test
DEBUG=True
```

### Pytest Configuration

See `pytest.ini` for detailed configuration including:
- Test discovery patterns
- Marker definitions
- Coverage settings
- Logging configuration
- Timeout settings

## Test Markers

Tests are marked for easy filtering:

- `@pytest.mark.critical` - Must pass for production
- `@pytest.mark.high` - High priority features
- `@pytest.mark.medium` - Supporting features
- `@pytest.mark.slow` - Tests taking >5 seconds
- `@pytest.mark.performance` - Performance tests
- `@pytest.mark.security` - Security tests
- `@pytest.mark.requires_db` - Requires database
- `@pytest.mark.requires_external` - Requires external services

## Success Criteria

### Critical Metrics
- **Overall Pass Rate**: ≥95%
- **Critical Test Pass Rate**: 100%
- **Performance Targets**:
  - Public search: <300ms
  - Authenticated search: <200ms
  - Image processing: <2s
- **Security Requirements**:
  - Zero cross-tenant data leaks
  - Zero critical vulnerabilities
  - HIPAA compliant
- **Scale Requirements**:
  - 10,000 concurrent users
  - 1,000 requests/second
  - 4.8M device records

### Exit Criteria by Phase

Each phase has specific exit criteria that must be met before proceeding:

**Phase 1 (Foundation)**:
- 100% pass rate
- Zero cross-tenant leaks
- All user roles functional
- Public search <300ms

**Phase 2 (Core Features)**:
- 95% pass rate
- Search performance <200ms with 4.8M records
- Image recognition >85% accuracy
- Barcode scanning >95% success

**Phase 3 (Advanced Features)**:
- 95% pass rate
- AI chat responses <3 seconds
- Video streaming stable
- Calendar sync working

**Phase 4 (Integration & Scale)**:
- 90% pass rate
- 10K concurrent users supported
- All integrations functional

**Phase 5 (Security & Compliance)**:
- 100% pass rate
- Zero vulnerabilities
- HIPAA audit passed

## Test Reports

Test execution generates detailed reports in `test_reports/`:

- `test_execution_summary.json` - Overall summary
- `phase_*_report.json` - Phase-specific results
- `htmlcov/` - Coverage HTML reports
- `pytest-report.html` - Detailed test report

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   ```bash
   # Ensure PostgreSQL is running
   pg_ctl status
   
   # Create test database
   createdb nyelux_test
   ```

2. **Redis Connection Errors**
   ```bash
   # Start Redis
   redis-server
   ```

3. **Elasticsearch Errors**
   ```bash
   # Check Elasticsearch status
   curl http://localhost:9200/_cluster/health
   ```

4. **External Service Timeouts**
   - Use `--no-cov` to skip coverage for faster runs
   - Use `-x` to stop on first failure
   - Increase timeout in pytest.ini if needed

## Best Practices

1. **Always run Phase 1 tests first** - They validate critical foundation
2. **Use parallel execution** for faster results: `-n auto`
3. **Monitor resource usage** during performance tests
4. **Review failed tests immediately** - Don't let failures accumulate
5. **Keep test data realistic** - Use production-like volumes
6. **Update tests with features** - Tests should evolve with code

## Continuous Integration

Example GitHub Actions workflow:

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-test.txt
    
    - name: Run critical tests
      run: |
        python run_tests.py --critical --coverage
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

## Contributing

When adding new features:

1. Write tests FIRST (TDD approach)
2. Follow the existing test structure
3. Use appropriate test IDs (TC-XXX-NNN)
4. Add markers for categorization
5. Update this README if adding new test categories
6. Ensure tests are idempotent and isolated

## Support

For test-related issues:
- Check test logs in `test_reports/`
- Review pytest output with `-vv` for verbose
- Enable debug logging in pytest.ini
- Contact QA team for assistance

---

**Remember**: A feature without tests is not complete. These tests ensure NYELUX meets the highest standards for medical device software.