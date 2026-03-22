from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import HTTPException

class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list) 
    
    def check_limit(self, api_key: str, limit: int, window_seconds: int = 60):
        """Check if request is within rate limit"""
        now = datetime.now()
        cutoff = now - timedelta(seconds=window_seconds)
        
        # Remove old requests outside the time window
        self.requests[api_key] = [
            req_time for req_time in self.requests[api_key] 
            if req_time > cutoff
        ]
        
        # Check if limit exceeded
        if len(self.requests[api_key]) >= limit:
            raise HTTPException(
                status_code=429, 
                detail=f"Rate limit exceeded. Max {limit} requests per minute"
            )
        
        self.requests[api_key].append(now)

