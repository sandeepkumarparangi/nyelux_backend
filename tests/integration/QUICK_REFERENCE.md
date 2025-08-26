# NYELUX Backend Tests - Quick Reference Guide

## 🚀 Quick Start

```bash
# Run all tests
python run_tests.py --all

# Run critical tests only (fastest)
python run_tests.py --critical

# Run specific phase
python run_tests.py --phase phase1
```

## 📋 Test Files by Priority

### 🔴 CRITICAL (Must Pass)
- `test_auth_comprehensive.py` - All user authentication
- `test_multi_tenant.py` - Data isolation 
- `test_security_compliance.py` - HIPAA & security
- `test_deployment_operations.py` - Deployment readiness

### 🟡 HIGH (Core Features)
- `test_device_management.py` - 4.8M device search
- `test_image_recognition.py` - Image & barcode scanning
- `test_ai_chat_system.py` - AI assistant functionality
- `test_team_collaboration.py` - Real-time collaboration
- `test_performance_load.py` - 10K concurrent users

### 🟢 MEDIUM (Supporting)
- `test_public_access.py` - Public search & leads
- `test_incident_reporting.py` - Device issue tracking
- `test_document_video_management.py` - Content management
- `test_calendar_scheduling.py` - Meeting scheduling
- Other supporting features...

## 🎯 Key Performance Targets

| Metric | Target | Test File |
|--------|--------|-----------|
| Public Search | <300ms | `test_public_access.py` |
| Auth Search | <200ms | `test_device_management.py` |
| Image Recognition | >85% accuracy | `test_image_recognition.py` |
| Barcode Scanning | >95% success | `test_image_recognition.py` |
| Concurrent Users | 10,000 | `test_performance_load.py` |
| Uptime | 99.9% | `test_deployment_operations.py` |

## 🛡️ Security Requirements

| Requirement | Test Coverage |
|-------------|---------------|
| Zero cross-tenant leaks | `test_multi_tenant.py` |
| HIPAA compliance | `test_security_compliance.py` |
| Authentication all roles | `test_auth_comprehensive.py` |
| Encryption verification | `test_security_compliance.py` |
| Vulnerability scanning | `test_security_compliance.py` |

## 📊 Test Execution Phases

```
Phase 1 (Weeks 1-2) → Foundation → 100% pass required
Phase 2 (Weeks 3-4) → Core Features → 95% pass required  
Phase 3 (Weeks 5-6) → Advanced → 95% pass required
Phase 4 (Weeks 7-8) → Integration → 90% pass required
Phase 5 (Weeks 9-10) → Security → 100% pass required
Phase 6 (Weeks 11-12) → UAT → Production ready
```

## 🔧 Common Commands

```bash
# Run with coverage
pytest tests/integration/ --cov=src --cov-report=html

# Run in parallel (faster)
pytest tests/integration/ -n auto

# Run specific test
pytest tests/integration/test_auth_comprehensive.py -v

# Run and stop on first failure
pytest tests/integration/ -x

# Run only marked tests
pytest tests/integration/ -m critical
pytest tests/integration/ -m performance
pytest tests/integration/ -m security
```

## 📁 Test Organization

```
tests/integration/
├── test_auth_comprehensive.py      # TC-AUTH-001 to 050
├── test_public_access.py          # TC-PUBLIC-001 to 050
├── test_device_management.py      # TC-DEVICE-001 to 050
├── test_image_recognition.py      # TC-IMAGE-001 to 050
├── test_ai_chat_system.py         # TC-AI-001 to 050
├── test_team_collaboration.py     # TC-TEAM-001 to 050
├── test_hospital_administration.py # TC-ADMIN-001 to 050
├── test_incident_reporting.py     # TC-INCIDENT-001 to 050
├── test_document_video_management.py # TC-DOC-001 to 050
├── test_calendar_scheduling.py    # TC-CAL-001 to 050
├── test_notification_system.py    # TC-NOTIF-001 to 050
├── test_analytics_reporting.py    # TC-ANALYTICS-001 to 050
├── test_multi_tenant.py          # TC-TENANT-001 to 050
├── test_performance_load.py      # TC-PERF-001 to 050
├── test_security_compliance.py   # TC-SEC-001 to 050
├── test_integrations.py          # TC-INT-001 to 050
├── test_browser_compatibility.py # TC-BROWSER-001 to 050
├── test_offline_functionality.py # TC-OFFLINE-001 to 050
├── test_billing_subscription.py  # TC-BILL-001 to 050
├── test_deployment_operations.py # TC-DEPLOY-001 to 050
└── test_execution_plan.py        # TC-EXEC-001 to 050
```

## ⚡ Quick Debugging

```bash
# Verbose output
pytest -vv tests/integration/test_name.py

# Show print statements
pytest -s tests/integration/test_name.py

# Run specific test function
pytest tests/integration/test_auth_comprehensive.py::TestAuthentication::test_user_registration_tc_auth_001

# Generate HTML report
pytest --html=report.html --self-contained-html
```

## 📈 Success Criteria

- ✅ Overall pass rate ≥ 95%
- ✅ Critical tests = 100% pass
- ✅ No cross-tenant data leaks
- ✅ Performance targets met
- ✅ HIPAA compliant
- ✅ Zero critical vulnerabilities

## 🚨 If Tests Fail

1. Check service dependencies (PostgreSQL, Redis, etc.)
2. Verify environment variables in `.env.test`
3. Review test output with `-vv` flag
4. Check `test_reports/` for detailed logs
5. Run individual test with `-s` for debugging

## 📞 Support

- Test issues → Check README.md
- Infrastructure → DevOps team
- Test coverage → QA team
- Security tests → Security team

---
**Remember**: A passing test suite = Production ready! 🎉