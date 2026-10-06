"""Integrations without a live verifier yet (Instagram, YouTube, Email, Google sign-in).

They are listed so the Config page and readiness can say honestly: "set, but not verified from the
dashboard yet" instead of pretending. Their checks arrive in later phases (spec P4/P7).
"""
from __future__ import annotations

from src.config_schema import fields_of
from src.verify.base import Result, Run


def make(integration: str):
    def verify(values: dict[str, str], depth: str = "live") -> Result:
        run = Run(integration, depth)
        present = [f.name for f in fields_of(integration) if values.get(f.name)]
        if not present:
            res = run.finish(not_set=True)
        else:
            run.skip("live", "Works with the provider", "No live check for this integration yet.",
                     code="verify.not_implemented")
            res = run.finish()
            res.status, res.error_class, res.code = "unknown", "not_implemented", "verify.not_implemented"
            from src.verify.base import CODES, docs_link
            res.message, res.hint = CODES["verify.not_implemented"].message, CODES["verify.not_implemented"].hint
            res.docs = docs_link("verify.not_implemented", integration)
        res.implemented = False
        res.evidence["fields_set"] = len(present)
        return res
    return verify
