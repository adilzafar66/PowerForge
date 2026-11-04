"""Pure source-admission contract, immutable rule identity and scoped policy behavior."""

import json
import subprocess
import sys
from pathlib import Path

from engineering_interpretation_support import attribute
from powerforge_extraction import interpretation_v1
from powerforge_extraction.interpretation import interpret_attribute, interpretation_identity
from powerforge_extraction.terminology import TERMINOLOGY, TerminologyEntry


def test_qualified_terms_do_not_gain_unimplemented_semantics_just_by_naming_a_valid_key(
    monkeypatch,
):
    invented = TerminologyEntry(
        "unimplemented-qualification",
        "ATTRIBUTE_LABEL",
        "TWO_WINDING_TRANSFORMER",
        "primary_voltage",
        None,
        ("Mystery Voltage",),
        "Requires separately approved context.",
    )
    monkeypatch.setattr(interpretation_v1, "TERMINOLOGY", (*TERMINOLOGY, invented))
    result = interpret_attribute(*attribute("Mystery Voltage", "600", "V", "primary_voltage"))
    assert result.mapping_status == "UNMAPPED" and result.attribute_key is None


def test_generic_registry_display_labels_and_absent_model_mappings_do_not_need_new_alias_code():
    observation, context = attribute(
        "Voltage Rating", "600", "V", None, equipment="Cable C1", equipment_type="CABLE"
    )
    result = interpret_attribute(observation.model_copy(update={"source_label": None}), context)
    assert result.mapping_status == "MAPPED" and result.attribute_key == "rated_voltage"
    assert str(result.value) == "0.6"


def test_explicit_zero_is_retained_but_absence_does_not_become_false():
    result = interpret_attribute(*attribute("Secondary Voltage", "0", "V", "secondary_voltage"))
    assert result.mapping_status == "MAPPED" and result.value == 0 and result.raw_value == "0"
    observation, context = attribute(
        "Normally Closed",
        "No",
        None,
        "normally_closed",
        equipment="LV Breaker CB1",
        equipment_type="LV_BREAKER",
    )
    result = interpret_attribute(observation.model_copy(update={"raw_value": None}), context)
    assert result.mapping_status == "UNMAPPED" and result.value is None


def test_interpreter_resources_have_a_pinned_reproducible_identity():
    expected = json.loads(
        (Path(__file__).parent / "fixtures/extraction/interpretation_v1_identity.json").read_text()
    )
    assert interpretation_identity() == expected


def test_interpreter_import_and_execution_need_no_orm_provider_or_storage_sdk():
    script = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    blocked = {'sqlalchemy','fastapi','celery','boto3','openai','PIL','powerforge_api'}
    if name.split('.')[0] in blocked:
        raise AssertionError('Unexpected infrastructure dependency: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from powerforge_extraction.interpretation import InterpretationContext, interpretation_identity
assert InterpretationContext('Secondary Voltage: 600 V')
assert interpretation_identity()['version']=='engineering-interpretation-v1'
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
