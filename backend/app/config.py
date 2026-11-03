import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "Internal QR Management System"
    APP_VERSION: str = "1.0.0"
    
    # Base URL for QR codes - change in production
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./qr_system.db")
    
    # JWT Settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production-use-openssl-rand-hex-32")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours
    
    # CORS
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]
    
    # Rate Limiting
    RATE_LIMIT_AUTH: str = "5/minute"
    RATE_LIMIT_GENERAL: str = "60/minute"
    
    # QR Settings
    QR_TOKEN_LENGTH: int = 12  # Characters in the random token
    QR_DEFAULT_SIZE: int = 300  # pixels
    QR_DEFAULT_BORDER: int = 2
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    OPERATOR_CAN_ASSIGN: bool = os.getenv("OPERATOR_CAN_ASSIGN", "true").lower() != "false"
    ENABLE_RATE_LIMITING: bool = os.getenv("ENABLE_RATE_LIMITING", "true").lower() != "false"
    # Reverse Proxy & Trusted Proxies (comma-separated IPs/CIDRs, e.g. "127.0.0.1,::1,10.0.0.0/8")
    TRUSTED_PROXIES: str = os.getenv("TRUSTED_PROXIES", "")

    @property
    def trusted_proxy_networks(self) -> list:
        """Parse TRUSTED_PROXIES string into ipaddress network objects."""
        if not self.TRUSTED_PROXIES:
            return []
        import ipaddress
        networks = []
        for p in self.TRUSTED_PROXIES.split(","):
            p = p.strip()
            if not p:
                continue
            try:
                networks.append(ipaddress.ip_network(p, strict=False))
            except ValueError:
                # Also support non-IP hostnames like 'testclient' or 'localhost' by storing string
                continue
        return networks

    @property
    def trusted_proxy_hosts(self) -> set:
        """Set of trusted host identifiers including non-IP names like 'testclient' or 'localhost'."""
        if not self.TRUSTED_PROXIES:
            return set()
        return {p.strip().lower() for p in self.TRUSTED_PROXIES.split(",") if p.strip()}

    class Config:
        env_file = ".env"
        extra = "allow"

    def validate_production_config(self):
        if self.ENVIRONMENT.lower() == "production":
            if self.SECRET_KEY == "dev-secret-key-change-in-production-use-openssl-rand-hex-32" or len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "CRITICAL SECURITY CONFIGURATION ERROR: "
                    "Default development or weak (<32 characters) SECRET_KEY detected in production! "
                    "Generate a secure random secret (e.g. openssl rand -hex 32) and set SECRET_KEY in .env."
                )
            if self.BASE_URL.startswith("http://localhost"):
                import logging
                logging.getLogger("uvicorn.error").warning(
                    "[SECURITY WARNING] Production ENVIRONMENT is active but BASE_URL points to localhost. "
                    "Update BASE_URL to your secure HTTPS production domain (e.g. https://qr.company.com)."
                )



@lru_cache()
def get_settings():
    return Settings()
