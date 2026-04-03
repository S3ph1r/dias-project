# NH-Mini SOPS+Age Integration for DIAS

## Overview
This document explains how to use NH-Mini's existing SOPS+Age secure credential management system to store and retrieve API keys and other secrets for DIAS (Document Intelligence Analysis System).

## System Architecture

NH-Mini uses **SOPS (Secrets OPerationS)** with **Age encryption** for secure credential storage:
- **SOPS**: Encrypts YAML/JSON files with multiple keys (Age, PGP, etc.)
- **Age**: Modern encryption tool with simple key management
- **File-based storage**: Encrypted credentials stored in `secrets/*.enc.yaml` files
- **Git-friendly**: Encrypted files can be committed to version control safely

## Key Components

### 1. Core Files
- `/home/Projects/NH-Mini/.sops.yaml` - SOPS configuration with Age public key
- `/home/Projects/NH-Mini/core/secure_credential_manager.py` - Main credential manager
- `/home/Projects/NH-Mini/scripts/setup_sops_local.py` - SOPS setup utility
- `/home/Projects/NH-Mini/scripts/credential_manager.py` - Interactive credential management

### 2. Main Functions

#### Store Credentials
```python
from core.secure_credential_manager import store_service_credential

# Store API key or any credential
success = store_service_credential(
    service="google_gemini",      # Service name (arbitrary)
    name="main",                   # Credential identifier
    data={"api_key": "your-key"}   # Credential data (dict)
)
```

#### Retrieve Credentials
```python
from core.secure_credential_manager import get_service_credential

# Retrieve stored credential
credential = get_service_credential(
    service="google_gemini",       # Service name used during storage
    name="main"                    # Credential identifier
)

if credential:
    api_key = credential["api_key"]
```

## Usage Examples for DIAS

### 1. Storing Google Gemini API Key
```python
#!/usr/bin/env python3
import sys
sys.path.append('/home/Projects/NH-Mini')

from core.secure_credential_manager import store_service_credential

# Store the API key
api_key = "AIzaSyBw3Dmu3ILR6Z2wzvczKjhkND_YyYgyEKo"
success = store_service_credential(
    service="google_gemini",
    name="main", 
    data={"api_key": api_key}
)

if success:
    print("API key stored successfully")
```

### 2. Retrieving API Key in DIAS
```python
#!/usr/bin/env python3
import sys
sys.path.append('/home/Projects/NH-Mini')

from core.secure_credential_manager import get_service_credential

# Retrieve API key for Stage B Semantic Analyzer
credential = get_service_credential("google_gemini", "main")
if credential:
    api_key = credential["api_key"]
    # Use api_key with Google GenAI SDK
    import google.generativeai as genai
    genai.configure(api_key=api_key)
else:
    raise ValueError("Google Gemini API key not found in secure storage")
```

### 3. Integration in Stage B Semantic Analyzer
```python
# In stage_b_semantic_analyzer.py
import sys
sys.path.append('/home/Projects/NH-Mini')
from core.secure_credential_manager import get_service_credential

class StageBSemanticAnalyzer:
    def __init__(self):
        # Retrieve API key from secure storage
        credential = get_service_credential("google_gemini", "main")
        if not credential:
            raise ValueError("Google Gemini API key not configured")
        
        self.api_key = credential["api_key"]
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-flash-lite-latest')
```

## Security Features

### 1. Encryption
- All credentials are encrypted with Age before storage
- Files are stored as `.enc.yaml` (encrypted YAML)
- Only users with the Age private key can decrypt credentials

### 2. File Permissions
- Age private key: `~/.age.key` (600 permissions)
- Encrypted files: `secrets/*.enc.yaml` (600 permissions)

### 3. Environment Variables
The system uses these environment variables:
- `SOPS_AGE_KEY_FILE`: Path to Age private key
- `SOPS_AGE_RECIPIENTS`: Age public key for encryption

## Setup Requirements

### 1. Age Key Generation
If not already set up, run:
```bash
cd /home/Projects/NH-Mini
python scripts/setup_sops_local.py
```

### 2. Verify Configuration
Check that these files exist:
- `~/.age.key` (private key)
- `/home/Projects/NH-Mini/.sops.yaml` (SOPS config)

## Best Practices

### 1. Service Naming
- Use descriptive service names: `google_gemini`, `openai`, `aws_s3`
- Use consistent naming conventions
- Group related credentials under the same service

### 2. Credential Structure
```python
# Good: Structured data
data = {
    "api_key": "key-here",
    "endpoint": "https://api.example.com",
    "rate_limit": 100
}

# Avoid: Flat strings
data = "just-a-key"
```

### 3. Error Handling
```python
try:
    credential = get_service_credential("service", "name")
    if not credential:
        raise ValueError("Credential not found")
    # Use credential
except Exception as e:
    logger.error(f"Failed to retrieve credential: {e}")
    # Handle gracefully
```

## Troubleshooting

### 1. "Age key not found"
- Run setup script: `python scripts/setup_sops_local.py`
- Check file permissions: `ls -la ~/.age.key`

### 2. "SOPS decryption failed"
- Verify Age key is correct: `age-keygen -y ~/.age.key`
- Check SOPS config matches Age public key

### 3. "Credential not found"
- Verify service/name parameters match storage
- Check encrypted files exist: `ls secrets/*.enc.yaml`

## Integration Checklist

- [ ] NH-Mini SOPS+Age system is configured
- [ ] API keys stored in secure storage
- [ ] DIAS Stage B updated to retrieve keys
- [ ] Error handling implemented
- [ ] Rate limiting configured (1 request/5min for Gemini)
- [ ] Tests updated to use mock credentials

## Files Created/Modified

1. **Storage Script**: `/home/Projects/NH-Mini/store_gemini_api_key.py`
   - Demonstrates API key storage
   - Verifies retrieval functionality

2. **Encrypted Credential**: `secrets/google_gemini.main.enc.yaml`
   - Contains encrypted Google Gemini API key
   - Safe for version control

3. **DIAS Integration**: Update `stage_b_semantic_analyzer.py`
   - Retrieve API key from secure storage
   - Configure Google GenAI SDK
   - Implement proper error handling

This documentation provides a complete guide for using NH-Mini's secure credential system with DIAS, ensuring API keys and other secrets are properly encrypted and managed.