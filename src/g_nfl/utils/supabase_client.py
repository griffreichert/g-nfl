"""Supabase client configuration for GNFL project"""

import os
from typing import Optional

from supabase import Client, create_client


class SupabaseClient:
    """Singleton Supabase client manager"""

    _instance: Optional[Client] = None
    _url: Optional[str] = None
    _key: Optional[str] = None

    @classmethod
    def get_client(cls) -> Client:
        """Get or create Supabase client instance"""
        if cls._instance is None:
            cls._instance = cls._create_client()
        return cls._instance

    @classmethod
    def _create_client(cls) -> Client:
        """Create new Supabase client"""
        url = cls._get_url()
        key = cls._get_key()
        return create_client(url, key)

    @classmethod
    def _get_url(cls) -> str:
        """Get Supabase URL from DATABASE_URL environment variable"""
        if cls._url:
            return cls._url

        # Get from DATABASE_URL (format: postgresql://...)
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            # Convert PostgreSQL URL to Supabase URL
            # Typically DATABASE_URL is postgresql://... but we need https://...
            if database_url.startswith("postgresql://"):
                # Extract project from the host part
                # Format: postgresql://postgres:[password]@[project].supabase.co:5432/postgres
                import re

                match = re.search(r"@([^.]+)\.supabase\.co", database_url)
                if match:
                    project_id = match.group(1)
                    return f"https://{project_id}.supabase.co"

        raise ValueError(
            "DATABASE_URL not found or invalid format. "
            "Expected format: postgresql://postgres:[password]@[project].supabase.co:5432/postgres"
        )

    @classmethod
    def _get_key(cls) -> str:
        """Get Supabase anon key from environment or config"""
        if cls._key:
            return cls._key

        # Try SUPABASE_ANON_KEY first
        key = os.getenv("SUPABASE_ANON_KEY")
        if key:
            return key

        # Extract key from DATABASE_URL if available
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            # Extract password from postgresql://postgres:[password]@...
            import re

            match = re.search(r"postgres:([^@]+)@", database_url)
            if match:
                return match.group(1)

        raise ValueError(
            "Supabase anon key not found. Set SUPABASE_ANON_KEY environment variable "
            "or ensure DATABASE_URL contains the anon key as the password"
        )

    @classmethod
    def configure(cls, url: str, key: str):
        """Configure Supabase client with URL and key"""
        cls._url = url
        cls._key = key
        cls._instance = None  # Reset instance to recreate with new config

    @classmethod
    def reset(cls):
        """Reset client instance (useful for testing)"""
        cls._instance = None
        cls._url = None
        cls._key = None


# Convenience function for getting client
def get_supabase() -> Client:
    """Get configured Supabase client"""
    return SupabaseClient.get_client()
