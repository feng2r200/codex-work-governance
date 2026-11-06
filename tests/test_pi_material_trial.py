"""Challenge the material-code trial's independent fixed-vector oracle."""

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "pi_material_trial", SCRIPTS / "run_pi_material_trial.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_oracle_accepts_reference_and_rejects_starter(tmp_path: Path) -> None:
    """An adjacent valid implementation passes while the original defect fails."""
    path = tmp_path / "pricing.py"
    path.write_text(MODULE.GOOD, encoding="utf-8")
    good = MODULE.grade(path)
    assert len(good) == 13 and all(good.values())
    path.write_text(MODULE.STARTER, encoding="utf-8")
    bad = MODULE.grade(path)
    assert len(bad) == 13 and not all(bad.values())
    assert not bad["bool_price"]
    boolean_price_only = MODULE.GOOD.replace(
        "type(price) is not int", "(type(price) is not int and type(price) is not bool)"
    )
    assert boolean_price_only != MODULE.GOOD
    path.write_text(boolean_price_only, encoding="utf-8")
    one_defect = MODULE.grade(path)
    assert {name for name, passed in one_defect.items() if not passed} == {"bool_price"}
