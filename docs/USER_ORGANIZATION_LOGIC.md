# NYELUX USER REGISTRATION & ORGANIZATION LOGIC

## Overview

This document explains the business logic for user registration and organization associations in the Nyelux platform.

## User Roles

### Healthcare Professionals (HCP)
- **Roles:** `physician`, `nurse`, `technician`, `clinical_admin`
- **Organization Requirement:** OPTIONAL
- **Can join organization:** YES (after signup)

### Vendor Users
- **Roles:** `vendor_admin`, `vendor_rep`
- **Organization Requirement:** MANDATORY
- **Can join organization:** NO (must be set during signup)

### System Administrators
- **Roles:** `super_admin`, `org_admin`
- **Organization Requirement:** Varies
- **Can join organization:** Through admin assignment only

## Registration Rules

### 1. Healthcare Professionals

Healthcare professionals can register WITHOUT being associated with an organization:

```json
{
  "email": "doctor@example.com",
  "password": "SecurePass123!",
  "first_name": "John",
  "last_name": "Doe",
  "role": "physician"
  // organization_id is OPTIONAL
}
```

**Benefits:**
- Quick registration process
- Can explore the platform independently
- Can join an organization later
- Access to public device information

### 2. Vendor Users

Vendor users MUST be associated with an organization during registration:

```json
{
  "email": "vendor@company.com",
  "password": "SecurePass123!",
  "first_name": "Jane",
  "last_name": "Smith",
  "role": "vendor_rep",
  "organization_id": 123  // REQUIRED
}
```

**Validation Error if organization_id is missing:**
```json
{
  "detail": [
    {
      "loc": ["body", "organization_id"],
      "msg": "Vendor users must be associated with an organization",
      "type": "value_error"
    }
  ]
}
```

## Post-Registration Organization Management

### Healthcare Professionals Joining Organizations

HCPs can join a healthcare organization after registration using the dedicated endpoint:

**Endpoint:** `PUT /api/v1/users/me/organization`

**Query Parameters:**
- `organization_id`: The ID of the organization to join

**Rules:**
1. User must be a healthcare professional
2. User must not already be in an organization
3. Organization must be a healthcare provider (hospital/clinic)
4. Organization must exist and be active

**Example Request:**
```bash
curl -X PUT "http://localhost:8000/api/v1/users/me/organization?organization_id=1" \
  -H "Authorization: Bearer <token>"
```

**Success Response:**
```json
{
  "id": 123,
  "email": "doctor@example.com",
  "organization_id": 1,
  "organization_name": "City General Hospital",
  // ... other user fields
}
```

**Error Cases:**

1. **Not a healthcare professional:**
```json
{
  "detail": "Only healthcare professionals can join organizations independently"
}
```

2. **Already in an organization:**
```json
{
  "detail": "You are already associated with an organization. Contact an admin to change."
}
```

3. **Invalid organization:**
```json
{
  "detail": "Organization not found or is not a healthcare provider"
}
```

## Implementation Details

### Schema Validation

The validation is implemented in `src/schemas/user.py`:

```python
@field_validator('organization_id')
def validate_organization_requirement(cls, v, values):
    """Validate organization requirement based on role"""
    role = values.data.get('role')
    vendor_roles = ['vendor_admin', 'vendor_rep']
    
    if role in vendor_roles and v is None:
        raise ValueError('Vendor users must be associated with an organization')
    
    return v
```

### Model Properties

The User model includes helper properties in `src/db/models/user.py`:

```python
@property
def is_healthcare_professional(self) -> bool:
    """Check if user is a healthcare professional (HCP)"""
    return self.role in ['physician', 'nurse', 'technician', 'clinical_admin']

@property
def requires_organization(self) -> bool:
    """Check if user role requires organization association"""
    return self.is_vendor
```

## Testing

Use the provided test script to verify the implementation:

```bash
python scripts/test_org_requirements.py
```

This will test:
1. ✅ HCP registration without organization (should succeed)
2. ✅ Vendor registration without organization (should fail)
3. ✅ Vendor registration with organization (should succeed)
4. ✅ HCP joining organization after registration (should succeed)

## Use Cases

### Use Case 1: Independent Physician

Dr. Smith wants to explore medical devices on Nyelux:
1. Registers without organization
2. Browses public device information
3. Uses AI chat for device questions
4. Later gets hired by City Hospital
5. Joins the hospital's organization to access private content

### Use Case 2: Medical Device Sales Rep

Jane from MedTech Corp needs to manage device listings:
1. MedTech admin creates her account with organization
2. She immediately has access to vendor features
3. Can upload device documents
4. Can respond to support tickets
5. Cannot change organization without admin help

### Use Case 3: Hospital Nurse

A nurse at Regional Medical Center:
1. Hospital admin can pre-create account with organization
2. OR nurse can self-register and request to join hospital
3. Once associated, gets access to hospital-specific content
4. Can report device incidents for hospital

## Security Considerations

1. **Vendor Isolation:** Vendors can only see/manage their own organization's data
2. **HCP Flexibility:** HCPs can start using the platform immediately
3. **Organization Verification:** Organizations should be verified before allowing joins
4. **Admin Control:** Org admins can manage their users' associations

## Future Enhancements

1. **Organization Invites:** Allow organizations to invite HCPs via email
2. **Approval Workflow:** Require org admin approval when HCP requests to join
3. **Multiple Organizations:** Support users belonging to multiple organizations
4. **Organization Discovery:** Help HCPs find and request to join their workplace
