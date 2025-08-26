"""
Supabase httpx proxy patch - Import this FIRST in main.py
"""
import os
import httpx

# Remove proxy environment variables
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    os.environ.pop(proxy_var, None)

# Patch httpx.Client to remove proxy parameter
_OriginalClient = httpx.Client
class PatchedClient(_OriginalClient):
    def __init__(self, *args, **kwargs):
        kwargs.pop('proxy', None)
        kwargs.pop('proxies', None)
        kwargs.pop('mounts', None)
        super().__init__(*args, **kwargs)
httpx.Client = PatchedClient

_OriginalAsyncClient = httpx.AsyncClient
class PatchedAsyncClient(_OriginalAsyncClient):
    def __init__(self, *args, **kwargs):
        kwargs.pop('proxy', None)
        kwargs.pop('proxies', None)
        kwargs.pop('mounts', None)
        super().__init__(*args, **kwargs)
httpx.AsyncClient = PatchedAsyncClient

print("✓ Supabase proxy patch applied")
