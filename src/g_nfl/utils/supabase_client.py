"""Supabase client configuration for GNFL project"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from supabase import create_client

if TYPE_CHECKING:
    from supabase.client import Client

# Load environment variables from .env file (if available)
try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    # dotenv not installed - likely in Streamlit Cloud where env vars are set via secrets
    pass


class SupabaseClient:
    """Singleton Supabase client manager"""

    _instance: Client | None = None
    _url: str | None = None
    _key: str | None = None

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
        """Get Supabase URL from environment variables"""
        if cls._url:
            return cls._url

        # Try SUPABASE_URL first
        url = os.getenv("SUPABASE_URL")
        if url:
            return url

        # Try to extract from DATABASE_URL if SUPABASE_URL not available
        database_url = os.getenv("DATABASE_URL")
        if database_url and "supabase.co" in database_url:
            import re

            # Extract project ID from db.project-id.supabase.co
            match = re.search(r"@db\.([^.]+)\.supabase\.co", database_url)
            if match:
                project_id = match.group(1)
                return f"https://{project_id}.supabase.co"

        raise ValueError(
            "Supabase URL not found. Please set SUPABASE_URL environment variable.\n"
            "Example: SUPABASE_URL=https://your-project-id.supabase.co"
        )

    @classmethod
    def _get_key(cls) -> str:
        """Get Supabase API key from environment variables

        Checks in order: SUPABASE_PUBLISHABLE_KEY (new-style, sb_publishable_...),
        SUPABASE_ANON_KEY (legacy), SUPABASE_SECRET_KEY (server-side, bypasses RLS).
        """
        if cls._key:
            return cls._key

        for var in (
            "SUPABASE_PUBLISHABLE_KEY",
            "SUPABASE_ANON_KEY",
            "SUPABASE_SECRET_KEY",
        ):
            key = os.getenv(var)
            if key:
                return key

        raise ValueError(
            "Supabase API key not found. Set SUPABASE_PUBLISHABLE_KEY (or legacy "
            "SUPABASE_ANON_KEY) in your environment.\n"
            "You can find this in your Supabase dashboard under Settings > API Keys"
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
