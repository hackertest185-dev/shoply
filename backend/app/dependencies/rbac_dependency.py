"""
dependencies/rbac_dependency.py
Factory that returns a FastAPI dependency enforcing role membership.
Usage:  require_roles("admin", "vendor")
"""
from fastapi import Depends, HTTPException, status

from .auth_dependency import get_current_user


def require_roles(*allowed_roles: str):
    """
    Returns a dependency that passes only if current_user.role is in allowed_roles.
    Chain after get_current_user — never standalone.
    """
    async def _check(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": "You do not have permission to access this resource.",
                },
            )
        return current_user

    return _check


# Convenience shortcuts
require_admin    = require_roles("admin")
require_customer = require_roles("customer")
require_vendor   = require_roles("vendor", "admin")
require_delivery = require_roles("delivery")
