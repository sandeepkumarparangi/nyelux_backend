"""
Enhanced CORS configuration for development
This fixes CORS issues with localhost:3000 and other development ports
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List

def setup_cors(app: FastAPI, origins: List[str] = None):
    """
    Setup CORS with proper configuration for development
    """
    
    # Default development origins if none provided
    if origins is None:
        origins = [
            "http://localhost:3000",
            "http://localhost:3001", 
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://localhost:8080",
            "http://localhost:4200",
            # Add any other ports your frontend might use
        ]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=[
            "Accept",
            "Accept-Language", 
            "Content-Language",
            "Content-Type",
            "Authorization",
            "Origin",
            "X-Requested-With",
            "X-Request-ID",
            "X-Session-ID",
            "Cache-Control",
            "Pragma",
            "Expires"
        ],
        expose_headers=[
            "Content-Length",
            "Content-Range",
            "X-Request-ID",
            "X-Process-Time",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining", 
            "X-RateLimit-Reset"
        ],
        max_age=3600,  # Cache preflight requests for 1 hour
    )
    
    return app
