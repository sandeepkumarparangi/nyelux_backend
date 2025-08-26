"""
Debug middleware to log all requests to track-search - FIXED VERSION
"""
from fastapi import Request
from starlette.datastructures import Headers
from starlette.requests import Request as StarletteRequest
import logging
import json

logger = logging.getLogger(__name__)

async def debug_track_search_middleware(request: Request, call_next):
    """Log all details of track-search requests"""
    
    # Only debug track-search endpoint
    if request.url.path == "/api/v1/public/track-search":
        logger.info("="*60)
        logger.info("TRACK-SEARCH REQUEST DEBUG")
        logger.info(f"Method: {request.method}")
        logger.info(f"URL: {request.url}")
        logger.info(f"Content-Type: {request.headers.get('content-type')}")
        
        # Read body for debugging
        if request.method == "POST":
            body = await request.body()
            logger.info(f"Raw body bytes: {body}")
            logger.info(f"Body as string: {body.decode('utf-8') if body else 'EMPTY'}")
            
            try:
                if body:
                    body_json = json.loads(body)
                    logger.info(f"Parsed JSON: {json.dumps(body_json, indent=2)}")
                else:
                    logger.info("EMPTY BODY RECEIVED")
            except Exception as e:
                logger.error(f"Could not parse body as JSON: {e}")
            
            # CRITICAL: Create new request with body for downstream
            async def receive():
                return {"type": "http.request", "body": body}
            
            request = StarletteRequest(request.scope, receive, request._send)
        
        logger.info("="*60)
    
    # Process request
    response = await call_next(request)
    
    # Log response for track-search
    if request.url.path == "/api/v1/public/track-search":
        if response.status_code != 200:
            logger.error(f"Track-search failed with status {response.status_code}")
        else:
            logger.info(f"Track-search succeeded with status {response.status_code}")
    
    return response
