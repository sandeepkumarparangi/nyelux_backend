"""
Monkey patch for httpx proxy issue in Supabase
Import this BEFORE importing supabase
"""
import os
import httpx

# Remove proxy environment variables
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY']:
    os.environ.pop(proxy_var, None)

# Patch httpx.Client to remove proxy parameter
original_init = httpx.Client.__init__

def patched_init(self, *args, **kwargs):
    kwargs.pop('proxy', None)
    kwargs.pop('proxies', None)
    original_init(self, *args, **kwargs)

httpx.Client.__init__ = patched_init

print("✓ Supabase proxy patch applied")
