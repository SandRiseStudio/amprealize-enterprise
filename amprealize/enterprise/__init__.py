"""Amprealize Enterprise — enterprise subpackage.

In the enterprise fork, this subpackage is always present (it ships with
the repo).  The OSS ``amprealize.__init__`` detects enterprise via:

    HAS_ENTERPRISE = importlib.util.find_spec("amprealize.enterprise") is not None

This subpackage contains: analytics, billing, crypto, midnighter,
multi_tenant, research, edition_tier, caps_enforcer, cloud_client,
deploy_migrate, and auto_reflection.
"""

__version__ = "0.1.0"
