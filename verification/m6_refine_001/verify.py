"""Monitored independent final Blender audit and immutable artifact validation."""

from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verify_quality
from common import identity, read, write


def main():
    sys.argv = [str(HERE / "verify_quality.py"), "--output-dir", str(HERE / "private/quality_audit_final")]
    verify_quality.main()
    audit = read("private/quality_audit_final/SUMMARY.json")
    write("QUALITY_VERIFICATION.json", dict(audit_status=audit["audit_status"], sessions=audit["sessions"],
        wall_s=audit["wall_s"], cpu_s=audit["cpu_s"], summary=identity(HERE / "private/quality_audit_final/SUMMARY.json"),
        independent_new_Blender_reads=12, consumer_geometry_claims_used=False))


if __name__ == "__main__":
    main()
