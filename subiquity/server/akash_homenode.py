# Copyright 2024 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""This module defines utilities to interface with the Akash HomeNode API."""

import base64
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional

import aiohttp

log = logging.getLogger("subiquity.server.akash_homenode")

# Akash HomeNode API base URL
AKASH_API_BASE_URL = "https://homenode-api-beta.akash.network/api/v1"
AKASH_VERIFY_ENDPOINT = "/installation-key/verify"


class InvalidTokenError(Exception):
    """Exception to be raised when the supplied installation key is invalid."""

    def __init__(self, token: str, message: str = "") -> None:
        self.token = token
        self.message = message
        super().__init__(message)


class ExpiredTokenError(Exception):
    """Exception to be raised when the supplied installation key has expired."""

    def __init__(self, token: str, message: str = "") -> None:
        self.token = token
        self.message = message
        super().__init__(message)


class CheckTokenError(Exception):
    """Exception to be raised when we are unable to verify the installation key."""

    def __init__(self, token: str, message: str = "") -> None:
        self.token = token
        self.message = message
        super().__init__(message)


class AkashAPIStrategy(ABC):
    """Strategy to query information about an Akash HomeNode installation key."""

    @abstractmethod
    async def verify_token(self, token: str) -> Dict:
        """Verify the installation key with the Akash API.
        
        Returns:
            Dict with API response data
            
        Raises:
            InvalidTokenError: If installation key is invalid
            ExpiredTokenError: If installation key has expired
            CheckTokenError: If API call fails
        """


class HTTPAkashAPIStrategy(AkashAPIStrategy):
    """HTTP implementation to verify installation keys with the Akash HomeNode API."""

    def __init__(self, base_url: str = AKASH_API_BASE_URL):
        self.base_url = base_url

    async def verify_token(self, token: str) -> Dict:
        """Verify the installation key with the Akash API."""
        url = f"{self.base_url}{AKASH_VERIFY_ENDPOINT}"
        
        # Encode token as base64 for Authorization header
        try:
            token_bytes = token.encode('utf-8')
            token_b64 = base64.b64encode(token_bytes).decode('utf-8')
        except Exception as e:
            log.error("Failed to encode token: %s", e)
            raise CheckTokenError(token, f"Failed to encode token: {e}")

        headers = {
            "Authorization": f"Bearer {token_b64}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "success":
                            return data
                        else:
                            # API returned success status but with error message
                            detail = data.get("detail", "Unknown error")
                            
                            # Handle detail being a dict or string
                            if isinstance(detail, dict):
                                error_msg = detail.get("error", str(detail))
                            else:
                                error_msg = str(detail)
                            
                            # Also check for error field at top level
                            if not error_msg or error_msg == str(detail):
                                error_msg = data.get("error", "Unknown error")
                            
                            if "expired" in str(error_msg).lower():
                                raise ExpiredTokenError(token, error_msg)
                            else:
                                raise InvalidTokenError(token, error_msg)
                    elif response.status == 401:
                        # Unauthorized - invalid token
                        try:
                            error_data = await response.json()
                            detail = error_data.get("detail", "Invalid or expired installation key")
                            
                            # Handle detail being a dict or string
                            if isinstance(detail, dict):
                                error_msg = detail.get("error", str(detail))
                            else:
                                error_msg = str(detail)
                            
                            # Also check for error field at top level
                            if not error_msg or error_msg == str(detail):
                                error_msg = error_data.get("error", "Invalid or expired installation key")
                        except Exception:
                            error_msg = "Invalid or expired installation key"
                        
                        if "expired" in str(error_msg).lower():
                            raise ExpiredTokenError(token, error_msg)
                        else:
                            raise InvalidTokenError(token, error_msg)
                    else:
                        # Other HTTP errors
                        try:
                            error_data = await response.json()
                            detail = error_data.get("detail", f"HTTP {response.status}")
                            
                            # Handle detail being a dict or string
                            if isinstance(detail, dict):
                                error_msg = detail.get("error", str(detail))
                            else:
                                error_msg = str(detail)
                            
                            # Also check for error field at top level
                            if not error_msg or error_msg == str(detail):
                                error_msg = error_data.get("error", f"HTTP {response.status}")
                        except Exception:
                            error_msg = f"HTTP {response.status}"
                        raise CheckTokenError(token, error_msg)
        except InvalidTokenError:
            raise
        except ExpiredTokenError:
            raise
        except CheckTokenError:
            raise
        except aiohttp.ClientError as e:
            log.error("Network error verifying installation key: %s", e)
            raise CheckTokenError(token, f"Network error: {e}")
        except Exception as e:
            log.error("Unexpected error verifying installation key: %s", e)
            raise CheckTokenError(token, f"Unexpected error: {e}")


class MockedAkashAPIStrategy(AkashAPIStrategy):
    """Mocked version of the Akash API strategy for testing."""

    async def verify_token(self, token: str) -> Dict:
        """Mock implementation that simulates API responses."""
        import asyncio
        await asyncio.sleep(0.1)  # Simulate network delay

        if not token:
            raise InvalidTokenError(token, "Token cannot be empty")

        # Mock responses based on token prefix
        if token.startswith("expired-") or token.startswith("x"):
            raise ExpiredTokenError(token, "Invalid or expired installation key")
        elif token.startswith("invalid-") or token.startswith("i"):
            raise InvalidTokenError(token, "Invalid or expired installation key")
        elif token.startswith("error-") or token.startswith("f"):
            raise CheckTokenError(token, "Network error")
        else:
            # Valid token
            return {
                "status": "success",
                "data": {
                    "valid": True,
                    "expired": False,
                    "install_id": "mock-install-id-12345",
                    "message": "Installation key is valid for this user"
                }
            }


class AkashAPIInterface:
    """Interface to interact with the Akash HomeNode API."""

    def __init__(self, strategy: AkashAPIStrategy):
        self.strategy = strategy

    async def verify_installation_key(self, token: str) -> Dict:
        """Verify an installation key token.
        
        Returns:
            Dict with API response data
            
        Raises:
            InvalidTokenError: If token is invalid
            ExpiredTokenError: If token has expired
            CheckTokenError: If API call fails
        """
        return await self.strategy.verify_token(token)

